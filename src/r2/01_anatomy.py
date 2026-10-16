"""Rodada 2 — 01: anatomia do apagão estatístico (descritivo central, §6.1).

Saídas (outputs/r2/tables/anatomy_*.csv, figures/anatomy_*.png):
1. por trajetória FCS e por status T1, ano a ano: % de países com pesquisa PIP no ano, média de anos desde a
   última pesquisa e distribuição do estimation_type;
2. ESTATÍSTICA-TÍTULO: % da população pobre estimada (US$ 3,00) que vive em país-anos com pobreza
   extrapolada ou estimada por modelo (estimation_type ∈ {extrapolation, CMD estimation}), global e nos FCS;
   variante "modelada" inclui interpolação (tudo que não é ano de pesquisa). Verificada recomputando do
   arquivo bruto do PIP;
3. excluídos da rodada 1 por falta de pesquisas: quantos são FCS e que parcela da pobreza global representam;
4. SPI e frequência de pesquisas DHS/MICS por trajetória;
5. figura principal: linha do tempo da parcela modelada, FCS × não FCS.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from r2config import FIG, INTERIM, PROCESSED, RAW, ROOT, TAB  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
import plotstyle as ps  # noqa: E402

EXTRAP = ["extrapolation", "CMD estimation"]


def pip_universe() -> pd.DataFrame:
    """Todos os países/territórios do PIP (lineup nacional, 1990–2024) com FCS e T1."""
    pov = pd.read_parquet(INTERIM / "poverty.parquet")
    pov = pov[pov.year.between(1990, 2024)].copy()
    fcs = pd.read_parquet(INTERIM / "r2_fcs.parquet").groupby(["iso3", "year"], as_index=False).fcs_any.max()
    tr = pd.read_parquet(INTERIM / "r2_treatment.parquet")[["iso3", "year", "t1"]]
    traj = pd.read_csv(TAB / "fcs_trajectories.csv").set_index("iso3").trajetoria
    pov = pov.merge(fcs, on=["iso3", "year"], how="left").merge(tr, on=["iso3", "year"], how="left")
    pov["trajetoria"] = pov.iso3.map(traj).fillna("nunca")
    pov["extrap"] = pov.estimation_type.isin(EXTRAP)
    pov["modeled"] = pov.estimation_type != "survey"
    pov["fcs_grp"] = np.where(pov.fcs_any == 1, "FCS no ano", np.where(pov.year >= 2005, "não FCS", "antes das listas"))
    return pov


def title_stat(pov: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (y, grp), d in pd.concat([pov.assign(fcs_grp="global"), pov]).groupby(["year", "fcs_grp"]):
        tot = d.n_poor.sum()
        rows.append({"year": y, "grupo": grp, "n_paises": d.iso3.nunique(), "pobres_milhoes": tot / 1e6,
                     "share_pobres_extrap": d.loc[d.extrap, "n_poor"].sum() / tot,
                     "share_pobres_modelada": d.loc[d.modeled, "n_poor"].sum() / tot,
                     "share_paises_extrap": d.extrap.mean(), "share_paises_survey": (~d.modeled).mean()})
    return pd.DataFrame(rows)


def verify(pov: pd.DataFrame, ts: pd.DataFrame) -> dict:
    """Recalcula a estatística-título direto do CSV bruto do PIP (lineup nacional, mesmos anos)."""
    v = pd.read_csv(RAW / "MANIFEST.csv").query("fonte == 'PIP'").versao.iloc[0]
    raw = pd.read_csv(RAW / f"pip_lineup_3.00_{v}.csv")
    raw = raw[(raw.reporting_level == "national") & raw.reporting_year.between(1990, 2024) & (raw.estimate_type != "nowcast")]
    raw["np"] = raw.headcount * raw.reporting_pop
    chk = raw.groupby("reporting_year").apply(lambda d: d.loc[d.estimation_type.isin(EXTRAP), "np"].sum() / d.np.sum(),
                                              include_groups=False)
    mine = ts[ts.grupo == "global"].set_index("year").share_pobres_extrap
    return {"max_abs_dif": float((chk - mine).abs().max()), "anos": len(chk)}


def r1_excluded(pov: pd.DataFrame) -> pd.DataFrame:
    e = pd.read_csv(ROOT / "outputs" / "tables" / "excluded_countries.csv")
    e["grupo"] = np.where(e.motivo.str.startswith("onset(s) sem"), "sem pesquisas pré-onset",
                          np.where(e.motivo.str.startswith("sempre"), "sempre tratado", "não soberano"))
    ever_fcs = set(pd.read_parquet(INTERIM / "r2_fcs.parquet").query("fcs_any == 1").iso3)
    rows = []
    for g, d in e.groupby("grupo"):
        isos = set(d.iso3)
        sub = pov[pov.iso3.isin(isos)]
        share = sub.groupby("year").n_poor.sum() / pov.groupby("year").n_poor.sum()
        rows.append({"grupo_excluido_r1": g, "n_paises": len(isos), "n_fcs_alguma_vez": len(isos & ever_fcs),
                     "paises_fcs": " ".join(sorted(isos & ever_fcs)),
                     "share_pobreza_global_2024": float(share.get(2024, np.nan)),
                     "share_pobreza_global_media_2010_2024": float(share.loc[2010:2024].mean()),
                     "share_pais_anos_extrap": float(sub.extrap.mean())})
    return pd.DataFrame(rows)


def by_group(p: pd.DataFrame, col: str) -> pd.DataFrame:
    d = p[p.in_pip == 1]
    g = d.groupby([col, "year"]).agg(n_paises=("iso3", "nunique"), share_survey_pip=("survey_pip", "mean"),
                                    share_survey_any=("survey_any", "mean"), anos_desde_pesquisa=("years_since_survey", "mean"),
                                    share_extrap=("share_extrapolated", "mean"), share_modelada=("modeled_any", "mean"),
                                    spi=("spi", "mean"), dhs=("survey_dhs", "mean"), mics=("survey_mics", "mean")).reset_index()
    return g.rename(columns={col: "grupo"})


def main() -> None:
    pov = pip_universe()
    ts = title_stat(pov)
    ts.to_csv(TAB / "anatomy_title_stat.csv", index=False)
    # resumo: janela 2005–2019 (antes de a defasagem das pesquisas recentes elevar a extrapolação em todos os
    # países) e último ano; média ponderada pelos pobres de cada ano
    rows = []
    for lab, yrs in [("2005-2019", range(2005, 2020)), ("2020-2024", range(2020, 2025)), ("2024", [2024])]:
        for grp in ["global", "FCS no ano", "não FCS"]:
            t = ts[(ts.grupo == grp) & ts.year.isin(yrs)]
            w = t.pobres_milhoes
            rows.append({"periodo": lab, "grupo": grp, "share_pobres_extrap": float((t.share_pobres_extrap * w).sum() / w.sum()),
                         "share_pobres_modelada": float((t.share_pobres_modelada * w).sum() / w.sum()),
                         "pobres_milhoes_medio": float(w.mean())})
    summ_ts = pd.DataFrame(rows)
    fcs_share = (ts[ts.grupo == "FCS no ano"].set_index("year").pobres_milhoes / ts[ts.grupo == "global"].set_index("year").pobres_milhoes)
    summ_ts["share_dos_pobres_mundiais_em_FCS"] = [float(fcs_share.loc[[y for y in (range(2005, 2020) if r.periodo == "2005-2019" else range(2020, 2025) if r.periodo == "2020-2024" else [2024])]].mean())
                                                    for r in summ_ts.itertuples()]
    summ_ts.to_csv(TAB / "anatomy_title_summary.csv", index=False)
    chk = verify(pov, ts)
    pd.DataFrame([chk]).to_csv(TAB / "anatomy_title_stat_check.csv", index=False)
    assert chk["max_abs_dif"] < 1e-9, chk

    p = pd.read_parquet(PROCESSED / "r2_panel.parquet")
    p["t1_status_ano"] = np.where(p.t1.fillna(False), "em conflito T1", "fora de conflito T1")
    traj = by_group(p, "trajetoria")
    t1 = by_group(p, "t1_status_ano")
    traj.to_csv(TAB / "anatomy_by_trajectory.csv", index=False)
    t1.to_csv(TAB / "anatomy_by_t1.csv", index=False)
    et = pd.crosstab([p.trajetoria], p.estimation_type, normalize="index")
    et.to_csv(TAB / "anatomy_estimation_type_by_trajectory.csv")
    summ = p[p.in_pip == 1].groupby("trajetoria").agg(
        n_paises=("iso3", "nunique"), share_survey_pip=("survey_pip", "mean"), share_survey_any=("survey_any", "mean"),
        anos_desde_pesquisa=("years_since_survey", "mean"), share_extrap=("share_extrapolated", "mean"),
        spi_medio=("spi", "mean"), dhs_por_decada=("survey_dhs", lambda s: 10 * s.mean()),
        mics_por_decada=("survey_mics", lambda s: 10 * s.mean())).reset_index()
    summ.to_csv(TAB / "anatomy_summary_by_trajectory.csv", index=False)
    exc = r1_excluded(pov)
    exc.to_csv(TAB / "anatomy_r1_excluded.csv", index=False)

    # figura principal
    fig, ax = ps.plt.subplots(figsize=(6.8, 4.0))
    for grp, c, lab in [("FCS no ano", ps.CONTROL, "Países na lista FCS no ano"), ("não FCS", ps.TREATED, "Demais países"),
                        ("global", ps.INK2, "Global")]:
        t = ts[(ts.grupo == grp) & (ts.year >= 2005)].sort_values("year")
        ax.plot(t.year, 100 * t.share_pobres_extrap, color=c, lw=2.2 if grp != "global" else 1.4,
                ls="-" if grp != "global" else "--", label=lab)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% dos pobres estimados (US$ 3,00/dia)")
    ax.set_title("Pobreza extrapolada ou estimada por modelo, 2005–2024", loc="left")
    ax.legend(fontsize=8, loc="upper left")
    ps.save(fig, FIG / "anatomy_modeled_poverty_timeline")
    fig, ax = ps.plt.subplots(figsize=(6.8, 4.0))
    for g, c in [("cronico", ps.CONTROL), ("entrada", ps.THIRD), ("saida", "#6250d6"), ("nunca", ps.TREATED)]:
        t = traj[traj.grupo == g].sort_values("year")
        ax.plot(t.year, 100 * t.share_survey_pip.rolling(3, min_periods=1).mean(), color=c, label=g)
    ax.set_ylabel("% dos países com pesquisa PIP no ano (média móvel 3 anos)")
    ax.set_title("Frequência de pesquisas domiciliares por trajetória FCS", loc="left")
    ax.legend(fontsize=8)
    ps.save(fig, FIG / "anatomy_survey_by_trajectory")

    g24 = ts[(ts.year == 2024)].set_index("grupo")
    print(f"ESTATÍSTICA-TÍTULO (2024): {100 * g24.loc['global', 'share_pobres_extrap']:.1f}% dos pobres estimados no mundo "
          f"vivem em país-anos com pobreza extrapolada/modelada; nos FCS: {100 * g24.loc['FCS no ano', 'share_pobres_extrap']:.1f}%; "
          f"fora dos FCS: {100 * g24.loc['não FCS', 'share_pobres_extrap']:.1f}%")
    print(f"   incluindo interpolação: global {100 * g24.loc['global', 'share_pobres_modelada']:.1f}%, "
          f"FCS {100 * g24.loc['FCS no ano', 'share_pobres_modelada']:.1f}%")
    print(f"   verificação contra o CSV bruto do PIP: dif. máx = {chk['max_abs_dif']:.1e} em {chk['anos']} anos")
    print("\nResumo por trajetória:\n" + summ.round(3).to_string(index=False))
    print("\nExcluídos da rodada 1:\n" + exc.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
