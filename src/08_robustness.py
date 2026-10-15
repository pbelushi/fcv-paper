"""Etapa 08 — robustez e validade (CLAUDE.md §8), em Python.

Especificação de referência: CS com regressão de resultado (REG), nunca tratados, ATT simple.
1. Pré-tendências (Wald) + sensibilidade Rambachan-Roth (relative magnitudes, M̄ ∈ {0,…,2}).
   Implementação própria: conjunto identificado em forma fechada; IC por simulação de
   N(β̂, Σ̂) — aproximação ao teste condicional/híbrido do HonestDiD (documentado).
2. Somente dados observados (pesquisas), blocos de 3 anos.
3. PEACE_WINDOW ∈ {3, 5, 10}.   4. Onset por guerra (≥ 1.000 mortes).
5. Spillovers: controles sem vizinhos de tratados nem grandes receptores de refugiados;
   vizinhos como tratamento à parte.
6. Antecipação 1 e 2.            7. Synthetic DiD (coortes com mais países).
8. Placebo: 500 permutações de datas de onset entre nunca tratados.
9. Linhas US$ 4,20 e 8,30.       10. Heterogeneidade.
"""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import optimize, stats

sys.path.insert(0, str(Path(__file__).parent))
import did_tools as dt  # noqa: E402
import plotstyle as ps  # noqa: E402
from config import FIGURES, INTERIM, PROCESSED, TABLES  # noqa: E402

est = importlib.import_module("07_estimate")
OUT = ["pov_rate", "ln_n_poor", "asinh_n_poor"]
M_GRID = [0, 0.5, 1, 1.5, 2]
N_PERM = 500
rows: list[dict] = []


def add(check, outcome, o, n_treat, note=""):
    rows.append({"teste": check, "outcome": outcome, "estimate": o["estimate"], "se": o["se"],
                 "ci_low": o["ci_low"], "ci_high": o["ci_high"],
                 "p_value": o.get("p_value", 2 * stats.norm.sf(abs(o["estimate"] / o["se"])) if o["se"] else np.nan),
                 "n_treated": n_treat, "nota": note})


def cs_simple(p, y, gcol="g", method="reg", **kw):
    w, info = dt.to_wide(p, y, g=gcol, covars=est.COVARS if method != "unc" else None,
                         balanced=kw.pop("balanced", True))
    res = dt.callaway_santanna(w, method=method, **kw)
    return dt.aggte(res, "simple", max_e=est.MAX_E, B=est.B)["overall"], info, res


# ============================================================================ 1. HonestDiD (RM)

def honest_rm(p, y, n_draws=5000, seed=11):
    w, _ = dt.to_wide(p, y, covars=est.COVARS)
    res = dt.callaway_santanna(w, method="reg", base="universal")
    dyn = dt.aggte(res, "dynamic", est.MIN_E, est.MAX_E, B=est.B)
    tab = dyn["table"]
    b = tab.estimate.to_numpy()
    terms = tab.term.to_numpy()
    Sigma = dyn["IF"].T @ dyn["IF"] / res.N ** 2
    pre_idx = np.where(terms < 0)[0]
    out = []

    def bounds(bvec, M, E):
        pre = np.append(bvec[pre_idx], 0.0)                 # inclui β_{-1} = 0 (universal)
        mbar = np.max(np.abs(np.diff(pre)))
        post = [np.where(terms == e)[0][0] for e in range(0, E + 1)]
        theta = bvec[post].mean()
        slack = M * mbar * (E + 2) / 2                       # max |viés médio| sob RM
        return theta - slack, theta + slack, theta, mbar
    rng = np.random.default_rng(seed)
    draws = rng.multivariate_normal(b, Sigma, size=n_draws, method="eigh")
    for E, lab in [(0, "e = 0"), (5, "média e ∈ [0,5]")]:
        for M in M_GRID:
            lb, ub, theta, mbar = bounds(b, M, E)
            sims = np.array([bounds(d, M, E)[:2] for d in draws])
            out.append({"outcome": y, "alvo": lab, "M": M, "theta": theta, "mbar": mbar,
                        "id_set_low": lb, "id_set_high": ub,
                        "ci_low": np.quantile(sims[:, 0], 0.025), "ci_high": np.quantile(sims[:, 1], 0.975)})

    # Suavidade com M = 0 (Δ^SD(0)): o viés segue a reta da tendência pré, ancorada em β_{-1} = 0.
    # Inclinação por MQO dos coeficientes pré em (e + 1); efeito = β_e - s (e + 1).
    pre_e = terms[pre_idx] + 1.0

    def detrended(bvec, E):
        s = (pre_e @ bvec[pre_idx]) / (pre_e @ pre_e)
        post = [np.where(terms == e)[0][0] for e in range(0, E + 1)]
        return float(np.mean(bvec[post] - s * (np.arange(E + 1) + 1))), s
    for E, lab in [(0, "e = 0"), (5, "média e ∈ [0,5]")]:
        th, slope = detrended(b, E)
        sims = np.array([detrended(d, E)[0] for d in draws])
        out.append({"outcome": y, "alvo": lab, "M": "SD(0): tendência linear extrapolada", "theta": th,
                    "mbar": slope, "id_set_low": th, "id_set_high": th,
                    "ci_low": np.quantile(sims, 0.025), "ci_high": np.quantile(sims, 0.975)})
    return pd.DataFrame(out)


