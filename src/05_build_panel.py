"""Etapa 05 — painel final e definição do tratamento -> data/processed/panel.parquet.

Tratamento (CLAUDE.md §5.3):
- onset = 1º ano com conflict_any == 1 após >= PEACE_WINDOW anos consecutivos sem conflito;
- coorte g = primeiro onset em [SAMPLE_START+1, END_YEAR] com >= MIN_PRE_OBS anos de
  pobreza observada (pesquisa) antes de g (g-1 precisa estar na amostra: período-base);
- nunca tratados: nenhum ano de conflito em [SAMPLE_START - PEACE_WINDOW, END_YEAR];
- demais países: excluídos da estimação principal, com motivo.
Variantes: g_pw3, g_pw10 (outras janelas) e g_war (onset definido por conflict_war).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import (INTERIM, MIN_PRE_OBS, PEACE_WINDOW, PEACE_WINDOWS_ROBUST,  # noqa: E402
                    PROCESSED, SAMPLE_START, TABLES)

COVARS = ["ln_gdppc", "urban_share", "ln_pop", "trade_gdp"]


def onsets(conf: pd.DataFrame, var: str, pw: int) -> pd.DataFrame:
    """Todos os anos de onset (var==1 após pw anos sem var) por país."""
    d = conf.sort_values(["iso3", "year"]).copy()
    prev = d.groupby("iso3")[var].transform(lambda s: s.shift(1).rolling(pw, min_periods=pw).sum())
    # exige que o histórico tenha pw anos observados (painel UCDP começa em 1946)
    d["onset"] = (d[var] == 1) & (prev == 0)
    return d.loc[d.onset, ["iso3", "year"]]


def assign_cohort(conf, pov, var, pw, end_year, start=SAMPLE_START):
    """Retorna DataFrame iso3 -> g, status, motivo."""
    obs_years = pov.loc[pov.flag_observed_survey == 1, ["iso3", "year"]]
    ons = onsets(conf, var, pw)
    ons = ons[(ons.year > start) & (ons.year <= end_year)]
    ons = ons.merge(obs_years.rename(columns={"year": "y_obs"}), on="iso3", how="left")
    ons["pre_obs"] = (ons.y_obs < ons.year).astype(int)
    ons = ons.groupby(["iso3", "year"]).pre_obs.sum().reset_index()
    elig = ons[ons.pre_obs >= MIN_PRE_OBS].sort_values("year").groupby("iso3").head(1)

    rows = []
    window = conf[(conf.year >= start - pw) & (conf.year <= end_year)]
    any_conf = window.groupby("iso3")[var].max()
    any_conf_all = window.groupby("iso3").conflict_any.max()
    first_onset = ons.sort_values("year").groupby("iso3").head(1).set_index("iso3")
    for iso in pov.iso3.unique():
        if iso not in any_conf.index:
            rows.append((iso, np.nan, "excluido", "sem código no sistema GW/UCDP (território não soberano)"))
        elif iso in set(elig.iso3):
            g = int(elig.loc[elig.iso3 == iso, "year"].iloc[0])
            rows.append((iso, g, "tratado", ""))
        elif any_conf_all[iso] == 0:
            rows.append((iso, np.nan, "nunca_tratado", ""))
        elif iso in first_onset.index:
            fo = first_onset.loc[iso]
            rows.append((iso, np.nan, "excluido",
                         f"onset(s) sem {MIN_PRE_OBS} anos de pobreza observada antes (1º onset {int(fo.year)}, {int(fo.pre_obs)} obs.)"))
        elif any_conf[iso] == 0:
            rows.append((iso, np.nan, "excluido", f"conflito menor (não-{var}) no período; sem onset de {var}"))
        else:
            in_start = conf[(conf.iso3 == iso) & (conf.year.between(start - pw, start))][var].max()
            motivo = ("sempre tratado: em conflito no início da amostra, sem janela de paz posterior"
                      if in_start == 1 else "conflito só antes de {} sem onset elegível na amostra".format(start))
            rows.append((iso, np.nan, "excluido", motivo))
    return pd.DataFrame(rows, columns=["iso3", "g", "status", "motivo"])


def main() -> None:
    pov = pd.read_parquet(INTERIM / "poverty.parquet")
    conf = pd.read_parquet(INTERIM / "conflict_cy.parquet")
    ctrl = pd.read_parquet(INTERIM / "controls.parquet")
    nb = pd.read_csv(INTERIM / "neighbors.csv")
    end_year = int(pov.year.max())

    main_c = assign_cohort(conf, pov, "conflict_any", PEACE_WINDOW, end_year)
    variants = {f"g_pw{pw}": assign_cohort(conf, pov, "conflict_any", pw, end_year)
                for pw in PEACE_WINDOWS_ROBUST if pw != PEACE_WINDOW}
    variants["g_war"] = assign_cohort(conf, pov, "conflict_war", PEACE_WINDOW, end_year)

    # ------------------------------------------------------------ painel
    panel = pov[(pov.year >= SAMPLE_START) & (pov.year <= end_year)].copy()
    panel = panel.merge(conf, on=["iso3", "year"], how="left")
    panel = panel.merge(ctrl.drop(columns=["pov_wdi"]), on=["iso3", "year"], how="left")
    panel["brd_pc"] = 1e5 * panel.brd / panel.pop_pip
    panel["deaths_orgvio_pc"] = 1e5 * panel.deaths_orgvio / panel.pop_pip
    panel["ln_gdppc"] = np.log(panel.gdppc_ppp)
    panel["ln_pop"] = np.log(panel.pop_pip)

    panel = panel.merge(main_c, on="iso3", how="left")
    for name, v in variants.items():
        panel = panel.merge(v[["iso3", "g", "status"]].rename(columns={"g": name, "status": f"status_{name[2:]}"}),
                            on="iso3", how="left")
    panel["g"] = panel.g.fillna(0).astype(int)                 # 0 = nunca tratado (convenção do `did`)
    panel["treated"] = (panel.status == "tratado").astype(int)
    panel["rel_time"] = np.where(panel.treated == 1, panel.year - panel.g, np.nan)
    panel["post"] = ((panel.treated == 1) & (panel.year >= panel.g)).astype(int)

    # ------------------------------------------------------------ covariáveis pré-tratamento
    # tratados: média de g-5..g-1; nunca tratados: média da amostra (não expostos ao tratamento)
    lagged = panel[["iso3", "year", "g", "treated", *COVARS]]
    pre_mask = np.where(lagged.treated == 1,
                        (lagged.year >= lagged.g - 5) & (lagged.year <= lagged.g - 1), True)
    pre = lagged[pre_mask].groupby("iso3")[COVARS].mean().add_suffix("_pre").reset_index()
    panel = panel.merge(pre, on="iso3", how="left")
    # região e grupo de renda pré (g-1 para tratados; 1º ano disponível para os demais)
    ig = panel[(panel.treated == 0) | (panel.year == panel.g - 1)].dropna(subset=["income_group"])
    ig = ig.sort_values("year").groupby("iso3").income_group.first().rename("income_group_pre")
    panel = panel.merge(ig, on="iso3", how="left")

    # ------------------------------------------------------------ características do onset (heterogeneidade)
    tr = panel[panel.treated == 1]
    at_g = tr[tr.year == tr.g].set_index("iso3")
    first3 = tr[(tr.year >= tr.g) & (tr.year <= tr.g + 2)].groupby("iso3").brd_pc.mean()
    c_full = conf.merge(main_c[main_c.status == "tratado"][["iso3", "g"]], on="iso3")
    c_full = c_full[c_full.year >= c_full.g].sort_values(["iso3", "year"])
    dur = c_full.groupby("iso3").apply(lambda d: int((d.conflict_any.cumprod()).sum()), include_groups=False)
    onset_info = pd.DataFrame({
        "onset_type": np.where(at_g.any_inter == 1, "interestatal",
                               np.where(at_g.any_intra == 1, "intraestatal", "extrassistêmico")),
        "onset_war": at_g.conflict_war, "brd_pc_onset3": first3, "duration_first_spell": dur,
    }).reset_index().rename(columns={"index": "iso3"})
    # onset "limpo": nenhum conflito em [SAMPLE_START - PEACE_WINDOW, g) (robustez de reincidência)
    prior = c_full[["iso3", "g"]].drop_duplicates().merge(conf, on="iso3")
    prior = prior[(prior.year >= SAMPLE_START - PEACE_WINDOW) & (prior.year < prior.g) & (prior.conflict_any == 1)]
    onset_info["onset_clean"] = (~onset_info.iso3.isin(prior.iso3)).astype(int)
    panel = panel.merge(onset_info, on="iso3", how="left")

    # vizinhos de tratados (para spillovers)
    treated_set = set(main_c.loc[main_c.status == "tratado", "iso3"])
    nb_t = nb[nb.iso3_nb.isin(treated_set)].groupby("iso3").iso3_nb.apply(lambda s: ",".join(sorted(s)))
    panel["neighbor_of_treated"] = panel.iso3.isin(nb_t.index).astype(int)

    panel = panel.sort_values(["iso3", "year"]).reset_index(drop=True)
    panel.to_parquet(PROCESSED / "panel.parquet", index=False)

    # ------------------------------------------------------------ tabelas
    names = pov[["iso3"]].drop_duplicates()
    cohorts = (main_c[main_c.status == "tratado"].merge(onset_info, on="iso3", how="left")
               .merge(panel[["iso3", "region_code"]].drop_duplicates(), on="iso3", how="left")
               .sort_values(["g", "iso3"]))
    cohorts.drop(columns=["status", "motivo"]).to_csv(TABLES / "cohorts.csv", index=False)
    excluded = main_c[main_c.status == "excluido"].sort_values(["motivo", "iso3"])
    excluded.drop(columns=["g", "status"]).to_csv(TABLES / "excluded_countries.csv", index=False)
    main_c.sort_values(["status", "iso3"]).to_csv(TABLES / "treatment_status.csv", index=False)
    var_summary = pd.DataFrame({k: v.status.value_counts() for k, v in {"g (PW=5)": main_c, **variants}.items()})
    var_summary.to_csv(TABLES / "treatment_variants_counts.csv")

    # ------------------------------------------------------------ resumo
    print(f"Painel: {panel.iso3.nunique()} países, {panel.year.min()}-{panel.year.max()}, {len(panel)} linhas")
    print("\nStatus (definição principal, PEACE_WINDOW=5):")
    print(main_c.status.value_counts().to_string())
    print("\nVariantes:\n" + var_summary.fillna(0).astype(int).to_string())
    print("\nCoortes (nº países por g):")
    print(cohorts.groupby("g").iso3.apply(lambda s: f"{len(s):2d}  " + " ".join(s)).to_string())
    print("\nTipo do conflito no onset:", cohorts.onset_type.value_counts().to_dict(),
          "| guerra no onset:", int(cohorts.onset_war.sum()))
    print("\nExcluídos por motivo:")
    excl = excluded.copy()
    excl["motivo_curto"] = excl.motivo.str.replace(r"\(1º onset.*\)", "", regex=True).str.strip()
    print(excl.groupby("motivo_curto").iso3.apply(lambda s: f"{len(s):3d}  " + " ".join(s)).to_string())
    print(f"\nTratados com conflito anterior ao g dentro de [{SAMPLE_START - PEACE_WINDOW}, g): "
          f"{prior.iso3.nunique()} -> {sorted(prior.iso3.unique())}")
    print("\nMissings no painel (variáveis-chave):")
    key = ["pov_rate", "ln_n_poor", "d_ln_n_poor", "flag_observed_survey", "brd_pc", *[c + "_pre" for c in COVARS]]
    print(panel[key].isna().sum().to_string())


if __name__ == "__main__":
    main()
