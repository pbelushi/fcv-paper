"""Etapa 11 — Exercício 2: tratamento não absorvente com intensidade contínua.

Tratamento D_it = mortes em combate (state-based) no território por 100 mil hab. (UCDP CY / PIP).
Toda variação de D conta como variação de tratamento (ex.: escalada de 1 para 50 por 100 mil).
Amostra: todos os países soberanos com dados (inclui os excluídos do desenho de onset), 1990-2024.

Estimadores
1. TWFE contínuo: y_it = α_i + λ_t + β D_it.
2. Defasagens distribuídas: y_it = α_i + λ_t + Σ_{k=-2..5} β_k D_{i,t-k}; antecipações (k<0)
   testam causalidade reversa; efeito cumulativo = Σ_{k=0..5} β_k.
3. Primeiras diferenças: Δy_it = λ_t + β ΔD_it (+ antecipação ΔD_{i,t+1}).
4. Switchers × quasi-stayers (à la de Chaisemartin, D'Haultfœuille, Pasquier, Sow & Vazquez-Bare,
   2024, "DiD for continuous treatments and instruments with stayers"; implementação própria e
   simplificada): para cada par (t-1, t), switchers têm |ΔD| > ε; quasi-stayers |ΔD| ≤ ε. O
   contrafactual de ΔY dos switchers vem de uma regressão, nos stayers, de ΔY em efeitos de ano +
   faixas do tratamento de partida D_{t-1}. Estimando (WAOSS):
       θ = Σ_sw sign(ΔD)·(ΔY − ΔŶ0) / Σ_sw |ΔD|
   = efeito médio por unidade de dose, ponderado por |ΔD|. Separado também para escaladas
   (ΔD > 0) e desescaladas (ΔD < 0). Placebo: mesma conta com ΔY do período anterior, entre
   unidades com D estável de t-2 a t-1. EP por bootstrap de países.
Escalas da dose: linear (por 1 morte/100 mil) e asinh(D) (≈ log para D grande; robusta a
valores extremos como a Síria, ~186/100 mil).
"""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import did_tools as dt  # noqa: E402
import plotstyle as ps  # noqa: E402
from config import FIGURES, PROCESSED, TABLES  # noqa: E402

est = importlib.import_module("07_estimate")
OUT = ["pov_rate", "ln_n_poor", "asinh_n_poor"]
BINS = [-np.inf, 0, 0.1, 1, 10, np.inf]          # faixas do tratamento de partida (por 100 mil)
EPS = {"brd_pc": 0.1, "asinh_brd_pc": 0.1}       # tolerância de quasi-stayer
REPS = 300
LEADS, LAGS = 2, 5


def load(exclude_high: bool = False) -> pd.DataFrame:
    p = pd.read_parquet(PROCESSED / "panel.parquet")
    p = p[~p.motivo.fillna("").str.contains("não soberano")].copy()
    p = p.dropna(subset=["brd_pc"]).sort_values(["iso3", "year"])
    p["asinh_brd_pc"] = np.arcsinh(p.brd_pc)
    if exclude_high:
        ig = p.dropna(subset=["income_group"]).sort_values("year").groupby("iso3").income_group.first()
        p = p[p.iso3.map(ig) != "H"]
    return p


def add_lags(p: pd.DataFrame, D: str) -> tuple[pd.DataFrame, list[str]]:
    p = p.copy()
    names = []
    for k in range(-LEADS, LAGS + 1):
        nm = f"{D}_L{k}" if k >= 0 else f"{D}_F{-k}"
        p[nm] = p.groupby("iso3")[D].shift(k)
        # shift só vale se o ano anterior/posterior existe (painel balanceado na prática)
        names.append(nm)
    return p, names