# ============================================================================ 2. só observados, blocos de 3 anos

def observed_blocks(p, y_obs):
    d = p.copy()
    d["block"] = 1990 + 3 * ((d.year - 1990) // 3)
    d["g_block"] = np.where(d.g > 0, 1990 + 3 * ((d.g - 1990) // 3), 0)
    agg = d.groupby(["iso3", "block"]).agg(y=(y_obs, "mean"), g=("g_block", "first")).reset_index()
    agg = agg.rename(columns={"block": "year"})
    w, info = dt.to_wide(agg, "y", balanced=False)
    res = dt.callaway_santanna(w, method="unc")
    o = dt.aggte(res, "simple", max_e=est.MAX_E, B=est.B)["overall"]
    return o, info, int(agg.y.notna().sum())


# ============================================================================ 7. Synthetic DiD

def _simplex_ridge(A, b, zeta2):
    """min ||A w - b||² + zeta2 ||w||², w no simplex (A e b já centrados)."""
    n = A.shape[1]
    fun = lambda w: np.sum((A @ w - b) ** 2) + zeta2 * np.sum(w ** 2)  # noqa: E731
    jac = lambda w: 2 * A.T @ (A @ w - b) + 2 * zeta2 * w  # noqa: E731
    r = optimize.minimize(fun, np.full(n, 1 / n), jac=jac, method="SLSQP", bounds=[(0, 1)] * n,
                          constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1, "jac": lambda w: np.ones(n)}],
                          options={"maxiter": 500, "ftol": 1e-12})
    return np.clip(r.x, 0, None) / np.clip(r.x, 0, None).sum()


def sdid_estimate(Y0: np.ndarray, Y1: np.ndarray, T0: int):
    """Arkhangelsky et al. (2021). Y0: controles N0 x T; Y1: tratados N1 x T; T0 períodos pré."""
    N1, T1 = Y1.shape[0], Y0.shape[1] - T0
    pre0, post0 = Y0[:, :T0], Y0[:, T0:]
    sd = np.std(np.diff(pre0, axis=1), ddof=1)
    zeta = (N1 * T1) ** 0.25 * sd
    # pesos de unidade (intercepto livre -> centrar cada série no tempo)
    A = (pre0 - pre0.mean(1, keepdims=True)).T
    bvec = Y1[:, :T0].mean(0) - Y1[:, :T0].mean()
    omega = _simplex_ridge(A, bvec, zeta ** 2 * T0)
    # pesos de tempo (com intercepto -> centrar nas unidades)
    Bm = pre0 - pre0.mean(0, keepdims=True)
    target = post0.mean(1) - post0.mean(1).mean()
    lam = _simplex_ridge(Bm, target, (1e-6 * sd) ** 2 * len(Y0))
    y1_pre, y1_post = Y1[:, :T0].mean(0) @ lam, Y1[:, T0:].mean()
    y0_pre, y0_post = omega @ (pre0 @ lam), omega @ post0.mean(1)
    return (y1_post - y1_pre) - (y0_post - y0_pre), omega, lam


def sdid_cohort(p, y, g, reps=200, seed=3, max_e=10):
    years = np.arange(1990, min(g + max_e, p.year.max()) + 1)
    d = p[p.year.isin(years) & ((p.g == g) | (p.treated == 0))]
    Yw = d.pivot(index="iso3", columns="year", values=y).dropna()
    G = d.drop_duplicates("iso3").set_index("iso3").g.reindex(Yw.index)
    Y1, Y0 = Yw[G == g].to_numpy(), Yw[G == 0].to_numpy()
    T0 = int((years < g).sum())
    if len(Y1) == 0 or T0 < 3:
        return None
    tau, omega, lam = sdid_estimate(Y0, Y1, T0)
    rng = np.random.default_rng(seed)
    pl = []
    for _ in range(reps):   # variância placebo (Arkhangelsky et al., alg. 4)
        idx = rng.permutation(len(Y0))
        pl.append(sdid_estimate(Y0[idx[len(Y1):]], Y0[idx[:len(Y1)]], T0)[0])
    se = float(np.std(pl, ddof=1))
    return {"estimate": tau, "se": se, "ci_low": tau - 1.96 * se, "ci_high": tau + 1.96 * se,
            "p_value": 2 * stats.norm.sf(abs(tau / se)), "n_treated": len(Y1), "n_controls": len(Y0),
            "top_controls": ", ".join(f"{u}:{w:.2f}" for u, w in sorted(zip(Yw[G == 0].index, omega),
                                                                       key=lambda x: -x[1])[:5])}


# ============================================================================ 8. placebo

def fast_simple_unc(Y, G, years):
    """ATT simple sem covariáveis (pesos pg por célula pós), sem inferência — para permutações."""
    num = den = 0.0
    never = G == 0
    for g in np.unique(G[G > 0]):
        ib = np.searchsorted(years, g - 1)
        tr = G == g
        pg = tr.mean()
        for it in range(ib + 1, len(years)):
            if years[it] - g > est.MAX_E:
                break
            att = (Y[tr, it] - Y[tr, ib]).mean() - (Y[never, it] - Y[never, ib]).mean()
            num += pg * att
            den += pg
    return num / den


def placebo(p, y, seed=2026):
    w, _ = dt.to_wide(p, y)
    actual = fast_simple_unc(w.Y, w.G, w.years)
    nt_idx = np.where(w.G == 0)[0]
    tr_g = w.G[w.G > 0]
    rng = np.random.default_rng(seed)
    Yc = w.Y[nt_idx]
    dist = []
    for _ in range(N_PERM):
        Gp = np.zeros(len(nt_idx), int)
        pick = rng.choice(len(nt_idx), size=len(tr_g), replace=False)
        Gp[pick] = rng.permutation(tr_g)
        dist.append(fast_simple_unc(Yc, Gp, w.years))
    dist = np.array(dist)
    pval = float((np.abs(dist) >= abs(actual)).mean())
    return actual, dist, pval


# ============================================================================ main

def main() -> None:
    p = est.load_sample()
    full = pd.read_parquet(PROCESSED / "panel.parquet")
    full["poverty_gap"] = 100 * full.poverty_gap
    nb = pd.read_csv(INTERIM / "neighbors.csv")

    # referência
    for y in OUT:
        o, info, _ = cs_simple(p, y)
        add("Referência: CS REG, nunca tratados", y, o, info["n_treated"])

    # ---------------------------------------------------------------- 1. pré-tendências + HonestDiD
    pre = pd.read_csv(TABLES / "pretrend_tests.csv")
    hd = pd.concat([honest_rm(p, y) for y in OUT])
    hd.to_csv(TABLES / "honestdid_rm.csv", index=False)
    print("1. Pré-tendências (Wald conjunto, CS):")
    print(pre.round(3).to_string(index=False))
    print("\n   HonestDiD (relative magnitudes), alvo e = 0 e média e∈[0,5]:")
    print(hd.round(3).to_string(index=False))
    for y in OUT:
        h = hd[(hd.outcome == y) & (hd.alvo == "média e ∈ [0,5]") & hd.M.isin(M_GRID)].copy()
        h["M"] = h.M.astype(float)
        fig, ax = ps.plt.subplots(figsize=(6.0, 3.6))
        ax.axhline(0, color=ps.INK2, lw=1)
        ax.vlines(h.M, h.ci_low, h.ci_high, color=ps.TREATED, lw=2.5, label="IC 95% robusto (aprox.)")
        ax.vlines(h.M, h.id_set_low, h.id_set_high, color=ps.CONTROL, lw=6, alpha=0.55, label="Conjunto identificado")
        ax.plot(h.M, h.theta, "o", color=ps.INK, ms=5, label="Estimativa (M̄ = 0)")
        ax.set_xticks(M_GRID)
        ax.set_xlabel("M̄ (violação pós relativa à maior variação pré)")
        ax.set_title(f"Sensibilidade Rambachan-Roth — {est.OUTCOMES[y]}", loc="left")
        ax.legend(fontsize=8)
        ps.save(fig, FIGURES / f"honestdid_{y}")

    # ---------------------------------------------------------------- 2. só observados
    for y_obs, lab in [("pov_rate_obs", "pov_rate"), ("ln_n_poor_obs", "ln_n_poor")]:
        o, info, nobs = observed_blocks(p, y_obs)
        add("Somente pesquisas observadas, blocos de 3 anos (CS sem X, desbalanceado)", lab, o,
            info["n_treated"], f"{nobs} unidade-blocos com dado")

    # ---------------------------------------------------------------- 3-4. janela de paz e guerra
    for col, lab in [("g_pw3", "PEACE_WINDOW = 3"), ("g_pw10", "PEACE_WINDOW = 10"),
                     ("g_war", "Onset por guerra (≥ 1.000 mortes)")]:
        st = f"status_{col[2:]}"
        d = full[full[st].isin(["tratado", "nunca_tratado"])].copy()
        d[col] = d[col].fillna(0).astype(int)
        for y in OUT:
            d2 = d.assign(g=d[col])
            # covariáveis pré recalculadas para a nova coorte seriam ideais; usa-se o ano-base da
            # definição principal quando disponível, senão a média amostral (nota no relatório)
            o, info, _ = cs_simple(d2, y, method="unc")
            add(f"{lab} (CS sem X)", y, o, info["n_treated"])

    # ---------------------------------------------------------------- 5. spillovers
    ref_share = (full.groupby("iso3").apply(lambda x: (x.refugees_hosted / x.pop_pip).mean(), include_groups=False))
    nt = p[p.treated == 0].iso3.unique()
    top_ref = ref_share.reindex(nt).dropna()
    top_ref = set(top_ref[top_ref >= top_ref.quantile(0.9)].index)
    nb_set = set(p.loc[(p.treated == 0) & (p.neighbor_of_treated == 1), "iso3"])
    clean = p[~p.iso3.isin(nb_set | top_ref)]
    for y in OUT:
        o, info, _ = cs_simple(clean, y)
        add("Controles sem vizinhos de tratados e sem grandes receptores de refugiados", y, o, info["n_treated"],
            f"removidos {len(nb_set)} vizinhos + {len(top_ref - nb_set)} receptores (decil superior refugiados/pop.)")
    # vizinhos como tratados: g = primeiro onset entre tratados vizinhos
    gmap = p[p.treated == 1].drop_duplicates("iso3").set_index("iso3").g
    nbg = nb[nb.iso3_nb.isin(gmap.index)].assign(gn=lambda x: x.iso3_nb.map(gmap)).groupby("iso3").gn.min()
    sp = p[(p.treated == 0)].copy()
    sp["g"] = sp.iso3.map(nbg).fillna(0).astype(int)
    sp = sp[~sp.iso3.isin(top_ref - set(nbg.index))]
    for y in OUT:
        o, info, _ = cs_simple(sp, y)
        add("Efeito sobre vizinhos de tratados (vizinho = tratado; controles não vizinhos)", y, o, info["n_treated"])

    # ---------------------------------------------------------------- 6. antecipação
    for a in (1, 2):
        for y in OUT:
            o, info, _ = cs_simple(p, y, anticipation=a)
            add(f"Antecipação = {a}", y, o, info["n_treated"])

    # ---------------------------------------------------------------- 7. SDID
    sizes = p[p.treated == 1].drop_duplicates("iso3").g.value_counts()
    big = sorted(sizes[sizes == sizes.max()].index)
    sd_rows = []
    for g in big:
        for y in OUT:
            r = sdid_cohort(p, y, g)
            if r:
                sd_rows.append({"g": g, "outcome": y, **r})
                add(f"Synthetic DiD — coorte {g}", y, r, r["n_treated"], f"placebo SE; pesos: {r['top_controls']}")
    pd.DataFrame(sd_rows).to_csv(TABLES / "sdid.csv", index=False)

    # ---------------------------------------------------------------- 8. placebo
    pl_rows = []
    fig, axes = ps.plt.subplots(1, len(OUT), figsize=(10, 3.2))
    for ax, y in zip(axes, OUT):
        actual, dist, pval = placebo(p, y)
        pl_rows.append({"outcome": y, "att_sem_covariaveis": actual, "p_permutacao": pval,
                        "placebo_media": dist.mean(), "placebo_dp": dist.std(), "n_perm": N_PERM})
        ax.hist(dist, bins=30, color=ps.CONTROL, alpha=0.7, edgecolor="white", linewidth=0.5)
        ax.axvline(actual, color=ps.TREATED, lw=2)
        ax.set_title(f"{y}  (p = {pval:.2f})".replace(".", ","), loc="left", fontsize=9)
        ax.grid(False)
    fig.suptitle("Placebo: 500 datas de onset aleatórias entre nunca tratados (linha = ATT estimado)",
                 x=0.01, ha="left", fontsize=10, fontweight="bold")
    ps.save(fig, FIGURES / "placebo_permutations")
    pl = pd.DataFrame(pl_rows)
    pl.to_csv(TABLES / "placebo_permutations.csv", index=False)
    print("\n8. Placebo:\n" + pl.round(3).to_string(index=False))

    # ---------------------------------------------------------------- 9. linhas alternativas
    for y, lab in [("pov_rate_420", "Linha US$ 4,20 — taxa"), ("ln_n_poor_420", "Linha US$ 4,20 — log nº pobres"),
                   ("pov_rate_830", "Linha US$ 8,30 — taxa"), ("ln_n_poor_830", "Linha US$ 8,30 — log nº pobres")]:
        o, info, _ = cs_simple(p, y)
        add(lab, y, o, info["n_treated"])

    # ---------------------------------------------------------------- 10. heterogeneidade
    tr = p[p.treated == 1].drop_duplicates("iso3").set_index("iso3")
    va = p[(p.treated == 1) & (p.year < p.g) & p.wgi_va.notna()].sort_values("year").groupby("iso3").wgi_va.last()
    groups = {
        "África Subsaariana": tr.region_code == "SSF",
        "Fora da África Subsaariana": tr.region_code != "SSF",
        "Renda baixa (pré)": tr.income_group_pre == "L",
        "Renda média/alta (pré)": tr.income_group_pre.isin(["LM", "UM", "H"]),
        "Intraestatal": tr.onset_type == "intraestatal",
        "Duração ≤ 2 anos": tr.duration_first_spell <= 2,
        "Duração > 2 anos": tr.duration_first_spell > 2,
        "Voz e responsabilização (WGI) ≤ mediana": va.reindex(tr.index) <= va.median(),
        "Voz e responsabilização (WGI) > mediana": va.reindex(tr.index) > va.median(),
        "Onset limpo (sem conflito desde 1985)": tr.onset_clean == 1,
        "Reincidência (conflito em 1985..g-1)": tr.onset_clean == 0,
    }
    het = []
    for lab, mask in groups.items():
        isos = set(tr.index[mask.fillna(False)])
        sub = p[(p.treated == 0) | p.iso3.isin(isos)]
        for y in OUT:
            try:
                o, info, _ = cs_simple(sub, y)
            except Exception as e:  # noqa: BLE001
                print(f"  heterogeneidade {lab}/{y}: {e}")
                continue
            het.append({"grupo": lab, "outcome": y, "n_treated": info["n_treated"], **{k: o[k] for k in
                        ("estimate", "se", "ci_low", "ci_high", "p_value")}})
            add(f"Heterogeneidade: {lab}", y, o, info["n_treated"])
    pd.DataFrame(het).to_csv(TABLES / "heterogeneity.csv", index=False)

    rob = pd.DataFrame(rows)
    rob.to_csv(TABLES / "robustness.csv", index=False)
    rob.drop(columns="nota").to_latex(TABLES / "robustness.tex", index=False, float_format="%.3f", na_rep="")
    print("\nTabela de robustez:")
    print(rob.drop(columns="nota").round(3).to_string(index=False))


if __name__ == "__main__":
    main()
