"""Rodada 2 — 03: conflito e PIB per capita (Q1, §6.3).

Bateria no onset T1 (sem exigir pesquisas; tratados × nunca T1/nunca FCS):
CS REG (nunca e ainda não tratados), CS sem covariáveis, Sun–Abraham, BJS (did2s), DiD empilhada de médias,
event study −5..+10, teste conjunto de pré-tendências, Rambachan–Roth (08_robustness.honest_rm),
placebo por permutação (500, 08_robustness.placebo), antecipação 1 e 2.
T3 contínuo (WAOSS) com escaladas/desescaladas e efeito líquido do placebo.
Causalidade reversa: coeficientes pré-onset reportados explicitamente.
Luminosidade noturna: não incluída (sem série harmonizada por país baixada; ver download_gaps / relatório).
"""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import common as C  # noqa: E402
from r2config import FIG, TAB  # noqa: E402

rob = importlib.import_module("08_robustness")
OUT = {"ln_gdppc": "log do PIB per capita PPC", "gdppc_growth": "crescimento do PIB per capita (Δlog)"}


def main() -> None:
    p = C.panel()
    d = C.onset_sample(p)
    rows, dyn, hd = [], [], []
    d_all, p_all = d, p
    for y, lab in OUT.items():
        # crescimento (Δlog) não existe em 1990: painel balanceado começa em 1991
        d = d_all[d_all.year >= 1991] if y == "gdppc_growth" else d_all
        p = p_all[p_all.year >= 1991] if y == "gdppc_growth" else p_all
        specs = [("CS REG, nunca tratados", dict(control="never")), ("CS REG, ainda não tratados", dict(control="notyet")),
                 ("CS sem covariáveis, nunca tratados", dict(control="never", method="unc")),
                 ("CS REG, antecipação 1", dict(control="never", anticipation=1)),
                 ("CS REG, antecipação 2", dict(control="never", anticipation=2))]
        for name, kw in specs:
            r = C.cs(d, y, **kw)
            rows.append({"outcome": y, "estimator": name, **r["row"]})
            dyn.append(r["r"]["dyn"]["table"].assign(outcome=y, estimator=name))
            if name == "CS REG, nunca tratados":
                C.plot_es(r["r"]["dyn"]["table"], f"{lab} — CS REG", FIG / f"q1_event_study_{y}")
                dropped = r["r"]["info"].get("dropped_unbalanced", [])
            print(f"  {y:13s} {name:36s} ATT = {r['row']['estimate']:8.4f} (EP {r['row']['se']:.4f}); n_trat "
                  f"{r['row']['n_treated']}; pré-tend. p = {r['row']['pretrend_p']:.3f}")
        sa_dyn, sa = C.dt.sun_abraham(d.dropna(subset=[y]), y, -5, 10)
        rows.append({"outcome": y, "estimator": "Sun-Abraham (IW)", **sa})
        dyn.append(sa_dyn.assign(outcome=y, estimator="Sun-Abraham"))
        b = C.bjs(d, y)
        dyn.append(b.pop("dyn").assign(outcome=y, estimator="BJS/did2s"))
        rows.append({"outcome": y, "estimator": "BJS/did2s", **b})
        rows.append({"outcome": y, "estimator": "DiD empilhada de médias", **C.stacked_means(d, y)})
        for var, lab2 in [("g_high_pw5", "só alta intensidade"), ("g_main_pw3", "janela de paz 3"),
                          ("g_main_pw10", "janela de paz 10"), ("g_sb_pw5", "mortes state-based"),
                          ("g_noconc_pw5", "sem regra de eventos concentrados")]:
            rows.append({"outcome": y, "estimator": f"CS REG — {lab2}", **C.cs(C.onset_sample(p, var), y)["row"]})
        rows.append({"outcome": y, "estimator": "CS REG — controles com fragilidade institucional",
                     **C.cs(C.onset_sample(p, ctrl="ctrl_incl_inst"), y)["row"]})
        # Rambachan–Roth e placebo
        h = rob.honest_rm(d, y)
        hd.append(h)
        actual, dist, pval = rob.placebo(d, y)
        rows.append({"outcome": y, "estimator": "Placebo por permutação (CS sem X; 500)", "estimate": actual,
                     "se": float(dist.std()), "p_value": pval, "n_treated": int(d.treated.groupby(d.iso3).max().sum())})
        print(f"  {y}: placebo p = {pval:.3f}; descartados por painel desbalanceado: {len(dropped)}")
    res = pd.DataFrame(rows)
    res.to_csv(TAB / "gdp_effect.csv", index=False)
    ev = pd.concat(dyn)
    ev.to_csv(TAB / "gdp_effect_event_study.csv", index=False)
    pd.concat(hd).to_csv(TAB / "gdp_effect_honestdid.csv", index=False)
    pre = ev[(ev.term < 0) & (ev.estimator == "CS REG, nunca tratados")]
    pre.to_csv(TAB / "gdp_effect_pretrends.csv", index=False)
    p = p_all
    # T3 contínuo
    w = []
    for y in OUT:
        r = C.waoss(p, y)
        w.append({"outcome": y, **r})
        print(f"  WAOSS {y}: θ = {r['efeito_all']:.4f} (EP {r['efeito_se_all']:.4f}); escalada {r['efeito_up']:.4f} "
              f"(EP {r['efeito_se_up']:.4f}); placebo escalada {r['placebo_up']:.4f}; líquido {r['liquido_up']:.4f} "
              f"(EP {r['liquido_se_up']:.4f}); desescalada {r['efeito_down']:.4f}")
    pd.DataFrame(w).to_csv(TAB / "gdp_effect_waoss.csv", index=False)
    print("\n" + res[["outcome", "estimator", "estimate", "se", "p_value", "n_treated"]].round(4).to_string(index=False))
    print("\nPré-onset (ln_gdppc):\n" + pre[pre.outcome == "ln_gdppc"][["term", "estimate", "se"]].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
