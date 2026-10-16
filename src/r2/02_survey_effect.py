"""Rodada 2 — 02: conflito e produção de dados (Q2, §6.2).

- CS REG, onset T1 (sem exigir pesquisas pré-onset), controles nunca e ainda não tratados, para
  survey_pip, survey_any e share_extrapolated; event study −5..+10 (duração do apagão).
- WAOSS com T3 (asinh das mortes/100 mil), escaladas × desescaladas, com placebo.
- Heterogeneidade (subamostras de tratados, mesmos controles): missão de paz da ONU antes do onset,
  CPIA pré-onset (só IDA, acima × abaixo da mediana), região (África Subsaariana × demais), renda (baixa × demais).
  Correção de Holm para múltiplos testes.
- Comparação com a rodada 1 (LPM survey ~ post | país + ano = −8,2 p.p.): mesma regressão com T1.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyfixest as pf

sys.path.insert(0, str(Path(__file__).parent))
import common as C  # noqa: E402
from r2config import FIG, ROOT, TAB  # noqa: E402

OUT = {"survey_pip": "Pesquisa nacional no PIP no ano", "survey_any": "Alguma pesquisa (PIP, DHS ou MICS)",
       "share_extrapolated": "Ponto do PIP extrapolado ou por modelo"}


def main() -> None:
    p = C.panel()
    pip = p[p.in_pip == 1]
    d = C.onset_sample(pip)
    rows, dyn, het = [], [], []
    tr = d[d.treated == 1].drop_duplicates("iso3").set_index("iso3")
    print(f"Amostra: {tr.shape[0]} tratados T1, {d[d.treated == 0].iso3.nunique()} controles (nunca T1, nunca FCS)")
    for y, lab in OUT.items():
        for name, kw in [("CS REG, nunca tratados", dict(control="never")), ("CS REG, ainda não tratados", dict(control="notyet")),
                         ("CS sem covariáveis, nunca tratados", dict(control="never", method="unc"))]:
            r = C.cs(d, y, **kw)
            rows.append({"outcome": y, "estimator": name, **r["row"]})
            dyn.append(r["r"]["dyn"]["table"].assign(outcome=y, estimator=name))
            if name.startswith("CS REG, nunca"):
                C.plot_es(r["r"]["dyn"]["table"], f"{lab} — CS REG", FIG / f"q2_event_study_{y}")
            print(f"  {y:19s} {name:36s} ATT = {r['row']['estimate']:7.3f} (EP {r['row']['se']:.3f}); "
                  f"n_trat {r['row']['n_treated']}; pré-tend. p = {r['row']['pretrend_p']:.3f}")
        # estimadores que usam todo o período pré como base
        b = C.bjs(d, y)
        dyn.append(b.pop("dyn").assign(outcome=y, estimator="BJS/did2s"))
        rows.append({"outcome": y, "estimator": "BJS/did2s (imputação, base = todo o pré)", **b})
        s = C.stacked_means(d, y)
        rows.append({"outcome": y, "estimator": "DiD empilhada de médias (g−5..g−1 × g..g+5)", **s})
        for var, lab2 in [("g_high_pw5", "só alta intensidade"), ("g_main_pw10", "janela de paz 10")]:
            dv = C.onset_sample(p[p.in_pip == 1], var)
            rows.append({"outcome": y, "estimator": f"DiD empilhada de médias — {lab2}", **C.stacked_means(dv, y)})
            rows.append({"outcome": y, "estimator": f"CS REG, nunca tratados — {lab2}", **C.cs(dv, y)["row"]})
        print(f"  {y:19s} BJS ATT = {b['estimate']:.3f} (EP {b['se']:.3f}); empilhada = {s['estimate']:.3f} (EP {s['se']:.3f})")
        # heterogeneidade (estimador de referência)
        cp = tr.cpia_pre.dropna()
        groups = {"missão de paz pré-onset": tr.pko_pre == 1, "sem missão de paz pré-onset": tr.pko_pre != 1,
                  "CPIA pré ≤ mediana (IDA)": tr.cpia_pre <= cp.median(), "CPIA pré > mediana (IDA)": tr.cpia_pre > cp.median(),
                  "África Subsaariana": tr.region_code == "SSF", "fora da África Subsaariana": tr.region_code != "SSF",
                  "renda baixa pré": tr.income_group_pre == "L", "renda média/alta pré": tr.income_group_pre.isin(["LM", "UM", "H"]),
                  "trajetória FCS crônica/entrada": tr.trajetoria.isin(["cronico", "entrada"]),
                  "nunca FCS": tr.trajetoria == "nunca"}
        for g, m in groups.items():
            isos = set(tr.index[m.fillna(False)])
            sub = d[(d.treated == 0) | d.iso3.isin(isos)]
            try:
                r = C.cs(sub, y)
            except Exception as e:  # noqa: BLE001
                print(f"    {g}: falhou ({e})")
                continue
            het.append({"outcome": y, "grupo": g, "estimador": "CS REG", **r["row"]})
            het.append({"outcome": y, "grupo": g, "estimador": "DiD empilhada", **C.stacked_means(sub, y, reps=499)})
    res = pd.DataFrame(rows)
    hetd = pd.DataFrame(het)
    hetd["p_holm"] = hetd.groupby("estimador").p_value.transform(C.holm)
    # WAOSS contínuo (todos os países do PIP, inclusive sempre tratados)
    w = []
    for y in OUT:
        r = C.waoss(pip, y)
        w.append({"outcome": y, **r})
        print(f"  WAOSS {y}: θ = {r['efeito_all']:.4f} (EP {r['efeito_se_all']:.4f}); escalada {r['efeito_up']:.4f}; "
              f"placebo escalada {r['placebo_up']:.4f}; líquido {r['liquido_up']:.4f} (EP {r['liquido_se_up']:.4f})")
    # comparação com a rodada 1: LPM com efeitos fixos
    lpm = []
    for y in OUT:
        m = pf.feols(f"{y} ~ post | iso3 + year", data=d.dropna(subset=[y]), vcov={"CRV1": "iso3"}).tidy().iloc[0]
        lpm.append({"outcome": y, "estimator": "LPM TWFE (como rodada 1)", "estimate": m.Estimate, "se": m["Std. Error"],
                    "ci_low": m["2.5%"], "ci_high": m["97.5%"], "p_value": m["Pr(>|t|)"], "n_treated": len(tr)})
    r1 = pd.read_csv(ROOT / "outputs" / "tables" / "missing_survey_regression.csv")
    r1 = r1[r1.modelo == "estatico"].iloc[0]
    lpm.append({"outcome": "survey_pip", "estimator": "Rodada 1 (onset 25 mortes, LPM TWFE)", "estimate": r1.Estimate,
                "se": r1["Std. Error"], "p_value": r1["Pr(>|t|)"], "n_treated": 33})
    res = pd.concat([res, pd.DataFrame(lpm)], ignore_index=True)
    res.to_csv(TAB / "survey_effect.csv", index=False)
    pd.concat(dyn).to_csv(TAB / "survey_effect_event_study.csv", index=False)
    hetd.to_csv(TAB / "survey_effect_heterogeneity.csv", index=False)
    pd.DataFrame(w).to_csv(TAB / "survey_effect_waoss.csv", index=False)
    # duração do apagão: anos pós-onset com IC excluindo zero (survey_pip)
    t = pd.concat(dyn)
    t = t[(t.outcome == "survey_pip") & (t.estimator == "CS REG, nunca tratados") & (t.term >= 0)]
    print("\nEvent study survey_pip (e ≥ 0):\n" + t[["term", "estimate", "se", "ci_low", "ci_high"]].round(3).to_string(index=False))
    print("\nComparação r1:\n" + pd.DataFrame(lpm).round(3).to_string(index=False))
    print("\nHeterogeneidade:\n" + hetd[["outcome", "grupo", "estimate", "se", "n_treated", "p_value", "p_holm"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