def twfe_models(p: pd.DataFrame, y: str, D: str) -> list[dict]:
    rows = []
    tab, *_ = dt.twfe(p, y, [D])
    r = tab.iloc[0]
    rows.append({"modelo": "TWFE nível", "termo": D, **r[["estimate", "se", "ci_low", "ci_high", "p_value"]].to_dict()})
    pl, names = add_lags(p, D)
    tab, V, n, Gc = dt.twfe(pl, y, names)
    for _, r in tab.iterrows():
        rows.append({"modelo": "Defasagens distribuídas", "termo": r.term,
                     **r[["estimate", "se", "ci_low", "ci_high", "p_value"]].to_dict()})
    lag_idx = [i for i, nm in enumerate(names) if "_L" in nm]
    lead_idx = [i for i, nm in enumerate(names) if "_F" in nm]
    w = np.zeros(len(names))
    w[lag_idx] = 1
    cum, se = float(w @ tab.estimate), float(np.sqrt(w @ V @ w))
    tcrit = stats.t(Gc - 1)
    rows.append({"modelo": "Defasagens distribuídas", "termo": f"cumulativo L0..L{LAGS}", "estimate": cum, "se": se,
                 "ci_low": cum - tcrit.ppf(0.975) * se, "ci_high": cum + tcrit.ppf(0.975) * se,
                 "p_value": 2 * tcrit.sf(abs(cum / se))})
    b = tab.estimate.to_numpy()[lead_idx]
    Vl = V[np.ix_(lead_idx, lead_idx)]
    W = float(b @ np.linalg.solve(Vl, b))
    rows.append({"modelo": "Defasagens distribuídas", "termo": "Wald antecipações (F1,F2) = 0", "estimate": W,
                 "se": np.nan, "ci_low": np.nan, "ci_high": np.nan, "p_value": float(stats.chi2.sf(W, len(lead_idx)))})
    # primeiras diferenças com efeitos de ano
    q = p.copy()
    q["dy"] = q.groupby("iso3")[y].diff()
    q["dD"] = q.groupby("iso3")[D].diff()
    q["dD_F1"] = q.groupby("iso3")["dD"].shift(-1)
    q = q.dropna(subset=["dy", "dD", "dD_F1"])
    M = q[["dy", "dD", "dD_F1"]].to_numpy()
    tm = q.year.to_numpy()
    Md = M - pd.DataFrame(M).groupby(tm).transform("mean").to_numpy()   # efeitos de ano
    bb, VV, Gc = dt.ols_cluster(Md[:, 0], Md[:, 1:], q.iso3.to_numpy(), k_fe=q.year.nunique())
    tcrit = stats.t(Gc - 1)
    for i, nm in enumerate(["ΔD_t", "ΔD_t+1 (antecipação)"]):
        se = float(np.sqrt(VV[i, i]))
        rows.append({"modelo": "Primeiras diferenças", "termo": nm, "estimate": bb[i], "se": se,
                     "ci_low": bb[i] - tcrit.ppf(0.975) * se, "ci_high": bb[i] + tcrit.ppf(0.975) * se,
                     "p_value": 2 * tcrit.sf(abs(bb[i] / se))})
    return rows


# ============================================================================ switchers × stayers

def _pairs(p: pd.DataFrame, y: str, D: str) -> pd.DataFrame:
    q = p[["iso3", "year", y, D]].copy()
    g = q.groupby("iso3")
    q["dY"] = g[y].diff()
    q["D0"] = g[D].shift(1)
    q["dD"] = q[D] - q.D0
    q["dY_lag"] = g[y].shift(1) - g[y].shift(2)
    q["dD_lag"] = q.D0 - g[D].shift(2)
    q["bin0"] = pd.cut(q.D0, BINS, labels=False)
    consecutive = g.year.diff() == 1
    return q[consecutive & q.dY.notna() & q.dD.notna()]


