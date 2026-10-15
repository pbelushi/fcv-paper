"""Etapa 13 — Exercício 3: decomposição regional do efeito no log do número de pobres.

Hipótese (usuário, 2026-10-15): no exercício 1 (limiar_1), o ATT ≈ +0,15 em ln_n_poor, com taxa ≈ 0,
vem de tratados com pobreza inicial muito baixa em Europa e Ásia Central (region_code == "ECS"),
onde pequenas variações em p.p. viram grandes variações em log.

Reusa a amostra/tratamento de 10_exercise_intensity.specs()["limiar_1"] e o estimador de
referência 07_estimate.run_cs(control="never", method="reg") (CS REG, covariáveis pré, bootstrap
multiplicador por país). Nada de CS é reimplementado aqui.

Saídas: outputs/tables/ex3_*.csv, outputs/figures/ex3_leave_one_out_*.png/.pdf; ao final
regenera report/exercicios.md (12_report_exercises), pois o run_all executa a etapa 12 antes da 13.
"""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import did_tools as dt  # noqa: E402
import plotstyle as ps  # noqa: E402
from config import FIGURES, TABLES  # noqa: E402

est = importlib.import_module("07_estimate")
ex1 = importlib.import_module("10_exercise_intensity")
REGION = "ECS"
OUT = ["pov_rate", "ln_n_poor", "asinh_n_poor"]
TOL_REPRO, TOL_IDENT = 1e-9, 1e-6
MIN_N = 5


def ref_cs(d: pd.DataFrame, y: str) -> dict:
    """Estimador de referência do exercício 1."""
    return est.run_cs(d, y, control="never", method="reg")


def summary(r: dict) -> dict:
    o, inf = r["simple"]["overall"], r["info"]
    return {**{k: o[k] for k in ("estimate", "se", "ci_low", "ci_high", "p_value")},
            "n_treated": inf["n_treated"], "n_controls": inf["n_units"] - inf["n_treated"]}


def subsample(d: pd.DataFrame, treated: set[str], controls: set[str] | None = None) -> pd.DataFrame:
    ctrl = (d.treated == 0) if controls is None else ((d.treated == 0) & d.iso3.isin(controls))
    return d[ctrl | ((d.treated == 1) & d.iso3.isin(treated))]


# ============================================================================ 0. reprodução

def check_reproduction(d: pd.DataFrame) -> None:
    ref = pd.read_csv(TABLES / "ex1_intensity_income.csv")
    ref = ref[(ref.spec == "limiar_1") & (ref.estimator == "CS (REG, nunca tratados)")].set_index("outcome")
    for y in OUT:
        s = summary(ref_cs(d, y))
        de, ds = abs(s["estimate"] - ref.loc[y, "estimate"]), abs(s["se"] - ref.loc[y, "se"])
        if de > TOL_REPRO or ds > TOL_REPRO or s["n_treated"] != ref.loc[y, "n_treated"]:
            sys.exit(f"PARADA: (a) não reproduz o exercício 1 em {y}: ATT {s['estimate']:.10f} vs "
                     f"{ref.loc[y, 'estimate']:.10f}; EP {s['se']:.10f} vs {ref.loc[y, 'se']:.10f}; "
                     f"n {s['n_treated']} vs {ref.loc[y, 'n_treated']}")
        print(f"  reprodução ok: {y:13s} ATT = {s['estimate']:.4f} (EP {s['se']:.4f}), n_trat = {s['n_treated']}")


# ============================================================================ 1. contribuições

def contributions(d: pd.DataFrame) -> pd.DataFrame:
    d = d.assign(ln_rate=np.log(d.pov_rate.where(d.pov_rate > 0)))
    ctrl = d[d.treated == 0]
    # controles com série completa de cada variável (mesma composição em todos os anos)
    cmean = {}
    for v in ["pov_rate", "ln_n_poor", "ln_rate"]:
        ok = ctrl.groupby("iso3")[v].apply(lambda s: s.notna().all())
        cmean[v] = ctrl[ctrl.iso3.isin(ok[ok].index)].groupby("year")[v].mean()
    rows = []
    for iso, t in d[d.treated == 1].groupby("iso3"):
        g = int(t.g.iloc[0])
        pre, post = t[t.year.between(g - 5, g - 1)], t[t.year.between(g, g + 5)]
        r = {"iso3": iso, "region_code": t.region_code.iloc[0], "ECS": int(t.region_code.iloc[0] == REGION), "g": g,
             "anos_pre": len(pre), "anos_pos": len(post),
             "pov_rate_pre": pre.pov_rate.mean(), "n_poor_pre": pre.n_poor.mean()}
        for v in ["pov_rate", "ln_n_poor", "ln_rate"]:
            dtr = post[v].mean() - pre[v].mean() if pre[v].notna().all() and post[v].notna().all() else np.nan
            dct = cmean[v].reindex(post.year).mean() - cmean[v].reindex(pre.year).mean()
            r[f"d_{v}_tratado"], r[f"d_{v}_controle"], r[f"d_{v}_dif"] = dtr, dct, dtr - dct
        r["log_indefinido"] = int(t.ln_n_poor.isna().any())
        rows.append(r)
    out = pd.DataFrame(rows).sort_values(["ECS", "pov_rate_pre"], ascending=[False, True])
    out.to_csv(TABLES / "ex3_treated_contributions.csv", index=False)
    return out


