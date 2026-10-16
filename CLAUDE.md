# Projeto: Medindo no escuro — conflito armado, apagão estatístico e os limites da evidência sobre pobreza (rodada 2)

> Instruções para o Claude Code. Leia este arquivo inteiro e também `docs/CLAUDE_rodada1.md`, `report/report.md` e `report/exercicios.md` antes de começar. Trabalhe em **plan mode** na primeira sessão: apresente o plano e aguarde aprovação antes de baixar dados ou escrever código.

## 0. Contexto e o que muda em relação à rodada 1

A rodada 1 estimou o efeito do onset de conflito sobre a pobreza extrema (DiD escalonado, tratamento contínuo, decomposição regional, poder estatístico). Conclusões que orientam esta rodada:

- O efeito do conflito sobre a **pobreza medida** não é identificável com os dados nacionais disponíveis. O efeito mínimo detectável fica entre 3 e 6 p.p. na taxa, e os resultados nulos não distinguem efeito zero de efeitos moderados.
- O conflito **reduz a probabilidade de haver pesquisa domiciliar** (−8,2 p.p.). Nos anos de conflito, a pobreza publicada pelo PIP é em boa parte interpolada ou extrapolada pelo PIB.
- A intensidade do conflito **reduz o PIB per capita**, e esse é o principal canal pelo qual a pobreza *estimada* responde.

O paper passa a ter como tese a **anatomia do apagão estatístico**: os exercícios econométricos servem para demonstrar e quantificar por que não se consegue medir o efeito do conflito sobre a pobreza, e o que seria necessário para conseguir.

A rodada 1 tem quatro limitações de desenho que esta rodada corrige: (a) não é comparável à classificação pública de situações de fragilidade e conflito (FCS) do Banco Mundial, referência usual em políticas de desenvolvimento; (b) usou uma única fonte de conflito (UCDP) e um limiar de 25 mortes, baixo demais, que levou EUA, Reino Unido e China ao grupo tratado; (c) não usou bases públicas relevantes, como ACLED, CPIA, missões de paz, histórico da lista FCS, deslocamento interno e pobreza multidimensional; (d) deixou de fora os países em situação de fragilidade e conflito crônicos, que concentram o problema estudado.

### Organização no repositório
- Crie a branch `rodada2`. Mova o `CLAUDE.md` anterior para `docs/CLAUDE_rodada1.md` antes de colocar este arquivo na raiz.
- **Não altere** scripts nem saídas da rodada 1. O código novo vai em `src/r2/`, as saídas em `outputs/r2/{tables,figures}` e o relatório em `report/r2_report.md`.
- Reutilize `src/did_tools.py` e as funções de construção do painel da rodada 1. Não reimplemente estimadores já validados.

## 1. Perguntas de pesquisa

**Q1. Conflito → PIB per capita.** Qual o efeito do conflito (onset e intensidade) sobre o PIB per capita? Esta é uma afirmação substantiva do paper e precisa da bateria completa de identificação.

**Q2. Conflito → produção de dados.** O conflito reduz a frequência e a cobertura das pesquisas domiciliares? Por quanto tempo? Que fração da pobreza publicada para países em conflito ou na lista FCS é **medida** e que fração é **modelada**?

**Q3. Limites da evidência sobre pobreza.** Dado Q1 e Q2:
- qual efeito sobre a pobreza o canal do PIB *prevê* mecanicamente, pela própria metodologia do PIP;
- esse efeito previsto seria detectável com o desenho disponível (efeito mínimo detectável);
- medidas alternativas (pobreza multidimensional, diferenças longas entre pesquisas observadas) contam a mesma história?

**Descritivo central.** Comparar a situação estatística de países por trajetória FCS: crônicos, que entram na lista, que saem da lista e nunca FCS.

## 2. Regras de trabalho (obrigatórias)

