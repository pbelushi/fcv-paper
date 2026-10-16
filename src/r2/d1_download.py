"""Rodada 2 — d1: download das novas bases públicas para data/raw/ + MANIFEST.

Regra: nada é alterado após o download; falha em base obrigatória interrompe com a URL.
Bases opcionais (luminosidade noturna) que falharem são registradas em
outputs/r2/tables/download_gaps.csv, sem substituição por outra fonte.
ACLED não é baixado: aguarda credenciais (ponto de parada a do CLAUDE.md).
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd
import requests
import truststore

truststore.inject_into_ssl()
sys.path.insert(0, str(Path(__file__).parent))
from r2config import MANIFEST, TAB, save_raw  # noqa: E402

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) fcv-paper research pipeline"}
WB_TERMS = "CC BY 4.0 (World Bank Open Data terms)"
gaps: list[dict] = []


def fetch(url, params=None, timeout=600, optional=False):
    try:
        r = requests.get(url, params=params, headers=H, timeout=timeout)
        r.raise_for_status()
        if not r.content:
            raise ValueError("resposta vazia")
        return r
    except Exception as e:  # noqa: BLE001
        full = requests.Request("GET", url, params=params).prepare().url
        if optional:
            gaps.append({"url": full, "erro": repr(e)[:300]})
            print(f"  FALHA (opcional) {full}: {e!r}"[:300])
            return None
        sys.exit(f"ERRO no download: {full}\n  -> {e!r}\nPipeline interrompido; nada foi substituído.")


# ------------------------------------------------------------------ FCS
FCS_PAGE = ("https://www.worldbank.org/en/topic/fragilityconflictviolence/brief/"
            "classification-of-fragile-and-conflict-affected-situations")
FCS_DOCS = {
    "fcs_list_FY06_FY26.pdf": "https://thedocs.worldbank.org/en/doc/aa5bc1b55f2c7d72c157de331ab71f30-0090082026/original/C2-FCSList-FY06toFY26.pdf",
    "fcs_historical_note_FY27.pdf": "https://thedocs.worldbank.org/en/doc/319d8616e6b765ebecadadc5bf06206c-0090082026/original/C1-FCS-Historical-Note-FY27.pdf",
    "fcv_methodology_summary_FY27.pdf": "https://thedocs.worldbank.org/en/doc/65ba10d34dcc1a25b0c5505c3700dcec-0090082026/original/A2-FY27-Methodology-Summary.pdf",
    "fcv_list_FY27.pdf": "https://thedocs.worldbank.org/en/doc/d2e218e68a25ba7a31147a7455f35cae-0090082026/original/A1-FY27-FCV-List.pdf",
    "institutional_fragility_list_FY27.pdf": "https://thedocs.worldbank.org/en/doc/5785e7e735f05d096b2ec74f92ffcf5a-0090082026/original/B1-Institutional-Fragility-FY27.pdf",
}


def download_fcs():
    page = fetch(FCS_PAGE)
    save_raw("fcs_classification_page.html", page.content, "WB-FCS", FCS_PAGE, f"página ({len(page.content)} bytes)", WB_TERMS)
    for name, url in FCS_DOCS.items():
        if url.split("/")[-1] not in page.text:
            sys.exit(f"ERRO: {url} não está mais linkado em {FCS_PAGE}; verifique a versão vigente.")
        r = fetch(url)
        m = re.search(rb"/CreationDate\s*\(D:(\d{8})", r.content)
        save_raw(name, r.content, "WB-FCS", url, f"publicado {m.group(1).decode() if m else 's/d'} (FY27, página FCS)",
                 WB_TERMS + "; documento publicado na página pública FCS")


# ------------------------------------------------------------------ WDI fontes 31 (CPIA) e 83 (SPI)
def download_wb_source(source_id: int, name: str, label: str):
    base = "https://api.worldbank.org/v2"
    inds = fetch(f"{base}/sources/{source_id}/indicators", {"format": "json", "per_page": 500}).json()[1]
    codes = [i["id"] for i in inds]
    recs, last = [], None
    for code in codes:
        page, pages = 1, 1
        while page <= pages:
            js = fetch(f"{base}/country/all/indicator/{code}",
                       {"source": source_id, "format": "json", "per_page": 20000, "page": page}).json()
            if len(js) < 2 or js[1] is None:
                break
            pages, last = js[0]["pages"], js[0].get("lastupdated", last)
            recs += js[1]
            page += 1
    df = pd.json_normalize(recs).rename(columns={"indicator.id": "indicator", "indicator.value": "indicator_name",
                                                 "countryiso3code": "iso3", "country.value": "country_name", "date": "year"})
    out = df[["indicator", "indicator_name", "iso3", "country_name", "year", "value"]]
    save_raw(name, out.to_csv(index=False).encode(), label, f"{base}/country/all/indicator/{{code}}?source={source_id}",
             f"lastupdated={last}; {len(codes)} indicadores", WB_TERMS)


# ------------------------------------------------------------------ pesquisas DHS e MICS (metadados)
def download_dhs():
    url = "https://api.dhsprogram.com/rest/dhs/surveys"
    rows, page, pages = [], 1, 1
    while page <= pages:
        js = fetch(url, {"f": "json", "perpage": 1000, "page": page, "surveyStatus": "all"}).json()
        pages = js["TotalPages"]
        rows += js["Data"]
        page += 1
    save_raw("dhs_surveys.json", json.dumps(rows).encode(), "DHS", url + "?f=json&surveyStatus=all",
             f"API REST, {len(rows)} pesquisas", "DHS Program API — metadados públicos")


def download_mics():
    url = "https://mics.unicef.org/api/surveys"
    rows, page = [], 0
    while True:                                              # API paginada (10 por página, page = 0, 1, ...)
        js = fetch(url, {"page": page}).json()
        if not js:
            break
        rows += js
        page += 1
        if page > 500:
            sys.exit(f"ERRO: paginação do MICS não terminou ({url})")
    ids = {r["id"] for r in rows}
    save_raw("mics_surveys.json", json.dumps(rows).encode(), "MICS", url + "?page=0..N",
             f"API pública, {len(ids)} pesquisas em {page} páginas", "UNICEF MICS — catálogo público de pesquisas (metadados)")


# ------------------------------------------------------------------ pobreza multidimensional
MPI = {
    "ophi_global_mpi.csv": "https://data.humdata.org/dataset/42b16840-3a56-4a20-9314-7aa171f1136c/resource/ef20310e-2821-4aa9-98a8-1950f45f10d0/download/global_mpi.csv",
    "ophi_global_mpi_trends.csv": "https://data.humdata.org/dataset/42b16840-3a56-4a20-9314-7aa171f1136c/resource/7c131db3-a172-4280-b37a-85f678192fbe/download/global_mpi_trends.csv",
    "undp_gmpi_2025_table1and2.xlsx": "https://hdr.undp.org/sites/default/files/publications/additional-files/2025-10/2025_gMPI_Table1and2.xlsx",
    "wb_mpm_AM26.xlsx": "https://datacatalogfiles.worldbank.org/ddh-published/0037589/DR0045426/MPM_AM26.xlsx",
}


def download_mpi():
    for name, url in MPI.items():
        src = "OPHI" if name.startswith("ophi") else ("UNDP-HDRO" if name.startswith("undp") else "WB-MPM")
        terms = {"OPHI": "OPHI/HDX — CC BY", "UNDP-HDRO": "UNDP HDRO — uso livre com citação", "WB-MPM": WB_TERMS}[src]
        save_raw(name, fetch(url).content, src, url, {"OPHI": "HDX (global MPI, OPHI)", "UNDP-HDRO": "gMPI 2025",
                                                       "WB-MPM": "MPM Annual Meetings 2026"}[src], terms)


# ------------------------------------------------------------------ deslocamento interno e operações de paz
IDMC = ("https://data.humdata.org/dataset/0b1c4dc1-6ae5-4e2d-8e32-2111d0e10697/resource/761feae0-f812-4f0f-8e38-54b5526baf85/"
        "download/idmc_internal_displacement_conflict-violence_disasters-39.xlsx")
DPO = {"dpo_operationslist.pdf": "https://peacekeeping.un.org/sites/default/files/operationslist.pdf",
       "dpo_past_operations.html": "https://peacekeeping.un.org/en/past-peacekeeping-operations",
       "dpo_where_we_operate.html": "https://peacekeeping.un.org/en/where-we-operate"}


def download_idmc_dpo():
    save_raw("idmc_conflict_disasters.xlsx", fetch(IDMC).content, "IDMC", IDMC, "GIDD via HDX (release 39)",
             "IDMC — CC BY-NC 4.0 (uso não comercial)")
    for name, url in DPO.items():
        save_raw(name, fetch(url).content, "UN-DPO", url, f"baixado {pd.Timestamp.today().date()}",
                 "United Nations — conteúdo público do site de peacekeeping")


# ------------------------------------------------------------------ luminosidade (opcional)
def download_nightlights():
    url = "https://zenodo.org/api/records"
    r = fetch(url, {"q": "harmonized global nighttime light DMSP VIIRS", "size": 5}, optional=True)
    if r is not None:
        save_raw("zenodo_nightlights_search.json", r.content, "Zenodo", r.url, "busca", "metadados Zenodo")


if __name__ == "__main__":
    print("Listas e notas FCS:")
    download_fcs()
    print("CPIA (WDI fonte 31) e SPI (fonte 83):")
    download_wb_source(31, "wb_cpia.csv", "WB-CPIA")
    download_wb_source(83, "wb_spi.csv", "WB-SPI")
    print("Pesquisas DHS e MICS:")
    download_dhs()
    download_mics()
    print("Pobreza multidimensional:")
    download_mpi()
    print("IDMC e DPO:")
    download_idmc_dpo()
    print("Luminosidade noturna (opcional):")
    download_nightlights()
    pd.DataFrame(gaps, columns=["url", "erro"]).to_csv(TAB / "download_gaps.csv", index=False)
    man = pd.read_csv(MANIFEST)
    print(f"\nResumo: MANIFEST com {len(man)} arquivos; lacunas registradas: {len(gaps)}")
