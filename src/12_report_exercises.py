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

    ex3_section(A)
    ex4_section(A)
    (REPORT / "exercicios.md").write_text("\n".join(L), encoding="utf-8")
    print("report/exercicios.md gerado.")


def ex3_section(A) -> None:
    """Exercício 3 (src/13_exercise_region_decomp.py); pulado se os CSVs ex3_ ainda não existem."""
    files = ["ex3_treated_contributions.csv", "ex3_region_att.csv", "ex3_leave_one_out.csv", "ex3_log_decomposition.csv"]
    if not all((TABLES / x).exists() for x in files):
        return
    con, reg, loo, dec = (T(x) for x in files)
    MIN_N = 5
    A("\n## Exercício 3 — Decomposição regional do efeito no número de pobres\n")
    A("*Gerado a partir de `outputs/tables/ex3_*.csv` (`src/13_exercise_region_decomp.py`). Especificação "
      "`limiar_1` do exercício 1, estimador de referência: CS com regressão de resultado, nunca tratados, "
      "covariáveis pré, bootstrap multiplicador por país.*\n")
    A("**Hipótese.** O ATT positivo no log do número de pobres, com taxa ≈ 0, viria de tratados com pobreza inicial "
      "muito baixa em Europa e Ásia Central (ECS), onde pequenas variações em p.p. viram grandes variações em log.\n")

    # --- 1. contribuições
    A("### 1. Contribuição de cada tratado (descritiva)\n")
    A("Médias em g−5..g−1 (pré) e g..g+5 (pós). Δ = pós − pré; controle = média dos nunca tratados nos mesmos anos; "
      "dif = tratado − controle. Logs indefinidos (zeros) aparecem como —.\n")
    A(md_table(con[["iso3", "region_code", "g", "pov_rate_pre", "n_poor_pre", "d_pov_rate_dif", "d_ln_n_poor_dif",
                    "d_ln_rate_dif"]].rename(columns={"pov_rate_pre": "pobreza pré (%)", "n_poor_pre": "nº pobres pré",
                    "d_pov_rate_dif": "Δ taxa (p.p.) dif", "d_ln_n_poor_dif": "Δ ln nº pobres dif",
                    "d_ln_rate_dif": "Δ ln taxa dif"}), {"pobreza pré (%)": 2, "nº pobres pré": 0}))
    ecs, oth = con[con.ECS == 1], con[con.ECS == 0]
    A(f"\nMediana da pobreza pré: ECS {f(ecs.pov_rate_pre.median())}% contra {f(oth.pov_rate_pre.median())}% nos demais. "
      f"Mediana de Δ ln nº pobres (dif): ECS {f(ecs.d_ln_n_poor_dif.median(), 3)} contra {f(oth.d_ln_n_poor_dif.median(), 3)}; "
      f"Δ taxa (dif): ECS {f(ecs.d_pov_rate_dif.median())} p.p. contra {f(oth.d_pov_rate_dif.median())} p.p.\n")

    # --- 2. subamostras
    A("### 2. ATT por subamostra de tratados (`ex3_region_att.csv`)\n")
    A(md_table(reg[["outcome", "subamostra", "estimate", "se", "ci_low", "ci_high", "p_value", "n_treated", "n_controls"]]))
    A(f"\nSubamostras com menos de {MIN_N} tratados: "
      + (", ".join(f"{r.subamostra} / {r.outcome} (n = {r.n_treated})" for r in reg[reg.n_treated < MIN_N].itertuples())
         or "nenhuma") + ". Nelas, reporto n e EP sem tirar conclusão de significância.\n")

    # --- 3. leave-one-out
    A("### 3. Leave-one-out (`ex3_leave_one_out.csv`)\n")
    A("![](../outputs/figures/ex3_leave_one_out_ln_n_poor.png)")
    A("![](../outputs/figures/ex3_leave_one_out_pov_rate.png)\n")
    ll = loo[loo.outcome == "ln_n_poor"].sort_values("variacao")
    n_ecs_ln = int(reg[(reg.outcome == "ln_n_poor") & reg.subamostra.str.startswith("(c)")].n_treated.iloc[0])
    ll = ll[~(ll.estimate == ll.att_completo)]       # países fora da amostra de ln (zeros) não alteram o ATT
    top = ll.head(n_ecs_ln)
    A(md_table(ll[["retirado", "region_code", "estimate", "se", "variacao"]].rename(columns={"variacao": "Δ vs completo"})))
    A(f"\nAs {n_ecs_ln} retiradas que mais reduzem o ATT de ln nº pobres ({n_ecs_ln} = nº de tratados ECS nessa "
      f"amostra) são {', '.join(top.retirado)}; delas, {int(top.ECS.sum())} de ECS "
      f"({', '.join(top[top.ECS == 1].retirado) or 'nenhuma'}). Retirar "
      f"{', '.join(ll[(ll.ECS == 1) & (ll.variacao > 0)].retirado) or 'nenhum ECS'} **aumenta** o ATT.\n")

    # --- 4. decomposição
    A("### 4. Decomposição: ln(nº pobres) = ln(taxa) + ln(população) (`ex3_log_decomposition.csv`)\n")
    ag = dec[dec.tipo == "agregado"].set_index("variavel")
    tst = dec[dec.tipo == "teste_identidade"].iloc[0]
    A(md_table(ag.reset_index()[["variavel", "estimate", "se", "ci_low", "ci_high", "p_value", "n_treated", "n_units"]]))
    A(f"\n**Teste da identidade:** ATT(ln taxa) + ATT(ln pop) − ATT(ln nº pobres) = {tst.estimate:.2e}; máximo por "
      f"célula ATT(g,t) = {tst.gap_max_celulas:.2e}; tolerância {tst.tolerancia:.0e} → "
      f"**{'passou' if bool(tst.passou) else 'FALHOU'}**.\n")
    pp = dec[dec.tipo == "pais_pp"]
    A("Conversão para p.p. por país: pobreza pré × (exp(ATT) − 1), com o ATT de ln(taxa) agregado e o da coorte "
      "do país, comparada à Δ taxa observada (tratado − controle):\n")
    A(md_table(pp[["iso3", "region_code", "g", "pov_rate_pre", "pp_com_att_agregado", "att_ln_rate_coorte",
                   "pp_com_att_coorte", "d_pov_rate_dif_observada"]].sort_values(["region_code", "iso3"])
               .rename(columns={"pov_rate_pre": "pobreza pré (%)", "pp_com_att_agregado": "p.p. (ATT agregado)",
                                "att_ln_rate_coorte": "ATT ln taxa (coorte)", "pp_com_att_coorte": "p.p. (ATT coorte)",
                                "d_pov_rate_dif_observada": "Δ taxa observada (dif)"}), {"pobreza pré (%)": 2}))

    # --- leitura objetiva
    full = reg[(reg.outcome == "ln_n_poor") & reg.subamostra.str.startswith("(a)")].iloc[0]
    noecs = reg[(reg.outcome == "ln_n_poor") & reg.subamostra.str.startswith("(b)")].iloc[0]
    onlyecs = reg[(reg.outcome == "ln_n_poor") & reg.subamostra.str.startswith("(c)")].iloc[0]
    c1 = bool(abs(noecs.estimate) < 0.5 * abs(full.estimate) and noecs.ci_low <= 0 <= noecs.ci_high
              and onlyecs.estimate > full.estimate)
    c2 = bool(top.ECS.sum() > n_ecs_ln / 2)
    share_pop = abs(ag.loc["ln_pop", "estimate"]) / abs(ag.loc["ln_n_poor", "estimate"])
    pp_ecs = pp[pp.ECS == 1].pp_com_att_coorte.abs().median()
    pp_oth = pp[pp.ECS == 0].pp_com_att_coorte.abs().median()
    c3 = bool(share_pop < 0.5 and pp_ecs < 1 and pp_ecs < pp_oth)
    verdict = "confirma-se" if (c1 and c3) else ("confirma-se parcialmente" if (c1 or c3) else "não se confirma")
    A("\n### Leitura\n")
    A(f"Critérios definidos antes de ver os resultados (`src/12_report_exercises.py`): (i) sem ECS, o ATT de ln nº "
      f"pobres cai para menos da metade e o IC contém zero, enquanto só ECS fica acima do total; (ii) as retiradas que "
      f"mais reduzem o ATT no leave-one-out são de países ECS; (iii) o efeito está em ln(taxa), não em ln(população) "
      f"(|ATT ln pop| < 50% do total), e o efeito implícito em p.p. nos ECS é pequeno (< 1 p.p.) e menor que nos demais.\n")
    A(f"- (i) {'Sim' if c1 else 'Não'}: total {f(full.estimate, 3)} (n = {full.n_treated}); sem ECS {f(noecs.estimate, 3)} "
      f"[{f(noecs.ci_low, 3)}; {f(noecs.ci_high, 3)}] (n = {noecs.n_treated}); só ECS {f(onlyecs.estimate, 3)} "
      f"(EP {f(onlyecs.se, 3)}, n = {onlyecs.n_treated}).")
    A(f"- (ii) {'Sim' if c2 else 'Não'}: {int(top.ECS.sum())} de {n_ecs_ln} maiores reduções vêm de ECS.")
    A(f"- (iii) {'Sim' if c3 else 'Não'}: ATT ln taxa = {f(ag.loc['ln_rate', 'estimate'], 3)}, ATT ln pop = "
      f"{f(ag.loc['ln_pop', 'estimate'], 3)} ({f(100 * share_pop, 0)}% do total); efeito implícito mediano "
      f"(ATT da coorte) |{f(pp_ecs)}| p.p. nos ECS contra |{f(pp_oth)}| p.p. nos demais.")
    A(f"\n**Veredito pela regra pré-definida: a hipótese {verdict}** (confirma se (i) e (iii) valem; parcialmente se só "
      "um deles; (ii) é evidência auxiliar).\n")
    regional = c1 or c2
    A("**Leitura por componente.** A regra acima mistura duas perguntas. O critério (iii) só verifica se o efeito vem da "
      "taxa e não da população; isso pode valer com ou sem concentração em ECS, então (iii) não discrimina a hipótese "
      "regional. Separando:\n")
    A(f"- *Componente regional* (o efeito em log vem dos ECS de pobreza inicial baixa?): "
      + ("**confirma-se**" if (c1 and c2) else "**confirma-se em parte**" if regional else "**não se confirma**")
      + f". Sem ECS o ATT {'cai' if noecs.estimate < full.estimate else 'sobe'} ({f(full.estimate, 3)} → "
      f"{f(noecs.estimate, 3)}), e só ECS dá {f(onlyecs.estimate, 3)}.")
    A(f"- *Componente de canal* (o efeito é na taxa, não na população): **{'confirma-se' if share_pop < 0.5 else 'não se confirma'}** "
      f"(ATT ln pop = {f(100 * share_pop, 0)}% do total).")
    A(f"- *O que os dados mostram:* nos tratados fora de ECS (pobreza pré mediana {f(oth.pov_rate_pre.median())}%), a "
      f"pobreza cai em p.p. em relação aos controles (Δ taxa dif mediana {f(oth.d_pov_rate_dif.median())} p.p.), mas cai "
      f"**proporcionalmente menos** (Δ ln taxa dif mediana {f(oth.d_ln_rate_dif.median(), 3)}). Os controles partem de "
      f"pobreza mais baixa e têm quedas proporcionais maiores. O ATT positivo em log reflete esse contraste de taxas "
      "proporcionais em países de pobreza alta (sobretudo África Subsaariana), não pequenas variações em países de "
      "pobreza baixa. Isso também mostra que o efeito em log e o efeito em p.p. dependem de hipóteses de tendências "
      "paralelas diferentes (em log ou em nível), que não podem valer ao mesmo tempo quando os níveis iniciais diferem tanto.")
    cp = reg[reg.subamostra.str.startswith("(c')") & (reg.outcome == "ln_n_poor")]
    if len(cp):
        A(f"- A variante (c′), só ECS com controles ECS, dá {f(cp.estimate.iloc[0], 3)} (EP {f(cp.se.iloc[0], 3)}), mas "
          f"com apenas {int(cp.n_controls.iloc[0])} controles com `ln_n_poor` completo. É frágil demais para sustentar "
          "conclusões.\n")



