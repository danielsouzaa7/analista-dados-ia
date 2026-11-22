# Confiabilidade

O que acontece quando algo externo falha, quando duas coisas acontecem ao mesmo tempo ou quando o processo reinicia. Cada linha liga um cenário ao comportamento definido e ao teste que o comprova. Os testes usam LLM e cliente de API falsos: nenhum chama o modelo real. A coluna "Resultado" é o que a suíte mostrou em 22/11/2026 (`python -m pytest --ignore=tests/e2e` e `deno test --allow-read tests/js/`).

Legenda dos arquivos: `test_confiabilidade.py` foi escrito para este documento; os demais já existiam.

## Cenários e testes

### Modelo (Gemini) indisponível, lento ou com cota esgotada

| Cenário | Comportamento esperado | Teste | Resultado |
|---|---|---|---|
| Erro de rede ao chamar o modelo | Evento `erro` com "O serviço de IA não respondeu agora...", sem número, sem pilha, sem nome de biblioteca; uma única tentativa; nenhum turno entra na memória | `tests/test_confiabilidade.py::test_gemini_fora_do_ar_por_erro_de_rede_vira_mensagem_amigavel` | passa |
| 5xx persistente (502, 504) no modelo principal e na reserva | Mesma mensagem; o corpo do erro do provedor não aparece | `tests/test_confiabilidade.py::test_5xx_persistente_nos_dois_modelos_vira_indisponivel_sem_numero` | passa |
| 404 ou 503 só no principal | Troca para o modelo reserva e continua; o evento `llm` mostra qual modelo respondeu | `tests/test_agent.py::test_modelo_reserva_quando_o_principal_falha` | passa |
| Principal e reserva falham | Mensagem de indisponibilidade | `tests/test_agent.py::test_reserva_tambem_falhando_vira_erro_de_indisponivel` | passa |
| Timeout da API | Mensagem de indisponibilidade em português | `tests/test_agent.py::test_timeout_da_api_em_portugues` | passa |
| 429 que passa no retry | Espera o `retry-after` (ou 5 s e 10 s), emite `aguardando_cota` e continua | `tests/test_agent.py::test_429_por_minuto_espera_e_tenta_de_novo` | passa |
| 429 persistente | Faz 3 chamadas com esperas de 5 s e 10 s, depois erro de cota ("limite gratuito...") com `erro_tipo` `cota` | `tests/test_confiabilidade.py::test_429_persistente_gasta_as_duas_esperas_e_vira_erro_de_cota` | passa |
| 429 que não cabe nos 120 s | Erro de cota sem esperar | `tests/test_agent.py::test_429_que_nao_cabe_no_prazo_vira_erro_de_cota` | passa |
| 429 numa pergunta de exemplo, antes de qualquer conteúdo | O exemplo cai na gravação, marcada como tal | `tests/test_api.py::test_cota_do_provedor_esgotada_cai_na_gravacao` | passa |
| Pergunta passa dos 120 s | Interrompida com mensagem de limite de tempo | `tests/test_agent.py::test_limite_de_tempo` | passa |
| Requisição recusada (400) | Mensagem própria, diferente de indisponibilidade | `tests/test_agent.py::test_requisicao_recusada_nao_e_indisponibilidade` | passa |
| Resposta vazia | "O modelo de IA não devolveu uma resposta" | `tests/test_agent.py::test_resposta_vazia_do_stream` | passa |

### Falha parcial no meio do stream

