"""Rodada 2 — d3: definições de tratamento T1 (padrão FCS, UCDP-only), T2 (status FCS), T3 (contínuo).

T1 (critérios UCDP da metodologia FCS FY20–26, limiares lidos de fcs_thresholds_used.csv):
- mortes D = total de violência organizada no território (UCDP CY: state-based + non-state + one-sided);
  variante "sb" = só state-based. pc = D por 100 mil hab. (população WDI SP.POP.TOTL).
- alta: D > 150 e pc > 10; média: D > 150 e 1 ≤ pc ≤ 10; deterioração rápida: 0,5 ≤ pc < 1 e D_t > 2·D_{t−1}.
- regra própria (não consta das notas): descarta o país-ano em que > 75% das mortes do GED ocorreram numa
  janela de 3 dias (mortes de eventos multi-dia distribuídas entre date_start e date_end).
- t1_source = "ucdp_only" (sem ACLED; credenciais pendentes).
Onset: 1º ano em T1 após ≥ PEACE_WINDOW anos fora; mortes só existem desde 1989 → onset ≥ 1989 + PW.
Controles: nunca T1 (1989–2025) e nunca FCS (FY06–FY27); variante: nunca T1 e nunca FCS por conflito
(reinclui países só com fragilidade institucional). T2 só para descritivas e Q2 (circularidade do CPIA).
"""
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from r2config import (CONC_DAYS, CONC_SHARE, INTERIM, PEACE_WINDOW, PEACE_WINDOWS, RAW, ROOT,  # noqa: E402
                      SAMPLE_END, TAB)

GED_FIRST, LAST = 1989, 2025


def thresholds() -> dict:
    t = pd.read_csv(TAB / "fcs_thresholds_used.csv")
    u = t[(t.metodologia == "FY20-26") & t.fonte_dados.str.contains("UCDP")].set_index("criterio").valor
    return {"abs": float(u["alta: mortes absolutas >"]), "high_pc": float(u["alta: mortes per capita >"]),
            "med_lo": float(u["media: per capita entre (min)"]), "med_hi": float(u["media: per capita entre (max)"]),
            "det_lo": float(u["deterioracao rapida: per capita entre (min)"]),
            "det_hi": float(u["deterioracao rapida: per capita entre (max)"]),
            "det_ratio": float(u["deterioracao rapida: mortes mais que dobram no ano"])}


def gw_map() -> pd.DataFrame:
    return pd.read_csv(ROOT / "outputs" / "tables" / "gw_iso3_mapping.csv")[["gwno", "iso3"]].dropna()


def population() -> pd.DataFrame:
    w = pd.read_csv(RAW / "wdi_controls.csv")
    w = w[(w.indicator == "SP.POP.TOTL") & (w.iso3.str.len() == 3)]
    return w.rename(columns={"value": "pop"})[["iso3", "year", "pop"]]


def deaths() -> pd.DataFrame:
    cy = pd.read_csv(zipfile.ZipFile(RAW / "organizedviolencecy-261-csv.zip").open("OrganizedViolenceCYDataSet26_1.csv"))
    cy = cy.merge(gw_map(), left_on="country_id", right_on="gwno", how="inner")
    cy["d_total"] = cy[["sb_total_deaths_best", "ns_total_deaths_best", "os_total_deaths_best"]].sum(axis=1)
    cy["d_sb"] = cy.sb_total_deaths_best
    return cy.groupby(["iso3", "year"], as_index=False)[["d_total", "d_sb"]].sum()


def concentrated() -> pd.DataFrame:
    """País-anos com > CONC_SHARE das mortes do ano (GED) numa janela de CONC_DAYS dias."""
    g = pd.read_csv(zipfile.ZipFile(RAW / "ged261-csv.zip").open("GEDEvent_v26_1.csv"),
                    usecols=["year", "type_of_violence", "country_id", "date_start", "date_end", "best"])
    g = g.merge(gw_map(), left_on="country_id", right_on="gwno", how="inner")
    g = g[g.best > 0]
    g["d0"] = pd.to_datetime(g.date_start.str[:10])
    g["d1"] = pd.to_datetime(g.date_end.str[:10]).clip(lower=g.d0)
    rows = []
    for (iso, yr), d in g.groupby(["iso3", "year"]):
        tot = d.best.sum()
        # eventos agregados do GED (intervalos de dias/meses) têm as mortes distribuídas igualmente
        # entre date_start e date_end; só eventos de um dia concentram mortes num único dia
        start, end = d.d0.min(), d.d1.max()
        idx = pd.date_range(start, end)
        daily = np.zeros(len(idx))
        for a, b, v in zip((d.d0 - start).dt.days, (d.d1 - start).dt.days, d.best):
            daily[a:b + 1] += v / (b - a + 1)
        daily = pd.Series(daily, index=idx)
        mx = daily.rolling(CONC_DAYS, min_periods=1).sum().max()
        rows.append({"iso3": iso, "year": yr, "ged_deaths": tot, "max_3d": mx, "share_3d": mx / tot})
    return pd.DataFrame(rows)


