"""Etapa 10 — Exercício 1: tratamento restrito por intensidade e renda.

Pedido do usuário (2026-10-15): exigir intensidade mínima (ex.: ≥ 1 morte em combate por
100 mil hab.) e excluir países de renda alta.

Especificações (todas sem países classificados como renda alta "H" no período pré):
- limiar_1 (principal): um país-ano só conta como conflito se brd_pc ≥ 1 (1989+; antes de
  1989 usa-se conflict_any do ACD, sem dados de mortes). Onset = 1º ano acima do limiar após
  ≥ PEACE_WINDOW anos abaixo dele; mesmas regras de elegibilidade da etapa 05.
  Controles: nunca tratados da definição principal (nenhum conflito ≥ 25 mortes).
- limiar_1_ctrl_baixa: idem, mas controles = países que nunca atingem o limiar no período
  (inclui conflitos de baixa intensidade).
- limiar_05: limiar de 0,5 por 100 mil.
- filtro_literal: onsets da definição principal com máximo de brd_pc nos 3 primeiros anos ≥ 1.
- limiar_1_com_H: limiar 1 sem excluir renda alta (isola o efeito do corte por renda).
"""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import did_tools as dt  # noqa: E402
import plotstyle as ps  # noqa: E402
from config import FIGURES, INTERIM, PEACE_WINDOW, PROCESSED, SAMPLE_START, TABLES  # noqa: E402

est = importlib.import_module("07_estimate")
build = importlib.import_module("05_build_panel")
rob = importlib.import_module("08_robustness")
OUT = ["pov_rate", "ln_n_poor", "asinh_n_poor", "d_ln_n_poor"]
RAW_COVARS = ["ln_gdppc", "urban_share", "ln_pop"]


def base_panel() -> pd.DataFrame:
    p = pd.read_parquet(PROCESSED / "panel.parquet")
    p = p[~p.motivo.fillna("").str.contains("não soberano")].copy()
    p["poverty_gap"] = 100 * p.poverty_gap
    p["ln_mean"] = np.log(p["mean"])
    return p


def threshold_conflict(th: float) -> pd.DataFrame:
    conf = pd.read_parquet(INTERIM / "conflict_cy.parquet")
    pov = pd.read_parquet(INTERIM / "poverty.parquet")[["iso3", "year", "pop_pip"]]
    c = conf.merge(pov, on=["iso3", "year"], how="left")
    bpc = 1e5 * c.brd / c.pop_pip
    c["conflict_any"] = np.where(c.year >= 1989, (bpc >= th).astype(int), c.conflict_any)
    return c


def with_cohorts(p: pd.DataFrame, status: pd.DataFrame, exclude_high: bool, controls: str = "never_any") -> pd.DataFrame:
    """Aplica novo g/status ao painel e recalcula covariáveis pré (g-5..g-1)."""
    d = p.drop(columns=["g", "treated", "rel_time", "post", *[c + "_pre" for c in RAW_COVARS]], errors="ignore")
    d = d.merge(status[["iso3", "g_new", "status_new"]], on="iso3", how="left")
    if controls == "never_any":          # controles = nunca tratados da definição principal
        keep = (d.status_new == "tratado") | (d.status == "nunca_tratado")
    else:                                 # controles = nunca acima do limiar
        keep = d.status_new.isin(["tratado", "nunca_tratado"])
    d = d[keep].copy()
    d["treated"] = (d.status_new == "tratado").astype(int)
    d["g"] = np.where(d.treated == 1, d.g_new, 0).astype(int)
    if exclude_high:
        ig = d[(d.treated == 0) | (d.year == d.g - 1)].dropna(subset=["income_group"]).sort_values("year")
        ig = ig.groupby("iso3").income_group.first()
        d = d[d.iso3.map(ig) != "H"]
    d["rel_time"] = np.where(d.treated == 1, d.year - d.g, np.nan)
    d["post"] = ((d.treated == 1) & (d.year >= d.g)).astype(int)
    pre_mask = np.where(d.treated == 1, (d.year >= d.g - 5) & (d.year <= d.g - 1), True)
    pre = d[pre_mask].groupby("iso3")[RAW_COVARS].mean().add_suffix("_pre").reset_index()
    return d.merge(pre, on="iso3", how="left")


def specs(p: pd.DataFrame) -> dict:
    pov = pd.read_parquet(INTERIM / "poverty.parquet")
    end = int(pov.year.max())
    out = {}
    for th, tag in [(1.0, "limiar_1"), (0.5, "limiar_05")]:
        st = build.assign_cohort(threshold_conflict(th), pov, "conflict_any", PEACE_WINDOW, end)
        st = st.rename(columns={"g": "g_new", "status": "status_new"})
        out[tag] = with_cohorts(p, st, exclude_high=True)
        if th == 1.0:
            out["limiar_1_ctrl_baixa"] = with_cohorts(p, st, exclude_high=True, controls="below")
            out["limiar_1_com_H"] = with_cohorts(p, st, exclude_high=False)
    # filtro literal sobre os onsets da definição principal
    tr = p[p.treated == 1]
    mx3 = tr[(tr.year >= tr.g) & (tr.year <= tr.g + 2)].groupby("iso3").brd_pc.max()
    st = p.drop_duplicates("iso3")[["iso3", "g", "status"]].rename(columns={"g": "g_new", "status": "status_new"})
    st.loc[(st.status_new == "tratado") & (st.iso3.map(mx3) < 1), "status_new"] = "excluido"
    out["filtro_literal"] = with_cohorts(p, st, exclude_high=True)
    return out


