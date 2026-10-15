"""Etapa 14 — Exercício 4: poder estatístico e efeito mínimo detectável (MDE) por simulação.

Desenho placebo nos dados reais: em cada réplica, sorteiam-se entre os nunca tratados "falsos
tratados" com o mesmo número de países e os mesmos anos de onset de cada especificação; soma-se
δ·s(e) ao resultado deles a partir de g; estima-se com o estimador de referência (CS REG, nunca
tratados, covariáveis pré g−5..g−1, bootstrap multiplicador por país, via did_tools) e registra-se
se o IC 95% exclui zero.
- s(e) = 1 (efeito constante) ou s(e) = min((e+1)/6, 1) (cresce linearmente até e = 5).
- Mesmos sorteios para todos os δ (números aleatórios comuns).
Especificações: desenho de onset original (07_estimate.load_sample) e "limiar_1" (exercício 1).
"""
import importlib
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import did_tools as dt  # noqa: E402

COVARS = ["ln_gdppc_pre", "urban_share_pre", "ln_pop_pre"]
RAW = ["ln_gdppc", "urban_share", "ln_pop"]
GRID = {"pov_rate": np.round(np.arange(0, 10.0001, 0.5), 2), "ln_n_poor": np.round(np.arange(0, 0.6001, 0.05), 2)}
SHAPES = {"constante": lambda e: np.ones_like(e, dtype=float),
          "linear até e=5": lambda e: np.minimum((e + 1) / 6.0, 1.0)}
SPECS = ["original", "limiar_1"]
N_REPS = 500
N_PROC = 12
MAX_HOURS = 2.0
B = 999


# ============================================================================ dados

def load_specs() -> dict:
    est = importlib.import_module("07_estimate")
    ex1 = importlib.import_module("10_exercise_intensity")
    return {"original": est.load_sample(), "limiar_1": ex1.specs(ex1.base_panel())["limiar_1"]}


def build_pool(d: pd.DataFrame, y: str) -> dict:
    """Pool de nunca tratados utilizáveis pelo estimador real + coortes dos tratados usados."""
    w, _ = dt.to_wide(d, y, covars=COVARS)                      # mesma amostra do estimador real
    cohorts = np.sort(w.G[w.G > 0])
    nt = w.G == 0
    units, years, Y, Xc = w.units[nt], w.years, w.Y[nt], w.X[nt]
    # covariáveis pré por país × g (média g−5..g−1 dos anos disponíveis), como na etapa 05/10
    raw = d[d.iso3.isin(units)].set_index(["iso3", "year"])[RAW]
    gs = np.unique(cohorts)
    Xpre = np.full((len(units), len(gs), len(RAW)), np.nan)
    for i, u in enumerate(units):
        ru = raw.loc[u]
        for j, g in enumerate(gs):
            win = ru[(ru.index >= g - 5) & (ru.index <= g - 1)]
            Xpre[i, j] = win.mean().to_numpy()
    return {"units": units, "years": years, "Y": Y, "Xc": Xc, "gs": gs, "Xpre": Xpre, "cohorts": cohorts}


def estimate(w: dt.Wide) -> tuple[float, float]:
    """Estimador de referência (idêntico a 07_estimate.run_cs, só a agregação simple)."""
    res = dt.callaway_santanna(w, control="never", method="reg")
    o = dt.aggte(res, "simple", max_e=10, B=B)["overall"]
    return o["estimate"], o["se"]


def replicate(pool: dict, seed: int, deltas: np.ndarray, shapes: dict = SHAPES) -> list[dict]:
    """Uma réplica placebo: sorteio de falsos tratados, todos os δ e formatos."""
    rng = np.random.default_rng(seed)
    n, cohorts = len(pool["units"]), pool["cohorts"]
    gidx = {g: j for j, g in enumerate(pool["gs"])}
    for _ in range(1000):                                      # rejeita sorteios sem covariável pré
        pick = rng.choice(n, size=len(cohorts), replace=False)
        g_assign = rng.permutation(cohorts)
        Xt = np.array([pool["Xpre"][i, gidx[g]] for i, g in zip(pick, g_assign)])
        if np.isfinite(Xt).all():
            break
    else:
        raise RuntimeError("não foi possível sortear falsos tratados com covariáveis pré")
    G = np.zeros(n, int)
    G[pick] = g_assign
    X = pool["Xc"].copy()
    X[pick] = Xt
    years = pool["years"]
    E = years[None, :] - G[pick][:, None]                     # tempo relativo dos falsos tratados
    out = []
    for sname, s in shapes.items():
        S = np.where(E >= 0, s(np.maximum(E, 0)), 0.0)
        for dlt in deltas:
            if sname != "constante" and dlt == 0:
                continue                                       # δ = 0 é igual nos dois formatos
            Y = pool["Y"].copy()
            Y[pick] += dlt * S
            att, se = estimate(dt.Wide(pool["units"], years, Y, G, X))
            out.append({"formato": sname, "delta": float(dlt), "att": att, "se": se,
                        "rejeita": int(abs(att) > 1.959963984540054 * se)})
    return out


