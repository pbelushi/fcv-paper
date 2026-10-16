"""Rodada 2 — 05: pobreza, medidas alternativas, poder e mecanismos (Q3, §6.5).

Amostra de pobreza: tratados T1 com ≥ 3 anos de pesquisa antes do onset + controles (nunca T1, nunca FCS) no PIP.
- CS REG: pov_rate (principal) e ln_n_poor (só robustez: efeito em log depende da escala — ver rodada 1);
  pov_rate_survey_only e mpi_headcount em blocos de 3 anos (08_robustness.observed_blocks; CS sem X, desbalanceado).
- Diferenças longas entre pesquisas: tratado = última pesquisa ≤ g−1 e primeira em [g, g+10]; controles = pares
  com a última pesquisa ≤ s0 e a primeira ≥ s1 com intervalo até ±2 anos do tratado; efeito = Δ tratado − média
  ponderada de Δ controles (pesos iguais por tratado); EP por bootstrap de países.
- MDE por simulação placebo (14_power_simulation.build_pool/replicate), efeito constante, 500 réplicas por δ;
  referência = max(MDE simulado, 2,8 × EP real).
- WAOSS para pov_rate na série lineup × só anos com pesquisa (pov_rate_obs): o placebo das escaladas some?
- Mecanismos demográficos: refugiados que saem (UNHCR COO) e deslocados internos (IDMC) por 100 mil.
- Figura-síntese: efeito implícito do PIB (04) × MDE × ATT estimado.
"""
import importlib
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import common as C  # noqa: E402
from r2config import FIG, MIN_PRE_SURVEYS, TAB  # noqa: E402

rob = importlib.import_module("08_robustness")
pw = importlib.import_module("14_power_simulation")
GRID = np.round(np.arange(0, 10.0001, 0.5), 2)
N_REPS = 500
_POOL = None


def _init(pool):
    global _POOL
    _POOL = pool


def _task(r):
    seed = np.random.SeedSequence([2027, r]).generate_state(1)[0]
    return [{"rep": r, **x} for x in pw.replicate(_POOL, seed, GRID, shapes={"constante": pw.SHAPES["constante"]})]


def poverty_sample(p: pd.DataFrame) -> pd.DataFrame:
    d = C.onset_sample(p[p.in_pip == 1])
    pre = d[(d.treated == 1) & (d.year < d.g)].groupby("iso3").survey_pip.sum()
    ok = set(pre[pre >= MIN_PRE_SURVEYS].index)
    return d[(d.treated == 0) | d.iso3.isin(ok)]


def long_differences(d: pd.DataFrame, reps: int = 999, seed: int = 11) -> tuple[dict, pd.DataFrame]:
    obs = d[d.pov_rate_obs.notna()][["iso3", "year", "pov_rate_obs", "g", "treated"]]
    S = {i: s.set_index("year").pov_rate_obs for i, s in obs.groupby("iso3")}
    ctrl = [i for i in S if obs[obs.iso3 == i].treated.iloc[0] == 0]
    pairs = []
    for i, g in obs[obs.treated == 1].drop_duplicates("iso3")[["iso3", "g"]].itertuples(index=False):
        s = S[i]
        pre, post = s[s.index <= g - 1], s[(s.index >= g) & (s.index <= g + 10)]
        if pre.empty or post.empty:
            continue
        s0, s1 = int(pre.index.max()), int(post.index.min())
        dt_ = s1 - s0
        cds = []
        for c in ctrl:
            sc = S[c]
            a, b = sc[sc.index <= s0], sc[sc.index >= s1]
            if a.empty or b.empty:
                continue
            gap = int(b.index.min()) - int(a.index.max())
            if abs(gap - dt_) <= 2:
                cds.append(b.iloc[0] - a.iloc[-1])
        if cds:
            pairs.append({"iso3": i, "g": g, "s0": s0, "s1": s1, "intervalo": dt_, "delta_tratado": s.loc[s1] - s.loc[s0],
                          "delta_controles": float(np.mean(cds)), "n_controles": len(cds)})
    pr = pd.DataFrame(pairs)
    pr["efeito"] = pr.delta_tratado - pr.delta_controles
    rng = np.random.default_rng(seed)
    boots = [pr.efeito.iloc[rng.integers(0, len(pr), len(pr))].mean() for _ in range(reps)]
    est_, se = float(pr.efeito.mean()), float(np.std(boots, ddof=1))
    from scipy import stats
    return ({"estimate": est_, "se": se, "ci_low": est_ - 1.96 * se, "ci_high": est_ + 1.96 * se,
             "p_value": float(2 * stats.norm.sf(abs(est_ / se))), "n_treated": len(pr)}, pr)


