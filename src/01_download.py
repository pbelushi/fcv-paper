"""Etapa 01 — download das bases brutas para data/raw/ + MANIFEST.csv.

Regras: nada é alterado após o download; qualquer falha interrompe o script
com a URL que falhou (nunca substituir por números de outra origem).
"""
import hashlib
import io
import json
import sys
from datetime import date

import pandas as pd
import requests
import truststore

truststore.inject_into_ssl()  # usa o repositório de certificados do SO (proxy corporativo)

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from config import MANIFEST, POVLINE, POVLINES_UPPER, PPP_VERSION, RAW  # noqa: E402

TODAY = date.today().isoformat()
HEADERS = {"User-Agent": "fcv-paper research pipeline (python-requests)"}
UCDP_VERSION = "26.1"
UCDP_TAG = UCDP_VERSION.replace(".", "")

TERMS = {
    "PIP": "CC BY 4.0 (World Bank Open Data terms)",
    "UCDP": "CC BY 4.0 — citar UCDP e artigos de referência",
    "WDI": "CC BY 4.0 (World Bank Open Data terms)",
    "WGI": "CC BY 4.0 (World Bank Open Data terms)",
    "WB-CLASS": "CC BY 4.0 (World Bank Open Data terms)",
    "UNHCR": "UNHCR Refugee Data Finder — CC BY 4.0 IGO",
    "COW": "Correlates of War — uso livre com citação",
}

manifest_rows: list[dict] = []


def fail(url: str, err: object) -> None:
    sys.exit(f"ERRO no download: {url}\n  -> {err}\nPipeline interrompido; nenhum dado foi substituído.")


def fetch(url: str, params: dict | None = None, timeout: int = 600) -> bytes:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        fail(requests.Request("GET", url, params=params).prepare().url, e)
    if not r.content:
        fail(r.url, "resposta vazia")
    return r.content


def save(name: str, content: bytes, source: str, url: str, version: str) -> None:
    path = RAW / name
    path.write_bytes(content)
    manifest_rows.append({
        "arquivo": name, "fonte": source, "url": url, "versao": version,
        "data_download": TODAY, "sha256": hashlib.sha256(content).hexdigest(),
        "licenca_termos": TERMS[source.split(" ")[0]],
    })
    print(f"  ok  {name:55s} {len(content)/1e6:8.2f} MB")


# ---------------------------------------------------------------- PIP
def download_pip() -> None:
    base = "https://api.worldbank.org/pip/v1"
    versions = pd.read_json(io.BytesIO(fetch(f"{base}/versions")))
    v = versions[(versions.ppp_version.astype(str) == str(PPP_VERSION)) & (versions.identity == "PROD")]
    v = v.sort_values("release_version", ascending=False).iloc[0]
    version = v["version"]
    print(f"PIP: versão mais recente PROD PPP{PPP_VERSION} = {version}")
    save(f"pip_versions_{TODAY}.json", fetch(f"{base}/versions"), "PIP", f"{base}/versions", version)

    # documentação das linhas de pobreza da versão (confirmar US$ 3,00)
    url = f"{base}/aux"
    params = {"table": "poverty_lines", "version": version, "format": "csv"}
    content = fetch(url, params)
    save(f"pip_aux_poverty_lines_{version}.csv", content, "PIP",
         requests.Request("GET", url, params=params).prepare().url, version)

    for line in [POVLINE, *POVLINES_UPPER]:
        for fill in ("false", "true"):
            params = {"country": "all", "year": "all", "povline": line, "fill_gaps": fill,
                      "ppp_version": PPP_VERSION, "version": version, "format": "csv"}
            url = f"{base}/pip"
            content = fetch(url, params, timeout=900)
            tag = "lineup" if fill == "true" else "survey"
            save(f"pip_{tag}_{line:.2f}_{version}.csv", content, "PIP",
                 requests.Request("GET", url, params=params).prepare().url, version)


# ---------------------------------------------------------------- UCDP
def download_ucdp() -> None:
    files = {
        "ucdpprio": f"ucdp-prio-acd-{UCDP_TAG}-csv.zip",
        "brd": f"ucdp-brd-conf-{UCDP_TAG}-csv.zip",
        "ged": f"ged{UCDP_TAG}-csv.zip",
        "organizedviolencecy": f"organizedviolencecy-{UCDP_TAG}-csv.zip",
    }
    for folder, fname in files.items():
        url = f"https://ucdp.uu.se/downloads/{folder}/{fname}"
        save(fname, fetch(url, timeout=1200), "UCDP", url, UCDP_VERSION)


