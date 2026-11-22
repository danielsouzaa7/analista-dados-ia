# Orquestração de agentes

Gerado por `scripts/orquestracao.py` a partir dos registros locais do Claude Code.

Mede só a construção do agente, até o commit `cec40ed`. Para reproduzir (exige os registros locais do Claude Code, que não são publicados): `python scripts/orquestracao.py --ate-commit cec40ed`.

**58 agentes geraram 2.027.193 tokens de saída; o orquestrador (conversa principal de 7 sessões) gerou 582.779** (3,5x). O pico de contexto do orquestrador foi 505.062 tokens; 57 de 58 agentes ficaram na zona de genialidade (pico até 300.000) e 1 passou dela. No máximo 5 agentes rodaram ao mesmo tempo (estimado).

Somando todo o contexto processado, o total é 170.766.532 nos agentes contra 157.573.255 no orquestrador (1,1x), bem menos favorável que a razão dos tokens gerados. Cache criado é contexto novo gravado no cache; cache lido é esse mesmo contexto relido a cada chamada, por isso infla o total bruto.

## Totais

| Medida | Agentes | Orquestrador | Razão agentes ÷ orquestrador |
|---|---:|---:|---:|
| Tokens gerados (saída) | 2.027.193 | 582.779 | 3,5x |
| Entrada nova (`input_tokens`) | 3.488 | 1.298 | 2,7x |
| Cache criado | 7.831.852 | 2.459.595 | 3,2x |
| **Tokens novos** (saída + entrada nova + cache criado) | 9.862.533 | 3.043.672 | 3,2x |
| Cache lido (releitura, não é trabalho novo) | 160.903.999 | 154.529.583 | 1,0x |
| Total bruto (tokens novos + cache lido) | 170.766.532 | 157.573.255 | 1,1x |
| Chamadas ao modelo | 1.660 | 613 | 2,7x |

## Por papel

| Papel | Agentes | Tokens gerados | Tokens novos | % dos tokens novos | Cache lido | Pico máx. | Pico mediano | Dentro da zona | Acima |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Implementador | 26 | 812.328 | 3.862.748 | 39% | 77.009.314 | 215.459 | 93.069 | 26 | 0 |
| Revisor | 12 | 371.912 | 1.838.484 | 19% | 25.048.076 | 160.096 | 115.970 | 12 | 0 |
| Engenheiro de segurança | 7 | 358.988 | 1.641.233 | 17% | 23.076.325 | 163.876 | 149.641 | 7 | 0 |
| Arquiteto | 4 | 91.152 | 941.900 | 10% | 5.629.143 | 225.163 | 76.545 | 4 | 0 |
| Planejador | 1 | 76.284 | 303.597 | 3% | 1.715.524 | 210.120 | 210.120 | 1 | 0 |
| QA | 2 | 39.631 | 215.241 | 2% | 2.661.231 | 117.641 | 73.396 | 2 | 0 |
| Documentador | 3 | 74.608 | 437.390 | 4% | 6.007.786 | 134.541 | 117.037 | 3 | 0 |
| Agente geral | 3 | 202.290 | 621.940 | 6% | 19.756.600 | 315.969 | 289.166 | 2 | 1 |

Sem registros (0 agentes): Crítico, Auditor, Pesquisador.

O papel Crítico não existiu nesta construção: as revisões foram feitas por revisores especializados e pelo engenheiro de segurança; nenhum revisor é rotulado como crítico.

## Agentes por sessão do orquestrador

| Sessão do orquestrador | Agentes | Tokens gerados pelos agentes | Tokens novos dos agentes | Pico máx. de agente | Pico do orquestrador | Ciclos de revisão | Reimplementações |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 13 | 640.607 | 2.674.036 | 315.969 | 311.740 | 2 | 1 |
| 2 | 0 | 0 | 0 | 0 | 78.885 | 0 | 0 |
| 3 | 19 | 614.097 | 2.653.258 | 163.876 | 398.116 | 2 | 1 |
| 4 | 0 | 0 | 0 | 0 | 81.295 | 0 | 0 |
| 5 | 0 | 0 | 0 | 0 | 82.956 | 0 | 0 |
| 6 | 26 | 772.489 | 4.535.239 | 289.166 | 505.062 | 3 | 3 |
| 7 | 0 | 0 | 0 | 0 | 82.411 | 0 | 0 |

Agentes criados por outros subagentes (aninhados): 2. Cada agente aparece uma vez, na sessão que o originou, e cada resposta (`message.id`) conta uma vez, na sessão principal quando também aparece num fork (cópia de uma conversa que herda o início dela).

## Agentes simultâneos: pico de 5 (estimado)

Calculado pela sobreposição dos segmentos de atividade de cada agente: pausas de mais de 15 minutos entre eventos cortam o segmento. Dentro de um segmento o agente pode estar só esperando uma resposta ou ferramenta, então o valor ainda pode superestimar; não é limite inferior.

## Agent loop (implementador → revisor; sem papel Crítico nesta construção)

| Métrica | Valor | Tipo |
|---|---:|---|
| Tarefas (lotes de implementação) | 4 | estimada |
| Tarefas revisadas / sem revisão | 3 / 1 | estimada |
| Ciclos de revisão | 7 | estimada |
| Revisões sem implementação antes na sessão | 1 | estimada |
| Voltas de revisão por tarefa revisada | 2,3 | estimada |
| Reimplementações | 5 | estimada |
| Lotes sem retrabalho após a revisão (proxy por palavras-chave; não é taxa de aprovação) | 0 de 3 (0%) | estimada |
| Veredito de cada revisor | — | indisponível |
| Agentes no papel Crítico | 0 | observada |

