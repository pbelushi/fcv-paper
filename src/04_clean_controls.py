"""Etapa 04 — controles e variáveis de heterogeneidade -> data/interim/controls.parquet
e data/interim/neighbors.csv.

- WDI: PIB pc PPC, crescimento, inflação, comércio/PIB, população, % urbana.
- WGI: 6 estimativas de governança (1996+, bienal até 2002).
- Grupo de renda histórico (OGHIST, por ano-calendário dos dados de GNI).
- Região: region_code do PIP.
- UNHCR: refugiados acolhidos (por país de asilo) e originados (por país de origem).
- Vizinhos: COW Direct Contiguity v3.2, contiguidade terrestre (conttype == 1)
  em qualquer ano 1990-2016 (último ano do COW).
"""
import sys
import zipfile
from pathlib import Path

import country_converter as coco
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import INTERIM, RAW, TABLES  # noqa: E402

WDI_NAMES = {"NY.GDP.PCAP.PP.KD": "gdppc_ppp", "NY.GDP.MKTP.KD.ZG": "gdp_growth",
             "FP.CPI.TOTL.ZG": "inflation", "NE.TRD.GNFS.ZS": "trade_gdp",
             "SP.POP.TOTL": "pop_wdi", "SP.URB.TOTL.IN.ZS": "urban_share",
             "SI.POV.DDAY": "pov_wdi"}
# Códigos COW cujo ISO3 o conversor GW não resolve
COW_MANUAL = {255: "DEU", 260: "DEU", 265: "DEU", 345: "SRB", 347: "XKX", 365: "RUS",
              678: "YEM", 679: "YEM", 680: "YEM", 816: "VNM", 817: "VNM", 315: "CZE", 316: "CZE",
              626: "SSD", 625: "SDN", 531: "ERI", 860: "TLS"}


def wb_long_to_wide(path: Path, names: dict | None = None) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df.iso3.notna() & (df.iso3.str.len() == 3)]
    wide = df.pivot_table(index=["iso3", "year"], columns="indicator", values="value").reset_index()
    wide.columns.name = None
    return wide.rename(columns=names or {})


def income_groups() -> pd.DataFrame:
    raw = pd.read_excel(RAW / next(p.name for p in RAW.glob("OGHIST_*.xlsx")),
                        sheet_name="Country Analytical History", header=None)
    years = raw.iloc[5, 2:].tolist()
    body = raw.iloc[6:, :].dropna(subset=[0])
    body = body[body[0].astype(str).str.len() == 3]
    long = body.melt(id_vars=[0], value_vars=list(range(2, raw.shape[1])), var_name="col", value_name="income_group")
    long["year"] = long.col.map(dict(zip(range(2, raw.shape[1]), years)))
    long = long.rename(columns={0: "iso3"})
    long["income_group"] = long.income_group.replace({"..": None, "LM*": "LM"})
    long = long.dropna(subset=["year"])
    long["year"] = long.year.astype(int)
    return long[["iso3", "year", "income_group"]]


def unhcr() -> pd.DataFrame:
    out = []
    for by, iso_col, name in [("coa", "Country of asylum (ISO)", "refugees_hosted"),
                              ("coo", "Country of origin (ISO)", "refugees_origin")]:
        d = pd.read_csv(zipfile.ZipFile(RAW / f"unhcr_population_by_{by}.zip").open("population.csv"))
        d = d[d[iso_col].str.len() == 3]
        cols = ["Refugees under UNHCR's mandate", "Asylum-seekers"]
        d[cols] = d[cols].apply(pd.to_numeric, errors="coerce")
        d[name] = d[cols].sum(axis=1)
        out.append(d.groupby([iso_col, "Year"])[name].sum().rename_axis(["iso3", "year"]))
    return pd.concat(out, axis=1).reset_index()


def neighbors() -> pd.DataFrame:
    c = pd.read_csv(zipfile.ZipFile(RAW / "DirectContiguity320.zip").open("DirectContiguity320/contdird.csv"))
    c = c[(c.conttype == 1) & (c.year >= 1990)]
    codes = sorted(set(c.state1no) | set(c.state2no))
    conv = dict(zip(codes, coco.convert(codes, src="GWcode", to="ISO3", not_found="NOTFOUND")))
    conv.update({k: v for k, v in COW_MANUAL.items() if k in conv})
    bad = [k for k, v in conv.items() if v == "NOTFOUND"]
    if bad:
        print(f"  aviso: códigos COW sem ISO3: {bad}")
    c["iso3"] = c.state1no.map(conv)
    c["iso3_nb"] = c.state2no.map(conv)
    nb = c[["iso3", "iso3_nb"]].drop_duplicates()
    return nb[(nb.iso3 != "NOTFOUND") & (nb.iso3_nb != "NOTFOUND") & (nb.iso3 != nb.iso3_nb)]


def main() -> None:
    wdi = wb_long_to_wide(RAW / "wdi_controls.csv", WDI_NAMES)
    wgi = wb_long_to_wide(RAW / "wgi_governance.csv")
    wgi.columns = [c.replace("GOV_WGI_", "wgi_").replace(".EST", "").lower() if c.startswith("GOV") else c
                   for c in wgi.columns]
    pip_version = pd.read_csv(RAW / "MANIFEST.csv").query("fonte == 'PIP'").versao.iloc[0]
    region = (pd.read_csv(RAW / f"pip_lineup_3.00_{pip_version}.csv", usecols=["country_code", "region_code"])
                .drop_duplicates("country_code").rename(columns={"country_code": "iso3"}))

    ctrl = (wdi.merge(wgi, on=["iso3", "year"], how="outer")
               .merge(income_groups(), on=["iso3", "year"], how="outer")
               .merge(unhcr(), on=["iso3", "year"], how="outer")
               .merge(region, on="iso3", how="left"))
    ctrl = ctrl[(ctrl.year >= 1960)]
    ctrl.to_parquet(INTERIM / "controls.parquet", index=False)
    nb = neighbors()
    nb.to_csv(INTERIM / "neighbors.csv", index=False)

    print(f"Controles: {ctrl.iso3.nunique()} países, {ctrl.year.min()}-{ctrl.year.max()}, {len(ctrl)} linhas")
    s = ctrl[ctrl.year >= 1990]
    print("Missings (1990+), proporção:\n" + s.isna().mean().round(3).to_string())
    print(f"Vizinhos (contiguidade terrestre): {nb.iso3.nunique()} países, {len(nb)} pares dirigidos")


if __name__ == "__main__":
    main()
