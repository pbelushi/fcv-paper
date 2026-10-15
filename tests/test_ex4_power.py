"""Exercício 4: a réplica placebo (src/14_power_simulation.replicate) recupera δ e tem tamanho ≈ 5%.

Executar: python tests/test_ex4_power.py
"""
import importlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
ps = importlib.import_module("14_power_simulation")


def fake_pool(N=80, T=20, seed=0):
    """Painel de nunca tratados com efeitos de unidade/ano, tendência ligada a X e ruído AR(1)."""
    rng = np.random.default_rng(seed)
    years = np.arange(2000, 2000 + T)
    x = rng.normal(size=N)
    a = rng.normal(size=N)
    lam = np.cumsum(rng.normal(0.2, 0.3, T))
    u = np.zeros((N, T))
    for t in range(1, T):
        u[:, t] = 0.5 * u[:, t - 1] + rng.normal(0, 0.5, N)
    Y = a[:, None] + lam[None, :] + 0.2 * x[:, None] * np.arange(T)[None, :] + u
    cohorts = np.array([2005, 2007, 2007, 2009, 2010, 2012, 2012, 2014, 2015, 2016])
    gs = np.unique(cohorts)
    Xpre = np.repeat(x[:, None, None], len(gs), axis=1)      # covariável invariante
    return {"units": np.arange(N).astype(str), "years": years, "Y": Y, "Xc": x[:, None],
            "gs": gs, "Xpre": Xpre, "cohorts": cohorts}


def test_size_and_bias(reps=120):
    pool = fake_pool()
    shapes = {"constante": ps.SHAPES["constante"]}
    rej, att2 = [], []
    for r in range(reps):
        out = ps.replicate(pool, seed=1000 + r, deltas=np.array([0.0, 2.0]), shapes=shapes)
        rej.append(out[0]["rejeita"])
        att2.append(out[1]["att"] - out[0]["att"])
    size = np.mean(rej)
    assert 0.0 <= size <= 0.12, size
    # efeito constante entra de forma exata e linear no ATT: ATT(δ) − ATT(0) = δ em cada réplica
    assert np.allclose(att2, 2.0, atol=1e-8), (min(att2), max(att2))
    print(f"  ok réplica placebo: tamanho a 5% = {size:.3f} ({reps} réplicas); ATT(δ=2) − ATT(0) = 2 exatamente")


if __name__ == "__main__":
    test_size_and_bias()
    print("Teste passou.")
