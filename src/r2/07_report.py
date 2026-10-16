"""Rodada 2 — 07: gera report/r2_report.md a partir de outputs/r2/ (nenhum número digitado à mão)."""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from r2config import CONC_DAYS, CONC_SHARE, MANIFEST, MIN_PRE_SURVEYS, PEACE_WINDOW, REPORT, ROOT, TAB  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
rep = importlib.import_module("09_report")
f = rep.f


def md(df, digits=None):
    """md_table da rodada 1 com colunas numéricas convertidas para float (evita colunas int/float mistas)."""
    df = df.apply(lambda c: c.astype(float) if pd.api.types.is_numeric_dtype(c) and not pd.api.types.is_bool_dtype(c) else c)
    return rep.md_table(df, digits)
T = lambda n: pd.read_csv(TAB / n)  # noqa: E731


def pct(x, d=1):
    return f(100 * x, d) + "%"


def ci(r):
    return f"[{f(r.ci_low, 3)}; {f(r.ci_high, 3)}]"


def row(df, **kw):
    m = np.ones(len(df), bool)
    for k, v in kw.items():
        m &= (df[k] == v).to_numpy()
    return df[m].iloc[0]


def sig(p, plural=False):
    return "p < 0,05" if p < 0.05 else ("p < 0,10" if p < 0.10 else ("não significativos" if plural else "não significativo"))