def mde(d: pd.DataFrame, se_real: float) -> tuple[pd.DataFrame, dict]:
    pool = pw.build_pool(d, "pov_rate")
    with mp.Pool(12, initializer=_init, initargs=(pool,)) as P:
        raw = [x for rows in P.imap_unordered(_task, range(N_REPS), chunksize=4) for x in rows]
    raw = pd.DataFrame(raw)
    curve = raw.groupby("delta").agg(poder=("rejeita", "mean"), ep_medio=("se", "mean")).reset_index()
    ok = curve[curve.poder >= 0.8]
    k = ok.index[0] if len(ok) else None
    if k is not None and k > 0:
        a, b = curve.loc[k - 1], curve.loc[k]
        m_sim = a.delta + (0.8 - a.poder) * (b.delta - a.delta) / (b.poder - a.poder)
    else:
        m_sim = float(ok.delta.iloc[0]) if len(ok) else np.nan
    summ = {"replicas": N_REPS, "tamanho_delta0": float(curve.loc[curve.delta == 0, "poder"].iloc[0]),
            "mde_simulado": float(m_sim), "ep_real": se_real, "mde_2_8_ep": 2.8 * se_real,
            "ep_simulado_delta0": float(curve.loc[curve.delta == 0, "ep_medio"].iloc[0]),
            "n_falsos_tratados": int(len(pool["cohorts"])), "pool": int(len(pool["units"]))}
    summ["mde_referencia"] = float(np.nanmax([summ["mde_simulado"], summ["mde_2_8_ep"]]))
    return curve, summ