| Cenário | Comportamento esperado | Teste | Resultado |
|---|---|---|---|
| O stream do modelo quebra depois de um trecho de texto | O cliente recebe `erro`, `metricas` e `fim`; nenhum evento `resposta`; `historico` e `turnos` ficam como antes; a pergunta seguinte funciona | `tests/test_confiabilidade.py::test_falha_no_meio_do_stream_do_llm_entrega_erro_e_nao_corrompe_o_estado` | passa |
| O socket cai no meio do stream com um erro que o SDK não converte (httpx) | O endpoint devolve `erro` e `fim` com a mensagem genérica; o log recebe só o tipo (`Erro inesperado no stream: ReadError`), sem a mensagem, e portanto sem o IP; a vaga volta; `erros["interno"]` sobe 1; a mesma sessão responde a pergunta seguinte | `tests/test_confiabilidade.py::test_stream_sse_com_falha_no_meio_termina_em_erro_e_fim_e_a_sessao_segue_usavel` | passa |
| Exceção qualquer dentro do gerador do agente | `erro` e `fim`, sem vazar a mensagem; vaga devolvida | `tests/test_api.py::test_erro_inesperado_no_meio_vira_erro_e_fim` | passa |
| O cliente fecha a aba no meio | `erro_tipo` `cancelado`; o gerador do agente é fechado; a vaga volta | `tests/test_api.py::test_stream_cancelado_conta_como_erro_cancelado`, `test_ao_vivo_fecha_o_gerador_do_agente_ao_cancelar` | passa |
| O cliente para de ler o stream | O prazo do SSE (135 s) fecha o gerador e devolve a vaga | `tests/test_api.py::test_cliente_lento_nao_segura_a_vaga` | passa |
| No navegador, o stream cai | O rascunho aparece como "interrompido" e o erro é mostrado (lado do front) | sem teste automatizado próprio; está em `static/turno.js` | não coberto |

### Postgres indisponível

| Cenário | Comportamento esperado | Teste | Resultado |
|---|---|---|---|
| URL que não conecta ao criar a sessão | 400 com mensagem fixa; senha e URL não aparecem na resposta nem no log | `tests/test_api.py::test_url_postgres_invalida_nao_vaza` | passa |
| O banco cai depois de a sessão existir (o driver falha com a URL e a senha na mensagem; o `abrir` real roda) | A exceção vira a mensagem fixa, sem causa encadeada; a ferramenta devolve "Não consegui conectar aos dados..." ao modelo, que responde sem inventar número; a senha não aparece nos passos nem no que vai ao modelo | `tests/test_confiabilidade.py::test_postgres_que_deixa_de_responder_antes_da_consulta_vira_erro_sem_segredo` | passa |
| A conexão cai no meio da consulta | `ErroUsuario` com a URL e a senha redigidas (`***`); a conexão é fechada | `tests/test_confiabilidade.py::test_postgres_que_cai_no_meio_da_consulta_nao_vaza_a_url` | passa |
| O perfil do Postgres falha ao criar a sessão | A sessão é criada sem perfil e sem grounding | `tests/test_confiabilidade.py::test_perfil_do_postgres_que_cai_nao_derruba_a_sessao`, `tests/test_sessions.py::test_perfil_do_postgres_usa_amostra_e_nao_derruba_a_sessao` | passa |
| Consulta lenta | Interrompida em 30 s com mensagem própria | `tests/test_sql_tool.py::test_timeout` | passa |

### Reinício do app

O estado de sessões, histórico, vaga de pergunta, contador diário e métricas fica só em memória (decisões 8 e 9). Depois de um reinício, ele some, e o comportamento é definido.

| Cenário | Comportamento esperado | Teste | Resultado |
|---|---|---|---|
| Reinício com uma sessão aberta | O lifespan apaga as pastas de sessão e zera métricas; pergunta, "nova conversa" e voto com o id antigo recebem 400 "Sessão expirada. Carregue seus dados de novo."; o app aceita dados novos | `tests/test_confiabilidade.py::test_reinicio_perde_as_sessoes_e_o_cliente_recebe_sessao_expirada` | passa |
| Desligamento limpo | As sessões são limpas ao sair | `tests/test_api.py::test_lifespan_limpa_sessoes_ao_sair` | passa |
| Resultado de Python chega depois do prazo (ou sem execução pendente) | 400, a mesma resposta de qualquer recusa | `tests/test_python_navegador.py::test_prazo_estourado_devolve_erro_e_recusa_resultado_atrasado`, `tests/test_api.py::test_resultado_python_valida_corpo` e `test_recusas_do_resultado_python_tem_uma_mensagem_so` | passa |
| O teto diário depois de reiniciar | Volta a zero (contador em memória, e também na virada do dia) | `tests/test_api.py::test_teto_diario_e_reinicio` cobre a virada do dia; o zero por reinício de processo não é testável no mesmo processo | parcial |

Limite: o reinício é simulado reabrindo o app (o lifespan roda de novo no mesmo processo). Uma execução de Python pendente no momento do reinício não é testada à parte: o `_PENDENTES` vive no processo, e um processo novo simplesmente não o tem, o que equivale a "sem execução pendente" (linha acima).

### Python no navegador e jsDelivr indisponível