Tudo acima, exceto a contagem de críticos, é estimado: os registros não trazem o fluxo nem o veredito, só a ordem dos agentes e a descrição de cada um. A "tarefa" é um lote de implementação, não uma fatia individual: fatias lançadas em paralelo compartilham as mesmas revisões.

## Zona de genialidade (pico de contexto até 300 mil tokens)

| Quem | Dentro da zona | Fora da zona |
|---|---:|---:|
| Agentes | 57 | 1 |
| Orquestrador (sessões) | 4 | 3 |

## Orquestrador por sessão

| Sessão (ordem cronológica) | Pico de contexto | Compactações | Maior contexto antes de compactar |
|---|---:|---:|---:|
| 1 | 311.740 | 1 | 245.244 |
| 2 | 78.885 | 0 | — |
| 3 | 398.116 | 2 | 398.417 |
| 4 | 81.295 | 0 | — |
| 5 | 82.956 | 0 | — |
| 6 | 505.062 | 0 | — |
| 7 | 82.411 | 0 | — |

O contexto antes de compactar vem do campo `preTokens` do evento de compactação, não das chamadas; por isso pode ser maior que o pico medido pelo `usage`.

**Honestidade:** 3 sessões do orquestrador passaram de 300.000 tokens de pico; o contexto foi compactado 3 vezes (maior contexto antes de compactar: 398.417).

## Metodologia

Cada métrica é observada (lida direto do registro), calculada (fórmula sobre dados observados), estimada (heurística) ou indisponível. Os registros são lidos até o corte do projeto (`--ate`); eventos depois dele são ignorados. Contexto (tamanho da janela num instante) e tokens consumidos (soma de chamadas) são medidas diferentes e nunca se misturam.

| Métrica | Tipo | Fonte | Fórmula |
|---|---|---|---|
| Tokens gerados, entrada nova, cache criado, cache lido | observada | campo `usage` de cada resposta (agente e orquestrador) | soma por `message.id` (maior valor de cada campo): `output_tokens`, `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`; um id que aparece em mais de um arquivo (fork que herda o início da conversa) conta uma vez, na sessão principal |
| Tokens novos / total bruto / razão agentes ÷ orquestrador | calculada | `usage` | novos = saída + entrada nova + cache criado; bruto = novos + cache lido; razão = total dos agentes ÷ total do orquestrador |
| Pico de contexto (tamanho da janela num instante, não é soma) | calculada | `usage` de cada chamada | máximo, entre as chamadas, de entrada + cache lido + cache criado |
| Dentro / acima da zona de genialidade | calculada | pico de contexto | dentro se pico ≤ limite (300.000 por padrão, `--zona`) |
| Número de agentes e agentes aninhados | observada | um arquivo de registro por subagente; `toolUseId` do agente × chamadas (`tool_use`) dos registros | contagem de arquivos; aninhado = chamada feita por outro subagente; cada agente conta uma vez, com o próprio `usage` |
| Papel do agente | calculada | tipo registrado do agente (`agentType`) | tabela tipo → papel em português; qualquer prefixo `plugin:` é ignorado; tipo genérico vira "Agente geral" |
| Sessão do orquestrador (agrupamento dos agentes) | observada | arquivo da sessão que contém os agentes | cada agente pertence à sessão cujo registro o originou, numerada por ordem cronológica; os registros não trazem o nome do fluxo ou da habilidade que disparou o lote |
| Pico de agentes simultâneos | estimada | timestamps dos eventos de cada agente | segmentos de atividade = eventos separados por até 15 minutos; pico = maior nº de segmentos abertos no mesmo instante; dentro de um segmento o agente pode só estar esperando, então pode superestimar (não é limite inferior) |
| Papel Crítico (quantidade) | observada | tipo registrado do agente | contagem de agentes com tipo de crítico |
| Ciclos de revisão, voltas por tarefa, reimplementações | estimada | ordem de início e descrição dos agentes (a descrição não é publicada) | lotes consecutivos de implementação/revisão por sessão; reimplementação = lote de implementação logo após revisão com descrição de retrabalho (corrigir, fix, volta, rodada 2, ajustar…); voltas = ciclos ÷ tarefas revisadas |
| Lotes sem retrabalho após a revisão | estimada | mesma sequência | tarefas revisadas sem reimplementação ÷ tarefas revisadas; proxy por palavras-chave, não é taxa de aprovação |
| Veredito de cada revisor; tokens por tarefa aprovada; qualidade × consumo | indisponível | o veredito está em texto livre, que este script não lê; não há avaliação independente por tarefa | sem fórmula: não é calculado nem estimado |
| Compactações de contexto | observada | evento de compactação do registro | contagem; o contexto antes de compactar vem de `preTokens` do evento, não do `usage` |

Limites: o orquestrador tem poucas sessões, cada uma longa; papéis diferentes não são comparáveis em custo; volume de tokens não mede qualidade nem produtividade. Só contagens agregadas: nenhum texto, identificador, descrição ou caminho é publicado.

Gerado por `scripts/orquestracao.py` em 22/11/2026.
