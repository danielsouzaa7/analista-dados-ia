# Tempo de construção

Período (horário de São Paulo): 19/11/2026 02:13 a 21/11/2026 19:55.

| Medida | Valor |
|---|---|
| Tempo ativo de relógio | 9h59 |
| Relógio corrido | 65h42 |
| Horas paradas excluídas | 55h43 |
| Tempo somado dos agentes | 14h05 |
| Paralelismo médio | 1.4x |
| Sessões | 7 |
| Agentes | 57 |

| Categoria de agente | Agentes | Tempo somado |
|---|---|---|
| Revisão | 19 | 4h37 |
| Implementação | 26 | 8h09 |
| Spec/plano | 5 | 0h34 |
| Documentação | 3 | 0h18 |
| Testes | 2 | 0h16 |
| Outros | 2 | 0h10 |

| Sessão | Ativo |
|---|---|
| 340e7bb2 | 2h58 |
| 418eb7c4 | 0h03 |
| 488ee353 | 0h01 |
| 617cf462 | 5h19 |
| 7111805b | 0h01 |
| 8ace5006 | 1h40 |
| 8dc7fd4f | 0h00 |

## Como foi medido

1. Todos os eventos (conversa principal e subagentes) entram numa linha do tempo única.
2. Tempo ativo = soma dos intervalos entre eventos consecutivos de até 5 minutos; intervalos maiores são parada e não contam.
3. A espera pelo Daniel (do fim de um turno, sem agentes em segundo plano pendentes, até a próxima mensagem que ponha a conversa para trabalhar) não conta. A espera é por sessão: o fim de uma sessão não desconta o trabalho de outra, e sessões sobrepostas não contam o mesmo minuto duas vezes.
3a. Notificações automáticas (fim de tarefa ou de agente, mensagem de outra sessão) chegam como role=user, mas não são o Daniel; como disparam trabalho do Claude, encerram a espera, e o tempo trabalhado depois delas conta. Resultados de ferramenta, lembretes do sistema e mensagens de hook nunca encerram a espera.
3b. Comandos `!` do Daniel (entrada e saída) são ações dele, mas o tempo do comando não é construção: não encerram a espera, que só acaba na próxima mensagem digitada ou notificação. Se o comando ocorrer com a conversa ou um agente já trabalhando, esse trabalho continua contando.
4. Tempo dos agentes = tempo ativo de cada subagente na sua própria linha do tempo, somado e agrupado por tipo; paralelismo = tempo somado dos agentes / tempo ativo de relógio.
5. Período = primeiro e último evento, em horário de São Paulo; relógio corrido = último menos primeiro.

Limites: o tempo que o Daniel gastou pensando fora da tela não é medido; o horário vem dos registros locais do Claude Code; os números exatos dependem do limite de ociosidade (5 minutos).

Gerado em 21/11/2026.
