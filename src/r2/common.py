"""Funções comuns das análises da rodada 2 (reuso dos estimadores validados da rodada 1)."""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
from r2config import PROCESSED, ROOT  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
import did_tools as dt  # noqa: E402,F401
import plotstyle as ps  # noqa: E402,F401

est = importlib.import_module("07_estimate")
cont = importlib.import_module("11_exercise_continuous")
COVARS = est.COVARS                      # ln_gdppc_pre, urban_share_pre, ln_pop_pre (mesmos nomes no painel r2)


def panel() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / "r2_panel.parquet")


def onset_sample(p: pd.DataFrame, gcol: str = "g_t1", ctrl: str = "ctrl_main") -> pd.DataFrame:
    """Tratados (com onset em gcol) + controles; g = 0 para controles."""
    d = p[p[gcol].notna() | (p[ctrl] == 1)].copy()
    d["g"] = d[gcol].fillna(0).astype(int)
    d["treated"] = (d.g > 0).astype(int)
    d["rel_time"] = np.where(d.treated == 1, d.year - d.g, np.nan)
    d["post"] = ((d.treated == 1) & (d.year >= d.g)).astype(int)
    return d


def cs(d: pd.DataFrame, y: str, control="never", method="reg", **kw) -> dict:
    r = est.run_cs(d, y, control=control, method=method, **kw)
    o = r["simple"]["overall"]
    return {"r": r, "row": {**{k: o[k] for k in ("estimate", "se", "ci_low", "ci_high", "p_value")},
                            "n_treated": r["info"]["n_treated"], "n_units": r["info"]["n_units"],
                            "pretrend_p": r["info"]["pretrend"]["p_value"]}}


def holm(p: pd.Series) -> pd.Series:
    """p-valores ajustados de Holm–Bonferroni."""
    order = p.sort_values().index
    m = p.notna().sum()
    adj, run = pd.Series(np.nan, index=p.index), 0.0
    for i, k in enumerate([k for k in order if pd.notna(p[k])]):
        run = max(run, min(1.0, (m - i) * p[k]))
        adj[k] = run
    return adj


def waoss(p: pd.DataFrame, y: str, D: str = "t3_asinh", eps: float = 0.1) -> dict:
    q = cont._pairs(p, y, D)
    e, pl = cont.waoss_boot(q, eps), cont.waoss_boot(q, eps, placebo=True)
    out = {}
    for tag, r in [("efeito", e), ("placebo", pl)]:
        for k in ("all", "up", "down"):
            out[f"{tag}_{k}"] = r[k]
            out[f"{tag}_se_{k}"] = r[f"se_{k}"]
            out[f"{tag}_p_{k}"] = float(2 * stats.norm.sf(abs(r[k] / r[f"se_{k}"]))) if r[f"se_{k}"] > 0 else np.nan
        out[f"{tag}_n_sw"] = r["n_sw"]
    out["liquido_up"] = out["efeito_up"] - out["placebo_up"]
    out["liquido_se_up"] = float(np.hypot(out["efeito_se_up"], out["placebo_se_up"]))   # conservador (sem covariância)
    return out


def stacked_means(d: pd.DataFrame, y: str, pre=(-5, -1), post=(0, 5), reps: int = 999, seed: int = 3) -> dict:
    """DiD empilhada de médias: para cada tratado, [média pós − média pré] menos o mesmo para a média dos
    controles nos mesmos anos-calendário; média simples entre tratados. Usa todo o período pré como base
    (robusto a oscilações de um único ano-base em resultados esporádicos, como 'há pesquisa no ano').
    EP por bootstrap de países (tratados e controles reamostrados separadamente)."""
    dd = d.dropna(subset=[y])
    W = dd.pivot_table(index="iso3", columns="year", values=y)
    G = dd.drop_duplicates("iso3").set_index("iso3").g.reindex(W.index)
    ctrl = W[G == 0]
    trs = [(i, int(g)) for i, g in G[G > 0].items()]

    def one(tr_list, C):
        cm = C.mean(axis=0)
        vals = []
        for i, g in tr_list:
            pr = [y_ for y_ in range(g + pre[0], g + pre[1] + 1) if y_ in W.columns]
            po = [y_ for y_ in range(g + post[0], g + post[1] + 1) if y_ in W.columns]
            a, b = W.loc[i, pr], W.loc[i, po]
            if a.notna().sum() >= 2 and b.notna().sum() >= 2:
                vals.append((b.mean() - a.mean()) - (cm[po].mean() - cm[pr].mean()))
        return float(np.mean(vals)) if vals else np.nan, len(vals)
    est_, n = one(trs, ctrl)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(reps):
        tb = [trs[k] for k in rng.integers(0, len(trs), len(trs))]
        cb = ctrl.iloc[rng.integers(0, len(ctrl), len(ctrl))]
        boots.append(one(tb, cb)[0])
    se = float(np.nanstd(boots, ddof=1))
    return {"estimate": est_, "se": se, "ci_low": est_ - 1.96 * se, "ci_high": est_ + 1.96 * se,
            "p_value": float(2 * stats.norm.sf(abs(est_ / se))) if se > 0 else np.nan, "n_treated": n,
            "n_units": n + len(ctrl)}


def bjs(d: pd.DataFrame, y: str) -> dict:
    o, dyn = est.run_did2s(d, y)
    return {**o, "n_treated": int(d.dropna(subset=[y]).query("treated == 1").iso3.nunique()),
            "n_units": int(d.dropna(subset=[y]).iso3.nunique()), "dyn": dyn}


def plot_es(tab: pd.DataFrame, title: str, path, color=None):
    est.plot_es(tab, title, path, band=True, color=color or ps.TREATED)