def waoss(q: pd.DataFrame, eps: float, placebo: bool = False) -> dict:
    """θ = Σ sign(ΔD)(ΔY − ΔŶ0) / Σ|ΔD| entre switchers; ΔŶ0 de stayers (ano + faixa de D_{t-1})."""
    q = q.copy()
    if placebo:
        q = q[q.dD_lag.abs() <= eps].dropna(subset=["dY_lag"])
        q["dY"] = q.dY_lag
    sw = q.dD.abs() > eps
    st = ~sw
    if sw.sum() == 0 or st.sum() < 10:
        return {k: np.nan for k in ("all", "up", "down", "n_sw", "n_up", "n_down")}
    S = q[st]
    yfe = S.groupby("year").dY.mean()
    resid = S.dY - S.year.map(yfe)
    bfe = resid.groupby(S.bin0).mean()                 # efeito aditivo da faixa de partida
    pred = q.year.map(yfe).fillna(S.dY.mean()) + q.bin0.map(bfe).fillna(0)
    e = (q.dY - pred)[sw]
    dD = q.dD[sw]
    out = {}
    for nm, m in [("all", np.ones(len(dD), bool)), ("up", (dD > 0).to_numpy()), ("down", (dD < 0).to_numpy())]:
        out[nm] = float((np.sign(dD[m]) * e[m]).sum() / dD[m].abs().sum()) if m.any() else np.nan
    out.update(n_sw=int(sw.sum()), n_up=int((dD > 0).sum()), n_down=int((dD < 0).sum()))
    return out


def waoss_boot(q: pd.DataFrame, eps: float, placebo: bool = False, seed: int = 5) -> dict:
    point = waoss(q, eps, placebo)
    units = q.iso3.unique()
    groups = {u: d for u, d in q.groupby("iso3")}
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(REPS):
        pick = rng.choice(units, len(units), replace=True)
        bq = pd.concat([groups[u].assign(iso3=f"{u}_{i}") for i, u in enumerate(pick)])
        r = waoss(bq, eps, placebo)
        draws.append([r["all"], r["up"], r["down"]])
    se = np.nanstd(np.array(draws), axis=0, ddof=1)
    return {**point, "se_all": se[0], "se_up": se[1], "se_down": se[2]}


EXTRA = {
    "pov_rate_obs": "Taxa de pobreza — só pares de anos com pesquisa observada nos dois anos",
    "ln_n_poor_obs": "log nº de pobres — só pares com pesquisa observada nos dois anos",
    "ln_gdppc": "log PIB per capita PPC (WDI) — canal da extrapolação do PIP",
}


def extras() -> pd.DataFrame:
    """Mecanismo / dados observados: dose asinh, amostra completa, ε = 0,1.
    Nas séries *_obs, anos sem pesquisa são NaN; logo ΔY só existe quando há pesquisa em t-1 e t."""
    p = load(False)
    D = "asinh_brd_pc"
    rows = []
    for y, lab in EXTRA.items():
        q = _pairs(p, y, D)
        for pl in (False, True):
            r = waoss_boot(q, EPS[D], pl)
            rows.append({"outcome": y, "descricao": lab, "tipo": "placebo" if pl else "efeito", "eps": EPS[D],
                         "n_pairs": len(q), **r})
        print(f"  {y:14s} pares = {len(q):5d}; WAOSS θ = {rows[-2]['all']:.4f} (EP {rows[-2]['se_all']:.4f}); "
              f"escalada {rows[-2]['up']:.4f} (EP {rows[-2]['se_up']:.4f}); placebo θ = {rows[-1]['all']:.4f} "
              f"(EP {rows[-1]['se_all']:.4f}); switchers {rows[-2]['n_sw']}")
    out = pd.DataFrame(rows)
    for k in ("all", "up", "down"):
        out[f"p_{k}"] = 2 * stats.norm.sf(np.abs(out[k] / out[f"se_{k}"]))
    out.to_csv(TABLES / "ex2_continuous_mechanism.csv", index=False)
    return out


