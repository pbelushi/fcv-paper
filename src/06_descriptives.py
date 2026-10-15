"""Etapa 06 — descritivas e diagnóstico de seleção por dados faltantes.

Saídas (outputs/tables, outputs/figures):
- cohort_summary.csv: nº de países por coorte, tipo e intensidade no onset.
- pretreatment_balance.csv: médias pré-tratamento, tratados x nunca tratados, teste t (Welch).
- raw_means_reltime.csv + fig raw_means_{pov_rate,ln_n_poor}.png.
- missing_survey_prepost.csv: proporção de anos com pesquisa observada antes/depois de g,
  tratados x controles nos mesmos anos-calendário.
- missing_survey_regression.csv: LPM flag_observed_survey ~ post | país + ano.
- estimation_type_by_period.csv: composição do dado de pobreza (pesquisa/interpolação/...).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyfixest as pf
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import plotstyle as ps  # noqa: E402
from config import FIGURES, PROCESSED, TABLES  # noqa: E402

WIN = 5  # janela pré/pós para o diagnóstico de missing


def load() -> pd.DataFrame:
    p = pd.read_parquet(PROCESSED / "panel.parquet")
    return p[p.status.isin(["tratado", "nunca_tratado"])].copy()


def cohort_summary(p: pd.DataFrame) -> pd.DataFrame:
    c = p[p.treated == 1].drop_duplicates("iso3")
    out = c.groupby("g").agg(n_paises=("iso3", "size"), paises=("iso3", lambda s: " ".join(sorted(s))),
                             n_intraestatal=("onset_type", lambda s: (s == "intraestatal").sum()),
                             n_interestatal=("onset_type", lambda s: (s == "interestatal").sum()),
                             n_guerra_onset=("onset_war", "sum"),
                             brd_pc_onset3_media=("brd_pc_onset3", "mean")).reset_index()
    out.to_csv(TABLES / "cohort_summary.csv", index=False)
    return out


def balance(p: pd.DataFrame) -> pd.DataFrame:
    """Médias pré: tratados em g-5..g-1; nunca tratados na amostra toda (por país, depois entre países)."""
    vars_ = ["pov_rate", "ln_n_poor", "mean", "ln_gdppc", "urban_share", "ln_pop", "trade_gdp",
             "flag_observed_survey", "wgi_va"]
    pre = p[(p.treated == 0) | ((p.year >= p.g - WIN) & (p.year < p.g))]
    by_c = pre.groupby(["iso3", "treated"])[vars_].mean().reset_index()
    rows = []
    for v in vars_:
        t = by_c.loc[by_c.treated == 1, v].dropna()
        c = by_c.loc[by_c.treated == 0, v].dropna()
        test = stats.ttest_ind(t, c, equal_var=False)
        rows.append({"variavel": v, "media_tratados": t.mean(), "n_tratados": len(t),
                     "media_nunca_tratados": c.mean(), "n_nunca_tratados": len(c),
                     "diferenca": t.mean() - c.mean(), "p_valor": test.pvalue})
    out = pd.DataFrame(rows)
    out.to_csv(TABLES / "pretreatment_balance.csv", index=False)
    return out


def raw_means(p: pd.DataFrame) -> pd.DataFrame:
    """Média dos tratados por tempo relativo vs. média dos nunca tratados nos mesmos anos-calendário."""
    ctrl_year = p[p.treated == 0].groupby("year")[["pov_rate", "ln_n_poor"]].mean().add_suffix("_ctrl")
    tr = p[(p.treated == 1) & p.rel_time.between(-10, 10)].join(ctrl_year, on="year")
    out = tr.groupby("rel_time").agg(
        n=("iso3", "nunique"),
        pov_rate_tratados=("pov_rate", "mean"), pov_rate_controles=("pov_rate_ctrl", "mean"),
        ln_n_poor_tratados=("ln_n_poor", "mean"), ln_n_poor_controles=("ln_n_poor_ctrl", "mean"),
    ).reset_index()
    out.to_csv(TABLES / "raw_means_reltime.csv", index=False)
    labels = {"pov_rate": "Taxa de pobreza extrema (%, US$ 3,00/dia)",
              "ln_n_poor": "log do número de pobres (US$ 3,00/dia)"}
    for v, lab in labels.items():
        fig, ax = ps.plt.subplots(figsize=(6.5, 3.8))
        ax.plot(out.rel_time, out[f"{v}_tratados"], color=ps.TREATED, marker="o", label="Tratados (onset em t = 0)")
        ax.plot(out.rel_time, out[f"{v}_controles"], color=ps.CONTROL, marker="o",
                label="Nunca tratados, mesmos anos-calendário")
        ax.axvline(-0.5, color=ps.INK2, lw=1, ls="--")
        ax.set_xlabel("Anos desde o início do conflito")
        ps.int_xaxis(ax)
        ax.set_title(lab, loc="left")
        ax.legend(loc="best", fontsize=9)
        ps.save(fig, FIGURES / f"raw_means_{v}")
    return out


def missing_prepost(p: pd.DataFrame) -> pd.DataFrame:
    """Para cada tratado: % de anos com pesquisa em [g-5,g-1] e [g,g+5]; controles nos mesmos anos."""
    ctrl_year = p[p.treated == 0].groupby("year").flag_observed_survey.mean()
    rows = []
    for iso, d in p[p.treated == 1].groupby("iso3"):
        g = d.g.iloc[0]
        for per, lo, hi in [("pre", g - WIN, g - 1), ("pos", g, g + WIN)]:
            w = d[d.year.between(lo, hi)]
            if len(w):
                rows.append({"iso3": iso, "g": g, "periodo": per, "anos": len(w),
                             "obs_tratado": w.flag_observed_survey.mean(),
                             "obs_controles": ctrl_year.reindex(w.year).mean()})
    byc = pd.DataFrame(rows)
    out = byc.groupby("periodo")[["obs_tratado", "obs_controles"]].mean()
    out["n_tratados"] = byc.groupby("periodo").iso3.nunique()
    out = out.loc[["pre", "pos"]].reset_index()
    out.to_csv(TABLES / "missing_survey_prepost.csv", index=False)
    byc.to_csv(TABLES / "missing_survey_prepost_by_country.csv", index=False)
    return out


def missing_regression(p: pd.DataFrame) -> pd.DataFrame:
    d = p.assign(flag=p.flag_observed_survey.astype(float))
    m1 = pf.feols("flag ~ post | iso3 + year", data=d, vcov={"CRV1": "iso3"})
    # versão dinâmica: binned rel_time, referência -1, nunca tratados = referência
    d["rt"] = d.rel_time.clip(-6, 6).fillna(-1).astype(int)
    m2 = pf.feols("flag ~ i(rt, ref=-1) | iso3 + year", data=d, vcov={"CRV1": "iso3"})
    t1 = m1.tidy().reset_index().assign(modelo="estatico")
    t2 = m2.tidy().reset_index().assign(modelo="dinamico")
    out = pd.concat([t1, t2])
    out.to_csv(TABLES / "missing_survey_regression.csv", index=False)
    # figura
    t2 = t2[t2.Coefficient.str.startswith("rt")].copy()
    t2["e"] = t2.Coefficient.str.extract(r"::(-?\d+)").astype(int)
    t2 = pd.concat([t2, pd.DataFrame({"e": [-1], "Estimate": [0.0], "2.5%": [0.0], "97.5%": [0.0]})]).sort_values("e")
    fig, ax = ps.plt.subplots(figsize=(6.5, 3.6))
    ax.axhline(0, color=ps.INK2, lw=1)
    ax.axvline(-0.5, color=ps.INK2, lw=1, ls="--")
    ax.fill_between(t2.e, t2["2.5%"], t2["97.5%"], color=ps.TREATED, alpha=0.18, lw=0)
    ax.plot(t2.e, t2.Estimate, color=ps.TREATED, marker="o")
    ax.set_xlabel("Anos desde o início do conflito (extremos agrupados em ±6)")
    ps.int_xaxis(ax)
    ax.set_title("Probabilidade de haver pesquisa domiciliar (LPM, IC 95%)", loc="left")
    ps.save(fig, FIGURES / "missing_survey_event_study")
    return out


def estimation_type(p: pd.DataFrame) -> pd.DataFrame:
    tr = p[p.treated == 1].copy()
    tr["periodo"] = np.where(tr.rel_time < 0, "pre", "pos")
    out = pd.crosstab(tr.periodo, tr.estimation_type, normalize="index").loc[["pre", "pos"]]
    out.to_csv(TABLES / "estimation_type_by_period.csv")
    return out


def main() -> None:
    p = load()
    print(f"Amostra de estimação: {p.iso3.nunique()} países ({p[p.treated == 1].iso3.nunique()} tratados, "
          f"{p[p.treated == 0].iso3.nunique()} nunca tratados), {p.year.min()}-{p.year.max()}, {len(p)} país-anos")
    print("\n1. Coortes:\n" + cohort_summary(p).drop(columns="paises").to_string(index=False))
    print("\n3. Balanço pré-tratamento:\n" + balance(p).round(3).to_string(index=False))
    rm = raw_means(p)
    print(f"\n4. Médias brutas em tempo relativo salvas (n tratados por e: {rm.n.min()}-{rm.n.max()})")
    print("\n5. DIAGNÓSTICO DE MISSING")
    print(missing_prepost(p).round(3).to_string(index=False))
    reg = missing_regression(p)
    st = reg[reg.modelo == "estatico"].iloc[0]
    print(f"   LPM flag_observed_survey ~ post | país + ano: coef = {st.Estimate:.3f} "
          f"(EP {st['Std. Error']:.3f}, p = {st['Pr(>|t|)']:.3f})")
    print("   Composição do dado de pobreza nos tratados:\n" + estimation_type(p).round(3).to_string())
    print("\nMissings (amostra de estimação):\n" + p[["pov_rate", "ln_n_poor", "ln_gdppc_pre",
                                                         "urban_share_pre", "trade_gdp_pre"]].isna().sum().to_string())


if __name__ == "__main__":
    main()