# ---------------------------------------------------------------- WDI / WGI
WDI_CODES = ["NY.GDP.PCAP.PP.KD", "NY.GDP.MKTP.KD.ZG", "FP.CPI.TOTL.ZG", "NE.TRD.GNFS.ZS",
             "SP.POP.TOTL", "SP.URB.TOTL.IN.ZS", "SI.POV.DDAY"]
WGI_CODES = [f"GOV_WGI_{c}.EST" for c in ("VA", "PV", "GE", "RQ", "RL", "CC")]


def download_wb_api(source_id: int, codes: list[str], name: str, source: str) -> None:
    """Baixa via API v2 (JSON paginado) e grava a resposta concatenada sem alteração de valores."""
    base = "https://api.worldbank.org/v2"
    lastupdated = None
    records = []
    for code in codes:
        url = f"{base}/country/all/indicator/{code}"
        page, pages = 1, 1
        while page <= pages:
            params = {"source": source_id, "format": "json", "per_page": 20000, "page": page,
                      "date": "1960:2026"}
            js = json.loads(fetch(url, params))
            if not isinstance(js, list) or len(js) < 2 or js[1] is None:
                fail(requests.Request("GET", url, params=params).prepare().url, js)
            pages = js[0]["pages"]
            lastupdated = js[0].get("lastupdated", lastupdated)
            records += js[1]
            page += 1
    df = pd.json_normalize(records)
    df = df.rename(columns={"indicator.id": "indicator", "country.value": "country_name",
                            "countryiso3code": "iso3", "date": "year"})
    out = df[["indicator", "iso3", "country_name", "year", "value"]]
    content = out.to_csv(index=False).encode()
    save(name, content, source, f"{base}/country/all/indicator/{{code}}?source={source_id} "
         f"codes={','.join(codes)}", f"lastupdated={lastupdated}")


def download_wb_class() -> None:
    url = "https://ddh-openapi.worldbank.org/resources/DR0095334/download"
    r = requests.get(url, headers=HEADERS, timeout=300)
    if r.status_code != 200:
        fail(url, r.status_code)
    cd = r.headers.get("content-disposition", "")
    fname = cd.split("filename=")[-1].split(";")[0].strip('"') if "filename=" in cd else "OGHIST.xlsx"
    save(fname, r.content, "WB-CLASS", url, fname.replace("OGHIST_", "").replace(".xlsx", ""))


# ---------------------------------------------------------------- UNHCR / COW
def download_unhcr() -> None:
    base = "https://api.unhcr.org/population/v1/population/"
    for by in ("coa", "coo"):  # país de asilo / país de origem
        params = {"yearFrom": 1990, "yearTo": 2026, f"{by}_all": "true", "download": "true"}
        content = fetch(base, params, timeout=900)
        save(f"unhcr_population_by_{by}.zip", content, "UNHCR",
             requests.Request("GET", base, params=params).prepare().url, f"API v1 ({TODAY})")


def download_cow() -> None:
    url = "https://correlatesofwar.org/wp-content/uploads/DirectContiguity320.zip"
    save("DirectContiguity320.zip", fetch(url), "COW", url, "3.2")


def write_manifest() -> None:
    new = pd.DataFrame(manifest_rows)
    if MANIFEST.exists():
        old = pd.read_csv(MANIFEST)
        new = pd.concat([old[~old.arquivo.isin(new.arquivo)], new], ignore_index=True)
    new.to_csv(MANIFEST, index=False)


if __name__ == "__main__":
    try:
        download_pip()
        download_ucdp()
        download_wb_api(2, WDI_CODES, "wdi_controls.csv", "WDI")
        download_wb_api(3, WGI_CODES, "wgi_governance.csv", "WGI")
        download_wb_class()
        download_unhcr()
        download_cow()
    finally:
        if manifest_rows:
            write_manifest()
    print(f"\nResumo: {len(manifest_rows)} arquivos baixados; MANIFEST em {MANIFEST}")