def main() -> None:
    print("Mecanismo e dados observados (asinh, todos os países):")
    extras()
    rows, wrows = [], []
    for sample, excl in [("todos", False), ("sem renda alta", True)]:
        p = load(excl)
        print(f"\n##### Amostra: {sample} — {p.iso3.nunique()} países, {p.year.min()}-{p.year.max()}; "
              f"país-anos com D > 0: {(p.brd_pc > 0).sum()} ({(p.brd_pc > 0).mean():.1%})")
        for D in ["brd_pc", "asinh_brd_pc"]:
            for y in OUT:
                for r in twfe_models(p, y, D):
                    rows.append({"amostra": sample, "dose": D, "outcome": y, **r})
                q = _pairs(p, y, D)
                for eps in sorted({0.0, EPS[D], 0.5}):
                    for pl in (False, True):
                        r = waoss_boot(q, eps, pl)
                        wrows.append({"amostra": sample, "dose": D, "outcome": y, "eps": eps,
                                      "tipo": "placebo" if pl else "efeito", **r})
            sel = [r for r in rows if r["amostra"] == sample and r["dose"] == D]
            print(f"\n  Dose = {D}")
            for r in sel:
                if r["modelo"] == "TWFE nível" or "cumulativo" in str(r["termo"]) or "Wald" in str(r["termo"]) \
                        or r["modelo"] == "Primeiras diferenças":
                    print(f"   {r['outcome']:13s} {r['modelo']:24s} {str(r['termo']):32s} {r['estimate']:9.4f} "
                          f"(EP {r['se']:.4f}; p = {r['p_value']:.3f})")
            ws = [w for w in wrows if w["amostra"] == sample and w["dose"] == D and w["eps"] == EPS[D]]
            for w in ws:
                print(f"   {w['outcome']:13s} WAOSS {w['tipo']:8s} ε={w['eps']}: θ = {w['all']:.4f} (EP {w['se_all']:.4f}); "
                      f"escalada {w['up']:.4f} (EP {w['se_up']:.4f}); desescalada {w['down']:.4f} (EP {w['se_down']:.4f}); "
                      f"switchers {w['n_sw']} (↑{w['n_up']} ↓{w['n_down']})")
    tw = pd.DataFrame(rows)
    tw.to_csv(TABLES / "ex2_continuous_twfe.csv", index=False)
    wa = pd.DataFrame(wrows)
    for k in ("all", "up", "down"):
        wa[f"p_{k}"] = 2 * stats.norm.sf(np.abs(wa[k] / wa[f"se_{k}"]))
    wa.to_csv(TABLES / "ex2_continuous_waoss.csv", index=False)

    # figura: coeficientes das defasagens distribuídas (asinh, todos)
    for y in OUT:
        t = tw[(tw.amostra == "todos") & (tw.dose == "asinh_brd_pc") & (tw.outcome == y)
               & (tw.modelo == "Defasagens distribuídas") & tw.termo.str.contains("_[LF]\\d", regex=True)].copy()
        t["k"] = t.termo.str.extract(r"_([LF])(\d)").apply(lambda r: int(r[1]) * (1 if r[0] == "L" else -1), axis=1)
        t = t.sort_values("k")
        fig, ax = ps.plt.subplots(figsize=(6.5, 3.6))
        ax.axhline(0, color=ps.INK2, lw=1)
        ax.axvline(-0.5, color=ps.INK2, lw=1, ls="--")
        ax.fill_between(t.k, t.ci_low, t.ci_high, color=ps.TREATED, alpha=0.22, lw=0, label="IC 95%")
        ax.plot(t.k, t.estimate, color=ps.TREATED, marker="o", label="β_k")
        ax.set_xlabel("k (negativo = antecipação: D em t+|k|; positivo = defasagem)")
        ps.int_xaxis(ax)
        ax.set_title(f"{est.OUTCOMES.get(y, y)} — efeito de asinh(mortes/100 mil) em t−k", loc="left")
        ax.legend(fontsize=8)
        ps.save(fig, FIGURES / f"ex2_distributed_lags_{y}")
    print("\nTabelas: ex2_continuous_twfe.csv, ex2_continuous_waoss.csv")


if __name__ == "__main__":
    main()
