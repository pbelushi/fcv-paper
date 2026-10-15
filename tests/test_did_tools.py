"""Validação dos estimadores próprios (src/did_tools.py) em dados simulados.

Executar: python tests/test_did_tools.py  (falha com AssertionError)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyfixest as pf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import did_tools as dt  # noqa: E402


def simulate(N=300, years=range(2000, 2016), seed=0, x_trend=0.0, x_select=0.0, dynamic=True):
    rng = np.random.default_rng(seed)
    years = np.array(list(years))
    x = rng.normal(size=N)
    # seleção em X: maior X -> mais chance de ser tratado
    p_treat = 1 / (1 + np.exp(-(-0.3 + x_select * x)))
    treated = rng.random(N) < p_treat
    cohorts = np.array([2004, 2007, 2010, 2013])
    g = np.where(treated, rng.choice(cohorts, N), 0)
    a = rng.normal(size=N)
    lam = np.cumsum(rng.normal(0.3, 0.2, len(years)))
    rows = []
    for i in range(N):
        for j, t in enumerate(years):
            e = t - g[i]
            tau = 0.0
            if g[i] > 0 and e >= 0:
                tau = (1 + 0.5 * e if dynamic else 2.0) * (1 + 0.5 * (g[i] == 2004))
            y = a[i] + lam[j] + x_trend * x[i] * j + tau + rng.normal(scale=0.5)
            rows.append((i, t, g[i], x[i], y, tau))
    return pd.DataFrame(rows, columns=["iso3", "year", "g", "x", "y", "tau"])


def true_dynamic(df, e):
    d = df[(df.g > 0) & (df.year - df.g == e)]
    return d.tau.mean()


def test_cs_unconditional():
    df = simulate(seed=1)
    w, _ = dt.to_wide(df, "y")
    res = dt.callaway_santanna(w, control="never", method="unc")
    dyn = dt.aggte(res, "dynamic", -3, 5)
    tab = dyn["table"].set_index("term")
    for e in range(0, 6):
        truth = true_dynamic(df, e)
        assert abs(tab.loc[e, "estimate"] - truth) < 4 * tab.loc[e, "se"] + 0.05, (e, tab.loc[e, "estimate"], truth)
    for e in range(-3, -1):
        assert abs(tab.loc[e, "estimate"]) < 4 * tab.loc[e, "se"]
    # not-yet
    res2 = dt.callaway_santanna(w, control="notyet", method="unc")
    s2 = dt.aggte(res2, "simple")["overall"]
    s1 = dt.aggte(res, "simple")["overall"]
    assert abs(s1["estimate"] - s2["estimate"]) < 4 * max(s1["se"], s2["se"])
    print(f"  ok CS sem covariáveis: dinâmico recupera τ(e); simple never={s1['estimate']:.3f} notyet={s2['estimate']:.3f}")


def test_cs_dr_covariate_trends():
    df = simulate(seed=2, x_trend=0.4, x_select=1.5, dynamic=False)
    w, _ = dt.to_wide(df, "y", covars=["x"])
    unc = dt.aggte(dt.callaway_santanna(w, method="unc"), "simple")["overall"]
    dr = dt.aggte(dt.callaway_santanna(w, method="dr"), "simple")["overall"]
    reg = dt.aggte(dt.callaway_santanna(w, method="reg"), "simple")["overall"]
    truth = df[(df.g > 0) & (df.year >= df.g)].groupby("g").tau.mean()
    # simple do `did` pondera células pós por pg -> verdade calculada com a mesma ponderação
    cells = df[(df.g > 0) & (df.year >= df.g)].groupby(["g", "year"]).tau.mean().reset_index()
    pg = df.drop_duplicates("iso3").g.value_counts(normalize=True)
    wts = cells.g.map(pg)
    truth = float((cells.tau * wts).sum() / wts.sum())
    assert abs(dr["estimate"] - truth) < 4 * dr["se"], (dr, truth)
    assert abs(reg["estimate"] - truth) < 4 * reg["se"], (reg, truth)
    assert abs(unc["estimate"] - truth) > abs(dr["estimate"] - truth), "sem covariáveis deveria ser viesado"
    print(f"  ok CS DR com tendência dependente de X: verdade={truth:.3f} DR={dr['estimate']:.3f} "
          f"REG={reg['estimate']:.3f} sem X={unc['estimate']:.3f}")


def test_cs_coverage(reps=150):
    hits = 0
    for r in range(reps):
        df = simulate(N=150, seed=100 + r, dynamic=False)
        w, _ = dt.to_wide(df, "y")
        o = dt.aggte(dt.callaway_santanna(w, method="unc"), "simple", B=299)["overall"]
        cells = df[(df.g > 0) & (df.year >= df.g)].groupby(["g", "year"]).tau.mean().reset_index()
        pg = df.drop_duplicates("iso3").g.value_counts(normalize=True)
        wts = cells.g.map(pg)
        truth = float((cells.tau * wts).sum() / wts.sum())
        hits += o["ci_low"] <= truth <= o["ci_high"]
    cov = hits / reps
    assert 0.88 <= cov <= 0.99, cov
    print(f"  ok cobertura IC 95% (bootstrap multiplicador) = {cov:.2f} em {reps} réplicas")


def test_twfe_matches_pyfixest():
    df = simulate(seed=3)
    df["post"] = ((df.g > 0) & (df.year >= df.g)).astype(float)
    tab, *_ = dt.twfe(df, "y", ["post"])
    ref = pf.feols("y ~ post | iso3 + year", data=df, vcov={"CRV1": "iso3"}).tidy()
    assert abs(tab.estimate[0] - ref.Estimate.iloc[0]) < 1e-6
    assert abs(tab.se[0] - ref["Std. Error"].iloc[0]) / ref["Std. Error"].iloc[0] < 1e-3
    print(f"  ok TWFE = pyfixest (β={tab.estimate[0]:.4f}, EP={tab.se[0]:.4f})")


def test_bacon_sums_to_twfe():
    df = simulate(seed=4)
    w, _ = dt.to_wide(df, "y")
    dec, b = dt.bacon_decomposition(w)
    assert abs(dec.weight.sum() - 1) < 1e-6, dec.weight.sum()
    assert abs((dec.weight * dec.estimate).sum() - b) < 1e-6, ((dec.weight * dec.estimate).sum(), b)
    print(f"  ok Bacon: Σw = {dec.weight.sum():.6f}, Σwβ = TWFE = {b:.4f}")


def test_sun_abraham():
    df = simulate(seed=5)
    df["rel_time"] = np.where(df.g > 0, df.year - df.g, np.nan)
    es, overall = dt.sun_abraham(df, "y", -3, 5)
    es = es.set_index("term")
    for e in range(0, 5):
        truth = true_dynamic(df, e)
        assert abs(es.loc[e, "estimate"] - truth) < 4 * es.loc[e, "se"] + 0.05, (e, es.loc[e, "estimate"], truth)
    print("  ok Sun-Abraham recupera τ(e)")


def test_against_differences_package():
    """Compara ATT(g,t) com o pacote `differences` (implementação independente de CS)."""
    try:
        from differences import ATTgt
    except Exception as e:  # noqa: BLE001
        print(f"  -- pacote differences indisponível ({e!r}); comparação pulada")
        return
    df = simulate(seed=6, x_trend=0.3, x_select=1.0)
    d = df.assign(cohort=df.g.replace(0, np.nan)).set_index(["iso3", "year"])
    for method, formula in [("unc", "y"), ("dr", "y ~ x")]:
        w, _ = dt.to_wide(df, "y", covars=None if method == "unc" else ["x"])
        cells = dt.callaway_santanna(w, method=method).cells
        mine = cells.set_index(["g", "t"]).att
        att = ATTgt(data=d, cohort_column="cohort")
        att.fit(formula=formula, est_method="reg" if method == "unc" else "dr",
                control_group="never_treated", progress_bar=False)
        r = att.results()
        r.columns = ["att", "se", *[f"c{i}" for i in range(r.shape[1] - 2)]]
        r = r.reset_index().rename(columns={"cohort": "g", "time": "t"}).set_index(["g", "t"])
        common = mine.index.intersection(r.index)
        diff = float(np.max(np.abs(mine.loc[common].to_numpy() - r.att.loc[common].to_numpy())))
        se_mine = cells.set_index(["g", "t"]).se.loc[common].to_numpy()
        se_ratio = float(np.median(se_mine / r.se.loc[common].to_numpy()))
        assert len(common) > 20 and diff < 1e-4, (method, len(common), diff)
        assert abs(se_ratio - 1) < 0.02, se_ratio
        print(f"  ok ATT(g,t) [{method}] = pacote differences em {len(common)} células "
              f"(dif. máx {diff:.1e}; razão mediana de EP {se_ratio:.3f})")


def test_sdid():
    """SDID recupera τ = 2 num modelo de fatores em que o tratado difere dos controles."""
    import importlib
    rob = importlib.import_module("08_robustness")
    rng = np.random.default_rng(9)
    T, T0, N0 = 25, 18, 60
    f = np.cumsum(rng.normal(0, 1, T))                     # fator comum com carga heterogênea
    load0 = rng.uniform(0, 2, N0)
    Y0 = 3 + load0[:, None] * f[None, :] + rng.normal(0, 0.3, (N0, T))
    Y1 = (5 + 1.5 * f + rng.normal(0, 0.3, T))[None, :]  # carga 1,5: TWFE simples seria viesado
    Y1[:, T0:] += 2.0
    tau, omega, lam = rob.sdid_estimate(Y0, Y1, T0)
    assert abs(tau - 2.0) < 0.5, tau
    assert abs(omega.sum() - 1) < 1e-8 and abs(lam.sum() - 1) < 1e-8
    print(f"  ok SDID recupera τ = 2 em modelo de fatores (τ̂ = {tau:.3f})")


if __name__ == "__main__":
    print("Validação de did_tools:")
    test_twfe_matches_pyfixest()
    test_bacon_sums_to_twfe()
    test_cs_unconditional()
    test_cs_dr_covariate_trends()
    test_sun_abraham()
    test_against_differences_package()
    test_sdid()
    test_cs_coverage()
    print("Todos os testes passaram.")
