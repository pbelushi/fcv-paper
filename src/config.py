"""Parâmetros e caminhos compartilhados por todas as etapas."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "outputs" / "tables"
FIGURES = ROOT / "outputs" / "figures"
REPORT = ROOT / "report"
MANIFEST = RAW / "MANIFEST.csv"

SAMPLE_START = 1990          # início da amostra de pobreza
PEACE_WINDOW = 5             # anos consecutivos sem conflito antes do onset
PEACE_WINDOWS_ROBUST = [3, 5, 10]
MIN_PRE_OBS = 3              # anos de pobreza observada antes de g
POVLINE = 3.0                # linha extrema (PPC 2021) — confirmar na versão do PIP
POVLINES_UPPER = [4.2, 8.3]
PPP_VERSION = 2021

for _d in (RAW, INTERIM, PROCESSED, TABLES, FIGURES, REPORT):
    _d.mkdir(parents=True, exist_ok=True)
