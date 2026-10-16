"""Testes da rodada 2: classificação T1, regra de eventos concentrados, parser FCS, fórmula do passthrough.

Executar: python tests/r2/test_r2.py
"""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "r2"))
d3 = importlib.import_module("d3_treatment")
TAB = ROOT / "outputs" / "r2" / "tables"


def test_t1_classification():
    thr = d3.thresholds()
    assert thr == {"abs": 150, "high_pc": 10, "med_lo": 1, "med_hi": 10, "det_lo": 0.5, "det_hi": 1, "det_ratio": 2}, thr
    pop = 1e6   # 100 mil hab. = 1/10 da população → pc = D / 10
    df = pd.DataFrame({"iso3": ["A"] * 6, "year": range(2000, 2006), "pop": pop,
                       "d_total": [0, 151, 120, 2000, 6, 4]})
    #  pc:            0  15.1  12.0  200  0.6  0.4
    x = d3.classify(df, "d_total", thr, None)
    assert list(x.high) == [False, True, False, True, False, False]       # 120 mortes: abaixo do mínimo absoluto
    assert list(x.medium) == [False] * 6
    assert list(x.rapid) == [False, False, False, False, False, False]    # 6 < 2 × 2000
    df2 = pd.DataFrame({"iso3": ["B"] * 3, "year": [2000, 2001, 2002], "pop": pop, "d_total": [2, 7, 60]})
    x2 = d3.classify(df2, "d_total", thr, None)                           # pc: 0.2, 0.7, 6.0
    assert list(x2.rapid) == [False, True, False]                         # 0,7 ∈ [0,5; 1) e 7 > 2 × 2
    assert list(x2.medium) == [False, False, False]                       # 60 mortes < 150
    print("  ok classificação T1 (alta, média, deterioração rápida) nos limiares da nota FY20–26")


def test_concentrated_events():
    c = pd.read_csv(TAB / "concentrated_events_dropped.csv")
    keys = set(zip(c.iso3, c.year))
    assert ("USA", 2001) in keys, "EUA 2001 deveria ser descartado"
    for case in [("ETH", 2021), ("SYR", 2013), ("UKR", 2022), ("MEX", 2012)]:
        assert case not in keys, f"{case} não é evento concentrado"
    assert (c.share_3d > 0.75).all()
    print(f"  ok regra de eventos concentrados ({len(c)} descartados; inclui USA 2001; guerras prolongadas mantidas)")


def test_fcs_parser():
    cnt = pd.read_csv(TAB / "fcs_counts_by_fy.csv").set_index("fy")
    assert (cnt.loc[2026, "n_conflict"], cnt.loc[2026, "n_institutional"]) == (21, 17)   # conferido no PDF
    assert (cnt.loc[2009, "n_fcs_any"], cnt.loc[2009, "n_marginal"]) == (25, 10)        # core × marginal FY09
    assert (cnt.loc[2008, "n_fcs_any"], cnt.loc[2008, "n_marginal"]) == (26, 8)
    assert (cnt.loc[2027, "n_conflict"], cnt.loc[2027, "n_institutional"]) == (24, 25)
    assert list(cnt.index) == list(range(2006, 2028))
    print("  ok parser das listas FCS (contagens conferidas manualmente em FY08, FY09, FY26, FY27)")


def test_passthrough_formula():
    """Distribuição constante: reduzir todas as rendas em x equivale a subir a linha para z/(1−x)."""
    rng = np.random.default_rng(0)
    y = rng.lognormal(mean=1.5, sigma=0.8, size=400_000)
    z = 3.0
    for x in [0.02, 0.1, 0.25]:
        h_scaled = np.mean(y * (1 - x) < z)
        h_line = np.mean(y < z / (1 - x))
        assert abs(h_scaled - h_line) < 1e-12
    print("  ok fórmula do passthrough: H((1−x)·y < z) = H(y < z/(1−x))")


if __name__ == "__main__":
    test_t1_classification()
    test_concentrated_events()
    test_fcs_parser()
    test_passthrough_formula()
    print("Todos os testes da rodada 2 passaram.")
