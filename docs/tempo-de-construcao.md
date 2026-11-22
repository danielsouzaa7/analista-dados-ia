# Tempo de construção

Mede só a construção do agente, até o commit `cec40ed` (agente pronto e publicado). Para reproduzir (exige os registros locais do Claude Code, que não são publicados): `python scripts/tempo_construcao.py --ate-commit cec40ed`. O trabalho de apresentação feito depois (README, animações, autoria, perfil) não está incluído.

Período (datas em horário de São Paulo): 19/11 a 21/11/2026.

| Medida | Valor |
|---|---|
| Tempo ativo de relógio | 10h06 |
| Relógio corrido | 65h49 |
| Horas paradas excluídas | 55h43 |
| Tempo somado dos agentes | 14h12 |
| Paralelismo médio | 1,4x |
| Sessões | 7 |
| Agentes | 58 |

| Categoria de agente | Agentes | Tempo somado |
|---|---|---|
| Revisão | 19 | 4h37 |
| Implementação | 27 | 8h15 |
| Spec/plano | 5 | 0h35 |
| Documentação | 3 | 0h18 |
| Testes | 2 | 0h16 |
| Outros | 2 | 0h10 |

| Sessão | Ativo |
|---|---|
| Sessão 1 | 1h40 |
| Sessão 2 | 0h01 |
| Sessão 3 | 2h58 |
| Sessão 4 | 0h01 |
| Sessão 5 | 0h00 |
| Sessão 6 | 5h26 |
| Sessão 7 | 0h03 |

## Como foi medido

1. Todos os eventos (conversa principal e subagentes) entram numa linha do tempo única.
2. Tempo ativo = soma dos intervalos entre eventos consecutivos de até 5 minutos; intervalos maiores são parada e não contam.
3. A espera pelo Daniel (do fim de um turno, sem agentes em segundo plano pendentes, até a próxima mensagem que ponha a conversa para trabalhar) não conta. A espera é por sessão: o fim de uma sessão não desconta o trabalho de outra, e sessões sobrepostas não contam o mesmo minuto duas vezes.
3a. Notificações automáticas (fim de tarefa ou de agente, mensagem de outra sessão) chegam como role=user, mas não são o Daniel; como disparam trabalho do Claude, encerram a espera, e o tempo trabalhado depois delas conta. Resultados de ferramenta, lembretes do sistema e mensagens de hook nunca encerram a espera.
3b. Comandos `!` do Daniel (entrada e saída) são ações dele, mas o tempo do comando não é construção: não encerram a espera, que só acaba na próxima mensagem digitada ou notificação. Se o comando ocorrer com a conversa ou um agente já trabalhando, esse trabalho continua contando.
4. Tempo dos agentes = tempo ativo de cada subagente na sua própria linha do tempo, somado e agrupado por tipo; paralelismo = tempo somado dos agentes / tempo ativo de relógio.
5. Período = data do primeiro e do último evento, em horário de São Paulo (só datas são publicadas); relógio corrido = último menos primeiro. As sessões são numeradas pela ordem cronológica.
6. As horas paradas somam a espera pelo Daniel e o tempo ocioso, e os registros não os separam com exatidão: sessões se sobrepõem, e uma espera de uma sessão pode coincidir com trabalho de outra. Por isso o total parado é publicado sem divisão.

Limites: o tempo que o Daniel gastou pensando fora da tela não é medido; o horário vem dos registros locais do Claude Code; os números exatos dependem do limite de ociosidade (5 minutos).

Gerado por `scripts/tempo_construcao.py` em 22/11/2026.