1. **Nunca invente, interpole ou "complete" dados manualmente.** Se um download falhar, pare e reporte o erro com a URL.
2. Toda base baixada vai para `data/raw/` sem alteração e recebe uma linha em `data/raw/MANIFEST.csv` (`arquivo, fonte, url, versão, data_download, sha256, licença/termos`).
3. **Verifique a versão vigente** de cada base e de cada metodologia na fonte oficial. Isso vale em especial para a **metodologia de classificação FCS**: não use limiares de memória nem deste documento; extraia-os da nota metodológica mais recente e registre a versão.
4. Um script por etapa em `src/r2/`, executável de ponta a ponta por `python run_r2.py`. Commit ao fim de cada etapa.
5. Ao fim de cada etapa, imprima: nº de países, anos, missings por variável e decisões tomadas.
6. **Pontos de parada** — pare e pergunte antes de:
   - (a) baixar ACLED (exige credenciais, ver §3.2);
   - (b) fixar os limiares FCS extraídos da nota metodológica;
   - (c) excluir países por critério não previsto aqui;
   - (d) iniciar a etapa subnacional opcional (§6.6).
7. Nenhum número no relatório sem origem em arquivo de `outputs/r2/`.
8. **Somente fontes públicas.** Use apenas dados e documentos abertos ao público, baixados de endereços públicos e registrados no MANIFEST com a URL. Não use documentos, bases, ferramentas ou acessos institucionais restritos. Se uma informação só estiver disponível por acesso restrito, pare e registre a lacuna em vez de buscá-la. O relatório e o código não devem conter referências a material não público.

## 3. Dados

### 3.1 Já disponíveis da rodada 1 (reutilizar)
PIP (lineup e survey, linhas 3,00/4,20/8,30, com `estimation_type`), UCDP (ACD, BRD, GED, Country-Year), WDI, WGI, classificação de renda histórica, UNHCR (COA e COO), contiguidade COW. Confirme no MANIFEST que as versões não mudaram; se mudaram, baixe de novo e registre.

### 3.2 Novas bases

| Base | Uso | Acesso / observação |
|---|---|---|
| **ACLED** | Segunda fonte de conflito, exigida pela metodologia FCS | Exige cadastro e aceite dos termos. **Pare e peça** as credenciais (`ACLED_EMAIL`, `ACLED_KEY` em `.env`, nunca no repositório). A cobertura varia por região: começa em 1997 para a África e bem depois em outras regiões. Registre a cobertura por país-ano. |
| **Lista FCS histórica do Banco Mundial** | Status FCS anual por país (desde FY2006), categoria (conflito/fragilidade institucional) e tipologia de trajetória | Páginas públicas do Banco Mundial (classification of fragile and conflict-affected situations). Baixe todas as listas anuais publicadas e a **nota metodológica publicada mais recente**. |
| **CPIA** | Qualidade institucional pré-conflito (heterogeneidade) | Série pública do WDI (`IQ.CPA.*`), disponível só para países IDA. Documente a cobertura. |
| **Missões de paz da ONU** | Heterogeneidade e diagnóstico de cobertura de pesquisas | Geo-PKO (Uppsala) ou lista oficial de operações (DPO), codificada por país-ano. |
| **IDMC** | Deslocamento interno (estoque e novos deslocamentos por conflito) | Dados públicos do IDMC. |
| **UNHCR** (agora nas estimações) | Saída de refugiados por 100 mil habitantes: critério FCS e mecanismo demográfico | Já baixado na rodada 1. |
| **Pobreza multidimensional** | Medida fora da série monetária | Global MPI (OPHI/PNUD) e/ou Multidimensional Poverty Measure do Banco Mundial. Registre os anos de pesquisa de origem: o MPI também depende de pesquisas. |
| **Statistical Performance Indicators (SPI)** | Capacidade estatística por país-ano | Banco Mundial. |
| **Catálogo de pesquisas DHS e MICS** | Contagem de pesquisas além das usadas no PIP | API do DHS Program; catálogo MICS (UNICEF). Só metadados: país, ano e tipo da pesquisa. |
| **Luminosidade noturna harmonizada** (opcional) | Checagem do PIB, também mal medido em conflito | Série harmonizada DMSP-VIIRS publicada em repositório aberto. Se o download for bloqueado, pare e avise. |

