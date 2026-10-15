"""Etapa 03 — variáveis de conflito país-ano -> data/interim/conflict_cy.parquet.

- Indicadores de conflito (conflict_any, conflict_war, tipo): UCDP/PRIO ACD,
  atribuídos ao país onde o conflito ocorre (gwno_loc); conflitos com várias
  localizações contam para cada país-localização.
- Mortes: UCDP Country-Year Dataset on Organized Violence within Country Borders
  (agregação geográfica do GED; 1989+). brd = mortes state-based no território;
  deaths_orgvio = state-based + non-state + one-sided.
- Painel país-ano completo 1946..último ano UCDP para todo país do sistema GW:
  ausência no ACD = ano sem conflito ativo (codificação do UCDP).
"""
import sys
import zipfile
from pathlib import Path

import country_converter as coco
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import INTERIM, RAW, TABLES  # noqa: E402

# Casos especiais GW -> ISO3 (sucessões de Estado e unificações). Regra: o conflito
# vai para o Estado atual que contém o território na maior parte do período.
GW_MANUAL = {
    260: "DEU", 255: "DEU", 265: "DEU",      # Alemanha Ocidental / unificada / Oriental
    345: "SRB",                             # Iugoslávia / Sérvia e Montenegro / Sérvia
    347: "XKX",                             # Kosovo (código usado pelo PIP/WDI)
    341: "MNE",
    365: "RUS",                             # URSS / Rússia
    625: "SDN", 626: "SSD",                 # Sudão / Sudão do Sul (2011+)
    530: "ETH", 531: "ERI",
    678: "YEM", 679: "YEM", 680: "YEM",     # Iêmen do Norte / unificado / do Sul
    816: "VNM", 817: "VNM",                 # Vietnã / Vietnã do Sul
    751: "IND",                             # Hyderabad
    711: "CHN",                             # Tibete
    713: "TWN",
    315: "CZE", 316: "CZE",                 # Tchecoslováquia / Tchéquia
    860: "TLS",
}


def gw_to_iso3(codes: pd.Series) -> pd.DataFrame:
    uniq = pd.Series(sorted(codes.dropna().astype(int).unique()))
    conv = coco.convert(uniq.tolist(), src="GWcode", to="ISO3", not_found="NOTFOUND")
    out = pd.DataFrame({"gwno": uniq, "iso3": conv})
    out["iso3"] = out.apply(lambda r: GW_MANUAL.get(r.gwno, r.iso3), axis=1)
    out.loc[(out.iso3 == "NOTFOUND") | out.iso3.isna(), "iso3"] = None
    out["metodo"] = np.where(out.gwno.isin(GW_MANUAL), "manual", "country_converter")
    return out


def read_zip(name: str, member: str) -> pd.DataFrame:
    return pd.read_csv(zipfile.ZipFile(RAW / name).open(member))