def classify(d: pd.DataFrame, col: str, thr: dict, drop_conc: pd.Series | None) -> pd.DataFrame:
    x = d.copy()
    D, pc = x[col], 1e5 * x[col] / x["pop"]
    prev = x.groupby("iso3")[col].shift(1)
    x[f"pc_{col}"] = pc
    x["high"] = (D > thr["abs"]) & (pc > thr["high_pc"])
    x["medium"] = (D > thr["abs"]) & (pc >= thr["med_lo"]) & (pc <= thr["med_hi"])
    x["rapid"] = (pc >= thr["det_lo"]) & (pc < thr["det_hi"]) & (D > thr["det_ratio"] * prev.fillna(0)) & (prev > 0)
    x["t1"] = x.high | x.medium | x.rapid
    x["t1_high"] = x.high.copy()
    if drop_conc is not None:
        x.loc[drop_conc.reindex(x.index, fill_value=False), ["t1", "t1_high"]] = False
    return x


def onsets(x: pd.DataFrame, var: str, pw: int) -> pd.Series:
    """1º ano com var após ≥ pw anos fora (anos anteriores a 1989 não observados)."""
    out = {}
    for iso, d in x.sort_values("year").groupby("iso3"):
        s = d.set_index("year")[var].astype(int).reindex(range(GED_FIRST, LAST + 1), fill_value=0)
        for y in range(GED_FIRST + pw, SAMPLE_END + 1):
            if s[y] == 1 and s.loc[y - pw:y - 1].sum() == 0:
                out[iso] = y
                break
    return pd.Series(out, name="g")


