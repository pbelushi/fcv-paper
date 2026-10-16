"""Rodada 2 — d4: painel país-ano -> data/processed/r2_panel.parquet.

Universo: países soberanos com código GW e população (d3), 1990–2024.
- Q1: ln_gdppc (WDI NY.GDP.PCAP.PP.KD), gdppc_growth (Δln), gdp_growth (WDI).
- Q2: survey_pip (pesquisa nacional no PIP), survey_dhs, survey_mics, survey_any (qualquer das três),
  years_since_survey (anos desde a última pesquisa PIP, desde 1963), share_extrapolated
  (estimation_type ∈ {extrapolation, CMD estimation}), modeled_any (≠ survey, inclui interpolação), spi.
- Q3: pov_rate, pov_rate_survey_only (= pov_rate_obs), mpi_headcount (OPHI trends harmonizado, ano = fim
  da pesquisa), ln_n_poor (só robustez).
- Mecanismos: refugiados originados (UNHCR COO) e deslocados internos (IDMC, estoque e novos) por 100 mil.
- Heterogeneidade: missão de paz da ONU (IPI 1990–2017/04 + listas DPO), CPIA (IRAI), região, renda.
"""
import json
import re
import sys
from pathlib import Path

import country_converter as coco
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from r2config import INTERIM, PROCESSED, RAW, SAMPLE_END, SAMPLE_START, TAB  # noqa: E402

YEARS = range(SAMPLE_START, SAMPLE_END + 1)
import logging
logging.getLogger("country_converter").setLevel(logging.ERROR)
cc = coco.CountryConverter()


def iso(names):
    out = cc.convert(list(names), to="ISO3", not_found=None)
    return [o if isinstance(o, str) and len(o) == 3 else None for o in (out if isinstance(out, list) else [out])]


def survey_flags() -> pd.DataFrame:
    dhs = pd.DataFrame(json.load(open(RAW / "dhs_surveys.json", encoding="utf-8")))
    dhs = dhs[(dhs.SurveyStatus == "Completed") & dhs.SurveyType.isin(["DHS", "MIS", "AIS"])]
    dhs["iso3"] = iso(dhs.CountryName)
    dhs["year"] = pd.to_numeric(dhs.SurveyYear, errors="coerce")
    mics = pd.DataFrame(json.load(open(RAW / "mics_surveys.json", encoding="utf-8"))).drop_duplicates("id")
    mics = mics[mics.status == "Completed"]
    mics["iso3"] = iso(mics.country)
    rows = []
    for r in mics.itertuples():
        y0 = pd.to_numeric(r.start_year, errors="coerce")
        y1 = pd.to_numeric(r.end_year, errors="coerce")
        if pd.notna(y0):
            for y in range(int(y0), int(y1 if pd.notna(y1) else y0) + 1):
                rows.append((r.iso3, y))
    m = pd.DataFrame(rows, columns=["iso3", "year"]).dropna().drop_duplicates().assign(survey_mics=1)
    d = dhs[["iso3", "year"]].dropna().drop_duplicates().assign(survey_dhs=1)
    unm = {"DHS": sorted(set(dhs[dhs.iso3.isna()].CountryName)), "MICS": sorted(set(mics[mics.iso3.isna()].country))}
    return d.merge(m, on=["iso3", "year"], how="outer"), unm


def pko() -> pd.DataFrame:
    """Presença de operação de paz da ONU por país-ano."""
    ipi = pd.read_csv(RAW / "ipi_pko_mission_level.csv")
    ipi["year"] = ipi.Date.str[:4].astype(int)
    pres = ipi[["Country of Mission ISO-3", "year", "Mission"]].rename(columns={"Country of Mission ISO-3": "iso3"})
    acr_iso = pres.groupby("Mission").iso3.agg(lambda s: s.mode().iloc[0])
    # DPO: missões em curso (página "where we operate") e encerradas com datas (página de operações passadas)
    txt = lambda f: [l.strip() for l in re.sub(r"<[^>]+>", "\n", open(RAW / f, encoding="utf-8", errors="ignore").read()).split("\n") if l.strip()]  # noqa: E731
    cur = txt("dpo_where_we_operate.html")
    current = {l for l in cur if l in set(acr_iso.index)}
    past = txt("dpo_past_operations.html")
    rows = []
    for i, l in enumerate(past[:-1]):
        m = re.match(r"^[A-Z][a-z]{2} (\d{4}) - [A-Z][a-z]{2} (\d{4})$", past[i + 1])
        a = re.search(r"\(([A-Z0-9 ]+)\)\s*$", l)
        if m and a:
            acr = a.group(1).strip()
            code = acr_iso.get(acr) or (iso([l])[0])
            if code:
                rows += [(code, y, acr) for y in range(int(m.group(1)), int(m.group(2)) + 1)]
    for acr in current:
        last = pres[pres.Mission == acr].year.max()
        rows += [(acr_iso[acr], y, acr) for y in range(int(last) + 1, SAMPLE_END + 2)]
    allp = pd.concat([pres, pd.DataFrame(rows, columns=["iso3", "year", "Mission"])]).dropna().drop_duplicates()
    return allp.groupby(["iso3", "year"]).Mission.nunique().rename("pko_n").reset_index()


