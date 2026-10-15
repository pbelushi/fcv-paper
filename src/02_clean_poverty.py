"""Etapa 02 — limpeza do PIP -> data/interim/poverty.parquet.

Regras (documentadas em outputs/tables/poverty_decisions.csv):
- Série principal: lineup (fill_gaps=true), reporting_level == "national".
- Anos com estimate_type == "nowcast" (2025-26 na versão 20260922) são excluídos:
  são projeções puramente de modelo, sem pesquisa nem interpolação.
- flag_observed_survey = 1 se há pesquisa nacional (fill_gaps=false) naquele país-ano.
- Série só-observada (survey): quando há renda e consumo no mesmo ano, mantém-se,
  por país, o welfare_type com mais anos de pesquisa (empate -> consumo), fixo no tempo.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import INTERIM, POVLINE, POVLINES_UPPER, RAW, TABLES  # noqa: E402

VERSION = pd.read_csv(RAW / "MANIFEST.csv").query("fonte == 'PIP'").versao.iloc[0]
# gini não é publicado na série lineup -> vem da série observada (gini_obs)
KEEP = ["country_code", "reporting_year", "welfare_type", "headcount", "poverty_gap",
        "poverty_severity", "mean", "reporting_pop", "survey_coverage",
        "estimation_type", "estimate_type"]


def load(kind: str, line: float) -> pd.DataFrame:
    df = pd.read_csv(RAW / f"pip_{kind}_{line:.2f}_{VERSION}.csv")
    return df[df.reporting_level == "national"]


def survey_series(line: float) -> pd.DataFrame:
    s = load("survey", line)
    n_years = s.groupby(["country_code", "welfare_type"]).reporting_year.nunique().reset_index(name="n")
    n_years["prio"] = n_years.n + np.where(n_years.welfare_type == "consumption", 0.5, 0)
    chosen = n_years.sort_values("prio").groupby("country_code").tail(1)[["country_code", "welfare_type"]]
    s = s.merge(chosen, on=["country_code", "welfare_type"])
    # mesmo welfare_type, mesmo ano (ex.: duas rodadas) -> média
    return (s.groupby(["country_code", "reporting_year"], as_index=False)
             .agg(headcount_obs=("headcount", "mean"), gini_obs=("gini", "mean"),
                  mean_obs=("mean", "mean"), welfare_type_obs=("welfare_type", "first")))


def main() -> None:
    decisions = []
    raw_lineup = pd.read_csv(RAW / f"pip_lineup_{POVLINE:.2f}_{VERSION}.csv")
    no_nat = sorted(set(raw_lineup.country_code) - set(raw_lineup.query("reporting_level=='national'").country_code))
    decisions.append(("reporting_level", f"apenas 'national'; países sem série nacional excluídos: {no_nat}"))

    lin = load("lineup", POVLINE)[KEEP].copy()
    nowcast_years = sorted(int(y) for y in lin.loc[lin.estimate_type == "nowcast", "reporting_year"].unique())
    lin = lin[lin.estimate_type != "nowcast"]
    decisions.append(("nowcast", f"anos nowcast excluídos: {nowcast_years}; fim da amostra = {lin.reporting_year.max()}"))

    lin = lin.rename(columns={"country_code": "iso3", "reporting_year": "year", "reporting_pop": "pop_pip"})
    lin["pov_rate"] = 100 * lin.headcount
    lin["n_poor"] = lin.headcount * lin.pop_pip
    lin["ln_n_poor"] = np.log(lin.n_poor.where(lin.n_poor > 0))
    lin["asinh_n_poor"] = np.arcsinh(lin.n_poor)
    lin = lin.sort_values(["iso3", "year"])
    lin["d_ln_n_poor"] = lin.groupby("iso3").ln_n_poor.diff().where(lin.groupby("iso3").year.diff() == 1)

    for line in POVLINES_UPPER:
        up = load("lineup", line)[["country_code", "reporting_year", "headcount"]]
        tag = f"{int(round(line * 100)):03d}"
        up = up.rename(columns={"country_code": "iso3", "reporting_year": "year", "headcount": f"hc_{tag}"})
        lin = lin.merge(up, on=["iso3", "year"], how="left")
        lin[f"pov_rate_{tag}"] = 100 * lin[f"hc_{tag}"]
        lin[f"ln_n_poor_{tag}"] = np.log((lin[f"hc_{tag}"] * lin.pop_pip).where(lambda x: x > 0))
        lin = lin.drop(columns=f"hc_{tag}")

    surv = survey_series(POVLINE).rename(columns={"country_code": "iso3", "reporting_year": "year"})
    lin = lin.merge(surv, on=["iso3", "year"], how="left")
    lin["flag_observed_survey"] = lin.headcount_obs.notna().astype(int)
    lin["pov_rate_obs"] = 100 * lin.headcount_obs
    lin["ln_n_poor_obs"] = np.log((lin.headcount_obs * lin.pop_pip).where(lambda x: x > 0))
    lin = lin.drop(columns=["headcount_obs"])

    switch = lin.groupby("iso3").welfare_type.nunique()
    decisions.append(("welfare_type_lineup", f"{(switch > 1).sum()} países mudam renda/consumo na série lineup (regra do PIP mantida)"))
    decisions.append(("welfare_type_survey", "série observada: welfare_type com mais anos por país (empate -> consumo)"))
    n_zero = int((lin.n_poor == 0).sum())
    decisions.append(("zeros", f"{n_zero} país-anos com n_poor == 0 (ln indefinido; usar asinh_n_poor)"))

    lin.to_parquet(INTERIM / "poverty.parquet", index=False)
    pd.DataFrame(decisions, columns=["regra", "decisao"]).to_csv(TABLES / "poverty_decisions.csv", index=False)

    print(f"PIP versão {VERSION}; linha US$ {POVLINE:.2f}")
    print(f"Países: {lin.iso3.nunique()} | anos: {lin.year.min()}-{lin.year.max()} | linhas: {len(lin)}")
    print(f"País-anos com pesquisa observada: {lin.flag_observed_survey.sum()} ({lin.flag_observed_survey.mean():.1%})")
    print("Missings por variável:\n" + lin.isna().sum()[lambda x: x > 0].to_string())
    print("Decisões:")
    for r, d in decisions:
        print(f"  - {r}: {d}")


if __name__ == "__main__":
    main()
