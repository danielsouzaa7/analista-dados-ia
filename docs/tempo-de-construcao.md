# Tempo de construção

Período (horário de São Paulo): 19/11/2026 02:13 a 19/11/2026 16:33.

| Medida | Valor |
|---|---|
| Tempo ativo de relógio | 4h32 |
| Relógio corrido | 14h20 |
| Horas paradas excluídas | 9h48 |
| Tempo somado dos agentes | 6h22 |
| Paralelismo médio | 1.4x |
| Sessões | 4 |
| Agentes | 32 |

| Categoria de agente | Agentes | Tempo somado |
|---|---|---|
| Revisão | 14 | 3h01 |
| Implementação | 13 | 2h53 |
| Spec/plano | 2 | 0h04 |
| Documentação | 2 | 0h12 |
| Testes | 1 | 0h12 |
| Outros | 0 | 0h00 |

## Como foi medido

1. Todos os eventos (conversa principal e subagentes) entram numa linha do tempo única.
2. Tempo ativo = soma dos intervalos entre eventos consecutivos de até 5 minutos; intervalos maiores são parada e não contam.
3. A espera pela resposta do Daniel (do fim de um turno até a próxima mensagem dele) não conta, salvo se havia agentes em segundo plano trabalhando.
4. Tempo dos agentes = tempo ativo de cada subagente na sua própria linha do tempo, somado e agrupado por tipo; paralelismo = tempo somado dos agentes / tempo ativo de relógio.
5. Período = primeiro e último evento, em horário de São Paulo; relógio corrido = último menos primeiro.

Limites: o tempo que o Daniel gastou pensando fora da tela não é medido; o horário vem dos registros locais do Claude Code; os números exatos dependem do limite de ociosidade (5 minutos).

Gerado em 19/11/2026.