## 4. Definições de tratamento

Construa **todas** as definições abaixo e mantenha as da rodada 1 como referência de comparação.

### T1 — Conflito no padrão FCS (principal)
- Extraia da nota metodológica vigente: limiares absolutos e per capita para intensidade alta e média, por fonte (ACLED e UCDP), tipos de violência considerados e regras de exclusão.
- Conte um país-ano como em conflito **somente se atingir os limiares nas duas fontes**, como faz a metodologia FCS. Nos anos sem cobertura ACLED, crie a versão UCDP-only com os limiares UCDP e marque `t1_source = "ucdp_only"`.
- **Regra de eventos concentrados:** descarte o país-ano em que mais de 75% das mortes anuais ocorreram em uma janela de 3 dias, usando as datas de eventos do GED e do ACLED. Confirme o percentual e a janela na nota metodológica. Liste os casos descartados (devem incluir EUA 2001).
- Onset T1: primeiro ano em conflito T1 após ≥ 5 anos fora dele. Exija ≥ 3 anos de pesquisa observada antes **apenas** para as análises de pobreza (Q3); para Q1 e Q2, **não** exija pesquisas, para não excluir os casos mais graves.

### T2 — Status FCS oficial
- `fcs_any`, `fcs_conflict`, `fcs_institutional` por país-ano, a partir das listas históricas.
- **Tipologia de trajetória** (FY2006 até a lista mais recente): crônico (na lista em ≥ 80% dos anos), entrada, saída e nunca FCS. Documente as regras de corte e teste ±10 p.p. no critério do crônico.
- **Uso restrito:** T2 serve para descritivas e para a Q2. **Não** use T2 como tratamento causal sobre pobreza ou PIB: a lista é construída em parte com o CPIA, que reflete o desempenho econômico e institucional, e isso tornaria a estimativa circular. Explique isso no relatório.

### T3 — Intensidade contínua, entrando e saindo (da rodada 1)
- Mortes por 100 mil habitantes, ano a ano, em duas versões: UCDP (como na rodada 1) e média UCDP–ACLED nos anos com as duas fontes.
- Dose em asinh e em faixas alinhadas aos limiares FCS: abaixo de média, média e alta intensidade.

### Grupos de comparação
- Nunca em conflito T1 e nunca FCS no período.
- Variante: excluir dos controles países com fragilidade institucional (`fcs_institutional`), que podem ter apagão estatístico sem conflito.

## 5. Variáveis de resultado

**Q1 — PIB:** log do PIB per capita PPC (WDI), crescimento anual e, opcionalmente, log da luminosidade noturna per capita.

**Q2 — produção de dados:**
- `survey_pip`: há pesquisa nacional no PIP no país-ano;
- `survey_any`: há pesquisa no PIP, DHS ou MICS;
- `years_since_survey`: anos desde a última pesquisa no PIP;
- `share_extrapolated`: o ponto do PIP é extrapolado ou estimado por modelo (pelo `estimation_type`);
- nota SPI, quando disponível.

**Q3 — pobreza:**
- `pov_rate` em pontos percentuais (principal). Pela rodada 1, **não use log do número de pobres como resultado principal**: o efeito em log depende da escala e é artefato da diferença de níveis entre tratados e controles. Reporte-o apenas como robustez, com essa ressalva;
- `mpi_headcount`;
- `pov_rate_survey_only`: pobreza apenas em anos com pesquisa observada.

**Mecanismos demográficos:** refugiados que saem (UNHCR COO) e deslocados internos (IDMC) por 100 mil habitantes.

## 6. Análises

