Leia CLAUDE.md, report/exercicios.md e src/10_exercise_intensity.py antes de começar.
Apresente o plano e aguarde minha aprovação antes de escrever código.

## Objetivo
No exercício 1 (especificação "limiar_1": onset com ≥ 1 morte em combate/100 mil,
sem países de renda alta, 18 tratados), a taxa de pobreza não muda (ATT ≈ −0,38 p.p.),
mas o log do número de pobres sobe ≈ 0,15. Hipótese a testar: o efeito em log vem de
países com pobreza inicial muito baixa, concentrados em Europa e Ásia Central
(region_code == "ECS": GEO, TJK, TUR, UKR, AZE, ARM), onde pequenas variações em p.p.
viram grandes variações em log.

## Tarefa
Crie src/13_exercise_region_decomp.py, reutilizando as funções de construção do
tratamento e de estimação já existentes (src/10_exercise_intensity.py e
src/did_tools.py). Não reimplemente o Callaway–Sant'Anna. Use sempre o estimador de
referência do exercício 1: CS com regressão de resultado (REG), nunca tratados,
mesmas covariáveis pré-tratamento, bootstrap multiplicador por país.

1. Contribuição de cada tratado (descritiva, sem inferência)
   Para cada um dos 18 tratados: região, pov_rate média em g−5..g−1, n_poor médio
   em g−5..g−1, e variação média entre g−5..g−1 e g..g+5 em pov_rate (p.p.),
   ln_n_poor e ln(pov_rate). Inclua a mesma variação para a média dos nunca tratados
   nos mesmos anos-calendário, e a diferença tratado − controle.
   Saída: outputs/tables/ex3_treated_contributions.csv

2. ATT por subamostra de tratados, para pov_rate, ln_n_poor e asinh_n_poor
   (a) todos os 18 (deve reproduzir ex1; se não reproduzir, pare e me avise);
   (b) sem os tratados ECS;
   (c) só os tratados ECS.
   Em (b) e (c), mantenha o mesmo grupo de nunca tratados. Como variante de (c),
   use como controles apenas nunca tratados de ECS.
   Saída: outputs/tables/ex3_region_att.csv (com n de tratados e de controles)

3. Leave-one-out
   Reestime o ATT de ln_n_poor e de pov_rate retirando um tratado de cada vez.
   Saídas: outputs/tables/ex3_leave_one_out.csv e um gráfico de pontos com IC 95%
   ordenado pela estimativa, marcando a estimativa completa e os países ECS
   (outputs/figures/ex3_leave_one_out_{outcome}.png/.pdf).

4. Decomposição do log do número de pobres
   ln(n_poor) = ln(pov_rate) + ln(população). Na mesma amostra (sem zeros, mesmas
   unidades e covariáveis), estime o ATT de ln(pov_rate) e de ln(reporting_pop).
   Verifique numericamente que ATT(ln_rate) + ATT(ln_pop) = ATT(ln_n_poor)
   (tolerância 1e-6) e reporte o resultado do teste.
   Converta o ATT em log para p.p. por país: pov_rate_pré × (exp(ATT) − 1).
   Saída: outputs/tables/ex3_log_decomposition.csv

## Regras
- Não altere scripts nem saídas anteriores; só acrescente arquivos novos com prefixo ex3_.
- Subgrupos com poucos tratados: reporte n e EP, mas não tire conclusão de
  significância com menos de 5 tratados.
- Ao final, gere a seção "Exercício 3 — Decomposição regional do efeito no número
  de pobres" em report/exercicios.md, a partir dos CSVs (estenda
  src/12_report_exercises.py), com uma leitura objetiva: a hipótese se confirma ou não?
- Rode os testes existentes (tests/) e acrescente um teste para a identidade da
  decomposição.
- Faça commit ao final, com mensagem descritiva.