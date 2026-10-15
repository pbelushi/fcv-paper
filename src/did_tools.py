"""Estimadores DiD implementados em Python (R não disponível no ambiente).

- callaway_santanna(): ATT(g,t) de Callaway & Sant'Anna (2021), replicando a lógica do
  pacote R `did` (att_gt + aggte): estimador DR de Sant'Anna & Zhao (2020, `drdid_panel`),
  funções de influência, bootstrap multiplicador (Rademacher) com cluster na unidade,
  agregações simple / group / dynamic, controles never / not-yet-treated, antecipação,
  período-base "varying" ou "universal".
- twfe(): OLS com efeitos fixos de unidade e ano (projeções alternadas) e EP cluster CR1.
- sun_abraham(): interações coorte x tempo relativo (Sun & Abraham 2021), agregadas por
  pesos de coorte (interaction-weighted).
- bacon_decomposition(): decomposição de Goodman-Bacon (2021) para painel balanceado.
Validação em tests/test_did_tools.py (dados simulados com efeito conhecido).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

# ============================================================================ dados


@dataclass
class Wide:
    units: np.ndarray
    years: np.ndarray
    Y: np.ndarray            # N x T (nan = ausente)
    G: np.ndarray            # N (0 = nunca tratado)
    X: np.ndarray | None     # N x k (sem intercepto), invariantes no tempo


def to_wide(df: pd.DataFrame, y: str, g: str = "g", unit: str = "iso3", time: str = "year",
            covars: list[str] | None = None, balanced: bool = True) -> tuple[Wide, dict]:
    """Converte painel longo para matrizes. balanced=True mantém só unidades com y completo
    (como o `did` com painel balanceado); unidades sem covariáveis são descartadas."""
    d = df[[unit, time, y, g, *(covars or [])]].copy()
    Yw = d.pivot(index=unit, columns=time, values=y)
    info = {"n_units_in": Yw.shape[0]}
    if balanced:
        keep = Yw.notna().all(axis=1)
        info["dropped_unbalanced"] = sorted(Yw.index[~keep])
        Yw = Yw[keep]
    first = d.drop_duplicates(unit).set_index(unit)
    X = None
    if covars:
        Xd = first.loc[Yw.index, covars]
        ok = Xd.notna().all(axis=1)
        info["dropped_missing_x"] = sorted(Yw.index[~ok])
        Yw, Xd = Yw[ok], Xd[ok]
        X = Xd.to_numpy(float)
    G = first.loc[Yw.index, g].fillna(0).to_numpy(int)
    info["n_units"] = len(Yw)
    info["n_treated"] = int((G > 0).sum())
    return Wide(Yw.index.to_numpy(), Yw.columns.to_numpy(int), Yw.to_numpy(float), G, X), info


# ============================================================================ 2x2 DR (Sant'Anna & Zhao)

def _logit(Z, D, maxit=100, tol=1e-10):
    """IRLS; devolve (p, hessian_inv*n, convergiu)."""
    b = np.zeros(Z.shape[1])
    for _ in range(maxit):
        eta = np.clip(Z @ b, -30, 30)
        p = 1 / (1 + np.exp(-eta))
        W = p * (1 - p)
        H = Z.T @ (Z * W[:, None])
        try:
            step = np.linalg.solve(H + 1e-10 * np.eye(len(b)), Z.T @ (D - p))
        except np.linalg.LinAlgError:
            return p, None, False
        b += step
        if np.max(np.abs(step)) < tol:
            break
    eta = np.clip(Z @ b, -30, 30)
    p = 1 / (1 + np.exp(-eta))
    H = Z.T @ (Z * (p * (1 - p))[:, None])
    try:
        Hinv = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        return p, None, False
    conv = np.all(np.isfinite(b)) and np.max(np.abs(b)) < 25
    return p, Hinv * len(D), conv


def drdid_panel(dy: np.ndarray, D: np.ndarray, X: np.ndarray | None, method: str = "dr"):
    """ATT 2x2 e função de influência (escala da subamostra). method: 'dr' | 'reg' | 'unc'.
    Replica DRDID::drdid_panel / reg_did_panel (pesos unitários iguais)."""
    n = len(dy)
    Z = np.ones((n, 1)) if (X is None or method == "unc") else np.column_stack([np.ones(n), X])
    C = 1 - D
    # regressão de resultado nos controles
    XtX = Z[C == 1].T @ Z[C == 1]
    beta = np.linalg.lstsq(XtX, Z[C == 1].T @ dy[C == 1], rcond=None)[0]
    m = Z @ beta
    XpX_inv = np.linalg.pinv((Z * C[:, None]).T @ Z / n)
    lin_ols = (C * (dy - m))[:, None] * Z @ XpX_inv
    flag = ""
    if method == "dr" and Z.shape[1] > 1:
        p, Hn, conv = _logit(Z, D)
        if not conv or Hn is None:
            method, flag = "reg", "logit não convergiu -> reg"
    if method == "dr" and Z.shape[1] > 1:
        p = np.minimum(p, 1 - 1e-16)
        trim = np.where(D == 1, True, p < 0.995)        # trimming do DRDID
        w_t = D * trim
        w_c = trim * p * C / (1 - p)
        att_t = w_t * (dy - m)
        att_c = w_c * (dy - m)
        eta_t, eta_c = att_t.mean() / w_t.mean(), att_c.mean() / w_c.mean()
        lin_ps = ((D - p)[:, None] * Z) @ Hn
        inf_t = (att_t - w_t * eta_t - lin_ols @ (w_t[:, None] * Z).mean(0)) / w_t.mean()
        M2 = (w_c * (dy - m - eta_c))[:, None] * Z
        inf_c = (att_c - w_c * eta_c + lin_ps @ M2.mean(0) - lin_ols @ (w_c[:, None] * Z).mean(0)) / w_c.mean()
        return eta_t - eta_c, inf_t - inf_c, flag
    # regressão de resultado (inclui o caso sem covariáveis: Z = intercepto)
    w = D.astype(float)
    eta_t = (w * dy).mean() / w.mean()
    eta_c = (w * m).mean() / w.mean()
    inf_t = (w * dy - w * eta_t) / w.mean()
    inf_c = (w * m - w * eta_c + lin_ols @ (w[:, None] * Z).mean(0)) / w.mean()
    return eta_t - eta_c, inf_t - inf_c, flag


# ============================================================================ Callaway & Sant'Anna

@dataclass
class CSResult:
    cells: pd.DataFrame          # g, t, e, att, se, n_treat, n_ctrl, flag
    IF: np.ndarray               # N x K (escala da amostra completa)
    G: np.ndarray
    N: int
    pg: dict
    info: dict = field(default_factory=dict)


def callaway_santanna(w: Wide, control: str = "never", anticipation: int = 0,
                      base: str = "varying", method: str = "dr") -> CSResult:
    years, Y, G, X = w.years, w.Y, w.G, w.X
    N = len(G)
    groups = sorted(set(G[G > 0]))
    pg = {g: (G == g).mean() for g in groups}
    rows, IFs = [], []
    for g in groups:
        ref = g - 1 - anticipation
        if ref < years.min():
            continue
        for t in years:
            if t == ref:
                continue
            post = t >= g - anticipation
            b = ref if (post or base == "universal") else t - 1
            if b < years.min():
                continue
            it, ib = np.searchsorted(years, t), np.searchsorted(years, b)
            if control == "never":
                ctrl = G == 0
            else:
                ctrl = (G == 0) | (G > max(t, b) + anticipation)
            ctrl &= G != g
            sub = ((G == g) | ctrl) & ~np.isnan(Y[:, it]) & ~np.isnan(Y[:, ib])
            D = (G[sub] == g).astype(float)
            k = 0 if X is None else X.shape[1]
            if D.sum() < 1 or (1 - D).sum() < max(2, k + 2):
                continue
            dy = Y[sub, it] - Y[sub, ib]
            att, inf, flag = drdid_panel(dy, D, None if X is None else X[sub], method)
            full = np.zeros(N)
            full[sub] = inf * N / sub.sum()
            IFs.append(full)
            rows.append({"g": g, "t": t, "e": t - g, "att": att, "n_treat": int(D.sum()),
                         "n_ctrl": int((1 - D).sum()), "flag": flag})
    cells = pd.DataFrame(rows)
    IF = np.column_stack(IFs) if IFs else np.zeros((N, 0))
    cells["se"] = np.sqrt((IF ** 2).sum(0)) / N
    return CSResult(cells, IF, G, N, pg, {"control": control, "anticipation": anticipation,
                                         "base": base, "method": method})


def _wif(keep_groups: np.ndarray, pg_k: np.ndarray, G: np.ndarray) -> np.ndarray:
    """Termo de influência dos pesos estimados (did:::wif)."""
    S = pg_k.sum()
    ind = (G[:, None] == keep_groups[None, :]).astype(float)
    if1 = (ind - pg_k) / S
    if2 = (ind - pg_k).sum(1, keepdims=True) * (pg_k / S ** 2)[None, :]
    return if1 - if2


def _agg(res: CSResult, mask: np.ndarray, by_pg: bool = True):
    c = res.cells[mask]
    idx = np.where(mask)[0]
    gk = c.g.to_numpy()
    pg_k = np.array([res.pg[g] for g in gk]) if by_pg else np.ones(len(gk))
    wts = pg_k / pg_k.sum()
    est = float(wts @ c.att.to_numpy())
    inf = res.IF[:, idx] @ wts
    if by_pg:
        inf = inf + _wif(gk, pg_k, res.G) @ c.att.to_numpy()
    return est, inf


def aggte(res: CSResult, kind: str = "dynamic", min_e: int = -5, max_e: int = 10,
          B: int = 999, seed: int = 1, alpha: float = 0.05) -> dict:
    """Agregações à la did::aggte. Devolve dict com 'table' (estimativas, EP bootstrap,
    IC pontual e banda uniforme) e 'overall'."""
    cells = res.cells
    rows, infs = [], []
    if kind == "simple":
        m = (cells.e >= 0) & (cells.e <= max_e)
        est, inf = _agg(res, m.to_numpy())
        rows.append({"term": "ATT"}), infs.append(inf)
        ests = [est]
    elif kind == "group":
        ests = []
        for g in sorted(cells.g.unique()):
            m = ((cells.g == g) & (cells.e >= 0) & (cells.e <= max_e)).to_numpy()
            if m.any():
                est, inf = _agg(res, m, by_pg=False)
                rows.append({"term": int(g)}), infs.append(inf), ests.append(est)
    elif kind == "dynamic":
        ests = []
        for e in range(min_e, max_e + 1):
            m = (cells.e == e).to_numpy()
            if m.any():
                est, inf = _agg(res, m)
                rows.append({"term": e}), infs.append(inf), ests.append(est)
    else:
        raise ValueError(kind)
    infs = np.column_stack(infs)
    out = pd.DataFrame(rows)
    out["estimate"] = ests
    se_a, se_b, crit = _bootstrap(infs, res.N, B, seed, alpha)
    out["se_analytic"] = se_a
    out["se"] = se_b
    z = stats.norm.ppf(1 - alpha / 2)
    out["ci_low"], out["ci_high"] = out.estimate - z * out.se, out.estimate + z * out.se
    out["cb_low"], out["cb_high"] = out.estimate - crit * out.se, out.estimate + crit * out.se
    overall = None
    if kind in ("group", "dynamic"):
        if kind == "group":
            gk = out.term.to_numpy()
            pg_k = np.array([res.pg[g] for g in gk])
            wts = pg_k / pg_k.sum()
            inf_o = infs @ wts + _wif(gk, pg_k, res.G) @ out.estimate.to_numpy()
            est_o = float(wts @ out.estimate)
        else:
            post = (out.term >= 0).to_numpy()
            est_o = float(out.estimate[post].mean())
            inf_o = infs[:, post].mean(1)
        sa, sb, _ = _bootstrap(inf_o[:, None], res.N, B, seed, alpha)
        overall = {"estimate": est_o, "se": float(sb[0]), "se_analytic": float(sa[0])}
    elif kind == "simple":
        overall = {"estimate": ests[0], "se": float(out.se.iloc[0]), "se_analytic": float(se_a[0])}
    overall["ci_low"] = overall["estimate"] - z * overall["se"]
    overall["ci_high"] = overall["estimate"] + z * overall["se"]
    overall["p_value"] = float(2 * stats.norm.sf(abs(overall["estimate"] / overall["se"]))) if overall["se"] > 0 else np.nan
    return {"table": out, "overall": overall, "IF": infs}


def _bootstrap(infs: np.ndarray, N: int, B: int, seed: int, alpha: float):
    """Bootstrap multiplicador Rademacher (cluster = unidade). EP = IQR/(z.75-z.25), como no `did`."""
    se_a = np.sqrt((infs ** 2).sum(0)) / N
    rng = np.random.default_rng(seed)
    V = rng.choice([-1.0, 1.0], size=(B, N))
    boot = V @ infs / N                                    # B x K
    q75, q25 = np.quantile(boot, 0.75, axis=0), np.quantile(boot, 0.25, axis=0)
    se_b = (q75 - q25) / (stats.norm.ppf(0.75) - stats.norm.ppf(0.25))
    se_b = np.where(se_b > 0, se_b, se_a)
    tmax = np.max(np.abs(boot) / se_b, axis=1)
    crit = float(np.quantile(tmax, 1 - alpha))
    return se_a, se_b, crit


def pretrend_wald(dyn: dict) -> dict:
    """Teste de Wald conjunto H0: todos os coeficientes pré (e < 0) = 0, usando as IFs."""
    tab = dyn["table"]
    pre = (tab.term < 0).to_numpy()
    IF = dyn["IF"][:, pre]
    N = IF.shape[0]
    b = tab.estimate.to_numpy()[pre]
    V = IF.T @ IF / N ** 2
    keep = np.diag(V) > 0
    b, V = b[keep], V[np.ix_(keep, keep)]
    W = float(b @ np.linalg.pinv(V) @ b)
    k = int(keep.sum())
    return {"wald": W, "df": k, "p_value": float(stats.chi2.sf(W, k)) if k else np.nan}


# ============================================================================ TWFE / Sun-Abraham

def demean_twfe(M: np.ndarray, unit: np.ndarray, time: np.ndarray, tol=1e-10, maxit=10000):
    """Remove efeitos fixos de unidade e tempo por projeções alternadas (painel desbalanceado ok)."""
    M = M.astype(float).copy()
    _, ui = np.unique(unit, return_inverse=True)
    _, ti = np.unique(time, return_inverse=True)
    nu, nt = ui.max() + 1, ti.max() + 1
    cu, ct = np.bincount(ui, minlength=nu), np.bincount(ti, minlength=nt)
    for _ in range(maxit):
        old = M.copy()
        for idx, cnt, n in ((ui, cu, nu), (ti, ct, nt)):
            sums = np.zeros((n, M.shape[1]))
            np.add.at(sums, idx, M)
            M -= (sums / cnt[:, None])[idx]
        if np.max(np.abs(M - old)) < tol:
            break
    return M


def ols_cluster(y, X, cluster, k_fe: int = 0):
    """OLS (dados já demeaned) com EP cluster CR1. k_fe = nº de efeitos fixos não aninhados
    no cluster (convenção do fixest/pyfixest: EF de unidade aninhados não contam)."""
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    u = y - X @ b
    _, ci = np.unique(cluster, return_inverse=True)
    Gc = ci.max() + 1
    S = np.zeros((Gc, X.shape[1]))
    np.add.at(S, ci, X * u[:, None])
    meat = S.T @ S
    n, k = X.shape
    k += k_fe
    adj = Gc / (Gc - 1) * (n - 1) / (n - k)
    V = adj * XtX_inv @ meat @ XtX_inv
    return b, V, Gc


def twfe(df: pd.DataFrame, y: str, regressors: list[str], unit="iso3", time="year"):
    d = df.dropna(subset=[y, *regressors])
    M = demean_twfe(d[[y, *regressors]].to_numpy(), d[unit].to_numpy(), d[time].to_numpy())
    b, V, Gc = ols_cluster(M[:, 0], M[:, 1:], d[unit].to_numpy(), k_fe=d[time].nunique())
    se = np.sqrt(np.diag(V))
    tdist = stats.t(Gc - 1)
    return pd.DataFrame({"term": regressors, "estimate": b, "se": se,
                         "ci_low": b - tdist.ppf(0.975) * se, "ci_high": b + tdist.ppf(0.975) * se,
                         "p_value": 2 * tdist.sf(np.abs(b / se))}), V, len(d), Gc


def event_dummies(df: pd.DataFrame, min_e=-5, max_e=10, bin_ends=True, by_cohort=False):
    """Dummies de tempo relativo (ref = -1). bin_ends agrupa e<min_e e e>max_e nos extremos."""
    d = df.copy()
    e = d.rel_time.copy()
    if bin_ends:
        e = e.clip(min_e, max_e)
    cols = {}
    cohorts = sorted(d.loc[d.g > 0, "g"].unique()) if by_cohort else [None]
    for c in cohorts:
        for k in range(min_e, max_e + 1):
            if k == -1:
                continue
            nm = f"ev_{k}" if c is None else f"sa_{c}_{k}"
            sel = (e == k) if c is None else ((e == k) & (d.g == c))
            if sel.sum():
                cols[nm] = sel.astype(float)
    names = list(cols)
    d = pd.concat([d, pd.DataFrame(cols, index=d.index)], axis=1)
    return d, names


def sun_abraham(df: pd.DataFrame, y: str, min_e=-5, max_e=10):
    """IW estimator: coorte x tempo relativo, controle = nunca tratados; extremos agrupados."""
    d, names = event_dummies(df, min_e, max_e, bin_ends=True, by_cohort=True)
    tab, V, n, Gc = twfe(d, y, names)
    tab["g"] = tab.term.str.split("_").str[1].astype(int)
    tab["e"] = tab.term.str.split("_").str[2].astype(int)
    # pesos: participação da coorte entre unidades tratadas observadas em cada e
    shares = (d[d.g > 0].dropna(subset=[y]).assign(e=lambda x: x.rel_time.clip(min_e, max_e))
                .groupby(["e", "g"]).iso3.nunique())
    rows = []
    bvec = tab.estimate.to_numpy()
    for e in sorted(tab.e.unique()):
        sel = (tab.e == e).to_numpy()
        w = np.zeros(len(tab))
        s = shares.loc[e].reindex(tab.g[sel]).to_numpy(float)
        w[sel] = s / s.sum()
        est = w @ bvec
        se = float(np.sqrt(w @ V @ w))
        rows.append({"term": e, "estimate": est, "se": se})
    out = pd.DataFrame(rows)
    # média pós (0..max_e) com pesos iguais por e — mesmo critério da agregação dinâmica do CS
    tdist = stats.t(Gc - 1)
    out["ci_low"] = out.estimate - tdist.ppf(0.975) * out.se
    out["ci_high"] = out.estimate + tdist.ppf(0.975) * out.se
    post = tab.e.between(0, max_e - 1).to_numpy()   # exclui o bin final (e >= max_e)
    wpost = np.zeros(len(tab))
    for e in sorted(tab.e[post].unique()):
        sel = (tab.e == e).to_numpy()
        s = shares.loc[e].reindex(tab.g[sel]).to_numpy(float)
        wpost[sel] = s / s.sum()
    wpost /= wpost.sum()
    overall = {"estimate": float(wpost @ bvec), "se": float(np.sqrt(wpost @ V @ wpost))}
    overall["ci_low"] = overall["estimate"] - tdist.ppf(0.975) * overall["se"]
    overall["ci_high"] = overall["estimate"] + tdist.ppf(0.975) * overall["se"]
    overall["p_value"] = float(2 * tdist.sf(abs(overall["estimate"] / overall["se"])))
    return out, overall


# ============================================================================ Goodman-Bacon

def _twfe_beta(Yw: np.ndarray, Dw: np.ndarray) -> float:
    N, T = Yw.shape
    unit = np.repeat(np.arange(N), T)
    time = np.tile(np.arange(T), N)
    M = demean_twfe(np.column_stack([Yw.ravel(), Dw.ravel()]), unit, time)
    return float(M[:, 0] @ M[:, 1] / (M[:, 1] @ M[:, 1]))


def bacon_decomposition(w: Wide) -> tuple[pd.DataFrame, float]:
    """Goodman-Bacon (2021), painel balanceado, tratamento absorvente, com nunca tratados.
    Unidades tratadas no 1º ano (sem pré-período) entram como grupo 'sempre tratado'."""
    years, Y, G = w.years, w.Y, w.G
    T = len(years)
    D = (G[:, None] > 0) & (years[None, :] >= G[:, None])
    beta_twfe = _twfe_beta(Y, D.astype(float))
    timing = sorted(set(G[G > 0]))
    n = {g: (G == g).mean() for g in timing}
    nU = (G == 0).mean()
    Dbar = {g: (years >= g).mean() for g in timing}
    # variância de D residualizado (TWFE) na amostra completa
    N = len(G)
    Dd = demean_twfe(D.astype(float).reshape(-1, 1), np.repeat(np.arange(N), T), np.tile(np.arange(T), N))
    VD = float((Dd ** 2).mean())
    rows = []
    for k in timing:
        # tratado k vs nunca tratados
        sel = (G == k) | (G == 0)
        b = _twfe_beta(Y[sel], D[sel].astype(float))
        nkU = n[k] / (n[k] + nU)
        s = (n[k] + nU) ** 2 * nkU * (1 - nkU) * Dbar[k] * (1 - Dbar[k]) / VD
        rows.append({"tipo": "Tratado vs nunca tratado", "g_trat": k, "g_ctrl": 0, "estimate": b, "weight": s})
        for l in timing:
            if l <= k:
                continue
            nkl = n[k] / (n[k] + n[l])
            sel = (G == k) | (G == l)
            # k (cedo) vs l (tarde, ainda não tratado): períodos t < l
            tm = years < l
            b1 = _twfe_beta(Y[sel][:, tm], D[sel][:, tm].astype(float))
            s1 = (((n[k] + n[l]) * (1 - Dbar[l])) ** 2 * nkl * (1 - nkl)
                  * ((Dbar[k] - Dbar[l]) / (1 - Dbar[l])) * ((1 - Dbar[k]) / (1 - Dbar[l])) / VD)
            rows.append({"tipo": "Cedo vs tarde (controle ainda não tratado)", "g_trat": k, "g_ctrl": l,
                         "estimate": b1, "weight": s1})
            # l (tarde) vs k (já tratado): períodos t >= k  -> comparação "proibida"
            tm = years >= k
            b2 = _twfe_beta(Y[sel][:, tm], D[sel][:, tm].astype(float))
            s2 = (((n[k] + n[l]) * Dbar[k]) ** 2 * nkl * (1 - nkl)
                  * (Dbar[l] / Dbar[k]) * ((Dbar[k] - Dbar[l]) / Dbar[k]) / VD)
            rows.append({"tipo": "Tarde vs cedo (controle já tratado)", "g_trat": l, "g_ctrl": k,
                         "estimate": b2, "weight": s2})
    out = pd.DataFrame(rows)
    out = out[out.weight > 0]
    return out, beta_twfe