### 6.1 Anatomia do apagão (descritivo central, `src/r2/01_anatomy.py`)
Por trajetória FCS (T2) e por status de conflito T1, ano a ano:
1. Proporção de países com pesquisa no ano, média de anos desde a última pesquisa e distribuição do `estimation_type`.
2. **Proporção da população pobre estimada que vive em países-ano com pobreza extrapolada ou modelada**, global e dentro dos países FCS. Esta é a estatística-título do paper.
3. Países excluídos da rodada 1 por falta de pesquisa: quantos são FCS e qual a parcela da pobreza global estimada que eles representam.
4. Nota SPI e frequência de pesquisas DHS/MICS por trajetória.
5. Figura principal: linha do tempo da proporção de pobreza modelada, FCS contra não FCS.

### 6.2 Q2 — Conflito e produção de dados (`src/r2/02_survey_effect.py`)
- CS com regressão de resultado, onset T1 contra nunca tratados e ainda não tratados, para `survey_pip`, `survey_any` e `share_extrapolated`. Sem exigência de pesquisa pré-onset (§4).
- Event study de −5 a +10, para medir **por quanto tempo** o apagão dura.
- T3 contínuo (WAOSS da rodada 1) para os mesmos resultados, com placebo.
- Heterogeneidade: presença de missão de paz da ONU (medida **antes** do onset — a missão iniciada depois é resultado do conflito, não controle), CPIA pré-onset (só IDA), região e renda.
- Comparar com a rodada 1 (−8,2 p.p.).

### 6.3 Q1 — Conflito e PIB per capita (`src/r2/03_gdp_effect.py`)
- Bateria completa no onset T1: CS (REG e sem covariáveis), Sun–Abraham, BJS, event study, teste conjunto de pré-tendências, sensibilidade de Rambachan–Roth, placebo por permutação (500), antecipação de 1 e 2 anos.
- T3 contínuo com placebo, separando escaladas e desescaladas. Na rodada 1, o placebo das escaladas também foi significativo para o PIB (−1,4%): reporte o efeito líquido do placebo.
- **Causalidade reversa:** choques de renda aumentam o risco de conflito. Reporte o event study pré-onset de forma explícita e discuta.
- Robustez com luminosidade noturna, se disponível: o PIB de países em conflito também é mal medido.

### 6.4 Q3 — O que o canal do PIB prevê para a pobreza (`src/r2/04_gdp_passthrough.py`)
Para cada país tratado (onset T1) com distribuição observada antes do onset:
1. Pegue a queda de PIB per capita estimada em 6.3: o ATT agregado e, como variante, o ATT da coorte do país, em e = 0…5.
2. Sob a hipótese do PIP (distribuição constante), a pobreza na linha *z* após uma queda de x% da renda média é igual à pobreza na linha *z*/(1 − x) da distribuição original. Consulte a **API do PIP** com `povline = 3.00/(1 − x)` no último ano observado antes do onset e calcule o aumento implícito em p.p.
3. Agregue com os mesmos pesos do CS e compare com o efeito mínimo detectável (6.5) e com o ATT estimado na pobreza.
4. Pergunta-chave a responder no relatório: **mesmo o efeito mecânico que o próprio modelo do PIP produz seria detectável com este desenho?**

### 6.5 Q3 — Pobreza: efeitos, medidas alternativas e poder (`src/r2/05_poverty.py`)
- CS REG onset T1 para `pov_rate`, `pov_rate_survey_only` (blocos de 3 anos) e `mpi_headcount`.
- **Diferenças longas entre pesquisas:** para cada tratado, a última pesquisa antes do onset e a primeira depois; para os controles, pares de pesquisas com intervalo comparável no mesmo período. Estime por regressão ponderada. Usa só pobreza medida e evita a interpolação.
- **Efeito mínimo detectável** por simulação placebo, reutilizando `src/14_power_simulation.py`, para o onset T1. Reporte também 2,8 × EP real e use o maior dos dois como referência, como na rodada 1.
- Placebo do T3 contínuo para `pov_rate`: verifique se o placebo positivo das escaladas da rodada 1 desaparece quando se usa só pobreza medida. Isso testa a hipótese de que a **interpolação entre pesquisas cria pré-tendência artificial**.
- Mecanismo demográfico: efeito do onset sobre refugiados que saem e deslocados internos por 100 mil habitantes.