# ============================================================================ 2. subamostras

def region_att(d: pd.DataFrame) -> pd.DataFrame:
    tr = d[d.treated == 1].drop_duplicates("iso3")
    all_t = set(tr.iso3)
    ecs_t = set(tr.loc[tr.region_code == REGION, "iso3"])
    ecs_c = set(d.loc[(d.treated == 0) & (d.region_code == REGION), "iso3"])
    subs = [("(a) todos os tratados", all_t, None),
            (f"(b) sem tratados {REGION}", all_t - ecs_t, None),
            (f"(c) só tratados {REGION}", ecs_t, None),
            (f"(c') só tratados {REGION}, controles nunca tratados {REGION}", ecs_t, ecs_c)]
    rows = []
    for y in OUT:
        for lab, T, C in subs:
            try:
                s = summary(ref_cs(subsample(d, T, C), y))
            except Exception as e:  # noqa: BLE001
                print(f"  {lab} / {y}: falhou ({e})")
                continue
            rows.append({"outcome": y, "subamostra": lab, **s, "poucos_tratados": int(s["n_treated"] < MIN_N)})
            print(f"  {y:13s} {lab:58s} ATT = {s['estimate']:7.3f} (EP {s['se']:.3f}); "
                  f"n_trat = {s['n_treated']}, n_ctrl = {s['n_controls']}")
    out = pd.DataFrame(rows)
    out.to_csv(TABLES / "ex3_region_att.csv", index=False)
    return out


# ============================================================================ 3. leave-one-out

def leave_one_out(d: pd.DataFrame) -> pd.DataFrame:
    tr = d[d.treated == 1].drop_duplicates("iso3").set_index("iso3")
    rows = []
    for y in ["ln_n_poor", "pov_rate"]:
        full = summary(ref_cs(d, y))
        for iso in tr.index:
            s = summary(ref_cs(d[d.iso3 != iso], y))
            rows.append({"outcome": y, "retirado": iso, "region_code": tr.loc[iso, "region_code"],
                         "ECS": int(tr.loc[iso, "region_code"] == REGION), **s,
                         "att_completo": full["estimate"], "variacao": s["estimate"] - full["estimate"]})
    out = pd.DataFrame(rows)
    out.to_csv(TABLES / "ex3_leave_one_out.csv", index=False)
    for y, lab in [("ln_n_poor", "log do número de pobres"), ("pov_rate", "taxa de pobreza (p.p.)")]:
        t = out[out.outcome == y].sort_values("estimate").reset_index(drop=True)
        fig, ax = ps.plt.subplots(figsize=(6.5, 5.2))
        ax.grid(axis="x", color=ps.GRID)
        ax.grid(axis="y", visible=False)
        ax.axvline(0, color=ps.INK2, lw=1)
        ax.axvline(t.att_completo.iloc[0], color=ps.INK, lw=1.2, ls="--")
        for ecs, c, lg in [(0, ps.TREATED, "Demais tratados"), (1, ps.CONTROL, f"Tratado {REGION}")]:
            s = t[t.ECS == ecs]
            ax.errorbar(s.estimate, s.index, xerr=[s.estimate - s.ci_low, s.ci_high - s.estimate], fmt="o",
                        color=c, ms=6, lw=1.6, capsize=0, label=f"Sem este país: {lg[0].lower() + lg[1:]}")
        ax.set_yticks(t.index, t.retirado)
        ax.set_ylabel("País retirado")
        ax.set_xlabel(f"ATT (CS REG, nunca tratados); tracejado = estimativa completa ({t.att_completo.iloc[0]:.3f})"
                      .replace(".", ","))
        ax.set_title(f"Leave-one-out — {lab}", loc="left")
        ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(0, -0.12), ncol=2, frameon=False)
        ps.save(fig, FIGURES / f"ex3_leave_one_out_{y}")
    return out


# ============================================================================ 4. decomposição

