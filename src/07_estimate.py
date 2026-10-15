"""Etapa 07 — estimação (Python; substitui 07_estimate.R por indisponibilidade de R).

Estimadores (CLAUDE.md §7):
- TWFE estático e dinâmico (referência) + decomposição de Goodman-Bacon.
- Callaway & Sant'Anna (principal): DR com covariáveis pré, nunca tratados; repetido com
  not-yet-treated e sem covariáveis. Agregações simple, group, dynamic (e ∈ [-5, 10]).
- Sun & Abraham (IW), Borusyak-Jaravel-Spiess via did2s de Gardner (pyfixest; mesmas
  estimativas pontuais da imputação), de Chaisemartin & D'Haultfœuille DID_M (não absorvente).
- Dose-resposta: CS por tercil de mortes em combate por 100 mil (3 primeiros anos).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyfixest as pf
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import did_tools as dt  # noqa: E402
import plotstyle as ps  # noqa: E402
from config import FIGURES, PROCESSED, TABLES  # noqa: E402

COVARS = ["ln_gdppc_pre", "urban_share_pre", "ln_pop_pre"]
MIN_E, MAX_E = -5, 10
OUTCOMES = {
    "pov_rate": "Taxa de pobreza extrema (p.p.)",
    "ln_n_poor": "log do número de pobres",
    "asinh_n_poor": "asinh do número de pobres",
    "d_ln_n_poor": "Crescimento do número de pobres (Δlog)",
    "poverty_gap": "Hiato de pobreza (p.p.)",
    "ln_mean": "log do consumo/renda média",
}
MAIN_OUTCOMES = ["pov_rate", "ln_n_poor", "asinh_n_poor", "d_ln_n_poor"]
B = 999


def load_sample() -> pd.DataFrame:
    p = pd.read_parquet(PROCESSED / "panel.parquet")
    p["poverty_gap"] = 100 * p.poverty_gap
    p["ln_mean"] = np.log(p["mean"])
    return p[p.status.isin(["tratado", "nunca_tratado"])].copy()


# ============================================================================ CS

def run_cs(p, y, control="never", covars=COVARS, method="dr", anticipation=0, base="varying",
           balanced=True, gcol="g"):
    w, info = dt.to_wide(p, y, g=gcol, covars=covars if method != "unc" else None, balanced=balanced)
    res = dt.callaway_santanna(w, control=control, anticipation=anticipation, base=base, method=method)
    dyn = dt.aggte(res, "dynamic", MIN_E, MAX_E, B=B)
    simple = dt.aggte(res, "simple", max_e=MAX_E, B=B)
    group = dt.aggte(res, "group", max_e=MAX_E, B=B)
    info["flags"] = int((res.cells.flag != "").sum())
    info["pretrend"] = dt.pretrend_wald(dyn)
    return {"res": res, "dyn": dyn, "simple": simple, "group": group, "info": info}


# ============================================================================ outros estimadores

def run_twfe(p, y):
    d = p.copy()
    static, *_ = dt.twfe(d, y, ["post"])
    d2, names = dt.event_dummies(d, MIN_E, MAX_E, bin_ends=True)
    dyn, *_ = dt.twfe(d2, y, names)
    dyn["term"] = dyn.term.str.replace("ev_", "").astype(int)
    return static.iloc[0].to_dict(), dyn


def run_did2s(p, y):
    d = p.dropna(subset=[y]).copy()
    d = d[~((d.treated == 1) & (d.rel_time > MAX_E))]          # pós fora da janela sai da amostra
    d["post"] = d.post.astype(int)
    d["ev"] = np.where(d.treated == 1, d.rel_time.clip(lower=MIN_E), -1).astype(int)
    d.loc[(d.treated == 1) & (d.rel_time < MIN_E), "ev"] = -1    # pré distante = referência
    stat = pf.did2s(d, yname=y, first_stage="~ 0 | iso3 + year", second_stage="~ post",
                    treatment="post", cluster="iso3").tidy().reset_index()
    dyn = pf.did2s(d, yname=y, first_stage="~ 0 | iso3 + year", second_stage="~ i(ev, ref=-1)",
                   treatment="post", cluster="iso3").tidy().reset_index()
    dyn["term"] = dyn.Coefficient.str.extract(r"::(-?\d+)").astype(int)
    dyn = dyn.rename(columns={"Estimate": "estimate", "Std. Error": "se", "2.5%": "ci_low", "97.5%": "ci_high"})
    s = stat.iloc[0]
    return ({"estimate": s.Estimate, "se": s["Std. Error"], "ci_low": s["2.5%"], "ci_high": s["97.5%"],
             "p_value": s["Pr(>|t|)"]}, dyn[["term", "estimate", "se", "ci_low", "ci_high"]])


def did_m(full: pd.DataFrame, y: str, dvar: str = "conflict_any", reps: int = 300, seed: int = 7):
    """de Chaisemartin & D'Haultfœuille (2020) DID_M e placebo, tratamento não absorvente.
    EP por bootstrap de países (cluster)."""
    d = full[["iso3", "year", y, dvar]].dropna().sort_values(["iso3", "year"])
    Yw = d.pivot(index="iso3", columns="year", values=y)
    Dw = d.pivot(index="iso3", columns="year", values=dvar)

    def est(Yv, Dv):
        num = num_pl = 0.0
        ns = ns_pl = 0
        T = Yv.shape[1]
        for t in range(1, T):
            dy = Yv[:, t] - Yv[:, t - 1]
            d0, d1 = Dv[:, t - 1], Dv[:, t]
            ok = ~np.isnan(dy) & ~np.isnan(d0) & ~np.isnan(d1)
            for a, b, sign in [(0, 1, 1), (1, 0, -1)]:
                sw = ok & (d0 == a) & (d1 == b)
                st = ok & (d0 == a) & (d1 == a)
                if sw.sum() and st.sum():
                    num += sw.sum() * sign * (dy[sw].mean() - dy[st].mean())
                    ns += sw.sum()
                    if t >= 2:   # placebo: mesma comparação no período anterior, exige D estável em t-2..t-1
                        dyp = Yv[:, t - 1] - Yv[:, t - 2]
                        okp = ~np.isnan(dyp) & (Dv[:, t - 2] == a)
                        swp, stp = sw & okp, st & okp
                        if swp.sum() and stp.sum():
                            num_pl += swp.sum() * sign * (dyp[swp].mean() - dyp[stp].mean())
                            ns_pl += swp.sum()
        return (num / ns if ns else np.nan), (num_pl / ns_pl if ns_pl else np.nan), ns
    Yv, Dv = Yw.to_numpy(float), Dw.reindex_like(Yw).to_numpy(float)
    b, bpl, ns = est(Yv, Dv)
    rng = np.random.default_rng(seed)
    boots = np.array([est(Yv[i], Dv[i])[:2] for i in (rng.integers(0, len(Yv), len(Yv)) for _ in range(reps))])
    se, se_pl = np.nanstd(boots, axis=0, ddof=1)
    return {"estimate": b, "se": se, "placebo": bpl, "se_placebo": se_pl, "n_switches": ns,
            "n_units": len(Yv)}


# ============================================================================ figuras

def plot_es(tab: pd.DataFrame, title: str, path: Path, band: bool = False, color=ps.TREATED):
    t = tab.sort_values("term")
    if -1 not in t.term.values:
        t = pd.concat([t, pd.DataFrame({"term": [-1], "estimate": [0.0], "ci_low": [0.0], "ci_high": [0.0]})]).sort_values("term")
    fig, ax = ps.plt.subplots(figsize=(6.5, 3.8))
    ax.axhline(0, color=ps.INK2, lw=1)
    ax.axvline(-1, color=ps.INK2, lw=1, ls="--")
    if band and "cb_low" in t:
        ax.fill_between(t.term, t.cb_low, t.cb_high, color=color, alpha=0.10, lw=0, label="Banda uniforme 95%")
    ax.fill_between(t.term, t.ci_low, t.ci_high, color=color, alpha=0.22, lw=0, label="IC 95% pontual")
    ax.plot(t.term, t.estimate, color=color, marker="o", label="Estimativa")
    ax.set_xlabel("Anos desde o início do conflito (referência: t = −1)")
    ps.int_xaxis(ax)
    ax.set_title(title, loc="left")
    ax.legend(loc="upper left", fontsize=8)
    ps.save(fig, path)


def plot_bacon(dec: pd.DataFrame, beta: float, y: str):
    fig, ax = ps.plt.subplots(figsize=(6.5, 3.8))
    colors = {"Tratado vs nunca tratado": ps.TREATED, "Cedo vs tarde (controle ainda não tratado)": ps.THIRD,
              "Tarde vs cedo (controle já tratado)": ps.CONTROL}
    for k, c in colors.items():
        s = dec[dec.tipo == k]
        ax.scatter(s.weight, s.estimate, s=28, color=c, edgecolor="white", linewidth=0.8,
                   label=f"{k} (peso {s.weight.sum():.2f})".replace(".", ","))
    ax.axhline(beta, color=ps.INK2, lw=1, ls="--")
    ax.text(ax.get_xlim()[1], beta, f" TWFE = {beta:.2f}".replace(".", ","), va="bottom", ha="right", color=ps.INK2, fontsize=8)
    ax.set_xlabel("Peso na estimativa TWFE")
    ax.set_ylabel("Estimativa 2x2")
    ax.set_title(f"Decomposição de Goodman-Bacon — {OUTCOMES[y]}", loc="left")
    ax.legend(fontsize=7.5, loc="best")
    ps.save(fig, FIGURES / f"bacon_{y}")


# ============================================================================ main

def row(outcome, estimator, d, n_treat=None, n_units=None, note=""):
    est, se = d["estimate"], d["se"]
    p = d.get("p_value", 2 * stats.norm.sf(abs(est / se)) if se and se > 0 else np.nan)
    lo = d.get("ci_low", est - 1.96 * se)
    hi = d.get("ci_high", est + 1.96 * se)
    return {"outcome": outcome, "estimator": estimator, "estimate": est, "se": se, "ci_low": lo,
            "ci_high": hi, "p_value": p, "n_treated": n_treat, "n_units": n_units, "nota": note}


def main() -> None:
    p = load_sample()
    # DID_M usa o tratamento não absorvente: entram todos os países soberanos, inclusive
    # os excluídos da estimação principal (sempre tratados, onsets sem pesquisas prévias)
    full = pd.read_parquet(PROCESSED / "panel.parquet")
    full = full[~full.motivo.fillna("").str.contains("não soberano")].copy()
    full["poverty_gap"] = 100 * full.poverty_gap
    full["ln_mean"] = np.log(full["mean"])
    results, dyn_all, group_all, bacon_all, pre_tests = [], [], [], [], []
    print(f"Amostra: {p.iso3.nunique()} países ({p[p.treated == 1].iso3.nunique()} tratados), {p.year.min()}-{p.year.max()}")

    for y, lab in OUTCOMES.items():
        print(f"\n=== {y} ===")
        # --- TWFE
        st, dyn_twfe = run_twfe(p, y)
        nT = p.dropna(subset=[y]).query("treated == 1").iso3.nunique()
        nU = p.dropna(subset=[y]).iso3.nunique()
        results.append(row(y, "TWFE", st, nT, nU, "referência; viesado com efeitos heterogêneos"))
        dyn_all.append(dyn_twfe.assign(outcome=y, estimator="TWFE"))
        # --- Bacon (painel balanceado)
        w_b, info_b = dt.to_wide(p, y, balanced=True)
        if info_b["n_treated"]:
            dec, beta = dt.bacon_decomposition(w_b)
            bacon_all.append(dec.assign(outcome=y, beta_twfe=beta))
            if y in ("pov_rate", "ln_n_poor"):
                plot_bacon(dec, beta, y)
            fb = dec[dec.tipo.str.startswith("Tarde")].weight.sum()
            print(f"  Bacon: β TWFE (balanceado) = {beta:.3f}; peso das comparações proibidas = {fb:.3f}")
        # --- CS
        # Especificação principal com covariáveis = regressão de resultado (REG). O DR do
        # `did` é inviável com 1-3 tratados por coorte (separação perfeita no propensity
        # score); fica como robustez, com fallback REG por célula reportado.
        specs = [("CS (REG, nunca tratados)", dict(control="never", method="reg"), "cs_never_reg"),
                 ("CS (REG, ainda não tratados)", dict(control="notyet", method="reg"), "cs_notyet_reg"),
                 ("CS (sem covariáveis, nunca tratados)", dict(control="never", method="unc"), "cs_never_unc"),
                 ("CS (DR c/ fallback REG, nunca tratados)", dict(control="never", method="dr"), "cs_never_dr")]
        for name, kw, tag in specs:
            r = run_cs(p, y, **kw)
            inf = r["info"]
            note = (f"{inf['n_units']} unidades; descartadas desbalanceadas: {len(inf.get('dropped_unbalanced', []))};"
                    f" sem X: {len(inf.get('dropped_missing_x', []))}; células com fallback: {inf['flags']}")
            results.append(row(y, f"{name} — simple", r["simple"]["overall"], inf["n_treated"], inf["n_units"], note))
            results.append(row(y, f"{name} — média dinâmica e∈[0,10]", r["dyn"]["overall"], inf["n_treated"], inf["n_units"]))
            results.append(row(y, f"{name} — group", r["group"]["overall"], inf["n_treated"], inf["n_units"]))
            dyn_all.append(r["dyn"]["table"].assign(outcome=y, estimator=name))
            group_all.append(r["group"]["table"].assign(outcome=y, estimator=name))
            pre_tests.append({"outcome": y, "estimator": name, **inf["pretrend"]})
            plot_es(r["dyn"]["table"], f"{lab} — {name}", FIGURES / f"event_study_{y}_{tag}", band=True)
            o = r["simple"]["overall"]
            print(f"  {name}: ATT = {o['estimate']:.3f} (EP {o['se']:.3f}); n_trat = {inf['n_treated']}; "
                  f"pré-tendência p = {inf['pretrend']['p_value']:.3f}; fallbacks = {inf['flags']}")
        # --- Sun-Abraham
        sa_dyn, sa_o = dt.sun_abraham(p.dropna(subset=[y]), y, MIN_E, MAX_E)
        results.append(row(y, "Sun-Abraham (IW) — média e∈[0,9]", sa_o, nT, nU))
        dyn_all.append(sa_dyn.assign(outcome=y, estimator="Sun-Abraham"))
        plot_es(sa_dyn, f"{lab} — Sun & Abraham", FIGURES / f"event_study_{y}_sunab", color=ps.THIRD)
        # --- BJS / did2s
        try:
            b_o, b_dyn = run_did2s(p, y)
            results.append(row(y, "Borusyak-Jaravel-Spiess (did2s) — estático", b_o, nT, nU))
            dyn_all.append(b_dyn.assign(outcome=y, estimator="BJS/did2s"))
            plot_es(b_dyn, f"{lab} — imputação (BJS / did2s)", FIGURES / f"event_study_{y}_bjs", color=ps.CONTROL)
        except Exception as e:  # noqa: BLE001
            print(f"  did2s falhou: {e}")
        plot_es(dyn_twfe, f"{lab} — TWFE dinâmico (referência)", FIGURES / f"event_study_{y}_twfe", color=ps.INK2)
        # --- dCDH
        if y in MAIN_OUTCOMES:
            dm = did_m(full, y)
            results.append(row(y, "de Chaisemartin-D'Haultfœuille DID_M (não absorvente)", dm, None, dm["n_units"],
                               f"placebo = {dm['placebo']:.3f} (EP {dm['se_placebo']:.3f}); {dm['n_switches']} trocas"))
            print(f"  DID_M = {dm['estimate']:.3f} (EP {dm['se']:.3f}); placebo {dm['placebo']:.3f} (EP {dm['se_placebo']:.3f})")

    # --- dose-resposta (tercis de brd_pc nos 3 primeiros anos, entre tratados)
    tr = p[p.treated == 1].drop_duplicates("iso3")
    q = tr.brd_pc_onset3.quantile([1 / 3, 2 / 3]).to_numpy()
    p["dose_tercile"] = np.where(p.treated == 1, np.digitize(p.brd_pc_onset3, q) + 1, 0)
    dose_rows = []
    for y in MAIN_OUTCOMES[:3]:
        for k in (1, 2, 3):
            sub = p[(p.treated == 0) | (p.dose_tercile == k)]
            r = run_cs(sub, y, control="never", method="reg")
            o = r["simple"]["overall"]
            dose_rows.append({"outcome": y, "tercil": k, "brd_pc_min": float(tr.brd_pc_onset3[np.digitize(tr.brd_pc_onset3, q) + 1 == k].min()),
                              "brd_pc_max": float(tr.brd_pc_onset3[np.digitize(tr.brd_pc_onset3, q) + 1 == k].max()),
                              "n_treated": r["info"]["n_treated"], **{k2: o[k2] for k2 in ("estimate", "se", "ci_low", "ci_high", "p_value")}})
            dyn_all.append(r["dyn"]["table"].assign(outcome=y, estimator=f"CS dose tercil {k}"))
    dose = pd.DataFrame(dose_rows)
    dose.to_csv(TABLES / "dose_response.csv", index=False)
    print("\nDose-resposta:\n" + dose.round(3).to_string(index=False))
    for y in MAIN_OUTCOMES[:3]:
        fig, ax = ps.plt.subplots(figsize=(6.5, 3.8))
        ax.axhline(0, color=ps.INK2, lw=1)
        ax.axvline(-1, color=ps.INK2, lw=1, ls="--")
        dd = pd.concat(dyn_all)
        for k, c in zip((1, 2, 3), (ps.THIRD, ps.TREATED, ps.CONTROL)):
            t = dd[(dd.outcome == y) & (dd.estimator == f"CS dose tercil {k}")].sort_values("term")
            ax.plot(t.term, t.estimate, color=c, marker="o", label=f"Tercil {k} de mortes/100 mil")
        ax.set_xlabel("Anos desde o início do conflito")
        ps.int_xaxis(ax)
        ax.set_title(f"{OUTCOMES[y]} — CS por intensidade", loc="left")
        ax.legend(fontsize=8)
        ps.save(fig, FIGURES / f"event_study_{y}_dose")

    main = pd.DataFrame(results)
    main.to_csv(TABLES / "main_results.csv", index=False)
    tex = main[main.outcome.isin(MAIN_OUTCOMES)][["outcome", "estimator", "estimate", "se", "ci_low", "ci_high", "p_value", "n_treated"]]
    tex.to_latex(TABLES / "main_results.tex", index=False, float_format="%.3f", na_rep="")
    pd.concat(dyn_all).to_csv(TABLES / "event_study_estimates.csv", index=False)
    pd.concat(group_all).to_csv(TABLES / "cs_group_estimates.csv", index=False)
    pd.concat(bacon_all).to_csv(TABLES / "bacon_decomposition.csv", index=False)
    pd.DataFrame(pre_tests).to_csv(TABLES / "pretrend_tests.csv", index=False)
    print("\nResultados principais:")
    print(main[main.outcome.isin(MAIN_OUTCOMES)][["outcome", "estimator", "estimate", "se", "p_value"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