### 6.6 Opcional — subnacional (pare e pergunte antes)
GED e ACLED georreferenciados cruzados com o índice de riqueza do DHS (exige cadastro) ou com estimativas subnacionais de pobreza (GSAP). Comparar regiões afetadas e não afetadas dentro do mesmo país. Só inicie com aprovação explícita: muda o escopo e o prazo.

## 7. Robustez transversal
- Todas as análises de 6.2 a 6.5 com: T1 dupla fonte × UCDP-only; limiar de intensidade média × alta; janela de paz 3, 5 e 10 anos; controles com e sem fragilidade institucional.
- Comparação explícita com a definição da rodada 1 (25 mortes): quantos tratados saem, quantos entram, e como os resultados mudam.
- Bonferroni ou Romano–Wolf para as heterogeneidades.

## 8. Saídas

- `outputs/r2/tables/`: `anatomy_*.csv`, `survey_effect.csv`, `gdp_effect.csv`, `passthrough.csv`, `poverty_effects.csv`, `mde.csv`, `treatment_comparison_r1_r2.csv`, `fcs_thresholds_used.csv` (com a versão da nota metodológica), `concentrated_events_dropped.csv`.
- `outputs/r2/figures/`: linha do tempo da pobreza modelada (figura principal), event studies de Q1 e Q2, gráfico comparando o efeito implícito do PIB, o MDE e o ATT estimado.
- `report/r2_report.md`, em português, organizado pela **anatomia do apagão**:
  1. Fontes, versões e limiares FCS usados.
  2. O que mudou em relação à rodada 1 (tratados, amostra).
  3. Anatomia do apagão (6.1).
  4. Conflito e produção de dados (Q2).
  5. Conflito e PIB (Q1).
  6. O que o canal do PIB prevê e o que o desenho consegue detectar (Q3).
  7. Medidas alternativas: MPI e diferenças longas.
  8. Limitações.
  9. Implicações para produção de dados em contextos FCV.

## 9. Limitações a discutir (não omitir)

- **Circularidade da lista FCS:** o CPIA e a classificação refletem desempenho econômico e institucional. Por isso, T2 não é usado como tratamento causal.
- **ACLED:** cobertura curta e desigual por região. Os resultados com dupla fonte valem para um período menor.
- **Missões de paz:** são consequência do conflito. Só entram como característica pré-onset.
- **PIB em conflito:** as contas nacionais também se deterioram. O efeito em Q1 pode estar mal medido na mesma direção do problema que o paper descreve.
- **MPI:** também depende de pesquisas e herda parte do apagão.
- **Causalidade reversa** em Q1 e na intensidade (T3).
- **Ausência de evidência:** nenhuma conclusão do tipo "o conflito não afeta a pobreza". A formulação correta é sobre o que é detectável com os dados disponíveis.

## 10. Checklist final

- [ ] `python run_r2.py` roda do zero sem intervenção (exceto credenciais ACLED).
- [ ] MANIFEST completo, com a versão da nota metodológica FCS.
- [ ] Limiares FCS extraídos da fonte, não de memória, e registrados em `fcs_thresholds_used.csv`.
- [ ] Rodada 1 intacta; comparação r1 × r2 documentada.
- [ ] Estatística-título (proporção da pobreza modelada) calculada e verificada contra o `estimation_type` do PIP.
- [ ] Contagens de países e anos batem entre tabelas, figuras e texto.
- [ ] Limitações da §9 presentes no relatório.