def main() -> None:
    acd = read_zip("ucdp-prio-acd-261-csv.zip", "UcdpPrioConflict_v26_1.csv")
    cy = read_zip("organizedviolencecy-261-csv.zip", "OrganizedViolenceCYDataSet26_1.csv")
    last_year = int(acd.year.max())

    # ACD: uma linha por conflito-ano-localização
    acd["gwno"] = acd.gwno_loc.astype(str).str.split(",")
    acd = acd.explode("gwno")
    acd["gwno"] = acd.gwno.str.strip().astype(int)
    n_multi = acd.groupby(["conflict_id", "year"]).gwno.transform("size").gt(1).sum()

    mapping = gw_to_iso3(pd.concat([acd.gwno, cy.country_id]))
    unmatched = mapping[mapping.iso3.isna()]
    names = pd.concat([acd[["gwno", "location"]].rename(columns={"location": "nome"}),
                       cy[["country_id", "country"]].rename(columns={"country_id": "gwno", "country": "nome"})])
    names = names.drop_duplicates("gwno")
    mapping.merge(names, on="gwno", how="left").to_csv(TABLES / "gw_iso3_mapping.csv", index=False)
    unmatched.merge(names, on="gwno", how="left").to_csv(TABLES / "unmatched_codes.csv", index=False)

    acd = acd.merge(mapping[["gwno", "iso3"]], on="gwno", how="left").dropna(subset=["iso3"])

    # Regra territorial (decisão do usuário, 2026-10-15): no ACD, a "localização" de um
    # conflito interestatal inclui o território de todo governo participante (ex.: AUS no
    # Iraque 2003). A partir de 1989, um conflito interestatal só conta para o país se houve
    # mortes interestatais state-based no seu território (UCDP CY). Antes de 1989 não há
    # dados de mortes e a localização do ACD é mantida.
    cy_iso = cy.merge(mapping[["gwno", "iso3"]], left_on="country_id", right_on="gwno", how="left")
    inter_d = cy_iso.groupby(["iso3", "year"]).sb_interstate_deaths_best.sum().rename("inter_deaths").reset_index()
    acd = acd.merge(inter_d, on=["iso3", "year"], how="left")
    drop = (acd.type_of_conflict == 2) & (acd.year >= 1989) & (acd.inter_deaths.fillna(0) == 0)
    dropped = acd[drop][["conflict_id", "year", "iso3", "location"]]
    dropped.to_csv(TABLES / "interstate_locations_dropped.csv", index=False)
    acd = acd[~drop]

    acd["intra"] = acd.type_of_conflict.isin([3, 4])
    acd["inter"] = acd.type_of_conflict == 2
    acd["extra"] = acd.type_of_conflict == 1
    acd["internationalized"] = acd.type_of_conflict == 4
    agg = acd.groupby(["iso3", "year"]).agg(
        n_conflicts=("conflict_id", "nunique"),
        conflict_war=("intensity_level", lambda s: int((s == 2).any())),
        any_intra=("intra", "max"), any_inter=("inter", "max"),
        any_extra=("extra", "max"), any_internationalized=("internationalized", "max"),
    ).reset_index()
    agg["conflict_any"] = 1

    # Painel completo: todos os ISO3 conhecidos (ACD + CY) x 1946..last_year
    isos = sorted(set(mapping.iso3.dropna()))
    panel = pd.MultiIndex.from_product([isos, range(1946, last_year + 1)], names=["iso3", "year"]).to_frame(index=False)
    panel = panel.merge(agg, on=["iso3", "year"], how="left")
    fill0 = ["n_conflicts", "conflict_war", "conflict_any", "any_intra", "any_inter",
             "any_extra", "any_internationalized"]
    panel[fill0] = panel[fill0].fillna(0).astype(int)
    panel["conflict_years_cum"] = panel.groupby("iso3").conflict_any.cumsum()

    # Mortes (1989+), por território
    cy = cy.merge(mapping[["gwno", "iso3"]], left_on="country_id", right_on="gwno", how="left")
    deaths = cy.groupby(["iso3", "year"]).agg(
        brd=("sb_total_deaths_best", "sum"),
        deaths_ns=("ns_total_deaths_best", "sum"),
        deaths_os=("os_total_deaths_best", "sum"),
    ).reset_index()
    deaths["deaths_orgvio"] = deaths[["brd", "deaths_ns", "deaths_os"]].sum(axis=1)
    panel = panel.merge(deaths, on=["iso3", "year"], how="left")
    pre = panel.year < 1989
    for c in ["brd", "deaths_ns", "deaths_os", "deaths_orgvio"]:
        panel.loc[~pre, c] = panel.loc[~pre, c].fillna(0)   # CY cobre todos os países 1989+
    panel.to_parquet(INTERIM / "conflict_cy.parquet", index=False)

    print(f"UCDP ACD v26.1: {acd.conflict_id.nunique()} conflitos, {acd.year.min()}-{last_year}")
    print(f"Linhas conflito-ano com múltiplas localizações (após explode): {n_multi}")
    print(f"Localizações interestatais sem mortes no território (1989+) descartadas: {len(dropped)} "
          f"({dropped.iso3.nunique()} países: {' '.join(sorted(dropped.iso3.unique()))})")
    print(f"Códigos GW: {len(mapping)} | manuais: {(mapping.metodo == 'manual').sum()} | não casados: {len(unmatched)}"
          f" -> outputs/tables/unmatched_codes.csv")
    if len(unmatched):
        print(unmatched.merge(names, on="gwno", how="left").to_string(index=False))
    print(f"Painel: {panel.iso3.nunique()} países x {panel.year.nunique()} anos")
    s = panel[panel.year >= 1990]
    print(f"1990+: país-anos em conflito = {s.conflict_any.sum()}, em guerra = {s.conflict_war.sum()}")
    print("Missings:\n" + panel.isna().sum()[lambda x: x > 0].to_string() + "  (mortes só existem a partir de 1989)")


if __name__ == "__main__":
    main()
