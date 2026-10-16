# Projeto: Conflitos armados e crescimento da população em pobreza — análise DiD

> Instruções para o Claude Code. Leia este arquivo inteiro antes de começar e trabalhe em **plan mode** na primeira sessão: apresente o plano de execução e aguarde aprovação antes de baixar dados ou escrever código.

## 1. Pergunta de pesquisa

Qual o efeito causal do início (*onset*) de um conflito armado sobre (a) a taxa de pobreza extrema e (b) o **número absoluto** de pessoas abaixo da linha de pobreza internacional, no país afetado, nos anos seguintes ao início do conflito?

- **Unidade:** país-ano.
- **Período:** 1990 até o último ano disponível no PIP (o lado do conflito começa antes para permitir janelas de paz, ver §5).
- **Desenho:** diferenças em diferenças com adoção escalonada (*staggered*), estimadores robustos a efeitos heterogêneos. TWFE convencional entra só como referência.

## 2. Regras de trabalho (obrigatórias)

1. **Nunca invente, interpole ou "complete" dados manualmente.** Se um download falhar, pare e reporte o erro com a URL. Não substitua por números de memória.
2. Toda base baixada vai para `data/raw/` sem alteração e recebe uma linha em `data/raw/MANIFEST.csv` com: `arquivo, fonte, url, versão, data_download, sha256, licença/termos`.
3. **Verifique a versão mais recente** de cada base na página oficial antes de baixar (UCDP, PIP, WDI, PWT e V-Dem são atualizados anualmente). Não assuma o número de versão deste documento.
4. Transformações só em scripts versionados (`src/`), nunca em notebooks soltos. Um script por etapa, executável de ponta a ponta via `make all` (ou `run_all.py`).
5. Faça `git commit` ao fim de cada etapa, com mensagem descritiva.
6. Ao final de cada etapa, imprima um resumo: nº de países, anos, missings por variável, e qualquer decisão tomada.
7. **Pontos de parada:** pare e pergunte ao usuário antes de (a) fixar a definição de tratamento final, (b) excluir países da amostra por critério não previsto aqui, (c) mudar a linha de pobreza.

## 3. Ambiente