LABELS = {
    "limiar_1": "Limiar ≥ 1/100 mil, sem renda alta (principal)",
    "limiar_1_ctrl_baixa": "Limiar ≥ 1/100 mil, controles = nunca acima do limiar",
    "limiar_05": "Limiar ≥ 0,5/100 mil, sem renda alta",
    "filtro_literal": "Onsets originais com ≥ 1/100 mil nos 3 primeiros anos, sem renda alta",
    "limiar_1_com_H": "Limiar ≥ 1/100 mil, com renda alta",
}


def main() -> None:
    p = base_panel()
    S = specs(p)
    rows, dyn_all, cohorts_all = [], [], []
    for tag, d in S.items():
        tr = d[d.treated == 1].drop_duplicates("iso3")
        cohorts_all.append(tr[["iso3", "g", "region_code", "income_group_pre"]].assign(spec=tag))
        print(f"\n=== {LABELS[tag]}: {tr.iso3.nunique()} tratados, {d[d.treated == 0].iso3.nunique()} controles ===")
        print("   " + " ".join(f"{r.iso3}{r.g}" for r in tr.sort_values("g").itertuples()))
        main_spec = tag == "limiar_1"
        estimators = [("CS (REG, nunca tratados)", dict(control="never", method="reg"))]
        if main_spec:
            estimators += [("CS (REG, ainda não tratados)", dict(control="notyet", method="reg")),
                           ("CS (sem covariáveis, nunca tratados)", dict(control="never", method="unc"))]
        for y in OUT:
            for name, kw in estimators:
                r = est.run_cs(d, y, **kw)
                o, inf = r["simple"]["overall"], r["info"]
                rows.append({"spec": tag, "descricao": LABELS[tag], "outcome": y, "estimator": name,
                             **{k: o[k] for k in ("estimate", "se", "ci_low", "ci_high", "p_value")},
                             "n_treated": inf["n_treated"], "n_units": inf["n_units"],
                             "pretrend_p": inf["pretrend"]["p_value"]})
                dyn_all.append(r["dyn"]["table"].assign(spec=tag, outcome=y, estimator=name))
                print(f"  {y:13s} {name:38s} ATT = {o['estimate']:7.3f} (EP {o['se']:.3f}; p = {o['p_value']:.3f}); "
                      f"n_trat = {inf['n_treated']}; pré-tend. p = {inf['pretrend']['p_value']:.3f}")
                if main_spec and name.startswith("CS (REG, nunca"):
                    est.plot_es(r["dyn"]["table"], f"{est.OUTCOMES.get(y, y)} — limiar ≥ 1/100 mil, sem renda alta",
                                FIGURES / f"ex1_event_study_{y}_cs_never_reg", band=True)
            if main_spec:
                tw, _ = est.run_twfe(d, y)
                sa_dyn, sa_o = dt.sun_abraham(d.dropna(subset=[y]), y, est.MIN_E, est.MAX_E)
                for name, o in [("TWFE", tw), ("Sun-Abraham (IW)", sa_o)]:
                    rows.append({"spec": tag, "descricao": LABELS[tag], "outcome": y, "estimator": name,
                                 **{k: o[k] for k in ("estimate", "se", "ci_low", "ci_high", "p_value")},
                                 "n_treated": tr.iso3.nunique(), "n_units": d.iso3.nunique()})
                    print(f"  {y:13s} {name:38s} ATT = {o['estimate']:7.3f} (EP {o['se']:.3f}; p = {o['p_value']:.3f})")
    res = pd.DataFrame(rows)
    res.to_csv(TABLES / "ex1_intensity_income.csv", index=False)
    pd.concat(dyn_all).to_csv(TABLES / "ex1_event_study.csv", index=False)
    pd.concat(cohorts_all).to_csv(TABLES / "ex1_cohorts.csv", index=False)
    hd = pd.concat([rob.honest_rm(S["limiar_1"], y) for y in ["pov_rate", "ln_n_poor", "asinh_n_poor"]])
    hd.to_csv(TABLES / "ex1_honestdid.csv", index=False)
    print("\nHonestDiD (limiar_1):\n" + hd[hd.M.astype(str).isin(["0", "1", "SD(0): tendência linear extrapolada"])]
          .round(3).to_string(index=False))


if __name__ == "__main__":
    main()