| Cenário | Comportamento esperado | Teste | Resultado |
|---|---|---|---|
| O módulo do Pyodide não carrega da CDN (o `import` do worker falha e o navegador chama `onerror`) | A execução termina em "Não consegui carregar o Python no seu navegador." e o worker é encerrado | `tests/js/python.test.js`: "jsDelivr fora do ar: o import do worker falha (onerror) e o erro em português chega à execução" | passa |
| O worker responde `falhou` na carga | Mesmo erro; a reserva que falhou não é reaproveitada | "worker que falha ao carregar devolve erro em português", "reserva que falhou ao carregar não é reaproveitada: a execução abre um worker novo", "jsDelivr fora do ar: a reserva que falhou no onerror não é reaproveitada" | passa |
| A carga passa de 45 s | Erro de carga em português | "carga acima do prazo devolve erro em português" | passa |
| O worker falha depois de carregado | "O Python do seu navegador falhou." | "falha do worker depois de carregado (onerror) devolve o erro de falha, não trava" | passa |
| A página precisa avisar o servidor da falha | O erro é postado em `/api/python/resultado`; o servidor não espera o prazo de 80 s e o agente responde com SQL | "jsDelivr fora do ar: responderPython posta o erro de carga para o servidor não esperar o prazo", "responderPython converte erro inesperado do executor em erro em português e posta" | passa |
| A rede cai ao postar o resultado | Uma segunda tentativa; sem nova tentativa em 400 ou 422 | "responderPython tenta de novo uma vez em erro de rede", "responderPython não tenta de novo num 400 ou 422" | passa |
| O navegador nunca responde | Em 80 s o servidor devolve o erro de prazo ao agente | `tests/test_python_navegador.py::test_prazo_estourado_devolve_erro_e_recusa_resultado_atrasado` | passa |

Não testado de verdade: um jsDelivr fora do ar em navegador real. Os testes de JS usam um worker falso que dispara `onerror`; o e2e (`tests/e2e/`) roda com o jsDelivr ao vivo.

### Concorrência, sobrecarga e idempotência

| Cenário | Comportamento esperado | Teste | Resultado |
|---|---|---|---|
| Duas perguntas ao mesmo tempo (threads reais) | Uma passa; a outra recebe 429 "Muita gente usando agora"; a vaga volta no fim | `tests/test_confiabilidade.py::test_duas_perguntas_ao_mesmo_tempo_so_uma_passa_e_a_vaga_volta` | passa |
| Sem vaga | 429 | `tests/test_api.py::test_sem_vaga_responde_429` | passa |
| A vaga só é devolvida no fim do stream | Uma nova pergunta só entra depois | `tests/test_api.py::test_vaga_so_e_devolvida_no_fim_do_stream` | passa |
| 100 perguntas simultâneas contra um teto de 10 (leitura do contador com pausa de 1 ms) | Exatamente 10 passam | `tests/test_confiabilidade.py::test_teto_diario_sob_concorrencia_nao_passa_do_limite` | passa |
| 20 uploads simultâneos contra um teto de 5 sessões | No máximo 5 sessões | `tests/test_api.py::test_upload_simultaneo_nao_passa_do_teto_de_sessoes` | passa |
| Reproduções de gravação acima de 4 | 429 | `tests/test_api.py::test_reproducoes_simultaneas_tem_teto` | passa |
| Voto no mesmo turno 10 vezes ao mesmo tempo (a checagem "já votou?" espera um segundo votante) | Um 204, nove 400, uma contagem | `tests/test_confiabilidade.py::test_voto_duplicado_simultaneo_conta_uma_vez` | passa |
| Resultado de Python entregue 16 vezes em paralelo (comparação do nonce com pausa) | Só uma entrega vale, sem `KeyError` | `tests/test_confiabilidade.py::test_resultado_de_python_entregue_em_paralelo_vale_uma_vez`, `tests/test_python_navegador.py::test_resultado_aceito_uma_unica_vez` | passa |
| Limpeza de sessão vencida disputada por duas requisições | Tolerada | `tests/test_sessions.py::test_limpar_expiradas_tolera_corrida` | passa |
| Python no servidor (avaliação e testes) | No máximo 2 execuções simultâneas | `tests/test_python_tool.py::test_semaforo_limita_concorrencia` | passa |
| Execução de Python do servidor que trava | Tem prazo; não deixa processo órfão | `tests/test_python_tool.py::test_timeout`, `test_espera_final_tem_prazo` | passa |