- Python ≥ 3.11 para coleta e limpeza: `pandas`, `pyarrow`, `requests`, `wbgapi`, `country_converter`, `pyfixest`, `matplotlib`.
- R ≥ 4.3 para estimação (pacotes mais maduros para DiD escalonado): `did`, `fixest`, `HonestDiD`, `synthdid`, `countrycode`, `arrow`, `modelsummary`, `ggplot2`.
- Se R não estiver disponível, use Python: `pyfixest` (TWFE, Sun–Abraham via `i()`, `did2s`) e `differences` (Callaway–Sant'Anna). Registre no relatório qual implementação foi usada.
- Crie `requirements.txt` e `renv.lock` (ou equivalente) para reprodutibilidade.

Estrutura do repositório:

```
.
├── CLAUDE.md
├── data/
│   ├── raw/            # downloads originais + MANIFEST.csv
│   ├── interim/        # bases limpas por fonte
│   └── processed/      # panel.parquet (painel final)
├── src/
│   ├── 01_download.py
│   ├── 02_clean_poverty.py
│   ├── 03_clean_conflict.py
│   ├── 04_clean_controls.py
│   ├── 05_build_panel.py
│   ├── 06_descriptives.py
│   ├── 07_estimate.R
│   └── 08_robustness.R
├── outputs/
│   ├── tables/         # .csv + .tex
│   └── figures/        # .png + .pdf
└── report/report.md
```

## 4. Coleta de dados (`01_download.py`)

### 4.1 Pobreza — variável dependente

**World Bank Poverty and Inequality Platform (PIP)** — fonte principal.

- API: `https://api.worldbank.org/pip/v1/pip?country=all&year=all&povline={linha}&fill_gaps={true|false}&format=csv`
- Baixe **duas versões**:
  - `fill_gaps=false` → só anos com pesquisa domiciliar (dado observado).
  - `fill_gaps=true` → séries "lineup" interpoladas/extrapoladas para todos os anos.
- Linha de pobreza: use a linha internacional vigente da versão do PIP (desde 2025 a base usa PPC 2021, com linha extrema de US$ 3,00/dia). **Confirme na documentação da versão baixada** e registre. Baixe também as linhas superiores (US$ 4,20 e US$ 8,30 em PPC 2021) para heterogeneidade.
- Variáveis a manter: `country_code, reporting_year, reporting_level, welfare_type, headcount, poverty_gap, poverty_severity, gini, mean, reporting_pop, survey_coverage, estimation_type` (os nomes podem variar entre versões; verifique o esquema).
- Mantenha apenas `reporting_level == "national"`. Se houver duas séries no mesmo ano (renda e consumo), mantenha uma por país de forma consistente no tempo e documente a regra.

Complementares (opcionais, para robustez):
- **WDI** `SI.POV.DDAY` (taxa de pobreza) e `SP.POP.TOTL` (população) via `wbgapi`.
- **Global MPI (OPHI/PNUD)** — pobreza multidimensional, para checar se o resultado não é artefato da medida monetária.

### 4.2 Conflito — tratamento

**UCDP/PRIO Armed Conflict Dataset (ACD)** — fonte principal.
- Download: `https://ucdp.uu.se/downloads/` (CSV da versão mais recente). Prefira o download direto; a API do UCDP pode exigir token de acesso.
- Campos-chave: `conflict_id, location, side_a, side_b, gwno_loc, type_of_conflict, intensity_level, year, start_date, start_date2, ep_end`.
- `type_of_conflict`: 1 = extrassistêmico, 2 = interestatal, 3 = intraestatal, 4 = intraestatal internacionalizado.
- `intensity_level`: 1 = 25–999 mortes em combate/ano; 2 = ≥ 1.000 (guerra).

**UCDP Battle-Related Deaths Dataset** — intensidade contínua (mortes por ano e conflito). Útil para tratamento por dose.

**UCDP Georeferenced Event Dataset (GED)** — eventos geocodificados desde 1989. Use para: mortes totais por país-ano (incluindo violência unilateral e não-estatal), e definição alternativa de tratamento.

Opcionais:
- **ACLED** — exige cadastro e aceite de termos de uso; só use se o usuário fornecer credenciais em `.env` (`ACLED_EMAIL`, `ACLED_KEY`). Nunca grave credenciais no repositório.
- **Correlates of War (COW)** — guerras com ≥ 1.000 mortes, para checagem cruzada.

### 4.3 Controles e variáveis de heterogeneidade

| Variável | Fonte | Acesso |
|---|---|---|
| PIB per capita PPC, crescimento, inflação, comércio/PIB | WDI (`NY.GDP.PCAP.PP.KD`, `NY.GDP.MKTP.KD.ZG`, `FP.CPI.TOTL.ZG`, `NE.TRD.GNFS.ZS`) | `wbgapi` |
| População total e urbana | WDI / UN World Population Prospects | `wbgapi` / site UN WPP |
| Capital humano, PIB real | Penn World Table (versão mais recente) | Dataverse / site GGDC |
| Regime político | V-Dem (`v2x_polyarchy`), Polity V | site V-Dem |
| Governança | Worldwide Governance Indicators | WDI/`wbgapi` |
| Desastres naturais | EM-DAT | exige cadastro (opcional) |
| Refugiados e deslocados (para spillovers) | UNHCR Refugee Data Finder (API), IDMC | API pública |
| Grupo de renda e região | Classificação do Banco Mundial (histórica) | site WB |

**Atenção:** controles medidos depois do início do conflito são *bad controls* (são afetados pelo tratamento). Use apenas valores pré-tratamento (média dos anos −5 a −1 ou ano-base fixo) como covariáveis nos estimadores com condicionamento.

## 5. Construção do painel e definição do tratamento (`03`, `05`)

### 5.1 Harmonização de códigos
- UCDP usa códigos Gleditsch-Ward (`gwno`); PIP/WDI usam ISO3. Converta com `countrycode` (R) ou `country_converter` (Python), e trate manualmente os casos especiais (Sérvia/Iugoslávia, Sudão/Sudão do Sul, Etiópia/Eritreia, ex-URSS, Iêmen). Liste todos os casos não casados em `outputs/tables/unmatched_codes.csv`.
- Atribua o conflito ao país **onde ocorre** (`location` / `gwno_loc`), não às partes. Conflitos interestatais com múltiplas localizações contam para cada país-localização.

### 5.2 Variáveis de conflito país-ano
- `conflict_any`: ≥ 1 conflito ativo (≥ 25 mortes) no território.
- `conflict_war`: ≥ 1 conflito com `intensity_level == 2`.
- `brd_pc`: mortes em combate por 100 mil habitantes (Battle-Related Deaths ÷ população).
- `conflict_years_cum`: anos acumulados em conflito.

### 5.3 Tratamento principal (absorvente, para DiD escalonado)
- **Coorte `g`** = ano de **início** do conflito, definido como o primeiro ano com `conflict_any == 1` após **pelo menos 5 anos consecutivos sem conflito** (parâmetro `PEACE_WINDOW = 5`, testar 3 e 10 na robustez).
- Exija ≥ 3 anos de pobreza observada antes de `g` para o país entrar como tratado.
- **Uma coorte por país:** use o primeiro onset elegível no período amostral. Onsets posteriores não geram nova coorte (o tratamento é tratado como absorvente; a reincidência entra na análise de heterogeneidade).
- **Nunca tratados:** países sem nenhum ano de conflito no território entre (início da amostra − `PEACE_WINDOW`) e o fim da amostra.
- **Sempre tratados:** países já em conflito no início da amostra sem janela de paz anterior → excluir da estimação principal (listar em tabela).
- Versão alternativa: `g` definido por `conflict_war` (≥ 1.000 mortes).

### 5.4 Variáveis de resultado
- `pov_rate`: headcount (proporção, em pontos percentuais).
- `n_poor = headcount × população`; `ln_n_poor = log(n_poor)`. Para valores zero, use `asinh(n_poor)` e reporte quantos zeros existem.
- `d_ln_n_poor`: crescimento anual do número de pobres (diferença de log).
- Variáveis secundárias: `poverty_gap`, `gini`, `mean` (consumo/renda média).

### 5.5 Painel final
Salve `data/processed/panel.parquet` com: `iso3, year, g, treated, rel_time, pov_rate, ln_n_poor, …, controles_pré, flag_observed_survey`. A flag `flag_observed_survey` indica se o ponto de pobreza é de pesquisa (`fill_gaps=false`) ou interpolado.

## 6. Descritivas e diagnóstico de seleção (`06_descriptives.py`)

Antes de estimar, produza:

1. Tabela de coortes: países por ano de onset, tipo e intensidade.
2. Mapa ou lista de países tratados, nunca tratados e excluídos.
3. Médias pré-tratamento por grupo (tratados × controles) com teste de diferença.
4. Gráfico de médias brutas de `pov_rate` e `ln_n_poor` em tempo relativo.
5. **Diagnóstico crítico — dados faltantes:** pesquisas domiciliares tendem a parar durante conflitos, e as séries "lineup" do PIP nesses anos são extrapoladas por modelo (frequentemente com base no PIB). Calcule:
   - proporção de anos com pesquisa observada antes e depois de `g`, tratados × controles;
   - regressão de `flag_observed_survey` sobre o tratamento (o conflito reduz a probabilidade de haver pesquisa?).
   Reporte o resultado em destaque no relatório; ele condiciona a interpretação de tudo o que vem depois.

## 7. Estimação (`07_estimate.R`)

### 7.1 Referência: TWFE
`y_it = α_i + λ_t + β·D_it + ε_it`, com `D_it = 1{t ≥ g_i}`. Erros-padrão agrupados por país. Reporte, mas **não use como resultado principal** (viés com efeitos heterogêneos e adoção escalonada). Rode a decomposição de Goodman-Bacon para mostrar o peso das comparações "proibidas".

### 7.2 Principal: Callaway & Sant'Anna (2021)
- Pacote `did`: `att_gt(yname, tname="year", idname, gname="g", control_group="nevertreated", est_method="dr", xformla=~ controles_pré)`.
- Agregações: `aggte(type="dynamic", min_e=-5, max_e=10)` (event study), `type="group"`, `type="simple"`.
- Repita com `control_group="notyettreated"`.
- Bootstrap com cluster por país.

### 7.3 Complementares
- **Sun & Abraham (2021)** via `fixest::sunab(g, year)`.
- **Borusyak, Jaravel & Spiess (2024)** — imputação (`didimputation` em R ou `did2s`).
- **de Chaisemartin & D'Haultfœuille** (`DIDmultiplegtDYN`) — permite tratamento não absorvente (entra e sai de conflito); use como checagem da hipótese de absorção.

### 7.4 Tratamento contínuo (intensidade)
Event study com `brd_pc` em faixas (tercis entre tratados) ou o estimador de Callaway, Goodman-Bacon & Sant'Anna para DiD contínuo, se disponível. Objetivo: verificar gradiente dose-resposta.

## 8. Robustez e validade (`08_robustness.R`)

1. **Tendências paralelas:** coeficientes pré-tratamento do event study + teste conjunto. Sensibilidade de Rambachan & Roth (`HonestDiD`) para violações de até M = {0, 0,5, 1, 1,5, 2} vezes a maior variação pré-tratamento.
2. **Somente dados observados:** reestimar usando apenas `flag_observed_survey == 1`, agregando em blocos de 3 anos para reduzir lacunas.
3. **Janela de paz:** `PEACE_WINDOW` ∈ {3, 5, 10}.
4. **Intensidade:** tratamento por `conflict_war` (≥ 1.000 mortes).
5. **Spillovers:** excluir do grupo controle os países vizinhos de tratados (contiguidade terrestre via dados de fronteira do COW ou CShapes) e os grandes receptores de refugiados (UNHCR). Em seguida, estimar o efeito sobre os vizinhos como tratamento à parte.
6. **Antecipação:** `anticipation = 1` e `= 2` no `att_gt`.
7. **Synthetic DiD** (`synthdid`) para as coortes com maior número de países.
8. **Placebo:** atribuir datas de onset aleatórias aos nunca tratados (500 permutações) e comparar a distribuição com o ATT estimado.
9. **Medida alternativa:** linhas de US$ 4,20 e US$ 8,30; MPI quando disponível.
10. **Heterogeneidade:** região, grupo de renda pré-conflito, tipo de conflito (intra × interestatal), duração (≤ 2 anos × > 2 anos), regime político pré-conflito.

## 9. Saídas esperadas

- `outputs/tables/main_results.(csv|tex)`: ATT agregado por estimador e variável de resultado.
- `outputs/figures/event_study_{outcome}_{estimator}.png`: com IC 95% e linha em t = −1.
- `outputs/tables/robustness.(csv|tex)`.
- `outputs/tables/cohorts.csv`, `excluded_countries.csv`, `unmatched_codes.csv`.
- `report/report.md` contendo: (1) fontes e versões (copiar do MANIFEST), (2) decisões de construção da amostra, (3) diagnóstico de dados faltantes, (4) resultados principais, (5) robustez, (6) limitações. Escreva em português.

## 10. Limitações a discutir no relatório (não omitir)

- **Causalidade reversa:** pobreza e choques econômicos aumentam o risco de conflito. O event study mostra se há divergência pré-tratamento, mas não resolve o problema; registre isso explicitamente.
- **Dados de pobreza em zonas de conflito** são escassos e, nos anos de guerra, frequentemente imputados por modelo. Isso pode atenuar ou exagerar efeitos.
- **Interpretação do ATT:** efeito médio sobre países que entraram em conflito após um período de paz — não generalizável para conflitos crônicos.
- **Deslocamento populacional:** refugiados que saem do país reduzem a população residente e podem reduzir mecanicamente `n_poor`. Compare os resultados para taxa e para número absoluto e discuta.

## 11. Checklist final antes de entregar

- [ ] `make all` (ou `python run_all.py`) roda do zero sem intervenção.
- [ ] MANIFEST completo, com versão e hash de todas as bases.
- [ ] Nenhum número no relatório sem origem em um arquivo de `outputs/`.
- [ ] Contagens de países e anos batem entre tabelas, figuras e texto.
- [ ] Diagnóstico de seleção por dados faltantes incluído e discutido.
- [ ] Limitações da §10 presentes no relatório.