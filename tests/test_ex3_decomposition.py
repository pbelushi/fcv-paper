"""Identidade da decomposição do exercício 3: o CS com regressão de resultado (REG) é linear em y
na mesma amostra, logo ATT(ln_rate) + ATT(ln_pop) = ATT(ln_rate + ln_pop) = ATT(ln_n_poor).

Executar: python tests/test_ex3_decomposition.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import did_tools as dt  # noqa: E402
from test_did_tools import simulate  # noqa: E402


def test_decomposition_identity(tol=1e-6):
    df = simulate(seed=21, x_trend=0.3, x_select=1.0)
    rng = np.random.default_rng(21)
    df["ln_rate"] = df.y
    df["ln_pop"] = 15 + 0.02 * (df.year - 2000) + rng.normal(0, 0.05, len(df)) + 0.1 * df.x
    df["ln_n_poor"] = df.ln_rate + df.ln_pop
    att, cells = {}, {}
    for y in ["ln_rate", "ln_pop", "ln_n_poor"]:
        w, _ = dt.to_wide(df, y, covars=["x"])
        res = dt.callaway_santanna(w, control="never", method="reg")
        att[y] = dt.aggte(res, "simple", B=99)["overall"]["estimate"]
        cells[y] = res.cells.set_index(["g", "t"]).att
    gap = abs(att["ln_rate"] + att["ln_pop"] - att["ln_n_poor"])
    gap_cells = float(np.max(np.abs(cells["ln_rate"] + cells["ln_pop"] - cells["ln_n_poor"])))
    assert gap < tol and gap_cells < tol, (gap, gap_cells)
    print(f"  ok identidade da decomposição (REG): |dif| agregado {gap:.1e}, por célula {gap_cells:.1e}")


if __name__ == "__main__":
    test_decomposition_identity()
    print("Teste passou.")