def main() -> None:
    thr = thresholds()
    pop = population()
    d = deaths()
    isos = sorted(set(gw_map().iso3))
    grid = pd.MultiIndex.from_product([isos, range(GED_FIRST, LAST + 1)], names=["iso3", "year"]).to_frame(index=False)
    x = grid.merge(d, on=["iso3", "year"], how="left").merge(pop, on=["iso3", "year"], how="left")
    x[["d_total", "d_sb"]] = x[["d_total", "d_sb"]].fillna(0)
    no_pop = sorted(x[x["pop"].isna()].iso3.unique())
    x = x.dropna(subset=["pop"]).reset_index(drop=True)

    conc = concentrated()
    conc["descartado"] = conc.share_3d > CONC_SHARE
    keyed = x.merge(conc[["iso3", "year", "descartado", "share_3d"]], on=["iso3", "year"], how="left")
    drop = keyed.descartado.fillna(False).astype(bool)

    main_x = classify(x, "d_total", thr, drop)
    pre_conc = classify(x, "d_total", thr, None)
    sb_x = classify(x, "d_sb", thr, drop)
    dropped = keyed[drop & pre_conc.t1].assign(d_total=pre_conc.d_total[drop & pre_conc.t1])
    dropped[["iso3", "year", "d_total", "share_3d"]].to_csv(TAB / "concentrated_events_dropped.csv", index=False)

    fcs = pd.read_parquet(INTERIM / "r2_fcs.parquet")
    ever_fcs = set(fcs[fcs.fcs_any == 1].iso3)
    ever_fcs_conf = set(fcs[fcs.fcs_conflict == 1].iso3)

    out = main_x[["iso3", "year", "pop", "d_total", "d_sb", "pc_d_total", "high", "medium", "rapid", "t1", "t1_high"]].copy()
    out["pc_d_sb"] = sb_x.pc_d_sb
    out["t1_sb"] = sb_x.t1
    out["t1_noconc"] = pre_conc.t1
    out["t1_source"] = "ucdp_only"
    out["t3_asinh"] = np.arcsinh(out.pc_d_total)
    out["t3_band"] = np.select([out.high, out.medium | out.rapid], ["alta", "media"], "abaixo_de_media")

    ever_t1 = set(out[out.t1].iso3)
    status_rows = []
    variants = {}
    for var, lab in [("t1", "main"), ("t1_high", "high"), ("t1_sb", "sb"), ("t1_noconc", "noconc")]:
        for pw in PEACE_WINDOWS:
            if lab != "main" and pw != PEACE_WINDOW:
                continue
            g = onsets(out, var, pw)
            tag = f"g_{lab}_pw{pw}"
            variants[tag] = g
            ever = set(out[out[var]].iso3)
            for iso in isos:
                if iso in no_pop:
                    continue
                if iso in g.index:
                    st = "tratado"
                elif iso in ever:
                    st = "excluido_sempre_tratado"
                elif iso in ever_fcs:
                    st = "fora_controle_fcs" if iso not in ever_fcs_conf else "fora_controle_fcs_conflito"
                else:
                    st = "nunca_tratado"
                status_rows.append({"spec": tag, "iso3": iso, "g": g.get(iso, np.nan), "status": st})
    status = pd.DataFrame(status_rows)
    status.to_csv(TAB / "t1_status_all_specs.csv", index=False)
    main_st = status[status.spec == f"g_main_pw{PEACE_WINDOW}"].set_index("iso3")
    out = out.merge(main_st[["g", "status"]].rename(columns={"g": "g_t1", "status": "status_t1"}),
                    left_on="iso3", right_index=True, how="left")
    for tag, g in variants.items():
        out[tag] = out.iso3.map(g)
    # controle variante: reinclui quem foi FCS só por fragilidade institucional
    out["ctrl_main"] = (out.status_t1 == "nunca_tratado").astype(int)
    out["ctrl_incl_inst"] = out.status_t1.isin(["nunca_tratado", "fora_controle_fcs"]).astype(int)
    out.to_parquet(INTERIM / "r2_treatment.parquet", index=False)

    # comparação com a rodada 1
    r1 = pd.read_csv(ROOT / "outputs" / "tables" / "treatment_status.csv").set_index("iso3")
    r1t = set(r1[r1.status == "tratado"].index)
    r2t = set(main_st[main_st.status == "tratado"].index)
    comp = pd.DataFrame({"iso3": sorted(r1t | r2t)})
    comp["r1_g"] = comp.iso3.map(r1.g)
    comp["r2_g"] = comp.iso3.map(main_st.g)
    comp["situacao"] = np.select([comp.iso3.isin(r1t & r2t), comp.iso3.isin(r1t)], ["em ambas", "sai na r2"], "entra na r2")
    comp["r2_status"] = comp.iso3.map(main_st.status)
    comp.to_csv(TAB / "treatment_comparison_r1_r2.csv", index=False)
    pd.DataFrame([
        ("mortes", "UCDP CY total de violência organizada (sb+ns+os) no território; variante state-based"),
        ("populacao", "WDI SP.POP.TOTL; países sem população excluídos: " + " ".join(no_pop)),
        ("deterioracao", "sem exigência de mínimo absoluto (a nota não exige); requer mortes no ano anterior > 0"),
        ("eventos concentrados", f"> {CONC_SHARE:.0%} das mortes GED em {CONC_DAYS} dias (eventos multi-dia distribuídos uniformemente) — regra própria"),
        ("onset", f"1º ano T1 após ≥ PW anos fora; mortes desde {GED_FIRST} → onsets a partir de {GED_FIRST}+PW"),
        ("controles", "principal: nunca T1 e nunca FCS; variante: reinclui FCS só por fragilidade institucional"),
        ("PSE", "sem código GW próprio no UCDP (mortes atribuídas a Israel): não pode ser T1"),
    ], columns=["regra", "decisao"]).to_csv(TAB / "t1_decisions.csv", index=False)

    # resumo
    sm = status.groupby(["spec", "status"]).size().unstack(fill_value=0)
    print(f"Países com população: {out.iso3.nunique()}; anos {out.year.min()}–{out.year.max()}; sem população: {no_pop}")
    print(f"País-anos T1 (média+): {int(out.t1.sum())}; alta: {int(out.t1_high.sum())}; "
          f"descartados por eventos concentrados: {len(dropped)}")
    print("Descartados:", " ".join(f"{r.iso3}{r.year}({r.share_3d:.0%})" for r in dropped.itertuples()))
    print("\nStatus por especificação:\n" + sm.to_string())
    tr = main_st[main_st.status == "tratado"].sort_values("g")
    print(f"\nTratados (principal, PW={PEACE_WINDOW}): {len(tr)}\n   " + " ".join(f"{i}{int(g)}" for i, g in tr.g.items()))
    print("\nr1 × r2:", comp.situacao.value_counts().to_dict())
    print("   saem:", " ".join(comp[comp.situacao == "sai na r2"].iso3), "| entram:", " ".join(comp[comp.situacao == "entra na r2"].iso3))
    print("\nMissings:\n" + out[["pop", "d_total", "pc_d_total", "g_t1"]].isna().sum().to_string())


if __name__ == "__main__":
    main()