def ex4_section(A) -> None:
    """Exercício 4 (src/14_power_simulation.py); pulado se os CSVs ex4_ ainda não existem."""
    if not ((TABLES / "ex4_power.csv").exists() and (TABLES / "ex4_mde.csv").exists()):
        return
    pw, mde = T("ex4_power.csv"), T("ex4_mde.csv")
    R = int(mde.replicas.min())
    lab = {"original": "Onset original", "limiar_1": "limiar_1"}
    A("\n## Exercício 4 — Poder estatístico\n")
    A("*Gerado a partir de `outputs/tables/ex4_power.csv` e `ex4_mde.csv` (`src/14_power_simulation.py`).*\n")
    A(f"**Desenho.** Simulação placebo nos dados reais. Em cada réplica ({R} por δ), sorteiam-se entre os nunca tratados "
      "\"falsos tratados\" com o mesmo número de países e os mesmos anos de onset dos tratados efetivamente usados em "
      "cada especificação e variável. As covariáveis pré são recalculadas para o g sorteado. Soma-se δ·s(e) ao resultado "
      "a partir de g, com s(e) = 1 (efeito constante) ou s(e) = min((e+1)/6, 1) (cresce linearmente e atinge δ em e = 5). "
      "Estima-se com o estimador de referência (CS REG, nunca tratados, bootstrap multiplicador). Poder = fração de "
      "réplicas com IC 95% excluindo zero; MDE = menor δ com poder ≥ 80%. Os mesmos sorteios são usados para todos os δ. "
      "Grade: taxa 0–10 p.p. (passo 0,5); log nº pobres 0–0,6 (passo 0,05).\n")
    t = mde.copy()
    t["spec"] = t.spec.map(lab)
    t["tamanho (IC 95%)"] = [f"{f(r.tamanho_delta0, 3)} [{f(r.tamanho_ic_low, 3)}; {f(r.tamanho_ic_high, 3)}]"
                            for r in t.itertuples()]
    gmax = pw.groupby("outcome").delta.max()
    for col in ("mde_grade", "mde_interpolado"):
        t[col] = [f(v, 3) if pd.notna(v) else f"> {f(gmax[o])}" for v, o in zip(t[col], t.outcome)]
    ep_sim = pw[pw.delta == 0].groupby(["spec", "outcome", "formato"]).ep_medio.first()
    t["EP simulado (δ=0)"] = [ep_sim.get((s, o, fm), np.nan) for s, o, fm in zip(mde.spec, mde.outcome, mde.formato)]
    A(md_table(t[["spec", "outcome", "formato", "tamanho (IC 95%)", "mde_grade", "mde_interpolado", "mde_aprox_2_8_ep",
                  "EP simulado (δ=0)", "ep_estimado", "att_estimado", "poder_no_att_estimado"]]
               .rename(columns={"mde_grade": "MDE (grade)", "mde_interpolado": "MDE (interp.)",
                                "mde_aprox_2_8_ep": "2,8 × EP real", "ep_estimado": "EP real",
                                "att_estimado": "ATT estimado", "poder_no_att_estimado": "poder em |ATT|"})))
    A("\n![](../outputs/figures/ex4_power_curve_pov_rate.png)")
    A("![](../outputs/figures/ex4_power_curve_ln_n_poor.png)\n")

    A("### Leitura\n")
    c = mde[mde.formato == "constante"]
    for r in c.itertuples():
        unit = "p.p." if r.outcome == "pov_rate" else "log-pontos"
        extra = "" if r.outcome == "pov_rate" else f" (≈ {f(100 * (np.exp(r.mde_interpolado) - 1), 0)}% mais pobres)"
        above = abs(r.att_estimado) >= r.mde_interpolado
        A(f"- **{lab[r.spec]} / {r.outcome}:** MDE ≈ {f(r.mde_interpolado)} {unit}{extra} com efeito constante. "
          f"O |ATT| estimado ({f(abs(r.att_estimado), 3)}) está {'acima' if above else 'abaixo'} do MDE; o poder para um "
          f"efeito desse tamanho seria {f(100 * r.poder_no_att_estimado, 0)}%.")
    sz = mde.drop_duplicates(["spec", "outcome"])
    over = sz[sz.tamanho_ic_low > 0.05]
    under = sz[sz.tamanho_ic_high < 0.05]
    A(f"- **Tamanho do teste (δ = 0):** de {f(100 * sz.tamanho_delta0.min(), 1)}% a {f(100 * sz.tamanho_delta0.max(), 1)}%. "
      + ("Rejeita acima de 5% (IC exclui 5%) em: " + ", ".join(f"{lab[r.spec]}/{r.outcome}" for r in over.itertuples())
         + ". O IC 95% bootstrap é liberal nesses casos, e o MDE fica otimista. " if len(over) else "")
      + ("Conservador em: " + ", ".join(f"{lab[r.spec]}/{r.outcome}" for r in under.itertuples()) + ". "
         if len(under) else "")
      + ("O teste tem tamanho compatível com 5% em todos os casos." if not len(over) and not len(under) else ""))
    lin = mde[mde.formato != "constante"].set_index(["spec", "outcome"])
    con = c.set_index(["spec", "outcome"])
    ratio = (lin.mde_interpolado / con.mde_interpolado).dropna()
    out_grid = mde[mde.mde_interpolado.isna()]
    A(f"- **Efeito que cresce até e = 5:** o MDE (em termos do efeito de longo prazo) é {f(ratio.min(), 2)}–{f(ratio.max(), 2)} "
      "vezes o do efeito constante, porque os primeiros anos pós-onset carregam só parte do efeito."
      + "".join(f" Em {lab[r.spec]}/{r.outcome} ({r.formato}), o poder não chega a 80% dentro da grade: o MDE é maior que "
                f"{f(pw[(pw.spec == r.spec) & (pw.outcome == r.outcome)].delta.max())}, com poder de "
                f"{f(100 * pw[(pw.spec == r.spec) & (pw.outcome == r.outcome) & (pw.formato == r.formato)].sort_values('delta').poder.iloc[-1], 0)}% "
                "no topo da grade." for r in out_grid.itertuples()))
    rr = (c.set_index(["spec", "outcome"]).mde_interpolado / c.set_index(["spec", "outcome"]).mde_aprox_2_8_ep)
    ci_ = c.set_index(["spec", "outcome"])
    ep_r = pd.Series([ep_sim.get((s, o, "constante"), np.nan) for s, o in ci_.index], index=ci_.index) / ci_.ep_estimado
    A("- **Simulação × 2,8 × EP real** (efeito constante):")
    for o, nome in [("pov_rate", "taxa"), ("ln_n_poor", "log nº pobres")]:
        ro, eo = rr.xs(o, level="outcome"), ep_r.xs(o, level="outcome")
        A(f"  - *{nome}*: MDE simulado / (2,8 × EP real) = {f(ro.min(), 2)}–{f(ro.max(), 2)}; EP das réplicas / EP real = "
          f"{f(eo.min(), 2)}–{f(eo.max(), 2)}. "
          + ("As réplicas são **menos ruidosas** que os tratados reais, pois os falsos tratados vêm de nunca tratados de "
             "pobreza mais baixa e estável. Por isso o MDE simulado **subestima** o relevante, e 2,8 × EP real "
             f"({f(c[c.outcome == o].mde_aprox_2_8_ep.min(), 2)}–{f(c[c.outcome == o].mde_aprox_2_8_ep.max(), 2)}) "
             "é a referência mais prudente."
             if eo.max() < 0.9 else
             "As réplicas são **mais ruidosas** que os tratados reais (logs de países com pobreza muito baixa oscilam "
             "muito). Aqui o MDE simulado é o mais prudente."
             if eo.min() > 1.1 else
             "Ruído comparável; as duas abordagens são coerentes."))
    A(f"- **Limitação:** o grupo de controle placebo é menor que o real (o pool cede os falsos tratados), o que tende a "
      "tornar o MDE simulado levemente conservador. Os falsos tratados também não reproduzem o perfil dos tratados reais "
      "(pobreza alta, choques correlacionados).\n")
    def span(o):
        v = pd.concat([c[c.outcome == o].mde_interpolado, c[c.outcome == o].mde_aprox_2_8_ep])
        return v.min(), v.max()
    pl, ph = span("pov_rate")
    ll_, lh = span("ln_n_poor")
    all_below = bool((c.att_estimado.abs() < c[["mde_interpolado", "mde_aprox_2_8_ep"]].min(axis=1)).all())
    A(f"**Conclusão.** Com o desenho atual, e contando os dois critérios (simulação e 2,8 × EP), só seriam detectados "
      f"com 80% de poder efeitos de cerca de {f(pl, 1)}–{f(ph, 1)} p.p. na taxa de pobreza extrema e de {f(ll_, 2)}–{f(lh, 2)} "
      f"no log do número de pobres (+{f(100 * (np.exp(ll_) - 1), 0)}% a +{f(100 * (np.exp(lh) - 1), 0)}% de pobres), "
      "para efeitos constantes. Efeitos que se acumulam ao longo do tempo exigem um δ de longo prazo ainda maior. "
      + ("Todos os |ATT| estimados estão abaixo desses limiares. Os resultados nulos dos exercícios anteriores são "
         "compatíveis tanto com efeito zero quanto com efeitos moderados, que o desenho não consegue distinguir: um "
         "efeito constante de 2 p.p. na taxa seria detectado em só "
         f"{f(100 * pw[(pw.outcome == 'pov_rate') & (pw.formato == 'constante') & (pw.delta == 2)].poder.min(), 0)}–"
         f"{f(100 * pw[(pw.outcome == 'pov_rate') & (pw.formato == 'constante') & (pw.delta == 2)].poder.max(), 0)}% "
         "das réplicas. \"Não significativo\" aqui significa \"não detectável\", não \"ausente\".\n"
         if all_below else
         "Pelo menos um |ATT| estimado supera o MDE; ver a tabela.\n"))


if __name__ == "__main__":
    main()