def main() -> None:
    p = C.panel()
    d = poverty_sample(p)
    ntr = d[d.treated == 1].iso3.nunique()
    print(f"Amostra de pobreza: {ntr} tratados (≥ {MIN_PRE_SURVEYS} pesquisas pré), {d[d.treated == 0].iso3.nunique()} controles")
    rows, dyn = [], []
    for y, note in [("pov_rate", "principal"), ("ln_n_poor", "só robustez (efeito em log depende da escala)")]:
        for name, kw in [("CS REG, nunca tratados", dict(control="never")), ("CS REG, ainda não tratados", dict(control="notyet")),
                         ("CS sem covariáveis, nunca tratados", dict(control="never", method="unc"))]:
            r = C.cs(d, y, **kw)
            rows.append({"outcome": y, "estimator": name, "nota": note, **r["row"]})
            dyn.append(r["r"]["dyn"]["table"].assign(outcome=y, estimator=name))
            if y == "pov_rate" and name.startswith("CS REG, nunca"):
                C.plot_es(r["r"]["dyn"]["table"], "Taxa de pobreza extrema (p.p.) — CS REG, onset T1", FIG / "q3_event_study_pov_rate")
                se_real = r["row"]["se"]
                att_real = r["row"]["estimate"]
        rows.append({"outcome": y, "estimator": "DiD empilhada de médias", "nota": note, **C.stacked_means(d, y)})
    for y, lab in [("pov_rate_obs", "pov_rate_survey_only"), ("mpi_headcount", "mpi_headcount")]:
        o, info, nobs = rob.observed_blocks(d, y)
        rows.append({"outcome": lab, "estimator": "CS sem X, blocos de 3 anos, desbalanceado", **o,
                     "n_treated": info["n_treated"], "nota": f"{nobs} unidade-blocos com dado"})
    ld, pairs = long_differences(d)
    rows.append({"outcome": "pov_rate_survey_only", "estimator": "Diferenças longas entre pesquisas", **ld,
                 "nota": "Δ entre última pesquisa pré e primeira pós; controles com intervalo comparável"})
    pairs.to_csv(TAB / "poverty_long_differences_pairs.csv", index=False)
    # mecanismos demográficos (amostra completa de onset, sem exigir pesquisas)
    dm = C.onset_sample(p)
    for y in ["refugees_origin_pc", "idp_stock_pc", "idp_new_pc"]:
        rows.append({"outcome": y, "estimator": "DiD empilhada de médias (mecanismo)", "nota": "por 100 mil hab.",
                     **C.stacked_means(dm, y)})
    res = pd.DataFrame(rows)
    res.to_csv(TAB / "poverty_effects.csv", index=False)
    pd.concat(dyn).to_csv(TAB / "poverty_event_study.csv", index=False)
    print(res[["outcome", "estimator", "estimate", "se", "p_value", "n_treated"]].round(3).to_string(index=False))

    # WAOSS lineup × só pesquisa
    w = []
    for y in ["pov_rate", "pov_rate_obs"]:
        r = C.waoss(p[p.in_pip == 1], y)
        w.append({"outcome": y, **r})
        print(f"  WAOSS {y}: θ = {r['efeito_all']:.3f} (EP {r['efeito_se_all']:.3f}); escalada {r['efeito_up']:.3f} "
              f"(EP {r['efeito_se_up']:.3f}); placebo escalada {r['placebo_up']:.3f} (EP {r['placebo_se_up']:.3f}); n_sw {r['efeito_n_sw']}")
    pd.DataFrame(w).to_csv(TAB / "poverty_waoss_lineup_vs_survey.csv", index=False)

    # MDE
    curve, summ = mde(d, se_real)
    curve.to_csv(TAB / "mde_power_curve.csv", index=False)
    pt = pd.read_csv(TAB / "passthrough.csv").set_index("variante")
    summ.update({"att_estimado": att_real, "passthrough_att_agregado": float(pt.loc["ATT agregado", "delta_pp_medio"]),
                 "passthrough_att_coorte": float(pt.loc["ATT da coorte", "delta_pp_medio"])})
    pd.DataFrame([summ]).to_csv(TAB / "mde.csv", index=False)
    print("\nMDE:", {k: round(v, 3) if isinstance(v, float) else v for k, v in summ.items()})

    plot_summary()



def plot_summary() -> None:
    """Figura-síntese: efeito implícito do PIB (04) × MDE × ATT estimado (lê mde.csv e passthrough.csv)."""
    m = pd.read_csv(TAB / "mde.csv").iloc[0]
    pt = pd.read_csv(TAB / "passthrough.csv").set_index("variante").delta_pp_medio
    items = [("Efeito implícito do PIB\n(ATT agregado, CS REG)", pt["ATT agregado"], C.ps.THIRD),
             ("Efeito implícito do PIB\n(ATT sem covariáveis)", pt["ATT agregado sem covariáveis"], C.ps.THIRD),
             ("Efeito implícito do PIB\n(ATT da coorte)", pt["ATT da coorte"], C.ps.THIRD),
             ("ATT estimado na pobreza", m.att_estimado, C.ps.TREATED),
             ("MDE simulado (80%)", m.mde_simulado, C.ps.CONTROL), ("MDE 2,8 × EP real", m.mde_2_8_ep, C.ps.CONTROL)]
    fig, ax = C.ps.plt.subplots(figsize=(6.8, 3.9))
    for k, (lab, v, c) in enumerate(items):
        ax.barh(k, v, color=c, height=0.55)
        ax.text(v, k, f" {v:.2f}".replace(".", ","), va="center", fontsize=8, color=C.ps.INK)
    ax.axvline(0, color=C.ps.INK2, lw=1)
    ax.set_yticks(range(len(items)), [i[0] for i in items], fontsize=8)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=C.ps.GRID)
    ax.set_xlabel("pontos percentuais de pobreza extrema (US$ 3,00/dia)")
    ax.set_title("O que o canal do PIB prevê × o que o desenho consegue detectar", loc="left")
    C.ps.save(fig, FIG / "q3_passthrough_vs_mde")


if __name__ == "__main__":
    main()