def mpi() -> pd.DataFrame:
    m = pd.read_csv(RAW / "ophi_global_mpi_trends.csv")
    m = m[m["Admin 1 Name"].isna()].copy()
    m["year"] = pd.to_datetime(m["End Date"]).dt.year
    m = m.rename(columns={"Country ISO3": "iso3", "Headcount Ratio": "mpi_headcount", "Survey": "mpi_survey"})
    return m.groupby(["iso3", "year"], as_index=False).agg(mpi_headcount=("mpi_headcount", "mean"),
                                                          mpi_survey=("mpi_survey", "first"))


def idmc() -> pd.DataFrame:
    d = pd.read_excel(RAW / "idmc_conflict_disasters.xlsx", sheet_name="1_Displacement_data")
    return d.rename(columns={"ISO3": "iso3", "Year": "year", "Conflict Stock Displacement": "idp_stock",
                             "Conflict Internal Displacements": "idp_new"})[["iso3", "year", "idp_stock", "idp_new"]]


def wb_series(path, code) -> pd.DataFrame:
    d = pd.read_csv(path)
    d = d[d.indicator == code].copy()
    d["iso3"] = d.iso3.fillna(d.country_id2)
    return d[d.iso3.str.len() == 3][["iso3", "year", "value"]]


def main() -> None:
    tr = pd.read_parquet(INTERIM / "r2_treatment.parquet")
    tr = tr[tr.year.isin(YEARS)]
    pov = pd.read_parquet(INTERIM / "poverty.parquet")
    raw_svy = pd.read_csv(RAW / f"pip_survey_3.00_{pd.read_csv(RAW / 'MANIFEST.csv').query('fonte == \"PIP\"').versao.iloc[0]}.csv")
    ctrl = pd.read_parquet(INTERIM / "controls.parquet")
    fcs = pd.read_parquet(INTERIM / "r2_fcs.parquet")

    p = tr.merge(pov[["iso3", "year", "pov_rate", "pov_rate_obs", "ln_n_poor", "n_poor", "pop_pip", "estimation_type",
                      "flag_observed_survey", "poverty_gap", "mean"]], on=["iso3", "year"], how="left")
    p = p.merge(ctrl[["iso3", "year", "gdppc_ppp", "gdp_growth", "urban_share", "refugees_origin", "income_group",
                      "region_code", "trade_gdp"]], on=["iso3", "year"], how="left")
    p["in_pip"] = p.iso3.isin(set(pov.iso3)).astype(int)
    p["survey_pip"] = p.flag_observed_survey.fillna(0).astype(int)
    p.loc[p.in_pip == 0, "survey_pip"] = np.nan
    # anos desde a última pesquisa nacional no PIP (histórico completo desde 1963)
    nat = raw_svy[raw_svy.reporting_level == "national"][["country_code", "reporting_year"]].drop_duplicates()
    last = {}
    for iso3, d in nat.groupby("country_code"):
        ys = np.sort(d.reporting_year.unique())
        for y in YEARS:
            prev = ys[ys <= y]
            last[(iso3, y)] = y - prev.max() if len(prev) else np.nan
    p["years_since_survey"] = [last.get((i, y), np.nan) for i, y in zip(p.iso3, p.year)]
    p["share_extrapolated"] = p.estimation_type.isin(["extrapolation", "CMD estimation"]).astype(float)
    p["modeled_any"] = (p.estimation_type != "survey").astype(float)
    p.loc[p.estimation_type.isna(), ["share_extrapolated", "modeled_any"]] = np.nan

    sv, unm = survey_flags()
    p = p.merge(sv, on=["iso3", "year"], how="left")
    p[["survey_dhs", "survey_mics"]] = p[["survey_dhs", "survey_mics"]].fillna(0)
    p["survey_any"] = ((p.survey_pip.fillna(0) + p.survey_dhs + p.survey_mics) > 0).astype(int)

    p = p.merge(wb_series(RAW / "wb_spi.csv", "SPI.INDEX").rename(columns={"value": "spi"}), on=["iso3", "year"], how="left")
    p = p.merge(wb_series(RAW / "wb_cpia.csv", "IQ.CPA.IRAI.XQ").rename(columns={"value": "cpia"}), on=["iso3", "year"], how="left")
    p = p.merge(mpi(), on=["iso3", "year"], how="left").merge(idmc(), on=["iso3", "year"], how="left")
    p = p.merge(pko(), on=["iso3", "year"], how="left")
    p["pko"] = (p.pko_n.fillna(0) > 0).astype(int)
    f = fcs.groupby(["iso3", "year"], as_index=False)[["fcs_any", "fcs_conflict", "fcs_institutional", "fcs_marginal"]].max()
    p = p.merge(f, on=["iso3", "year"], how="left")
    traj = pd.read_csv(TAB / "fcs_trajectories.csv")
    p["trajetoria"] = p.iso3.map(traj.set_index("iso3").trajetoria).fillna("nunca")
    p.loc[p.year >= 2005, "fcs_any"] = p.loc[p.year >= 2005, "fcs_any"].fillna(0)

    p["ln_gdppc"] = np.log(p.gdppc_ppp)
    p = p.sort_values(["iso3", "year"])
    p["gdppc_growth"] = p.groupby("iso3").ln_gdppc.diff().where(p.groupby("iso3").year.diff() == 1)
    for c in ["refugees_origin", "idp_stock", "idp_new"]:
        p[f"{c}_pc"] = 1e5 * p[c] / p["pop"]
    p["ln_pop"] = np.log(p["pop"])
    # covariáveis pré (média g−5..g−1; controles: média da amostra), como na rodada 1
    cov = ["ln_gdppc", "urban_share", "ln_pop"]
    pre_mask = np.where(p.g_t1.notna(), (p.year >= p.g_t1 - 5) & (p.year <= p.g_t1 - 1), True)
    pre = p[pre_mask].groupby("iso3")[cov].mean().add_suffix("_pre")
    p = p.merge(pre, left_on="iso3", right_index=True, how="left")
    for c, src in [("pko_pre", "pko"), ("cpia_pre", "cpia")]:
        w = p[(p.year >= p.g_t1 - 5) & (p.year <= p.g_t1 - 1)].groupby("iso3")[src].max() if c == "pko_pre" else \
            p[(p.year >= p.g_t1 - 5) & (p.year <= p.g_t1 - 1)].groupby("iso3")[src].mean()
        p[c] = p.iso3.map(w)
    ig = p[(p.g_t1.isna()) | (p.year == p.g_t1 - 1)].dropna(subset=["income_group"]).sort_values("year")
    p["income_group_pre"] = p.iso3.map(ig.groupby("iso3").income_group.first())
    p["region_code"] = p.groupby("iso3").region_code.transform(lambda s: s.ffill().bfill())
    p.to_parquet(PROCESSED / "r2_panel.parquet", index=False)

    print(f"Painel r2: {p.iso3.nunique()} países, {p.year.min()}–{p.year.max()}, {len(p)} linhas; "
          f"no PIP: {p[p.in_pip == 1].iso3.nunique()}")
    print(f"T1: {p[p.status_t1 == 'tratado'].iso3.nunique()} tratados, {p[p.ctrl_main == 1].iso3.nunique()} controles")
    print("Nomes DHS/MICS sem ISO3:", unm)
    key = ["ln_gdppc", "survey_pip", "survey_any", "years_since_survey", "share_extrapolated", "spi", "cpia", "pov_rate",
           "pov_rate_obs", "mpi_headcount", "refugees_origin_pc", "idp_stock_pc", "pko", "fcs_any", *[c + "_pre" for c in cov]]
    print("Missings (proporção):\n" + p[key].isna().mean().round(3).to_string())
    print("Cobertura: SPI", p.dropna(subset=["spi"]).year.agg(["min", "max"]).tolist(), "| CPIA",
          p.dropna(subset=["cpia"]).year.agg(["min", "max"]).tolist(), "| IDMC", p.dropna(subset=["idp_stock"]).year.agg(["min", "max"]).tolist(),
          "| MPI país-anos", int(p.mpi_headcount.notna().sum()), "| PKO país-anos", int(p.pko.sum()))


if __name__ == "__main__":
    main()