Como os testes de lock provam o lock: cada um alarga a janela entre "ler" e "gravar" com uma pausa determinística (um `dict` com leitura lenta, um `set` cuja checagem espera um segundo votante, a comparação do nonce com pausa). Trocar o `with _LOCK:` por um contexto vazio em `_contar_pergunta`, em `feedback` ou em `entregar` deixa o teste correspondente vermelho (conferido em 22/11/2026). O teste do voto passa pelo HTTP: 10 threads com o `TestClient` votam no mesmo turno (o cliente não serializa as requisições, cada uma roda na própria thread); com `main._LOCK` trocado por `contextlib.nullcontext()` via monkeypatch o teste fica vermelho, e com o lock ele passa 3 vezes seguidas.

Não testado: carga sustentada (muitas perguntas por minuto) e latência elevada do modelo na URL publicada. Com 1 pergunta por vez e teto diário, a carga é limitada por projeto; o 0,1 vCPU do Render não foi submetido a teste de carga.

## Observabilidade

O que os logs e as métricas permitem diagnosticar, conferido no código (`app/main.py`, `app/agent.py`, `app/python_navegador.py`):

- **Uma linha JSON por pergunta** no logger `analista.metricas`, com `trace_id`, `ms`, `chamadas_llm`, `chamadas_ferramenta`, `tokens_entrada`, `tokens_saida`, `conferido`, `reanalises`, `erro_tipo`, `modelo`, `versao_prompt` e `gravacao`. Não leva a pergunta, a resposta nem dados. O mesmo `trace_id` aparece no evento `metricas` do SSE, então uma reclamação do visitante pode ser ligada à linha do log.
- **`erro_tipo`** distingue a causa: `cota`, `provedor`, `requisicao`, `limite_tempo`, `limite_ferramentas`, `limite_llm`, `resposta_vazia`, `validacao`, `interno` e `cancelado`. Isso separa "o Gemini caiu" de "o visitante fechou a aba" e de "bug nosso".
- **`modelo`** mostra se a pergunta foi atendida pelo modelo principal ou pelo reserva; `versao_prompt` liga a resposta ao texto do prompt.
- **`GET /api/metricas`** agrega em memória (perguntas, respondidas, % conferidas, reanálises médias, p50 e p90 de latência, tokens médios, votos e erros por tipo), com as últimas 2.000 execuções. Zera no reinício.
- **Eventos de erro no processo**: `Erro inesperado no stream: <TipoDaExceção>` e `Erro inesperado: <TipoDaExceção>` (só o tipo; a mensagem pode ter segredo), `Stream SSE encerrado pelo prazo`, `Gerador do SSE ainda em execução ao encerrar o stream` e `python_pedido bytes=<n>` (tamanho do pedido de Python ao navegador).
- **Linha do tempo no próprio SSE**: `llm` (fase, modelo, ms, tokens), `ferramenta_fim` (ms e erro), `aguardando_cota` e `conferencia` permitem reconstruir uma execução na tela, sem o log.

Lacunas conhecidas, para não tratar como cobertas:

- Os logs de um 429 com espera só existem como evento SSE (`aguardando_cota`); o servidor não loga cada espera.
- O erro de uma ferramenta (SQL recusado, Python com erro) vai ao modelo e ao SSE, mas não ao log do processo. O log não diz qual SQL falhou.
- A exceção completa de um erro `interno` não é registrada (só o tipo), por decisão de segurança; reproduzir exige o `trace_id` e a pergunta.
- Antes desta revisão o logger `analista` não tinha handler nem nível (a guarda `if not log.handlers` contra handler duplicado tem teste: `test_recarregar_o_modulo_nao_duplica_o_handler_do_log` recarrega o módulo duas vezes e confere 1 handler; sem a guarda ele fica vermelho): o uvicorn só configura os próprios loggers e o root fica em WARNING, então a linha JSON por pergunta (INFO) não saía do processo. `app/main.py` agora instala um handler em `stderr` e fixa o nível INFO; o teste troca o stream do handler por um buffer, faz uma pergunta e confere que a linha JSON sai nele, sem o texto da pergunta (`test_log_de_metricas_sai_no_stream_do_processo_em_producao`). Não há agregação de logs nem alarme: no Render gratuito, a leitura é pelo painel de logs.
