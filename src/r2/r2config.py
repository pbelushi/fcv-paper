"""Configuração da rodada 2: caminhos, parâmetros e utilitários de download com MANIFEST.

Reusa src/config.py (rodada 1) para os caminhos de dados brutos e intermediários.
"""
import hashlib
import sys
from datetime import date
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))
from config import INTERIM, MANIFEST, PROCESSED, RAW, ROOT  # noqa: E402,F401

OUT = ROOT / "outputs" / "r2"
TAB = OUT / "tables"
FIG = OUT / "figures"
REPORT = ROOT / "report"
for _d in (TAB, FIG):
    _d.mkdir(parents=True, exist_ok=True)

SAMPLE_START, SAMPLE_END = 1990, 2024     # pobreza: PIP lineup sem nowcast (rodada 1)
PEACE_WINDOW = 5
PEACE_WINDOWS = [3, 5, 10]
MIN_PRE_SURVEYS = 3                       # só para Q3 (pobreza)
CONC_SHARE, CONC_DAYS = 0.75, 3           # regra própria (não consta das notas FCS publicadas)
CHRONIC_SHARE = 0.80
CHRONIC_ROBUST = [0.70, 0.90]
TODAY = date.today().isoformat()


def save_raw(name: str, content: bytes, source: str, url: str, version: str, terms: str) -> Path:
    """Grava o arquivo bruto sem alteração e acrescenta/atualiza a linha do MANIFEST."""
    path = RAW / name
    path.write_bytes(content)
    row = {"arquivo": name, "fonte": source, "url": url, "versao": version, "data_download": TODAY,
           "sha256": hashlib.sha256(content).hexdigest(), "licenca_termos": terms}
    man = pd.read_csv(MANIFEST) if MANIFEST.exists() else pd.DataFrame(columns=list(row))
    man = pd.concat([man[man.arquivo != name], pd.DataFrame([row])], ignore_index=True)
    man.to_csv(MANIFEST, index=False)
    print(f"  ok  {name:60s} {len(content) / 1e6:8.2f} MB")
    return path


def manifest_version(name: str) -> str:
    man = pd.read_csv(MANIFEST)
    return str(man.loc[man.arquivo == name, "versao"].iloc[0])