# ============================================================================ paralelismo

_POOLS: dict = {}


def _init(pools):
    global _POOLS
    _POOLS = pools


def _task(args):
    spec, y, r = args
    seed = [SPECS.index(spec), list(GRID).index(y), r, 2026]
    rows = replicate(_POOLS[(spec, y)], np.random.SeedSequence(seed).generate_state(1)[0], GRID[y])
    return [{"spec": spec, "outcome": y, "rep": r, **x} for x in rows]


def check_equivalence(specs: dict) -> None:
    est = importlib.import_module("07_estimate")
    for spec, d in specs.items():
        for y in GRID:
            ref = est.run_cs(d, y, control="never", method="reg")["simple"]["overall"]
            w, _ = dt.to_wide(d, y, covars=COVARS)
            a, s = estimate(w)
            assert abs(a - ref["estimate"]) < 1e-12 and abs(s - ref["se"]) < 1e-12, (spec, y, a, ref)
    print("  estimador leve = 07_estimate.run_cs (ATT e EP idênticos) nas 4 combinações")


def summarize(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    d0 = raw[raw.delta == 0]
    raw = pd.concat([raw, d0.assign(formato="linear até e=5")])     # δ = 0 vale para os dois formatos
    pw = raw.groupby(["spec", "outcome", "formato", "delta"]).agg(
        replicas=("rejeita", "size"), poder=("rejeita", "mean"), ep_medio=("se", "mean"),
        att_medio=("att", "mean")).reset_index()
    pw["ep_mc"] = np.sqrt(pw.poder * (1 - pw.poder) / pw.replicas)
    ref = reference_estimates()
    rows = []
    for (spec, y, f), t in pw.groupby(["spec", "outcome", "formato"]):
        t = t.sort_values("delta")
        size = t[t.delta == 0].iloc[0]
        ok = t[t.poder >= 0.8]
        mde = float(ok.delta.iloc[0]) if len(ok) else np.nan
        mde_i = np.nan
        if len(ok):
            k = t.index.get_loc(ok.index[0])
            if k > 0:
                a, b = t.iloc[k - 1], t.iloc[k]
                mde_i = a.delta + (0.8 - a.poder) * (b.delta - a.delta) / (b.poder - a.poder)
            else:
                mde_i = mde
        n = 1.959963984540054
        lo, hi = size.poder - n * size.ep_mc, size.poder + n * size.ep_mc
        r = ref[(spec, y)]
        rows.append({"spec": spec, "outcome": y, "formato": f, "replicas": int(size.replicas),
                     "tamanho_delta0": size.poder, "tamanho_ic_low": max(lo, 0), "tamanho_ic_high": hi,
                     "mde_grade": mde, "mde_interpolado": mde_i, "ep_estimado": r["se"],
                     "mde_aprox_2_8_ep": 2.8 * r["se"], "att_estimado": r["estimate"],
                     "poder_no_att_estimado": float(np.interp(abs(r["estimate"]), t.delta, t.poder))})
    return pw, pd.DataFrame(rows)


def reference_estimates() -> dict:
    from config import TABLES
    m = pd.read_csv(TABLES / "main_results.csv")
    m = m[m.estimator == "CS (REG, nunca tratados) — simple"].set_index("outcome")
    e = pd.read_csv(TABLES / "ex1_intensity_income.csv")
    e = e[(e.spec == "limiar_1") & (e.estimator == "CS (REG, nunca tratados)")].set_index("outcome")
    return {(s, y): {"estimate": float(t.loc[y, "estimate"]), "se": float(t.loc[y, "se"])}
            for s, t in [("original", m), ("limiar_1", e)] for y in GRID}


def plot(pw: pd.DataFrame, mde: pd.DataFrame) -> None:
    import plotstyle as ps
    from config import FIGURES
    colors = {"original": ps.TREATED, "limiar_1": ps.CONTROL}
    labels = {"original": "Onset original", "limiar_1": "Limiar ≥ 1/100 mil (limiar_1)"}
    xl = {"pov_rate": "δ — efeito verdadeiro na taxa de pobreza (p.p.)", "ln_n_poor": "δ — efeito verdadeiro no log do nº de pobres"}
    for y in GRID:
        fig, ax = ps.plt.subplots(figsize=(6.8, 4.0))
        ax.axhline(0.8, color=ps.INK2, lw=1, ls=":")
        ax.axhline(0.05, color=ps.INK2, lw=1, ls=":")
        ax.text(GRID[y].max(), 0.81, "80%", ha="right", va="bottom", fontsize=8, color=ps.INK2)
        ax.text(GRID[y].max(), 0.06, "5%", ha="right", va="bottom", fontsize=8, color=ps.INK2)
        for spec in SPECS:
            for f, ls in [("constante", "-"), ("linear até e=5", "--")]:
                t = pw[(pw.spec == spec) & (pw.outcome == y) & (pw.formato == f)].sort_values("delta")
                ax.plot(t.delta, t.poder, color=colors[spec], ls=ls, marker="o" if f == "constante" else None, ms=3.5,
                        label=f"{labels[spec]} — efeito {f}")
            a = abs(mde[(mde.spec == spec) & (mde.outcome == y)].att_estimado.iloc[0])
            ax.axvline(a, color=colors[spec], lw=1.2, alpha=0.6)
            ax.text(a, 0.98, f" |ATT| {labels[spec].split(' (')[0].lower()}", rotation=90, va="top", ha="right",
                    fontsize=7, color=colors[spec])
        ax.set_ylim(0, 1.02)
        ax.set_xlabel(xl[y])
        ax.set_ylabel("Poder (IC 95% exclui zero)")
        ax.set_title(f"Curva de poder — {'taxa de pobreza' if y == 'pov_rate' else 'log do número de pobres'}", loc="left")
        ax.legend(fontsize=7.5, loc="upper left", bbox_to_anchor=(0, -0.16), ncol=2, frameon=False)
        ps.save(fig, FIGURES / f"ex4_power_curve_{y}")


def main() -> None:
    from config import TABLES
    t0 = time.time()
    specs = load_specs()
    check_equivalence(specs)
    pools = {(s, y): build_pool(specs[s], y) for s in SPECS for y in GRID}
    for (s, y), p in pools.items():
        print(f"  {s:9s} {y:10s}: {len(p['cohorts'])} falsos tratados por réplica, pool de {len(p['units'])} nunca "
              f"tratados -> {len(p['units']) - len(p['cohorts'])} controles")
    n_reps = N_REPS
    tasks = [(s, y, r) for r in range(n_reps) for s in SPECS for y in GRID]
    raw = []
    with mp.Pool(N_PROC, initializer=_init, initargs=(pools,)) as pool:
        it = pool.imap_unordered(_task, tasks, chunksize=2)
        t1 = time.time()
        for k, rows in enumerate(it, 1):
            raw.extend(rows)
            if k == 200:
                proj = (time.time() - t1) / 200 * len(tasks) / 3600
                print(f"  projeção: {proj:.2f} h para {len(tasks)} tarefas ({n_reps} réplicas)")
                if proj > MAX_HOURS:
                    n_reps = 200
                    print(f"  AVISO: projeção > {MAX_HOURS} h; reduzindo para {n_reps} réplicas por δ")
                    pool.terminate()
                    break
            if k % 400 == 0:
                print(f"  {k}/{len(tasks)} tarefas ({(time.time() - t1) / 60:.1f} min)")
    if n_reps != N_REPS:                                      # refaz com 200 réplicas (mesmas seeds)
        tasks = [(s, y, r) for r in range(n_reps) for s in SPECS for y in GRID]
        done = {(x["spec"], x["outcome"], x["rep"]) for x in raw}
        with mp.Pool(N_PROC, initializer=_init, initargs=(pools,)) as pool:
            for rows in pool.imap_unordered(_task, [t for t in tasks if t not in done], chunksize=2):
                raw.extend(rows)
        raw = [x for x in raw if x["rep"] < n_reps]
    raw = pd.DataFrame(raw)
    raw.to_csv(TABLES / "ex4_power_replicas.csv", index=False)
    pw, mde = summarize(raw)
    pw.to_csv(TABLES / "ex4_power.csv", index=False)
    mde.to_csv(TABLES / "ex4_mde.csv", index=False)
    # viés: ATT médio vs δ (constante) e vs δ·média ponderada de s(e) (linear) — reportado no console
    print(mde.round(3).to_string(index=False))
    plot(pw, mde)
    print(f"Tempo total: {(time.time() - t0) / 60:.1f} min")
    importlib.import_module("12_report_exercises").main()


if __name__ == "__main__":
    main()