def log_decomposition(d: pd.DataFrame, contrib: pd.DataFrame) -> pd.DataFrame:
    w, _ = dt.to_wide(d, "ln_n_poor", covars=est.COVARS)       # mesmas unidades do ATT de ln_n_poor
    dd = d[d.iso3.isin(w.units)].copy()
    dd["ln_rate"] = np.log(dd.pov_rate)                         # = ln(headcount) + ln(100)
    dd["ln_pop"] = np.log(dd.pop_pip)                           # reporting_pop do PIP
    R = {y: ref_cs(dd, y) for y in ["ln_n_poor", "ln_rate", "ln_pop"]}
    n_units = {y: R[y]["info"]["n_units"] for y in R}
    assert len(set(n_units.values())) == 1, f"amostras diferentes: {n_units}"
    agg = {y: R[y]["simple"]["overall"]["estimate"] for y in R}
    gap_agg = abs(agg["ln_rate"] + agg["ln_pop"] - agg["ln_n_poor"])
    cells = {y: R[y]["res"].cells.set_index(["g", "t"]).att for y in R}
    gap_cells = float(np.max(np.abs(cells["ln_rate"] + cells["ln_pop"] - cells["ln_n_poor"])))
    passed = bool(gap_agg < TOL_IDENT and gap_cells < TOL_IDENT)
    print(f"  identidade ATT(ln_rate) + ATT(ln_pop) = ATT(ln_n_poor): {agg['ln_rate']:.6f} + {agg['ln_pop']:.6f} = "
          f"{agg['ln_rate'] + agg['ln_pop']:.6f} vs {agg['ln_n_poor']:.6f}; |dif| agregado = {gap_agg:.2e}, "
          f"máx. por célula = {gap_cells:.2e} -> {'PASSOU' if passed else 'FALHOU'} (tol {TOL_IDENT})")
    rows = []
    for y in R:
        o = R[y]["simple"]["overall"]
        rows.append({"tipo": "agregado", "variavel": y, "iso3": "", "estimate": o["estimate"], "se": o["se"],
                     "ci_low": o["ci_low"], "ci_high": o["ci_high"], "p_value": o["p_value"],
                     "n_treated": R[y]["info"]["n_treated"], "n_units": n_units[y]})
    rows.append({"tipo": "teste_identidade", "variavel": "ln_rate + ln_pop - ln_n_poor", "iso3": "",
                 "estimate": agg["ln_rate"] + agg["ln_pop"] - agg["ln_n_poor"], "se": np.nan,
                 "gap_max_celulas": gap_cells, "tolerancia": TOL_IDENT, "passou": passed})
    # conversão para p.p. por país: pov_rate_pré × (exp(ATT) − 1), ATT agregado e ATT da coorte do país
    grp = R["ln_rate"]["group"]["table"].set_index("term").estimate
    tr = dd[dd.treated == 1].drop_duplicates("iso3")[["iso3", "g", "region_code"]]
    c = contrib.set_index("iso3")
    for r in tr.itertuples():
        pre = c.loc[r.iso3, "pov_rate_pre"]
        rows.append({"tipo": "pais_pp", "variavel": "ln_rate", "iso3": r.iso3, "region_code": r.region_code,
                     "ECS": int(r.region_code == REGION), "g": r.g, "pov_rate_pre": pre,
                     "att_ln_rate_agregado": agg["ln_rate"], "pp_com_att_agregado": pre * (np.exp(agg["ln_rate"]) - 1),
                     "att_ln_rate_coorte": grp.get(r.g, np.nan),
                     "pp_com_att_coorte": pre * (np.exp(grp.get(r.g, np.nan)) - 1),
                     "d_pov_rate_dif_observada": c.loc[r.iso3, "d_pov_rate_dif"]})
    out = pd.DataFrame(rows)
    out.to_csv(TABLES / "ex3_log_decomposition.csv", index=False)
    if not passed:
        sys.exit("PARADA: identidade da decomposição falhou.")
    return out


def main() -> None:
    d = ex1.specs(ex1.base_panel())["limiar_1"]
    tr = d[d.treated == 1].drop_duplicates("iso3")
    print(f"Amostra limiar_1: {tr.iso3.nunique()} tratados ({(tr.region_code == REGION).sum()} {REGION}: "
          f"{' '.join(sorted(tr[tr.region_code == REGION].iso3))}), {d[d.treated == 0].iso3.nunique()} nunca tratados")
    print("0. Reprodução do exercício 1:")
    check_reproduction(d)
    print("1. Contribuições por tratado:")
    contrib = contributions(d)
    print(contrib[["iso3", "region_code", "g", "pov_rate_pre", "d_pov_rate_dif", "d_ln_n_poor_dif", "d_ln_rate_dif"]]
          .round(3).to_string(index=False))
    print("2. ATT por subamostra:")
    region_att(d)
    print("3. Leave-one-out:")
    loo = leave_one_out(d)
    print(loo.sort_values(["outcome", "variacao"])[["outcome", "retirado", "region_code", "estimate", "variacao"]]
          .round(3).to_string(index=False))
    print("4. Decomposição do log do número de pobres:")
    log_decomposition(d, contrib)
    importlib.import_module("12_report_exercises").main()


if __name__ == "__main__":
    main()
