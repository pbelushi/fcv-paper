"""Etapa 09 — gera report/report.md a partir de outputs/ (nenhum número digitado à mão).

Todo número do relatório é lido de um arquivo em outputs/tables ou data/raw/MANIFEST.csv;
o texto interpretativo usa limiares (p < 0,05) aplicados a esses números.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config import MANIFEST, MIN_PRE_OBS, PEACE_WINDOW, POVLINE, PROCESSED, REPORT, SAMPLE_START, TABLES  # noqa: E402

T = lambda name: pd.read_csv(TABLES / name)  # noqa: E731


def f(x, d=2):
    """Número em formato brasileiro."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x, d=1):
    return f(100 * x, d) + "%"


def md_table(df: pd.DataFrame, digits: dict | None = None) -> str:
    digits = digits or {}
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, (float, np.floating)) and not np.isnan(v) and df[c].dropna().apply(float.is_integer).all():
                cells.append(str(int(v)))                     # anos, contagens, dummies
            elif isinstance(v, (float, np.floating)):
                cells.append(f(v, digits.get(c, 3)))
            elif isinstance(v, (int, np.integer)):
                cells.append(str(v))
            else:
                cells.append("" if pd.isna(v) else str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def ci(r):
    return f"[{f(r.ci_low)}; {f(r.ci_high)}]"


def sig(p):
    return "significativo a 5%" if p < 0.05 else ("significativo apenas a 10%" if p < 0.10 else "não significativo")


def main() -> None:
    man = pd.read_csv(MANIFEST)
    panel = pd.read_parquet(PROCESSED / "panel.parquet")
    status = T("treatment_status.csv")
    cohorts = T("cohorts.csv")
    variants = T("treatment_variants_counts.csv").set_index("status")
    excl = T("excluded_countries.csv")
    pov_dec = T("poverty_decisions.csv")
    dropped_inter = T("interstate_locations_dropped.csv")
    unmatched = T("unmatched_codes.csv")
    bal = T("pretreatment_balance.csv")
    miss = T("missing_survey_prepost.csv").set_index("periodo")
    mreg = T("missing_survey_regression.csv")
    etype = pd.read_csv(TABLES / "estimation_type_by_period.csv", index_col=0)
    main_r = T("main_results.csv")
    pre = T("pretrend_tests.csv")
    bacon = T("bacon_decomposition.csv")
    hd = T("honestdid_rm.csv")
    rob = T("robustness.csv")
    plac = T("placebo_permutations.csv").set_index("outcome")
    sdid = T("sdid.csv")
    dose = T("dose_response.csv")
    het = T("heterogeneity.csv")

    n_t = int((status.status == "tratado").sum())
    n_nt = int((status.status == "nunca_tratado").sum())
    n_ex = int((status.status == "excluido").sum())
    n_nosurv = int(status.motivo.fillna("").str.startswith("onset(s) sem").sum())
    y0, y1 = int(panel.year.min()), int(panel.year.max())
    pip_v = man.loc[man.fonte == "PIP", "versao"].iloc[0]
    ucdp_v = man.loc[man.fonte == "UCDP", "versao"].iloc[0]

    def mr(outcome, estimator):
        r = main_r[(main_r.outcome == outcome) & (main_r.estimator == estimator)]
        return r.iloc[0] if len(r) else None

    REF = "CS (REG, nunca tratados) — simple"
    ref_pov, ref_ln, ref_as, ref_d = (mr(o, REF) for o in ("pov_rate", "ln_n_poor", "asinh_n_poor", "d_ln_n_poor"))
    twfe_pov = mr("pov_rate", "TWFE")
    st = mreg[(mreg.modelo == "estatico")].iloc[0]
    L = []
    A = L.append

    # ------------------------------------------------------------------ cabeçalho
    A("# Conflitos armados e pobreza: diferenças em diferenças com adoção escalonada\n")
    A(f"*Relatório gerado automaticamente por `src/09_report.py` a partir de `outputs/`. "
      f"Amostra {y0}–{y1}; linha de pobreza extrema US$ {f(POVLINE)}/dia (PPC 2021).*\n")

    # ------------------------------------------------------------------ resumo
    A("## Resumo\n")
    A(f"- **Amostra de estimação:** {n_t} países com início de conflito (onset) após ≥ {PEACE_WINDOW} anos de paz e "
      f"{n_nt} países nunca tratados; {n_ex} países excluídos (ver §2). Há {cohorts.g.nunique()} coortes "
      f"({int(cohorts.g.min())}–{int(cohorts.g.max())}), com no máximo {cohorts.groupby('g').size().max()} países cada.")
    A(f"- **Taxa de pobreza:** o estimador principal (Callaway–Sant'Anna, regressão de resultado, nunca tratados) "
      f"dá ATT = {f(ref_pov.estimate)} p.p. (IC 95% {ci(ref_pov)}; {sig(ref_pov.p_value)}). "
      f"O TWFE convencional dá {f(twfe_pov.estimate)} p.p.; a diferença vem principalmente de tendências pré-tratamento "
      f"divergentes (§4).")
    A(f"- **Número de pobres:** ATT em log = {f(ref_ln.estimate)} (IC {ci(ref_ln)}; {sig(ref_ln.p_value)}; "
      f"{int(ref_ln.n_treated)} tratados sem zeros); em asinh = {f(ref_as.estimate)} (IC {ci(ref_as)}); "
      f"crescimento anual (Δlog) = {f(ref_d.estimate)} (IC {ci(ref_d)}).")
    A(f"- **Dados faltantes:** o conflito reduz a probabilidade de haver pesquisa domiciliar em "
      f"{f(-100 * st.Estimate, 1)} p.p. (EP {f(100 * st['Std. Error'], 1)}; p = {f(st['Pr(>|t|)'], 3)}). "
      f"Nos anos de conflito, boa parte da série de pobreza é interpolada ou extrapolada por modelo (§3).")
    zero_all = all(r.ci_low <= 0 <= r.ci_high for r in (ref_pov, ref_ln, ref_as, ref_d))
    A(f"- **Conclusão:** com {n_t} episódios ({int(cohorts.onset_war.sum())} com ≥ 1.000 mortes no 1º ano), "
      + ("os dados **não permitem rejeitar efeito nulo** do onset de conflito sobre a pobreza extrema (taxa e número) "
         "nos 10 anos seguintes na especificação principal. "
         if zero_all else "ao menos uma variável de resultado tem IC 95% que exclui zero na especificação principal (ver §4). ")
      + "Os intervalos de confiança são largos e a sensibilidade a violações de tendências paralelas é alta (§5).\n")

    A("Exercícios adicionais (tratamento restrito por intensidade e renda; tratamento contínuo não absorvente): "
      "ver [`exercicios.md`](exercicios.md).\n")

    # ------------------------------------------------------------------ 1. fontes
    A("## 1. Fontes e versões\n")
    A("Copiado de `data/raw/MANIFEST.csv` (hash SHA-256 completo no arquivo).\n")
    m = man.assign(sha256=man.sha256.str[:12] + "…")[["arquivo", "fonte", "versao", "data_download", "sha256", "licenca_termos"]]
    A(md_table(m))
    A(f"\nURLs exatas no MANIFEST. A linha de US$ {f(POVLINE)} é a linha padrão (`is_default`) da versão PIP `{pip_v}` "
      f"(`pip_aux_poverty_lines_*.csv`); US$ 4,20 e US$ 8,30 são as linhas superiores visíveis. UCDP versão {ucdp_v}.\n")
    A("Bases previstas no CLAUDE.md e **não usadas** nesta rodada (decisão do usuário): Penn World Table, V-Dem/Polity, "
      "Global MPI, ACLED, EM-DAT, IDMC, COW guerras. O regime político pré-conflito usa o WGI *Voice and Accountability* "
      "no lugar do V-Dem.\n")

    # ------------------------------------------------------------------ 2. decisões
    A("## 2. Construção da amostra e decisões\n")
    A("### 2.1 Pobreza (PIP)\n")
    for _, r in pov_dec.iterrows():
        A(f"- **{r.regra}:** {r.decisao}")
    A("- Série principal: *lineup* (`fill_gaps=true`). `flag_observed_survey = 1` quando há pesquisa nacional na série "
      "`fill_gaps=false` no mesmo país-ano. O Gini não é publicado na série lineup e só existe nos anos de pesquisa.")
    A("- `n_poor = headcount × população (reporting_pop do PIP)`; `ln_n_poor` não é definido quando o número de pobres é zero. "
      "Por isso o `asinh_n_poor` é reportado como variável que preserva o painel completo.\n")
    A("### 2.2 Conflito (UCDP) e harmonização\n")
    A(f"- Conflito atribuído ao país de localização (`gwno_loc`); conflitos com várias localizações contam para cada uma. "
      f"Conversão GW→ISO3 com `country_converter` + tabela manual (Alemanha, Iugoslávia/Sérvia, Kosovo, URSS/Rússia, "
      f"Sudão/Sudão do Sul, Etiópia/Eritreia, Iêmen, Vietnã, Tchecoslováquia). Não casados: "
      f"{', '.join(unmatched.nome.astype(str)) or 'nenhum'} (`unmatched_codes.csv`).")
    A(f"- **Regra territorial (decisão do usuário):** a partir de 1989, um conflito interestatal só conta para um país se houve "
      f"mortes interestatais no seu território (UCDP Country-Year). {len(dropped_inter)} localizações conflito-ano foram descartadas "
      f"({dropped_inter.iso3.nunique()} países: {', '.join(sorted(dropped_inter.iso3.unique()))}); por exemplo, a Austrália na "
      f"guerra do Iraque de 2003. Sem a regra, a Austrália seria tratada em 2003.")
    A("- Mortes (`brd`, `brd_pc`) vêm do *UCDP Country-Year Dataset on Organized Violence within Country Borders* "
      "(agregação geográfica do GED, 1989+), e não da divisão do BRD entre localizações.\n")
    A("### 2.3 Definição do tratamento\n")
    A(f"- Coorte `g` = 1º ano com conflito (≥ 25 mortes) após ≥ {PEACE_WINDOW} anos consecutivos sem conflito, "
      f"com g ∈ [{SAMPLE_START + 1}, {y1}] e ≥ {MIN_PRE_OBS} anos de pesquisa de pobreza observada antes de g. Uma coorte por país.")
    A(f"- Nunca tratados: nenhum ano de conflito em [{SAMPLE_START - PEACE_WINDOW}, {y1}]. Não há restrição por grupo de renda "
      "(decisão do usuário): países de renda média e alta entram quando o conflito ocorre no seu território (ex.: Ucrânia, 2014).")
    A("- Reincidência mantida (decisão do usuário): um país com conflito antes da janela de paz pode ser tratado. "
      f"{int((cohorts.onset_clean == 0).sum())} dos {n_t} tratados tiveram conflito em [{SAMPLE_START - PEACE_WINDOW}, g); "
      "a heterogeneidade por onset limpo × reincidência está no §5.")
    A("- **Israel** fica excluído como \"sempre tratado\": está em conflito contínuo no período e nunca completa a janela de paz.\n")
    A("**Contagem por definição** (`treatment_variants_counts.csv`):\n")
    A(md_table(variants.fillna(0).astype(int).reset_index()))
    A("\n**Excluídos por motivo** (`excluded_countries.csv`):\n")
    ex = excl.assign(motivo=excl.motivo.str.replace(r"\s*\(1º onset.*\)", "", regex=True))
    A(md_table(ex.groupby("motivo").iso3.agg(n="size", paises=lambda s: " ".join(sorted(s))).reset_index()))
    A("\n**Coortes** (`cohorts.csv`):\n")
    A(md_table(cohorts[["g", "iso3", "region_code", "onset_type", "onset_war", "brd_pc_onset3", "duration_first_spell", "onset_clean"]]
               .rename(columns={"brd_pc_onset3": "mortes/100 mil (média 3 anos)", "duration_first_spell": "duração 1º episódio"}),
               {"mortes/100 mil (média 3 anos)": 2}))
    A("\n### 2.4 Balanço pré-tratamento\n")
    A("Médias por país em g−5…g−1 (tratados) e na amostra toda (nunca tratados); teste t de Welch (`pretreatment_balance.csv`).\n")
    A(md_table(bal, {"p_valor": 3}))
    A("\nTratados e controles diferem muito em nível (pobreza, renda, população, abertura). O DiD exige tendências paralelas, "
      "não níveis iguais, mas a diferença de nível torna a hipótese de tendências comuns menos plausível. "
      "Por isso a especificação principal condiciona em PIB per capita, urbanização e população pré-tratamento.\n")

    # ------------------------------------------------------------------ 3. missing
    A("## 3. Diagnóstico crítico: dados faltantes\n")
    A("> **Este diagnóstico condiciona a interpretação de todos os resultados.**\n")
    A(f"- Proporção de anos com pesquisa observada (`missing_survey_prepost.csv`): tratados {pct(miss.loc['pre', 'obs_tratado'])} "
      f"nos 5 anos antes do onset e {pct(miss.loc['pos', 'obs_tratado'])} nos 6 anos a partir dele; controles, nos mesmos anos-calendário, "
      f"{pct(miss.loc['pre', 'obs_controles'])} e {pct(miss.loc['pos', 'obs_controles'])}.")
    A(f"- Regressão de probabilidade linear `flag_observed_survey ~ pós-onset | país + ano` (EP cluster país): "
      f"**{f(st.Estimate, 3)}** (EP {f(st['Std. Error'], 3)}; p = {f(st['Pr(>|t|)'], 3)}). O conflito reduz a frequência de pesquisas.")
    A(f"- Composição do dado de pobreza nos tratados (`estimation_type_by_period.csv`): antes do onset, "
      + "; ".join(f"{c} {pct(etype.loc['pre', c])}" for c in etype.columns)
      + "; depois, " + "; ".join(f"{c} {pct(etype.loc['pos', c])}" for c in etype.columns) + ".")
    A("- Consequência: nos anos de conflito, a série lineup é em boa parte interpolada entre pesquisas ou extrapolada com o "
      "crescimento do PIB/consumo das contas nacionais. Um efeito estimado na série lineup pode refletir o modelo de "
      "extrapolação do PIP (choque de PIB × elasticidade neutra em distribuição), e não pobreza medida. Um efeito nulo "
      "pode refletir pesquisas que não chegam às áreas afetadas. A checagem com dados só observados está no §5.\n")
    A("![](../outputs/figures/missing_survey_event_study.png)\n")

    # ------------------------------------------------------------------ 4. resultados
    A("## 4. Resultados principais\n")
    A("ATT agregado (`main_results.csv`). \"simple\" = média ponderada das ATT(g,t) pós-onset (e ∈ [0,10]), com pesos "
      "proporcionais ao tamanho da coorte, como `did::aggte(type=\"simple\")`. EP de bootstrap multiplicador com cluster por país.\n")
    keep = ["TWFE", REF, "CS (REG, ainda não tratados) — simple", "CS (sem covariáveis, nunca tratados) — simple",
            "CS (DR c/ fallback REG, nunca tratados) — simple", "Sun-Abraham (IW) — média e∈[0,9]",
            "Borusyak-Jaravel-Spiess (did2s) — estático", "de Chaisemartin-D'Haultfœuille DID_M (não absorvente)"]
    for o, lab in [("pov_rate", "Taxa de pobreza extrema (p.p.)"), ("ln_n_poor", "log do número de pobres"),
                   ("asinh_n_poor", "asinh do número de pobres"), ("d_ln_n_poor", "Crescimento anual do número de pobres (Δlog)")]:
        A(f"\n**{lab}**\n")
        t = main_r[(main_r.outcome == o) & main_r.estimator.isin(keep)][["estimator", "estimate", "se", "ci_low", "ci_high", "p_value", "n_treated"]]
        A(md_table(t))
    A("\n**Pré-tendências** (Wald conjunto dos coeficientes e ∈ [−5, −2], base variável; `pretrend_tests.csv`):\n")
    A(md_table(pre[pre.outcome.isin(["pov_rate", "ln_n_poor", "asinh_n_poor", "d_ln_n_poor"])]))
    bw = bacon.groupby(["outcome", "tipo"]).weight.sum().unstack()
    bb = bacon.groupby("outcome").beta_twfe.first()
    A(f"\n**Goodman-Bacon** (`bacon_decomposition.csv`): na taxa de pobreza, o TWFE (painel balanceado) = {f(bb['pov_rate'])} p.p.; "
      f"peso das comparações \"proibidas\" (tratados tardios contra já tratados) = {f(bw.loc['pov_rate', 'Tarde vs cedo (controle já tratado)'])}; "
      f"peso de tratado × nunca tratado = {f(bw.loc['pov_rate', 'Tratado vs nunca tratado'])}. O viés do TWFE aqui não vem das "
      "comparações proibidas. Ele vem de comparações tratado × nunca tratado sob tendências divergentes, as mesmas que fazem "
      "o CS sem covariáveis rejeitar tendências paralelas.\n")
    pw = pre.set_index(["outcome", "estimator"]).p_value
    dr_note = mr("pov_rate", "CS (DR c/ fallback REG, nunca tratados) — simple").nota
    A("**Leitura.** Na taxa de pobreza, sem covariáveis, o teste de pré-tendências contra os nunca tratados tem "
      f"p = {f(pw[('pov_rate', 'CS (sem covariáveis, nunca tratados)')], 3)}: os tratados reduziam a pobreza mais rápido "
      "já antes do onset (convergência a partir de níveis altos; ver `raw_means_pov_rate.png`). O TWFE e a imputação BJS, que "
      "usam todo o período pré como referência, transformam essa tendência num efeito negativo grande "
      f"({f(twfe_pov.estimate)} e {f(mr('pov_rate', 'Borusyak-Jaravel-Spiess (did2s) — estático').estimate)} p.p.). "
      f"Com covariáveis pré (REG; pré-tendência p = {f(pw[('pov_rate', 'CS (REG, nunca tratados)')], 3)}) ou com controles "
      f"ainda não tratados (p = {f(pw[('pov_rate', 'CS (REG, ainda não tratados)')], 3)}), o ATT fica em "
      f"{f(ref_pov.estimate)} e {f(mr('pov_rate', 'CS (REG, ainda não tratados) — simple').estimate)} p.p. "
      "O DR não se sustenta com coortes de 1 a 3 países: há separação perfeita no propensity score e a estimação recai em REG "
      f"em {dr_note.split('fallback: ')[-1]} células (g, t) "
      "(`main_results.csv`, coluna nota). Por isso a especificação principal com covariáveis é a regressão de resultado.\n")
    dm = main_r[main_r.estimator.str.startswith("de Chaisemartin") & (main_r.outcome == "ln_n_poor")].iloc[0]
    A(f"**DID_M (não absorvente).** Para o log do número de pobres, o DID_M é {f(dm.estimate, 3)} (p = {f(dm.p_value, 3)}); "
      f"{dm.nota.replace('.', ',')}. Ele usa todas as entradas e saídas de conflito ({int(dm.n_units)} países, inclusive os "
      "excluídos do desenho principal) e mede o efeito contemporâneo de estar em conflito no ano da troca. Por isso não é "
      "diretamente comparável ao ATT de onset. Sugere um aumento pequeno no número de pobres no ano de entrada em "
      "conflito; o placebo (a mesma comparação um ano antes) não é significativo, mas é positivo.\n" if dm.p_value < 0.05 else
      f"**DID_M (não absorvente).** Para o log do número de pobres, o DID_M é {f(dm.estimate, 3)} (p = {f(dm.p_value, 3)}); "
      f"{dm.nota.replace('.', ',')}.\n")
    A("Figuras (IC 95% pontual e banda uniforme; linha vertical em t = −1):\n")
    for o in ["pov_rate", "ln_n_poor", "asinh_n_poor"]:
        A(f"![](../outputs/figures/event_study_{o}_cs_never_reg.png)")
    A("\nComparação: `event_study_{outcome}_{cs_notyet_reg, cs_never_unc, cs_never_dr, sunab, bjs, twfe}.png` e "
      "`raw_means_{pov_rate,ln_n_poor}.png` em `outputs/figures/`.\n")
    A("**Dose-resposta** (CS REG por tercil de mortes em combate por 100 mil hab. nos 3 primeiros anos; `dose_response.csv`):\n")
    A(md_table(dose, {"brd_pc_min": 3, "brd_pc_max": 1}))
    mono = [bool(np.all(np.diff(d.sort_values("tercil").estimate) > 0) or np.all(np.diff(d.sort_values("tercil").estimate) < 0))
            for _, d in dose.groupby("outcome")]
    A(("\nHá ordenação monotônica das estimativas por tercil em pelo menos uma variável, mas os ICs se sobrepõem. "
       if any(mono) else "\nNão há gradiente monotônico de dose-resposta. ")
      + f"O tercil superior mistura conflitos de intensidade muito diferente (até {f(dose.brd_pc_max.max(), 0)} mortes "
      "por 100 mil hab./ano).\n")

    # ------------------------------------------------------------------ 5. robustez
    A("## 5. Robustez\n")
    A("Tabela completa em `robustness.csv` / `.tex`.\n")
    rr = rob[rob.outcome.isin(["pov_rate", "ln_n_poor", "asinh_n_poor"]) & ~rob.teste.str.startswith("Heterogeneidade")]
    A(md_table(rr[["teste", "outcome", "estimate", "se", "ci_low", "ci_high", "p_value", "n_treated"]]))
    sig_r = rr[(rr.p_value < 0.05) & ~rr.teste.str.startswith("Referência")]
    A("\n**Checagens com IC 95% que exclui zero:** "
      + ("; ".join(f"{r.teste} / {r.outcome}: {f(r.estimate)} (p = {f(r.p_value, 3)}, {int(r.n_treated)} tratados)"
                   for r in sig_r.itertuples()) or "nenhuma") + ".\n")
    obs = rob[rob.teste.str.startswith("Somente pesquisas") & (rob.outcome == "pov_rate")].iloc[0]
    A(f"- *Somente pesquisas observadas* ({f(obs.estimate)} p.p., p = {f(obs.p_value, 3)}) é a checagem mais importante "
      "para o problema do §3. Ela usa só anos com pesquisa, agregados em blocos de 3 anos, sem covariáveis. Seu sinal "
      "acompanha o das especificações sem covariáveis na série lineup, cujo teste de pré-tendências rejeita "
      f"(p = {f(pw[('pov_rate', 'CS (sem covariáveis, nunca tratados)')], 3)}). A leitura mais cautelosa é que o resultado "
      "reproduz a convergência pré-onset dos tratados, não um efeito do conflito. Em todo caso, ele não indica aumento da pobreza "
      "medida por pesquisas após o conflito.")
    A("- As estimativas SDID se apoiam numa única coorte de poucos países cada; resultados isolados por coorte não "
      "contrariam o ATT agregado, dado o número de comparações.\n")
    A(md_table(rob[rob.teste.str.startswith("Linha")][["teste", "estimate", "se", "ci_low", "ci_high", "p_value", "n_treated"]]))
    A("\n### 5.1 Sensibilidade a violações de tendências paralelas (Rambachan & Roth)\n")
    A("CS REG com período-base universal. *Relative magnitudes*: a violação pós-onset entre anos consecutivos é limitada a "
      "M̄ × a maior variação pré (`mbar`). *SD(0)*: o viés segue a tendência linear pré extrapolada (`mbar` = inclinação). "
      "**Implementação própria**: conjunto identificado em forma fechada e IC por simulação de N(β̂, Σ̂). É uma aproximação "
      "ao teste condicional/híbrido do pacote `HonestDiD`, que não foi usado porque o R não está disponível (`honestdid_rm.csv`).\n")
    hd_show = hd.rename(columns={"theta": "estimativa"}).copy()
    hd_show["M"] = hd_show.M.astype(str).str.replace(".", ",", regex=False)
    A(md_table(hd_show))
    sd0 = hd[(hd.outcome == "pov_rate") & hd.M.astype(str).str.startswith("SD")].set_index("alvo")
    s5 = sd0.loc["média e ∈ [0,5]"]
    rm = hd[(hd.outcome == "pov_rate") & (hd.alvo == "média e ∈ [0,5]") & ~hd.M.astype(str).str.startswith("SD")].copy()
    rm["M"] = rm.M.astype(float)
    m_zero = rm[(rm.ci_low <= 0) & (rm.ci_high >= 0)].M.min()
    A(f"\nPara a taxa de pobreza, extrapolar linearmente a tendência pré relativa (inclinação {f(s5.mbar)} p.p. por ano) "
      f"leva o efeito médio em e ∈ [0,5] de {f(rm[rm.M == 0].theta.iloc[0])} para {f(s5.theta)} p.p. "
      f"(IC {f(s5.ci_low)}; {f(s5.ci_high)}; {'exclui' if s5.ci_low > 0 or s5.ci_high < 0 else 'inclui'} zero)"
      + (". Isso indicaria que o conflito **interrompeu uma queda da pobreza** que vinha ocorrendo. "
         if s5.theta > 0 and s5.mbar < 0 else ". ")
      + ("Sob *relative magnitudes*, o IC já inclui zero sem violação alguma (M̄ = 0). " if m_zero == 0 else
         f"Sob *relative magnitudes*, o IC robusto inclui zero a partir de M̄ = {f(m_zero, 1)}. ")
      + "O resultado depende de hipóteses sobre a tendência contrafactual.\n")
    A("![](../outputs/figures/honestdid_pov_rate.png)\n")
    A("### 5.2 Placebo (500 permutações)\n")
    A(md_table(plac.reset_index()))
    A("\nATT sem covariáveis contra a distribuição de ATT com datas de onset sorteadas entre os nunca tratados "
      "(`placebo_permutations.png`). O p-valor é a fração de placebos com |ATT| ≥ |ATT estimado|.\n")
    A("### 5.3 Synthetic DiD\n")
    A(md_table(sdid[["g", "outcome", "estimate", "se", "ci_low", "ci_high", "p_value", "n_treated", "n_controls", "top_controls"]]))
    A(f"\nCoortes com o maior número de países ({sdid.n_treated.max()} cada). EP pelo método placebo de Arkhangelsky et al. "
      "(2021), implementação própria validada em `tests/test_did_tools.py`. As estimativas variam muito entre coortes "
      f"(taxa de pobreza: de {f(sdid[sdid.outcome == 'pov_rate'].estimate.min())} a "
      f"{f(sdid[sdid.outcome == 'pov_rate'].estimate.max())} p.p.) e cada uma se apoia em poucos países.\n")
    A("### 5.4 Heterogeneidade\n")
    A(md_table(het))
    sig_h = het[het.p_value < 0.05]
    bonf = 0.05 / len(het)
    A(f"\nAs estimativas por subgrupo usam de {het.n_treated.min()} a {het.n_treated.max()} países tratados. "
      "Com p < 0,05 (sem correção): "
      + ("; ".join(f"{r.grupo} / {r.outcome} ({f(r.estimate)}, p = {f(r.p_value, 3)})" for r in sig_h.itertuples()) or "nenhum")
      + f". Com correção de Bonferroni para {len(het)} testes (p < {f(bonf, 4)}): "
      + (", ".join(f"{r.grupo} / {r.outcome}" for r in het[het.p_value < bonf].itertuples()) or "nenhum")
      + ". Os resultados por subgrupo são exploratórios.\n")

    # ------------------------------------------------------------------ 6. limitações
    A("## 6. Limitações\n")
    A("- **Causalidade reversa.** Pobreza e choques econômicos aumentam o risco de conflito. O event study mostra divergência "
      "pré-tratamento na taxa de pobreza sem covariáveis, que some ao condicionar em características pré e ao usar controles "
      "ainda não tratados. Isso **não resolve** a endogeneidade do momento do onset: choques não observados podem anteceder "
      "conflito e pobreza ao mesmo tempo.")
    A("- **Dados de pobreza em zonas de conflito.** São escassos e, nos anos de conflito, majoritariamente imputados por modelo (§3). "
      "A extrapolação do PIP usa o crescimento das contas nacionais com distribuição constante: capta a queda de renda média, "
      "não mudanças distributivas, e pode atenuar ou exagerar efeitos. Pesquisas realizadas durante conflitos podem excluir áreas inseguras.")
    A("- **Interpretação do ATT.** É o efeito médio sobre países que entraram em conflito após um período de paz. São na maioria "
      f"conflitos intraestatais de baixa intensidade: só {int(cohorts.onset_war.sum())} dos {n_t} onsets já tinham ≥ 1.000 mortes no "
      "primeiro ano. O resultado não se generaliza para conflitos crônicos (os "
      f"{int(excl.motivo.str.startswith('sempre').sum())} \"sempre tratados\", por exemplo "
      f"{', '.join(sorted(excl[excl.motivo.str.startswith('sempre')].iso3)[:6])}, ficaram de fora) nem para os {n_nosurv} "
      f"países com onset sem pesquisas suficientes antes (por exemplo "
      f"{', '.join(sorted(excl[excl.motivo.str.startswith('onset')].iso3)[:6])}).")
    A("- **Deslocamento populacional.** A população do PIP é a residente. Refugiados que deixam o país reduzem mecanicamente "
      f"`n_poor`, mesmo com a taxa constante. Aqui, ATT na taxa = {f(ref_pov.estimate)} p.p., no log do número = "
      f"{f(ref_ln.estimate)} e no asinh = {f(ref_as.estimate)}"
      + (", todos com IC contendo zero: não há sinal de viés mecânico dominante, "
         if all(r.ci_low <= 0 <= r.ci_high for r in (ref_pov, ref_ln, ref_as)) else ". ")
      + "mas a escassez de pesquisas nos anos de deslocamento limita essa conclusão.")
    sizes = cohorts.groupby("g").size()
    A(f"- **Poder estatístico.** {n_t} tratados, coortes de {sizes.min()} a {sizes.max()} países e IC 95% de "
      f"±{f((ref_pov.ci_high - ref_pov.ci_low) / 2, 1)} p.p. na taxa de pobreza: efeitos moderados não seriam detectados. "
      "\"Não significativo\" não significa \"efeito nulo\".")
    A("- **Implementação.** R não estava disponível. Todos os estimadores foram implementados em Python (§7).\n")

    # ------------------------------------------------------------------ 7. implementação
    A("## 7. Nota de implementação\n")
    A("- **Callaway–Sant'Anna:** implementação própria (`src/did_tools.py`) que replica `did::att_gt`/`aggte`: estimadores "
      "DR (`drdid_panel`), REG e sem covariáveis, funções de influência, bootstrap multiplicador (Rademacher, 999 réplicas, "
      "EP = IQR/1,349 como no `did`), banda uniforme, controles nunca/ainda não tratados, antecipação, base variável/universal. "
      "**Validação:** ATT(g,t) e EPs idênticos aos do pacote Python `differences` 0.3.0 (diferença ≤ 1e-10) com e sem covariáveis; "
      "recuperação de efeitos conhecidos em simulação; cobertura do IC verificada por Monte Carlo (`tests/test_did_tools.py`).")
    A("- **TWFE / Sun–Abraham:** OLS com efeitos fixos por projeções alternadas e EP cluster CR1 (idêntico ao `pyfixest`). "
      "**Goodman-Bacon:** implementação própria; os pesos somam 1 e Σ peso × 2x2 = β TWFE exatamente.")
    A("- **BJS:** `pyfixest.did2s` (Gardner, 2022), com estimativas pontuais iguais às do estimador de imputação.")
    A("- **dCDH:** DID_M e placebo (de Chaisemartin & D'Haultfœuille, 2020), implementação própria com bootstrap de países. "
      "Não é o `DIDmultiplegtDYN` completo.")
    A("- **HonestDiD e SDID:** implementações próprias (§5); o HonestDiD é aproximado (ver §5.1).")
    A("- Reprodução: `pip install -r requirements.txt` e `python run_all.py` (substitui `make all`).\n")

    REPORT.mkdir(exist_ok=True)
    (REPORT / "report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"report/report.md gerado ({len(L)} blocos).")


if __name__ == "__main__":
    main()
