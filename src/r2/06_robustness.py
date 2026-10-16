"""Rodada 2 — 06: robustez transversal (§7).

Para os resultados-chave de Q2 (survey_pip, share_extrapolated), Q1 (ln_gdppc) e Q3 (pov_rate, amostra com
≥ 3 pesquisas pré-onset), reestima com:
- intensidade: média+ (principal) × só alta;
- janela de paz 3, 5, 10;
- mortes totais × só state-based; com × sem regra de eventos concentrados;
- controles sem × com fragilidade institucional;
- definição da rodada 1 (onset ≥ 25 mortes, ACD), com os controles da rodada 1;
- dupla fonte ACLED+UCDP: pendente (sem credenciais ACLED) — registrado como linha "não estimado".
Estimadores: CS REG nunca tratados (referência) e DiD empilhada de médias (robusta ao ano-base).
"""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import common as C  # noqa: E402
from r2config import MIN_PRE_SURVEYS, PROCESSED, TAB  # noqa: E402

pov5 = importlib.import_module("05_poverty")
SPECS = [("principal (média+, PW 5)", "g_t1", "ctrl_main"), ("só alta intensidade", "g_high_pw5", "ctrl_main"),
         ("janela de paz 3", "g_main_pw3", "ctrl_main"), ("janela de paz 10", "g_main_pw10", "ctrl_main"),
         ("mortes state-based", "g_sb_pw5", "ctrl_main"), ("sem regra de eventos concentrados", "g_noconc_pw5", "ctrl_main"),
         ("controles com fragilidade institucional", "g_t1", "ctrl_incl_inst"), ("definição da rodada 1 (25 mortes)", "g_r1", "ctrl_r1")]
OUTCOMES = [("Q2", "survey_pip"), ("Q2", "share_extrapolated"), ("Q1", "ln_gdppc"), ("Q3", "pov_rate")]


def add_r1(p: pd.DataFrame) -> pd.DataFrame:
    r1 = pd.read_parquet(PROCESSED / "panel.parquet").drop_duplicates("iso3").set_index("iso3")
    p["g_r1"] = p.iso3.map(r1.g.where(r1.status == "tratado"))
    p["ctrl_r1"] = p.iso3.map((r1.status == "nunca_tratado").astype(int)).fillna(0).astype(int)
    return p


def main() -> None:
    p = add_r1(C.panel())
    rows = []
    for q, y in OUTCOMES:
        base = p[p.in_pip == 1] if q != "Q1" else p
        for lab, gcol, ctrl in SPECS:
            d = C.onset_sample(base, gcol, ctrl)
            if q == "Q3":
                d = d[(d.treated == 0) | d.iso3.isin(
                    set((s := d[(d.treated == 1) & (d.year < d.g)].groupby("iso3").survey_pip.sum())[s >= MIN_PRE_SURVEYS].index))]
            for name, f in [("CS REG, nunca tratados", lambda d_: C.cs(d_, y)["row"]),
                            ("DiD empilhada de médias", lambda d_: C.stacked_means(d_, y, reps=499))]:
                try:
                    r = f(d)
                except Exception as e:  # noqa: BLE001
                    r = {"estimate": np.nan, "nota": f"falhou: {e}"}
                rows.append({"pergunta": q, "outcome": y, "especificacao": lab, "estimator": name, **r})
            print(f"  {q} {y:18s} {lab:42s} CS = {rows[-2].get('estimate', np.nan):8.4f}  empilhada = {rows[-1].get('estimate', np.nan):8.4f}  "
                  f"n_trat = {rows[-2].get('n_treated', '-')}")
        rows.append({"pergunta": q, "outcome": y, "especificacao": "dupla fonte ACLED + UCDP", "estimator": "-",
                     "nota": "não estimado: credenciais ACLED pendentes (ponto de parada a)"})
    out = pd.DataFrame(rows)
    out.to_csv(TAB / "robustness_grid.csv", index=False)
    _ = pov5


if __name__ == "__main__":
    main()
