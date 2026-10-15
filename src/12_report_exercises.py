"""Etapa 12 — gera report/exercicios.md (exercícios 1 e 2) a partir de outputs/tables."""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import REPORT, TABLES  # noqa: E402

rep = importlib.import_module("09_report")
f, md_table, sig = rep.f, rep.md_table, rep.sig
T = lambda n: pd.read_csv(TABLES / n)  # noqa: E731
OUTL = {"pov_rate": "taxa de pobreza (p.p.)", "ln_n_poor": "log nº de pobres", "asinh_n_poor": "asinh nº de pobres",
        "d_ln_n_poor": "Δlog nº de pobres"}


def ci(r):
    return f"[{f(r.ci_low)}; {f(r.ci_high)}]"


def main() -> None:
    e1 = T("ex1_intensity_income.csv")
    c1 = T("ex1_cohorts.csv")
    h1 = T("ex1_honestdid.csv")
    tw = T("ex2_continuous_twfe.csv")
    wa = T("ex2_continuous_waoss.csv")
    mech = T("ex2_continuous_mechanism.csv")
    main_r = T("main_results.csv")
    L = []
    A = L.append

    A("# Exercícios adicionais: intensidade, renda e tratamento contínuo\n")
    A("*Gerado por `src/12_report_exercises.py` a partir de `outputs/tables/ex1_*` e `ex2_*`. "
      "Complementa `report/report.md`.*\n")

    # ================================================================== Exercício 1
    A("## Exercício 1 — Tratamento restrito por intensidade (≥ 1 morte/100 mil) e sem países de renda alta\n")
    lit = c1[c1.spec == "filtro_literal"]
    m1 = c1[c1.spec == "limiar_1"]
    A(f"**Por que duas leituras.** Aplicado literalmente aos onsets originais (máximo de mortes nos 3 primeiros anos "
      f"≥ 1/100 mil, sem renda alta), o filtro deixa só {len(lit)} tratados ({' '.join(sorted(lit.iso3))}). A leitura "
      "principal muda o que conta como conflito: um país-ano só é \"em conflito\" se tiver ≥ 1 morte em combate por "
      "100 mil hab. no território (antes de 1989 usa-se o ACD, porque não há dados de mortes). O onset passa a ser o "
      "1º ano acima do limiar após ≥ 5 anos abaixo dele, com as mesmas regras de elegibilidade (≥ 3 pesquisas antes). "
      f"Isso dá {len(m1)} tratados e traz de volta países antes \"sempre tratados\" por conflitos crônicos de baixa "
      "intensidade que tiveram uma escalada. Países de renda alta (classificação do Banco Mundial em g−1 para "
      "tratados e no 1º ano disponível para controles) saem da amostra.\n")
    A("**Coortes por especificação** (`ex1_cohorts.csv`):\n")
    cs = c1.groupby("spec").apply(lambda d: pd.Series({"n": len(d), "coortes": " ".join(
        f"{r.iso3}{int(r.g)}" for r in d.sort_values("g").itertuples())}), include_groups=False).reset_index()
    A(md_table(cs))
    A("\n**Especificação principal (limiar ≥ 1/100 mil, sem renda alta), todos os estimadores:**\n")
    t = e1[e1.spec == "limiar_1"][["outcome", "estimator", "estimate", "se", "ci_low", "ci_high", "p_value", "n_treated", "pretrend_p"]]
    A(md_table(t))
    A("\n**Variantes (CS REG, nunca tratados):**\n")
    t = e1[(e1.spec != "limiar_1") & (e1.estimator == "CS (REG, nunca tratados)")]
    A(md_table(t[["descricao", "outcome", "estimate", "se", "ci_low", "ci_high", "p_value", "n_treated", "pretrend_p"]]))
    ref = e1[(e1.spec == "limiar_1") & (e1.estimator == "CS (REG, nunca tratados)")].set_index("outcome")
    orig = main_r[main_r.estimator == "CS (REG, nunca tratados) — simple"].set_index("outcome")
    sa = e1[(e1.spec == "limiar_1") & (e1.estimator == "Sun-Abraham (IW)")].set_index("outcome")
    A("\n**Leitura.**\n")
    A(f"- Taxa de pobreza: ATT = {f(ref.loc['pov_rate', 'estimate'])} p.p. (IC {ci(ref.loc['pov_rate'])}; "
      f"{sig(ref.loc['pov_rate', 'p_value'])}), contra {f(orig.loc['pov_rate', 'estimate'])} na definição original. "
      f"Pré-tendências não rejeitadas (p = {f(ref.loc['pov_rate', 'pretrend_p'], 3)}).")
    A(f"- Número de pobres: log = {f(ref.loc['ln_n_poor', 'estimate'])} (IC {ci(ref.loc['ln_n_poor'])}); asinh = "
      f"{f(ref.loc['asinh_n_poor', 'estimate'])} (IC {ci(ref.loc['asinh_n_poor'])}). As estimativas pontuais "
      + ("são maiores que na definição original e positivas em todas as variantes, mas "
         if (e1[e1.outcome.isin(['ln_n_poor', 'asinh_n_poor']) & e1.estimator.str.startswith('CS')].estimate > 0).all()
         else "variam de sinal entre variantes e ")
      + ("o IC da especificação principal inclui zero." if ref.loc['ln_n_poor', 'ci_low'] <= 0 <= ref.loc['ln_n_poor', 'ci_high']
         else "o IC da especificação principal exclui zero."))
    A(f"- Sun–Abraham dá EP muito menores (ex.: log nº de pobres {f(sa.loc['ln_n_poor', 'estimate'])}, EP "
      f"{f(sa.loc['ln_n_poor', 'se'])}). Com coortes de um único país, cada interação coorte × período é identificada "
      "por um só cluster e o EP agrupado não é confiável. Esses EPs não devem ser usados para inferência; o "
      "bootstrap multiplicador do CS é a referência.")
    hs = h1[(h1.alvo == "média e ∈ [0,5]") & h1.M.astype(str).isin(["0", "1", "SD(0): tendência linear extrapolada"])]
    A("- Sensibilidade Rambachan–Roth (aprox., média e ∈ [0,5]), `ex1_honestdid.csv`:\n")
    hs2 = hs[["outcome", "M", "theta", "ci_low", "ci_high"]].copy()
    hs2["M"] = hs2.M.astype(str).str.replace(".", ",", regex=False)
    A(md_table(hs2))
    A("\n![](../outputs/figures/ex1_event_study_pov_rate_cs_never_reg.png)")
    A("![](../outputs/figures/ex1_event_study_asinh_n_poor_cs_never_reg.png)\n")

    # ================================================================== Exercício 2
    A("## Exercício 2 — Tratamento não absorvente com intensidade contínua\n")
    A("Tratamento D_it = mortes em combate (state-based) no território por 100 mil hab., ano a ano, entrando e "
      "saindo livremente. Uma escalada de 1 para 50/100 mil é variação de tratamento. Amostra: todos os países "
      "soberanos (inclusive os excluídos do desenho de onset, como os \"sempre tratados\"), 1990–2024; variante sem "
      "renda alta. Como a distribuição de D é muito assimétrica (Síria ≈ 186/100 mil), a dose é usada em duas escalas: "
      "linear e **asinh(D)** (≈ log para D grande).\n")
    A("**Estimadores** (`src/11_exercise_continuous.py`):\n")
    A("1. *TWFE nível*: y = α_i + λ_t + βD. Sujeito aos vieses de TWFE com efeitos heterogêneos (de Chaisemartin & "
      "D'Haultfœuille, 2020); só como referência.")
    A("2. *Defasagens distribuídas*: D em t+2…t−5. As antecipações (t+1, t+2) testam causalidade reversa; o "
      "cumulativo soma L0…L5.")
    A("3. *Primeiras diferenças*: Δy = λ_t + βΔD (+ ΔD_{t+1}).")
    A("4. **WAOSS (principal)**: switchers (|ΔD| > ε) contra quasi-stayers (|ΔD| ≤ ε) com o mesmo nível de partida "
      "(faixas de D_{t−1}: 0; ≤ 0,1; ≤ 1; ≤ 10; > 10) e efeitos de ano; θ = Σ sinal(ΔD)(ΔY − ΔŶ0)/Σ|ΔD|, ou seja, o "
      "efeito médio por unidade de dose ponderado pela magnitude da mudança. Também é estimado separadamente para "
      "escaladas e desescaladas. Placebo: a mesma conta com ΔY do período anterior. EP por bootstrap de países "
      "(300 réplicas). **Implementação própria**, inspirada em de Chaisemartin, D'Haultfœuille, Pasquier, Sow & "
      "Vazquez-Bare (2024). Validada em simulação (`tests/test_did_tools.py`: θ̂ = β com seleção em nível), mas não "
      "é o pacote oficial (`did_multiplegt_dyn` / `did_had`).\n")

    for D, lab in [("asinh_brd_pc", "asinh(mortes/100 mil)"), ("brd_pc", "mortes/100 mil (linear)")]:
        A(f"### Dose = {lab}\n")
        t = tw[(tw.dose == D) & ((tw.modelo != "Defasagens distribuídas") | tw.termo.str.contains("cumulativo|Wald"))]
        A(md_table(t[["amostra", "outcome", "modelo", "termo", "estimate", "se", "p_value"]], {"estimate": 4, "se": 4}))
        w = wa[(wa.dose == D) & (wa.eps == 0.1)]
        A("\n**WAOSS (ε = 0,1):**\n")
        A(md_table(w[["amostra", "outcome", "tipo", "all", "se_all", "p_all", "up", "se_up", "p_up", "down", "se_down",
                      "n_sw", "n_up", "n_down"]].rename(columns={"all": "θ", "se_all": "EP", "p_all": "p",
                      "up": "θ escalada", "se_up": "EP esc.", "p_up": "p esc.", "down": "θ desescalada", "se_down": "EP desesc.",
                      "n_sw": "switchers", "n_up": "↑", "n_down": "↓"}), {"θ": 4, "EP": 4, "θ escalada": 4, "EP esc.": 4,
                                                                        "θ desescalada": 4, "EP desesc.": 4}))
        A("")
    A("**Sensibilidade a ε** (`ex2_continuous_waoss.csv`, efeito, amostra completa):\n")
    s = wa[(wa.amostra == "todos") & (wa.tipo == "efeito")][["dose", "outcome", "eps", "all", "se_all", "p_all", "n_sw"]]
    A(md_table(s, {"all": 4, "se_all": 4}))

    A("\n### Mecanismo e dados observados (dose asinh, amostra completa, ε = 0,1)\n")
    A(md_table(mech[["descricao", "tipo", "n_pairs", "all", "se_all", "p_all", "up", "se_up", "n_sw"]]
               .rename(columns={"all": "θ", "se_all": "EP", "p_all": "p", "up": "θ escalada", "se_up": "EP esc.",
                                "n_sw": "switchers"}), {"θ": 4, "EP": 4, "θ escalada": 4, "EP esc.": 4}))

    # ------------------------------------------------------------------ leitura ex. 2
    w0 = wa[(wa.amostra == "todos") & (wa.dose == "asinh_brd_pc") & (wa.eps == 0.1)].set_index(["outcome", "tipo"])
    pe, pp = w0.loc[("pov_rate", "efeito")], w0.loc[("pov_rate", "placebo")]
    le, lp = w0.loc[("ln_n_poor", "efeito")], w0.loc[("ln_n_poor", "placebo")]
    dA = float(np.arcsinh(50) - np.arcsinh(1))
    g = mech[(mech.outcome == "ln_gdppc") & (mech.tipo == "efeito")].iloc[0]
    gp = mech[(mech.outcome == "ln_gdppc") & (mech.tipo == "placebo")].iloc[0]
    ob = mech[(mech.outcome == "pov_rate_obs") & (mech.tipo == "efeito")].iloc[0]
    lin_lead = tw[(tw.amostra == "todos") & (tw.dose == "brd_pc") & (tw.outcome == "pov_rate")
                  & tw.termo.str.contains("Wald")].iloc[0]
    A("\n### Leitura\n")
    A(f"- **Taxa de pobreza.** Com a dose em asinh, o WAOSS dá θ = {f(pe['all'], 3)} p.p. por unidade de asinh "
      f"(EP {f(pe.se_all, 3)}; p = {f(pe.p_all, 3)}), com placebo {f(pp['all'], 3)} (EP {f(pp.se_all, 3)}). Uma escalada de "
      f"1 para 50 mortes/100 mil é Δasinh = {f(dA)}, o que implica ≈ {f(pe['all'] * dA, 1)} p.p. de pobreza extrema no ano "
      "da escalada. Primeiras diferenças e TWFE vão na mesma direção, e o modelo de defasagens sugere efeito "
      "cumulativo maior em 5 anos.")
    A(f"- **Escaladas × desescaladas.** O efeito aparece nas escaladas ({f(pe.up, 3)}, EP {f(pe.se_up, 3)}), mas o "
      f"**placebo das escaladas também é positivo** ({f(pp.up, 3)}, EP {f(pp.se_up, 3)}; no log do nº de pobres "
      f"{f(lp.up, 3)}, EP {f(lp.se_up, 3)}, contra efeito {f(le.up, 3)}). A pobreza já vinha subindo no ano anterior à "
      "escalada. Escaladas tendem a ocorrer em trajetórias de deterioração, o que é compatível com causalidade reversa "
      "ou com escaladas em série. Parte do efeito contemporâneo provavelmente não é causal.")
    A(f"- **Escala linear.** Por morte/100 mil, os efeitos são pequenos e dominados por casos extremos. No modelo de "
      f"defasagens, as antecipações são conjuntamente significativas para a taxa (Wald p = {f(lin_lead.p_value, 3)}), "
      "o que reforça o problema de pré-tendência. A escala asinh é a mais confiável.")
    A(f"- **Mecanismo.** A intensidade reduz o PIB per capita: θ = {f(g['all'], 4)} log-pontos por unidade de asinh "
      f"(EP {f(g.se_all, 4)}; escalada {f(g.up, 4)}), com placebo {f(gp['all'], 4)} (EP {f(gp.se_all, 4)}). Nos anos sem "
      "pesquisa, o PIP extrapola a pobreza pelo crescimento das contas nacionais. Logo, o efeito sobre a pobreza na "
      "série lineup é, em boa medida, a queda do PIB repassada mecanicamente, com distribuição constante.")
    A(f"- **Só dados observados.** Restringindo a pares de anos com pesquisa nos dois anos, sobram {int(ob.n_sw)} "
      f"switchers; θ = {f(ob['all'], 3)} (EP {f(ob.se_all, 3)}). Não há informação suficiente para confirmar ou "
      "refutar o efeito com pobreza medida.\n")
    A("### Comparação dos dois exercícios\n")
    A("- O desenho de onset (exercício 1) mede o efeito médio de *entrar* em conflito intenso após um período de paz e "
      "não encontra efeito significativo na taxa. O desenho contínuo (exercício 2) usa toda a variação de intensidade, "
      "inclusive escaladas em conflitos crônicos. Isso aumenta muito a variação útil, e o desenho detecta uma associação "
      "positiva entre intensidade e pobreza estimada.")
    A("- A diferença é coerente com efeitos concentrados em escaladas de alta intensidade, mas o placebo das escaladas e "
      "o canal do PIB na extrapolação do PIP impedem uma leitura causal forte. A evidência é de que conflitos intensos "
      "reduzem a renda média e, por construção dos dados, elevam a pobreza estimada. Não há evidência independente com "
      "pobreza medida por pesquisas.\n")
    A("![](../outputs/figures/ex2_distributed_lags_pov_rate.png)")
    A("![](../outputs/figures/ex2_distributed_lags_ln_n_poor.png)\n")

    (REPORT / "exercicios.md").write_text("\n".join(L), encoding="utf-8")
    print("report/exercicios.md gerado.")


if __name__ == "__main__":
    main()