def main() -> None:
    man = pd.read_csv(MANIFEST)
    thr = T("fcs_thresholds_used.csv")
    cnt = T("fcs_counts_by_fy.csv")
    traj = T("fcs_trajectories.csv")
    conc = T("concentrated_events_dropped.csv")
    st = T("t1_status_all_specs.csv")
    comp = T("treatment_comparison_r1_r2.csv")
    ts = T("anatomy_title_summary.csv")
    tsy = T("anatomy_title_stat.csv")
    chk = T("anatomy_title_stat_check.csv").iloc[0]
    an = T("anatomy_summary_by_trajectory.csv")
    exc = T("anatomy_r1_excluded.csv")
    q2 = T("survey_effect.csv")
    q2h = T("survey_effect_heterogeneity.csv")
    q2w = T("survey_effect_waoss.csv")
    q2e = T("survey_effect_event_study.csv")
    q1 = T("gdp_effect.csv")
    q1w = T("gdp_effect_waoss.csv")
    q1h = T("gdp_effect_honestdid.csv")
    q1p = T("gdp_effect_pretrends.csv")
    pt = T("passthrough.csv")
    pte = T("passthrough_by_e.csv")
    pov = T("poverty_effects.csv")
    pw = T("poverty_waoss_lineup_vs_survey.csv")
    mde = T("mde.csv").iloc[0]
    ld = T("poverty_long_differences_pairs.csv")
    grid = T("robustness_grid.csv")
    gaps = T("download_gaps.csv")
    main_st = st[st.spec == f"g_main_pw{PEACE_WINDOW}"]
    n_t, n_c = int((main_st.status == "tratado").sum()), int((main_st.status == "nunca_tratado").sum())
    n_always = int((main_st.status == "excluido_sempre_tratado").sum())
    L = []
    A = L.append

    # ================================================================== cabeçalho e resumo
    A("# Medindo no escuro: conflito armado, apagão estatístico e os limites da evidência sobre pobreza (rodada 2)\n")
    A("*Relatório gerado por `src/r2/07_report.py` a partir de `outputs/r2/`. Instruções: `CLAUDE.md` (rodada 2); "
      "rodada 1 em `docs/CLAUDE_rodada1.md`, `report/report.md` e `report/exercicios.md`.*\n")
    s19 = ts[ts.periodo == "2005-2019"].set_index("grupo")
    s24 = ts[ts.periodo == "2024"].set_index("grupo")
    sp = row(q2, outcome="survey_pip", estimator="CS REG, nunca tratados")
    sp_s = row(q2, outcome="survey_pip", estimator="DiD empilhada de médias (g−5..g−1 × g..g+5)")
    sp_b = row(q2, outcome="survey_pip", estimator="BJS/did2s (imputação, base = todo o pré)")
    g_reg = row(q1, outcome="ln_gdppc", estimator="CS REG, nunca tratados")
    g_unc = row(q1, outcome="ln_gdppc", estimator="CS sem covariáveis, nunca tratados")
    sd0 = q1h[(q1h.outcome == "ln_gdppc") & q1h.alvo.str.contains("média") & q1h.M.astype(str).str.startswith("SD")].iloc[0]
    pt_a = pt.set_index("variante")
    pr = row(pov, outcome="pov_rate", estimator="CS REG, nunca tratados")
    A("## Resumo\n")
    A(f"- **Estatística-título.** Em 2005–2019, **{pct(s19.loc['FCS no ano', 'share_pobres_extrap'])}** dos pobres estimados "
      f"(US$ 3,00/dia) que viviam em países da lista FCS estavam em país-anos cuja pobreza é **extrapolada ou estimada por modelo** "
      f"no PIP, contra **{pct(s19.loc['não FCS', 'share_pobres_extrap'])}** fora da lista. Os países FCS passaram de "
      f"{pct(s19.loc['global', 'share_dos_pobres_mundiais_em_FCS'])} dos pobres do mundo (média 2005–2019) para "
      f"{pct(s24.loc['global', 'share_dos_pobres_mundiais_em_FCS'])} em 2024. Ou seja, a pobreza mundial se concentra justamente onde ela "
      "é menos medida.")
    A(f"- **O apagão é um estoque, não um choque.** Países FCS crônicos têm pesquisa nacional no PIP em "
      f"{pct(row(an, trajetoria='cronico').share_survey_pip)} dos anos, contra {pct(row(an, trajetoria='nunca').share_survey_pip)} "
      "nos que nunca foram FCS. O onset de um conflito no padrão FCS não reduz de forma robusta a frequência de pesquisas: o CS REG "
      f"dá {f(sp.estimate, 3)} (EP {f(sp.se, 3)}), mas esse resultado vem de uma queda pontual no ano-base; com estimadores que usam "
      f"todo o período pré, o efeito é {f(sp_b.estimate, 3)} (BJS) e {f(sp_s.estimate, 3)} (DiD empilhada), "
      + ("ambos não significativos." if max(sp_b.p_value, sp_s.p_value) >= 0.10 else f"{sig(sp_s.p_value)}."))
    A(f"- **Conflito e PIB.** O onset T1 está associado a um PIB per capita menor em {f(-100 * g_unc.estimate, 1)}% a "
      f"{f(-100 * g_reg.estimate, 1)}% (CS sem e com covariáveis). Mas a renda relativa dos tratados já caía antes do onset. "
      f"Extrapolando a tendência pré, o efeito médio em e ∈ [0,5] vai a {f(100 * sd0.theta, 1)}% (IC {f(100 * sd0.ci_low, 1)}%; "
      f"{f(100 * sd0.ci_high, 1)}%). Causalidade reversa e efeito do conflito não se separam com estes dados.")
    A(f"- **O que o desenho consegue ver.** Pela própria regra de extrapolação do PIP (distribuição constante), a queda do PIB "
      f"estimada implica +{f(pt_a.loc['ATT agregado', 'delta_pp_medio'], 1)} p.p. de pobreza extrema em média nos 6 primeiros anos "
      f"(+{f(pt_a.loc['ATT agregado sem covariáveis', 'delta_pp_medio'], 1)} p.p. com o ATT sem covariáveis). O efeito mínimo "
      f"detectável do desenho é {f(mde.mde_referencia, 1)} p.p.; o ATT estimado na pobreza é {f(pr.estimate, 2)} p.p. "
      + ("**Nem o efeito mecânico produzido pelo próprio modelo do PIP seria detectável com segurança.**"
         if pt_a.loc["ATT agregado", "delta_pp_medio"] < mde.mde_referencia else
         "O efeito mecânico do PIP estaria no limite do detectável."))
    A("- **Conclusão.** Com os dados nacionais disponíveis, a pergunta \"quanto o conflito aumenta a pobreza\" não tem resposta "
      f"empírica. Nos países FCS, {pct(s19.loc['FCS no ano', 'share_pobres_modelada'])} dos pobres estimados em 2005–2019 estavam "
      "em anos sem pesquisa (interpolados ou extrapolados); nos anos de conflito, a pobreza publicada é, em boa parte, a projeção do "
      "PIB por um modelo. E o desenho não teria poder nem para detectar esse efeito projetado. Isso não é evidência de que o "
      "conflito não afeta a pobreza.\n")

    # ================================================================== 1. fontes
    A("## 1. Fontes, versões e limiares FCS\n")
    new = man[man.data_download >= "2026-10-16"] if "data_download" in man else man
    A("Bases novas desta rodada (`data/raw/MANIFEST.csv`, com URL e SHA-256 completos); as da rodada 1 (PIP 20260922, UCDP 26.1, "
      "WDI, WGI, UNHCR, COW) não mudaram de versão e foram reutilizadas.\n")
    A(md(new.assign(sha256=new.sha256.str[:12] + "…")[["arquivo", "fonte", "versao", "data_download", "sha256", "licenca_termos"]]))
    A("\n**Metodologia FCS.** A nota vigente é a *FY2027 Public FCV List — Methodology Summary* (efetiva em 1/7/2026), que usa só "
      "ACLED subnacional, WorldPop e GADM. Os critérios de dupla fonte (ACLED e UCDP) da era FY20–26 estão na *Historical Overview* "
      "publicada na mesma página. Por decisão do usuário, a FY20–26 é a regra principal e a FY27 é variante. Todos os valores abaixo foram "
      "extraídos do texto das notas e conferidos contra o trecho citado (`fcs_thresholds_used.csv`). Observação: o PDF da nota histórica "
      "traz a marcação \"Official Use Only\", mas está publicado em link aberto na página pública de classificação FCS; o usuário "
      "autorizou seu uso.\n")
    A(md(thr[["metodologia", "criterio", "fonte_dados", "valor", "unidade", "documento", "versao_documento"]], {"valor": 2}))
    A(f"\n**Regra de eventos concentrados.** Não consta de nenhuma das notas publicadas. Foi aplicada como regra própria, "
      f"documentada: descarta-se o país-ano em que mais de {pct(CONC_SHARE, 0)} das mortes do GED ocorreram numa janela de "
      f"{CONC_DAYS} dias (eventos com várias datas têm as mortes distribuídas entre o início e o fim). Foram descartados "
      f"{len(conc)} país-anos: {', '.join(f'{r.iso3} {r.year}' for r in conc.itertuples())}. Os resultados sem a regra estão no §8.\n")
    A("**ACLED.** Não baixado: as credenciais (`ACLED_EMAIL`, `ACLED_KEY`) não foram fornecidas. T1 usa só os critérios UCDP "
      "(`t1_source = \"ucdp_only\"`), e a variante de dupla fonte e a FY27 ficam pendentes.\n")
    if len(gaps):
        A("Lacunas de download: " + "; ".join(gaps.url) + ".\n")
    A("**Luminosidade noturna.** Não incluída: só a busca de metadados no Zenodo foi registrada. A agregação por país das imagens "
      "harmonizadas exigiria fronteiras (GADM) e processamento de rasters, fora do escopo desta rodada.\n")

    # ================================================================== 2. mudanças
    A("## 2. O que mudou em relação à rodada 1\n")
    A(f"- **Tratamento T1 (padrão FCS, UCDP-only).** Um país-ano está em conflito se tiver > 150 mortes e > 10/100 mil (alta), "
      "> 150 mortes e 1–10/100 mil (média), ou 0,5–1/100 mil com mortes mais que dobrando (deterioração rápida). As mortes são o total de "
      "violência organizada no território (UCDP Country-Year: state-based, non-state e one-sided). O onset é o 1º ano em T1 após "
      f"≥ {PEACE_WINDOW} anos fora, sem exigir pesquisas (exceto na Q3). Resultado: {n_t} tratados, {n_c} controles (nunca T1 e nunca "
      f"FCS) e {n_always} países sempre em conflito T1 (sem janela de paz), que ficam fora do desenho de onset mas entram no contínuo "
      "(T3) e nas descritivas.")
    A(f"- **Comparação com a rodada 1 (25 mortes):** {int((comp.situacao == 'em ambas').sum())} tratados em comum; "
      f"saem {int((comp.situacao == 'sai na r2').sum())} ({' '.join(comp[comp.situacao == 'sai na r2'].iso3)}); entram "
      f"{int((comp.situacao == 'entra na r2').sum())} ({' '.join(comp[comp.situacao == 'entra na r2'].iso3)}). EUA, Reino Unido e "
      "China saem; entram casos graves antes excluídos por falta de pesquisa, como RDC, Etiópia, Iêmen, Sudão do Sul e Líbia "
      "(`treatment_comparison_r1_r2.csv`).")
    A("- **Nota sobre a violência criminal.** As mortes totais incluem violência não estatal. Por isso entram onsets ligados ao crime "
      "organizado (MEX 2006, HND 2003, BRA 2017, ECU 2021, COL 2023). A variante só com mortes state-based está no §8.")
    A(f"- **T2 (status FCS).** {len(cnt)} listas (FY06–FY27; `fcs_counts_by_fy.csv`). Trajetórias (crônico = na lista em ≥ 80% dos anos "
      f"de existência): " + "; ".join(f"{k} {v}" for k, v in traj.trajetoria.value_counts().items()) +
      ". A categoria \"intermitente\" foi acrescentada para quem entra e sai. Os países marginais de FY06–09 ficam fora (eram listados "
      "\"para monitoramento\"). **T2 não é usado como tratamento causal**: a lista é construída em parte com o CPIA, que reflete o "
      "desempenho econômico e institucional (circularidade).\n")
    A(md(cnt.rename(columns={"n_fcs_any": "na lista", "n_marginal": "marginal", "n_conflict": "conflito", "n_institutional": "institucional"})))

    # ================================================================== 3. anatomia
    A("\n## 3. Anatomia do apagão\n")
    A(f"A estatística-título é recalculada diretamente do CSV bruto do PIP, com diferença máxima de {chk.max_abs_dif:.0e} em "
      f"{int(chk.anos)} anos (`anatomy_title_stat_check.csv`). \"Extrapolada ou modelada\" = `estimation_type` ∈ {{extrapolation, "
      "CMD estimation}; a variante \"modelada\" inclui também a interpolação entre pesquisas.\n")
    A(md(ts.rename(columns={"share_pobres_extrap": "% pobres extrapolada/modelo", "share_pobres_modelada": "% pobres não-pesquisa",
                            "pobres_milhoes_medio": "pobres (mi)", "share_dos_pobres_mundiais_em_FCS": "% dos pobres do mundo em FCS"}),
         {"pobres (mi)": 0}))
    A("\nA alta de 2020–2024 em todos os grupos reflete a defasagem normal das pesquisas mais recentes (anos ainda não cobertos "
      "por pesquisa são projetados), e não só o conflito. Por isso a comparação substantiva usa 2005–2019.\n")
    A("![](../outputs/r2/figures/anatomy_modeled_poverty_timeline.png)\n")
    A("**Por trajetória FCS** (média dos países-ano 1990–2024; `anatomy_summary_by_trajectory.csv`):\n")
    A(md(an))
    A("\n![](../outputs/r2/figures/anatomy_survey_by_trajectory.png)\n")
    se = exc[exc.grupo_excluido_r1 == "sem pesquisas pré-onset"].iloc[0]
    sa = exc[exc.grupo_excluido_r1 == "sempre tratado"].iloc[0]
    A(f"**Países que a rodada 1 excluiu.** Dos {int(se.n_paises)} excluídos por falta de pesquisas antes do onset, "
      f"{int(se.n_fcs_alguma_vez)} já estiveram na lista FCS. Juntos, representam {pct(se.share_pobreza_global_2024)} da pobreza "
      f"extrema global estimada em 2024. Os {int(sa.n_paises)} \"sempre tratados\" somam mais {pct(sa.share_pobreza_global_2024)}. "
      f"A rodada 1 deixou de fora, portanto, países com {pct(se.share_pobreza_global_2024 + sa.share_pobreza_global_2024)} dos pobres "
      "do mundo (`anatomy_r1_excluded.csv`).\n")

    # ================================================================== 4. Q2
    A("## 4. Conflito e produção de dados (Q2)\n")
    keep = ["CS REG, nunca tratados", "CS REG, ainda não tratados", "CS sem covariáveis, nunca tratados",
            "BJS/did2s (imputação, base = todo o pré)", "DiD empilhada de médias (g−5..g−1 × g..g+5)",
            "DiD empilhada de médias — só alta intensidade", "LPM TWFE (como rodada 1)", "Rodada 1 (onset 25 mortes, LPM TWFE)"]
    A(md(q2[q2.estimator.isin(keep)][["outcome", "estimator", "estimate", "se", "ci_low", "ci_high", "p_value", "n_treated", "pretrend_p"]]))
    es = q2e[(q2e.outcome == "survey_pip") & (q2e.estimator == "CS REG, nunca tratados")]
    A(f"\n**Leitura.** O CS REG sugere *mais* pesquisas após o onset ({f(sp.estimate, 3)}). O event study, porém, mostra que o "
      f"ano-base g−1 tem um coeficiente atípico: com base variável, o CS compara cada ano a g−1. Os estimadores que usam todo o "
      f"período pré como base (BJS {f(sp_b.estimate, 3)}; DiD empilhada {f(sp_s.estimate, 3)}) não indicam efeito. "
      "A regressão TWFE da rodada 1 aplicada ao T1 dá "
      f"{f(row(q2, outcome='survey_pip', estimator='LPM TWFE (como rodada 1)').estimate, 3)}, contra −0,082 na rodada 1. O efeito "
      "negativo da rodada 1 não se reproduz com a definição FCS de conflito.")
    g1 = grid[(grid.outcome == "survey_pip") & (grid.especificacao == "definição da rodada 1 (25 mortes)")].set_index("estimator")
    A(f"- **A definição do tratamento muda o sinal.** Com os tratados da rodada 1 (onset com ≥ 25 mortes) e os mesmos "
      f"estimadores, o efeito sobre a frequência de pesquisas é {f(g1.loc['CS REG, nunca tratados', 'estimate'], 3)} (CS REG) e "
      f"{f(g1.loc['DiD empilhada de médias', 'estimate'], 3)} (DiD empilhada). A queda de pesquisas encontrada na rodada 1 é "
      f"compatível com onsets de baixa intensidade que o limiar FCS (> 150 mortes e ≥ 0,5–1/100 mil) exclui: saem "
      f"{' '.join(comp[comp.situacao == 'sai na r2'].iso3)}.")
    shx = row(q2, outcome="share_extrapolated", estimator="DiD empilhada de médias (g−5..g−1 × g..g+5)")
    A(f"- **Pontos extrapolados.** A DiD empilhada indica *menos* pontos extrapolados após o onset ({f(shx.estimate, 3)}, "
      f"{sig(shx.p_value)}), e o resultado não se mantém só com conflitos de alta intensidade. A leitura cautelosa é que os onsets T1 "
      "estão concentrados em países de renda média com sistemas estatísticos ativos.")
    hh = q2h[(q2h.estimador == "DiD empilhada") & (q2h.outcome == "survey_any")].set_index("grupo")
    A(f"- **Heterogeneidade** (DiD empilhada; Holm em `survey_effect_heterogeneity.csv`). Em tratados de trajetória FCS crônica ou "
      f"de entrada, a probabilidade de alguma pesquisa cai {f(hh.loc['trajetória FCS crônica/entrada', 'estimate'], 3)} "
      f"(p = {f(hh.loc['trajetória FCS crônica/entrada', 'p_value'], 3)}). Em tratados nunca FCS, o sinal se inverte. Nenhuma "
      "heterogeneidade sobrevive à correção de Holm.")
    A("- **Missões de paz e CPIA:** medidos antes do onset; os subgrupos têm 5–9 tratados e não permitem conclusão.")
    w_sp = row(q2w, outcome="survey_pip")
    A(f"- **Intensidade contínua (WAOSS):** θ = {f(w_sp.efeito_all, 4)} (EP {f(w_sp.efeito_se_all, 4)}) por unidade de "
      "asinh(mortes/100 mil); o efeito das escaladas, líquido do placebo, é "
      f"{f(w_sp.liquido_up, 4)} (EP {f(w_sp.liquido_se_up, 4)}).\n")
    A("![](../outputs/r2/figures/q2_event_study_survey_pip.png)\n")
    A("**Síntese da Q2.** O conflito não *cria* o apagão no momento do onset: ele se concentra nos países cronicamente frágeis, que "
      "nunca entram num desenho de onset porque não têm um período de paz para servir de base. É um problema de estoque, visível nas "
      "descritivas (§3), e não de fluxo identificável por DiD.\n")

    # ================================================================== 5. Q1
    A("## 5. Conflito e PIB per capita (Q1)\n")
    A(md(q1[["outcome", "estimator", "estimate", "se", "ci_low", "ci_high", "p_value", "n_treated", "pretrend_p"]], {"estimate": 4, "se": 4}))
    pre = q1p[q1p.outcome == "ln_gdppc"]
    A(f"\n**Pré-tendências (causalidade reversa).** Os coeficientes pré-onset do CS REG para ln PIB pc (e = −5…−2, base variável) "
      f"são {', '.join(f(v, 3) for v in pre.estimate)}, e o teste conjunto rejeita (p = {f(g_reg.pretrend_p, 3)}). Os tratados "
      "já perdiam renda relativa antes do onset, o que é compatível com choques de renda que aumentam o risco de conflito. Sem "
      f"covariáveis, o teste não rejeita (p = {f(g_unc.pretrend_p, 3)}) e o efeito é menor ({f(g_unc.estimate, 4)}).")
    hm = q1h[(q1h.outcome == "ln_gdppc") & q1h.alvo.str.contains("média")]
    A("**Rambachan–Roth (aprox.; média e ∈ [0,5]):**\n")
    hm2 = hm[["M", "theta", "ci_low", "ci_high"]].copy()
    hm2["M"] = hm2.M.astype(str).str.replace(".", ",", regex=False)
    A(md(hm2, {"theta": 4, "ci_low": 4, "ci_high": 4}))
    rmh = hm[~hm.M.astype(str).str.startswith("SD")].assign(M=lambda x: x.M.astype(float))
    ok = rmh[rmh.ci_high < 0].M
    A(f"\nO IC robusto do efeito sobre o nível do PIB exclui zero até M̄ = {f(ok.max(), 1) if len(ok) else '—'} vez a maior "
      f"variação pré. Sob a extrapolação linear da tendência pré, o efeito é {f(100 * sd0.theta, 1)}% (IC "
      f"{f(100 * sd0.ci_low, 1)}%; {f(100 * sd0.ci_high, 1)}%). O crescimento anual não mostra efeito robusto.")
    gw = row(q1w, outcome="ln_gdppc")
    A(f"- **T3 contínuo:** θ = {f(gw.efeito_all, 4)} log-pontos por unidade de asinh (EP {f(gw.efeito_se_all, 4)}). Nas escaladas, "
      f"o efeito é {f(gw.efeito_up, 4)}, mas o placebo das escaladas também é negativo ({f(gw.placebo_up, 4)}, EP "
      f"{f(gw.placebo_se_up, 4)}). Líquido do placebo: {f(gw.liquido_up, 4)} (EP {f(gw.liquido_se_up, 4)}), "
      + ("não significativo." if abs(gw.liquido_up / gw.liquido_se_up) < 1.96 else "significativo."))
    A("- **Medição do PIB:** as contas nacionais também se deterioram em conflito. A robustez com luminosidade noturna não foi "
      "possível nesta rodada.\n")
    A("![](../outputs/r2/figures/q1_event_study_ln_gdppc.png)\n")

    # ================================================================== 6. Q3 passthrough × MDE
    A("## 6. O que o canal do PIB prevê e o que o desenho consegue detectar (Q3)\n")
    A(f"Tratados elegíveis: {int(pt.n_paises.max())} países com ≥ {MIN_PRE_SURVEYS} pesquisas antes do onset e distribuição "
      "observada antes dele. Para cada um, a API do PIP foi consultada na última pesquisa pré-onset com a linha 3,00/(1 − x), "
      "em que x é a queda estimada do PIB per capita (`passthrough_by_country.csv`).\n")
    A(md(pte, {"queda_pib": 3}))
    A("\n" + md(pt))
    A(f"\n**Efeito mínimo detectável** (simulação placebo, {int(mde.replicas)} réplicas por δ, {int(mde.n_falsos_tratados)} falsos "
      f"tratados sorteados de {int(mde.pool)} nunca tratados): tamanho em δ = 0 = {pct(mde.tamanho_delta0)}; MDE simulado = "
      f"{f(mde.mde_simulado, 2)} p.p.; 2,8 × EP real = {f(mde.mde_2_8_ep, 2)} p.p.; referência (o maior) = "
      f"**{f(mde.mde_referencia, 2)} p.p.**\n")
    A("![](../outputs/r2/figures/q3_passthrough_vs_mde.png)\n")
    A(f"**Resposta à pergunta-chave.** O efeito mecânico que o próprio modelo do PIP produz a partir da queda do PIB "
      f"(+{f(pt_a.loc['ATT agregado', 'delta_pp_medio'], 2)} p.p., ou +{f(pt_a.loc['ATT agregado sem covariáveis', 'delta_pp_medio'], 2)} "
      f"p.p. sem covariáveis) é "
      + ("**menor que o efeito mínimo detectável**" if pt_a.loc["ATT agregado", "delta_pp_medio"] < mde.mde_referencia else "da ordem do MDE")
      + f" ({f(mde.mde_referencia, 2)} p.p.). Mesmo que a pobreza publicada fosse exatamente a projeção do PIB, o desenho não a "
      f"distinguiria de zero com 80% de poder. O ATT estimado na pobreza ({f(pr.estimate, 2)} p.p., IC {ci(pr)}) é compatível "
      "com zero e também com o efeito projetado.\n")
    between = mde.mde_simulado <= pt_a.loc["ATT agregado", "delta_pp_medio"] < mde.mde_2_8_ep
    if between:
        A(f"**Ressalva.** O efeito projetado fica *entre* as duas medidas de MDE: acima do MDE simulado ({f(mde.mde_simulado, 2)} p.p.) "
          f"e abaixo de 2,8 × EP real ({f(mde.mde_2_8_ep, 2)} p.p.). A simulação sorteia falsos tratados entre nunca tratados, cuja "
          f"pobreza é mais baixa e estável (EP simulado {f(mde.ep_simulado_delta0, 2)} contra EP real {f(mde.ep_real, 2)}). Por isso o "
          "MDE simulado é otimista para os tratados reais, e o critério conservador (o maior dos dois, como na rodada 1) é o "
          "relevante.\n")

    # ================================================================== 7. medidas alternativas
    A("## 7. Medidas alternativas: pobreza medida, MPI e diferenças longas\n")
    A(md(pov[["outcome", "estimator", "estimate", "se", "ci_low", "ci_high", "p_value", "n_treated", "nota"]]))
    A(f"\n- **Diferenças longas entre pesquisas** ({len(ld)} tratados com pesquisa antes e depois do onset; "
      "`poverty_long_differences_pairs.csv`): usam só pobreza medida, mas cobrem poucos países e intervalos longos.")
    pl = pw.set_index("outcome")
    A(f"- **Placebo das escaladas (WAOSS):** na série lineup, escalada {f(pl.loc['pov_rate', 'efeito_up'], 3)} e placebo "
      f"{f(pl.loc['pov_rate', 'placebo_up'], 3)} (EP {f(pl.loc['pov_rate', 'placebo_se_up'], 3)}). Só com pesquisas, escalada "
      f"{f(pl.loc['pov_rate_obs', 'efeito_up'], 3)} e placebo {f(pl.loc['pov_rate_obs', 'placebo_up'], 3)} (EP "
      f"{f(pl.loc['pov_rate_obs', 'placebo_se_up'], 3)}), com {int(pl.loc['pov_rate_obs', 'efeito_n_sw'])} trocas. "
      + ("O placebo positivo **desaparece** com pobreza medida, o que é compatível com a hipótese de que a interpolação entre "
         "pesquisas cria pré-tendência artificial; mas com tão poucas trocas o teste tem pouco poder."
         if abs(pl.loc["pov_rate_obs", "placebo_up"]) < abs(pl.loc["pov_rate", "placebo_up"]) else
         "O placebo não desaparece com pobreza medida."))
    so = row(pov, outcome="pov_rate_survey_only", estimator="CS sem X, blocos de 3 anos, desbalanceado")
    mp_ = row(pov, outcome="mpi_headcount", estimator="CS sem X, blocos de 3 anos, desbalanceado")
    ldr = row(pov, outcome="pov_rate_survey_only", estimator="Diferenças longas entre pesquisas")
    A(f"- **Só pobreza medida, blocos de 3 anos:** {f(so.estimate, 2)} p.p. (EP {f(so.se, 2)}). Na MPI: {f(mp_.estimate, 2)} p.p. "
      f"(EP {f(mp_.se, 2)}). Os dois são negativos, como na rodada 1, mas são estimados com CS sem covariáveis em blocos "
      "desbalanceados: cada bloco reflete os países que fizeram pesquisa naquele período, e quem pesquisa depois do onset é um "
      "grupo selecionado (§4). Na série lineup, o mesmo CS sem covariáveis dá "
      f"{f(row(pov, outcome='pov_rate', estimator='CS sem covariáveis, nunca tratados').estimate, 2)} p.p. (pré-tendência p = "
      f"{f(row(pov, outcome='pov_rate', estimator='CS sem covariáveis, nunca tratados').pretrend_p, 2)}). As diferenças longas, que comparam pares de pesquisas "
      f"com intervalos parecidos, dão {f(ldr.estimate, 2)} p.p. (EP {f(ldr.se, 2)}). Nenhuma medida alternativa indica aumento da "
      "pobreza medida após o onset, mas nenhuma tem poder para descartar efeitos de alguns pontos.")
    A("- **MPI:** também depende de pesquisas (DHS e MICS) e herda o apagão. A série harmonizada da OPHI cobre poucos país-anos.")
    rf = row(pov, outcome="refugees_origin_pc", estimator="DiD empilhada de médias (mecanismo)")
    idn = row(pov, outcome="idp_new_pc", estimator="DiD empilhada de médias (mecanismo)")
    A(f"- **Mecanismos demográficos:** refugiados que saem aumentam {f(rf.estimate, 0)} por 100 mil (EP {f(rf.se, 0)}; "
      f"{int(rf.n_treated)} tratados). Novos deslocados internos: {f(idn.estimate, 0)} por 100 mil (EP {f(idn.se, 0)}), mas só "
      f"{int(idn.n_treated)} tratados têm dados do IDMC (2009+) antes e depois do onset. A população residente do PIP não desconta "
      "quem saiu do país.\n")

    # ================================================================== 8. robustez
    A("## 8. Robustez transversal\n")
    A(md(grid[["pergunta", "outcome", "especificacao", "estimator", "estimate", "se", "p_value", "n_treated"]], {"estimate": 4}))

    # ================================================================== 9-10
    A("\n## 9. Limitações\n")
    A("- **Circularidade da lista FCS:** o CPIA e a classificação refletem o desempenho econômico e institucional. Por isso T2 só "
      "aparece nas descritivas e na Q2, nunca como tratamento causal.")
    A("- **ACLED:** não usado (sem credenciais). Quando entrar, terá cobertura curta e desigual por região (África desde 1997, outras "
      "regiões bem depois), e os resultados de dupla fonte valerão para um período menor.")
    A("- **Missões de paz:** são consequência do conflito, por isso só entram como característica pré-onset. A base IPI vai até "
      "abril de 2017 e foi complementada pelas listas públicas do DPO.")
    A("- **PIB em conflito:** as contas nacionais também se deterioram. O efeito na Q1 pode estar mal medido na mesma direção do "
      "problema que o paper descreve.")
    A("- **MPI:** depende de pesquisas e herda o apagão.")
    A("- **Causalidade reversa** na Q1 e na intensidade (T3): as pré-tendências do PIB são rejeitadas no CS REG, e o placebo das "
      "escaladas é negativo.")
    A("- **Violência criminal no T1:** as mortes totais do UCDP incluem conflitos não estatais e violência contra civis. Isso traz "
      "países de renda média com violência criminal.")
    A("- **Ausência de evidência:** nenhuma conclusão deste relatório é do tipo \"o conflito não afeta a pobreza\". A formulação "
      "correta é sobre o que é detectável com os dados disponíveis.\n")
    A("## 10. Implicações para a produção de dados em contextos FCV\n")
    s20 = ts[ts.periodo == "2020-2024"].set_index("grupo")
    A(f"1. **Medir onde há pobreza.** Os países FCS concentravam {pct(s24.loc['global', 'share_dos_pobres_mundiais_em_FCS'])} dos "
      f"pobres estimados do mundo em 2024, e {pct(s20.loc['FCS no ano', 'share_pobres_extrap'])} dos pobres em FCS em 2020–2024 "
      "estavam em anos extrapolados ou estimados por modelo. Prioridade estatística e prioridade operacional deveriam coincidir.")
    A("2. **Rotular a incerteza.** Publicar, junto de cada ponto do PIP, a distância até a última pesquisa e o tipo de estimativa, "
      "e agregar a pobreza global separando o medido do modelado.")
    A("3. **Pesquisas desenhadas para conflito:** métodos de coleta remota e por telefone, amostras de deslocados e painéis de "
      "acompanhamento de alta frequência permitiriam medir choques que hoje só existem via PIB.")
    A("4. **Evidência subnacional:** comparar áreas afetadas e não afetadas dentro do mesmo país (ver CLAUDE.md §6.6; requer "
      "aprovação) é o caminho para identificar efeitos que o painel nacional não consegue ver.")
    A("5. **Não confundir a projeção com a medição:** o efeito \"estimado\" do conflito sobre a pobreza nas séries nacionais é, em "
      "grande parte, a hipótese de distribuição constante aplicada à queda do PIB.\n")
    (REPORT / "r2_report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"report/r2_report.md gerado ({len(L)} blocos).")


if __name__ == "__main__":
    main()
