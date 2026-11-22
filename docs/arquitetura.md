# Arquitetura

Última revisão: 2026-11-21. Tudo aqui foi conferido contra o código em `app/`, `sandbox/` e `static/`.

## Visão geral

Um processo FastAPI (1 worker) serve a página estática e uma API. O visitante carrega dados (CSV ou Postgres), faz uma pergunta e recebe a resposta em streaming SSE. O agente (`app/agent.py`) é um laço próprio, sem framework de agentes: chama o LLM com três ferramentas (`consultar_banco`, `rodar_python`, `gerar_grafico`), confere os números da resposta em código e refaz a análise até 2 vezes se algum número não bater. Em produção, o servidor nunca executa o Python da IA: ele pede a execução ao navegador do visitante (decisão 13). O executor Deno continua só na avaliação, nos testes e na regressão.

### O que ele faz

1. Recebe a pergunta e o modelo escreve um plano curto.
2. Em laço, chama as ferramentas: SQL só leitura (DuckDB), Python (Pyodide num Web Worker do navegador, sem rede) e gráfico (5 tipos).
3. Escreve um rascunho da resposta, transmitido ao vivo.
4. Confere em código se cada número do rascunho aparece nos resultados. Se não, descarta e refaz, até 2 vezes.
5. Entrega resposta, até 3 sugestões de próxima pergunta e métricas (tempo, tokens, trace).

## Fluxo do agente

```mermaid
flowchart TD
    P[Pergunta] --> R[evento recebido]
    R --> PL[LLM escreve o plano em até 4 passos - evento plano]
    PL --> L{LLM decide}
    L -- tool_calls --> T[Ferramentas: SQL / Python / gráfico]
    T -- ferramenta_inicio, ferramenta_fim --> L
    L -- texto --> RA[rascunho transmitido ao vivo]
    RA --> C{Conferência dos números}
    C -- todos batem --> OK[resposta + sugestões]
    C -- não batem e reanalises < 2 --> D[evento descartado] --> L
    C -- não batem após 2 reanálises --> AV[resposta com aviso]
    OK --> M[métricas e fim]
    AV --> M
```

Cada chamada ao LLM fecha com um evento `llm` (fase, modelo, ms, tokens). Qualquer limite estourado ou falha do provedor vira o evento `erro`, seguido de `metricas` e `fim`.

## Componentes

```mermaid
flowchart LR
    N[Navegador<br/>static/] <-- "POST /api/perguntar (SSE)" --> F[FastAPI<br/>app/main.py]
    F <--> A[Agente<br/>app/agent.py]
    A <-- "API compatível com OpenAI" --> G[Gemini]
    A <--> D[DuckDB]
    D --- CSV[(CSV da sessão<br/>arquivo .duckdb somente leitura)]
    D --- PG[(Postgres do visitante<br/>ATTACH READ_ONLY via SECRET)]
    N <-- "python_pedido (SSE) / POST /api/python/resultado" --> W[Web Worker novo por execução<br/>Pyodide 0.28.3 + pandas, CSP própria]
    A <-. "avaliação e testes" .-> S[Subprocesso Deno<br/>sem permissões]
    S --> P[Pyodide WASM + pandas]
```

O agente não conhece o executor de Python: `agent.executar` recebe uma função. Na web ao vivo, ela é `app/python_navegador.py` (o Worker do navegador); a avaliação (`scripts/avaliar.py`), os testes e a regressão usam o padrão, `app/python_tool.py` (Deno, aresta tracejada). O Pyodide do navegador vem do jsDelivr, não do servidor.

## Contrato de eventos SSE

`POST /api/perguntar` responde `text/event-stream`. Cada mensagem é `event: <nome>` + `data: <json>`. Os nomes e campos abaixo vêm de `app/agent.py` (`executar`). Eventos reproduzidos de uma gravação levam `"gravacao": true`.

| Evento | Campos | Quando |
|---|---|---|
| `recebido` | `modelo`, `turno` | Antes de qualquer chamada ao LLM |
| `plano` | `texto` | Fim da chamada do plano (o plano não é transmitido em pedaços) |
| `llm` | `n`, `fase` (`plano`, `ferramentas`, `resposta`), `modelo`, `ms`, `tokens_entrada`, `tokens_saida` | Fim de cada chamada ao LLM |
| `aguardando_cota` | `segundos` | O provedor devolveu 429 e o agente vai esperar para tentar de novo |
| `ferramenta_inicio` | `id`, `tipo` (`sql`, `python`, `grafico`), `sql`, `codigo` (só no Python) | Antes de rodar uma ferramenta |
| `python_pedido` | `id`, `nonce`, `codigo`, `csv`, `preludio` | Só na web ao vivo, entre `ferramenta_inicio` e `ferramenta_fim` do Python: o servidor pede ao navegador que execute o código. O nonce fica entre o servidor e a página (o worker não o recebe) |
| `python_aguardando` | `id` | A cada 2 s enquanto o servidor espera o resultado. A página o ignora; a batida faz o gerador devolver o controle ao Starlette, o que deixa o cancelamento entrar quando a aba fecha |
| `ferramenta_fim` | `id`, `ms` e: `colunas`, `linhas`, `total_linhas` (SQL); `saida` (Python); `grafico` (gráfico); ou `erro` | Depois de cada ferramenta |
| `rascunho` | `delta`, `tentativa` | Texto da resposta em pedaços. O marcador `SUGESTOES:` nunca é transmitido |
| `conferencia` | `ok`, `falhas`, `significancia`, `tentativa` | Depois de cada rascunho completo |
| `descartado` | `tentativa`, `falhas`, `significancia` | (`significancia` true: afirmou significância sem p-valor nas saídas) O rascunho foi jogado fora e haverá reanálise |
| `resposta` | `texto`, `aviso`, `reanalises`, `sugestoes`, `conferido`, `turno` | Resposta final |
| `erro` | `mensagem` | Limite, cota, provedor indisponível, validação ou erro interno |
| `metricas` | `ms_total`, `chamadas_llm`, `chamadas_ferramenta`, `tokens_entrada`, `tokens_saida`, `reanalises`, `modelo`, `custo`, `trace_id`, `versao_prompt` | Sempre, antes do `fim` |
| `fim` | (vazio) | Último evento |

Ordem típica: `recebido`, `llm`, `plano`, (`llm`, `ferramenta_inicio`, [`python_pedido`, `python_aguardando`\*,] `ferramenta_fim`)\*, `llm`, `rascunho`\*, `conferencia`, `resposta`, `metricas`, `fim`. Em `ferramenta_fim` com erro, o texto do erro volta ao LLM e o laço continua.

O contrato é executável: `static/fake-stream.html` carrega a tela inteira com `static/fake-api.js`, que troca `fetch` por um servidor falso que responde nesses eventos (perfil, métricas e feedback incluídos). Serve para desenvolver e testar a tela sem LLM nem backend.

## Outros endpoints

| Rota | Papel |
|---|---|
| `GET /` | `static/index.html` |
| `GET /api/status` | `restantes_hoje`, `teto_diario`, `modelo`, `gravacoes` (ids disponíveis) |
| `GET /api/metricas` | Agregado em memória: perguntas, respondidas, % conferidas, p50/p90, tokens médios, feedback, erros por tipo |
| `GET /api/exemplos` | Perguntas de exemplo (sem o gabarito) |
| `POST /api/sessao/csv`, `/exemplo`, `/postgres` | Criam a sessão e devolvem tabelas, perfil e perguntas sugeridas |
| `POST /api/conversa/nova` | Apaga a memória da sessão |
| `POST /api/feedback` | Nota `util`/`nao_util` do turno, com motivo opcional |
| `POST /api/python/resultado` | Devolve a saída do Python executado no navegador. Corpo `{sessao, id, nonce, saida, erro}` (até 80 KB). Aceita um único resultado por execução pendente, da mesma sessão, com o mesmo id e nonce; qualquer divergência recebe a mesma mensagem 400. 204 em caso de sucesso |

`/docs`, `/redoc` e `/openapi.json` estão desligados.

## Memória curta

`Sessao.historico` guarda os últimos 3 turnos (`MAX_TURNOS`). Cada turno tem pergunta, resposta, SQLs sem erro, um resumo de até 2.000 caracteres (`MAX_RESUMO`) e os resultados das ferramentas até 10.000 caracteres (`MAX_RESULTADOS`). O resumo entra no prompt de sistema; os resultados dos turnos anteriores entram na conferência, para que um número citado de novo ("e só em São Paulo?") continue verificável. Erros não entram no histórico. A memória vive só no servidor, por sessão, e "Nova conversa" a apaga.

## Perfil, grounding e dado pessoal

Ao criar a sessão, `app/perfil.py` calcula por coluna: nulos (%), valores distintos, mínimo e máximo (numéricas e datas) e até 5 exemplos. Colunas de texto com até 30 valores distintos (`LIMITE_VALORES`) entram inteiras no prompt como "grounding" (os valores possíveis), para o modelo filtrar por "Sul" e não por "sul". O perfil tem tempo limite de 10 s; se falhar, vira um perfil mínimo.

Dado pessoal: uma coluna é marcada `pii` (`cpf`, `email`, `telefone`) pelo nome ou quando 60% ou mais de uma amostra de 200 valores casa com o padrão. Colunas marcadas não têm exemplos nem valores no prompt, e o prompt de sistema manda só agregá-las. Isto reduz o vazamento para o LLM, mas não impede que o visitante escreva o dado na pergunta. No Postgres, o perfil usa amostra de 5.000 linhas e até 10 tabelas.

`perguntas_sugeridas` gera até 4 perguntas por regras sobre os tipos das colunas, sem LLM.

## Limites

| Limite | Valor | Onde |
|---|---|---|
| Ferramentas por pergunta | 8 | `agent.MAX_CHAMADAS` |
| Chamadas ao LLM por pergunta | 12 | `agent.MAX_CHAMADAS_LLM` |
| Reanálises | 2 | `agent.MAX_REANALISES` |
| Tempo por pergunta | 120 s (o restante é repassado ao LLM e às ferramentas) | `agent.LIMITE_SEGUNDOS` |
| Tempo por ferramenta | 30 s (ou o restante, se menor) | `agent._ferramenta`, `sql_tool.executar`, `python_tool.rodar` |
| Perguntas simultâneas | 1 (as demais recebem 429, ou a gravação se for um exemplo) | `main._VAGAS` |
| Teto diário global | 80, ou `DEMO_TETO_DIARIO` | `main.LIMITE_DIARIO` |
| Sessões | 200, TTL de 1 h | `main.MAX_SESSOES`, `sessions.TTL_SEGUNDOS` |
| Pergunta | 500 caracteres | `main.PerguntaIn` |
| Corpo JSON | 16 KB | `main.LIMITE_CORPO` |
| Upload de CSV | 20 MB (limite por Content-Length; corpo chunked recusado) | `sessions.MAX_CSV_BYTES` |
| Linhas devolvidas ao LLM | 1.000 por consulta, 50 no texto; 5.000 no gráfico | `sql_tool.executar`, `para_texto`, `agent.MAX_LINHAS_GRAFICO` |
| Linhas no `df` do Python | 100.000; acima disso a saída começa com um aviso de corte para o modelo agregar no SQL | `agent.MAX_LINHAS_PYTHON` |
| Texto de resultado | 10.000 caracteres | `sql_tool.MAX_CHARS` |
| Saída do Python | 10.000 caracteres; no executor Deno, leitura do processo até 1 MB | `python_tool.MAX_CHARS`, `MAX_STDOUT_BYTES` |
| Sandboxes simultâneos (Deno: avaliação e testes) | 2 | `python_tool.SEMAFORO` |
| Python no navegador: carga do Pyodide / execução | 45 s / 30 s, com `terminate()` | `static/python.js` |
| Python no navegador: espera do servidor por resultado | 80 s (45 + 30 + 5 de folga), ou o que resta dos 120 s da pergunta (já descontado o SQL) | `python_navegador.PRAZO_S` |
| Batida `python_aguardando` | 2 s | `python_navegador.BATIDA_S` |
| Corpo de `POST /api/python/resultado` | 80 KB | `main.LIMITE_RESULTADO_PYTHON` |
| `python_pedido` | 2 MiB por pedido serializado e 6 MiB por pergunta | `python_navegador.MAX_BYTES_PEDIDO_PYTHON`, `ORCAMENTO_BYTES_PERGUNTA` |
| DuckDB | `memory_limit` 512 MB, 2 threads, sem arquivos temporários | `sql_tool.LIMITES_DUCKDB` |
| Gráficos | ranking 12 barras (resto em "Outros"), composição 6 fatias, tendência 400 pontos e 4 séries, mapa de calor 31 x 24, dispersão 1.500 pontos | `app/graficos.py` |

Todos os contadores do teto diário e das sessões ficam em memória e reiniciam com o processo.

## Gravações e cassetes

- **Gravações** (`data/gravacoes/<id>.jsonl`): o stream de eventos de um caso da avaliação que passou, gerado por `scripts/avaliar.py` (que usa o executor Deno, então não há `python_pedido` nelas). Quando o teto diário acaba, não há vaga, ou o provedor devolve 429 antes de qualquer evento substantivo, e a pergunta veio de um exemplo (`exemplo_id`), a API reproduz a gravação, com pausa de 40% do tempo original (no máximo 1,5 s entre eventos) e `"gravacao": true` em cada evento. A tela marca o turno com o selo "gravação". O `exemplo_id` só aceita ids que existem na pasta.
- **Cassetes** (`tests/cassetes/<id>.json`): as respostas do LLM de um acerto, gravadas com `--gravar-cassetes`. `tests/test_regressao.py` as reproduz pelo agente real, sem chamar o Gemini, e confere os números-chave. Sem cassete, o teste é pulado.

Ambos são gerados por uma execução real da avaliação, que mede o Python do servidor (Deno); o tempo do Python no navegador vem do e2e (decisão 13). Com `--rodadas N` a avaliação não sobrescreve as gravações nem grava cassetes; ver [avaliacao.md](avaliacao.md).

## Observabilidade

- **Trace**: cada pergunta tem um `trace_id` (12 hex) e a `versao_prompt` (`app/prompts.py`). O evento `metricas` entrega totais; os eventos `llm` e `ferramenta_fim` entregam o tempo de cada passo. A tela monta uma cascata com esses tempos, em um bloco recolhível.
- **Métricas**: `GET /api/metricas` agrega em memória (últimas 2.000 execuções): perguntas, respondidas, % conferidas, reanálises médias, p50 e p90, tokens médios, feedback por motivo e erros por tipo (`limite_tempo`, `limite_ferramentas`, `limite_llm`, `resposta_vazia`, `validacao`, `cota`, `provedor`, `interno`). Gravações reproduzidas não entram.
- **Log estruturado**: uma linha JSON por pergunta no logger `analista.metricas`, com `trace_id`, `ms`, contagens, tokens, `conferido`, `reanalises`, `erro_tipo`, `modelo`, `versao_prompt` e `gravacao`. Não tem pergunta, resposta nem dados. Erros inesperados registram só o tipo da exceção.
- **Custo**: o campo `custo` é o texto fixo "R$ 0 (plano gratuito)".

## Front-end

Sem build: HTML, CSS e módulos ES em `static/`. Apache ECharts 5.5.0 vem de CDN com SRI (`integrity` sha384) e a CSP só libera `script-src 'self'` e a CDN. O Python roda num Worker de módulo (`static/python-worker.js`) que carrega o Pyodide do jsDelivr; a resposta desse arquivo leva uma CSP própria, sem rede além do caminho do Pyodide.

- **Trilho de passos e linha do tempo ao vivo** por turno (`turno.js`): plano, cada ferramenta (SQL, Python, gráfico) com código e tabela de resultado (até 100 linhas visíveis) e o rascunho aparecendo.
- **Conferência visível**: o rascunho aprovado recebe o selo "números conferidos"; um rascunho descartado fica marcado "descartado" e a resposta mostra "reanalisou N×". Se sobrar número sem conferência, aparece o aviso.
- **Trace em cascata**: bloco recolhível com tempo e tokens de cada chamada ao LLM e de cada ferramenta, mais totais e `trace_id`.
- **Gráficos** (`graficos.js`): ECharts com tema tirado das variáveis CSS, tema claro e escuro, botão "ver tabela" (até 200 linhas) e resumo acessível. Os 5 tipos: ranking, tendência, composição, mapa de calor (com `visualMap`) e dispersão com linha de tendência.
- **Painel de métricas da demo**: bloco recolhível que lê `/api/metricas`.
- **Feedback** 👍/👎 por turno, com motivo ao marcar 👎, enviado a `/api/feedback`.
- Cliente SSE próprio (`stream.js`) sobre `fetch` + `ReadableStream`, porque `EventSource` não faz POST. Todo texto do servidor entra por `textContent`.

## Módulos

| Arquivo | Papel |
|---|---|
| `app/main.py` | `create_app()`, rotas, SSE, teto diário, vaga única, gravações, métricas, log estruturado, cabeçalhos de segurança, limites de corpo |
| `app/agent.py` | Laço do agente, contrato de eventos, retentor do marcador `SUGESTOES:`, memória, cliente LLM com 429 e modelo reserva |
| `app/checker.py` | Conferência determinística dos números (formato BR, 1% de tolerância, `%`, "mil", "milhão") |
| `app/sql_tool.py` | Validação do SQL (extract_statements + árvore sintática), conexão travada, timeout, redação de segredos |
| `app/python_tool.py` | Executor Deno (avaliação, testes e regressão): subprocesso, entrada por stdin, nonce, teto de 1 MB, semáforo |
| `app/python_navegador.py` | Executor de produção: emite `python_pedido`, espera o resultado com batida de 2 s, aceita um único resultado por nonce, tetos de bytes |
| `app/graficos.py` | Moldagem dos 5 tipos de gráfico a partir do resultado SQL |
| `app/perfil.py` | Perfil dos dados, grounding, detecção de PII, perguntas sugeridas |
| `app/sessions.py` | Sessões isoladas (CSV vira um `.duckdb` próprio; URL Postgres só em memória), TTL |
| `app/prompts.py` | Prompts versionados (`VERSAO`) |
| `app/config.py`, `app/errors.py` | Variáveis de ambiente; `ErroUsuario` (mensagem segura em português) |
| `sandbox/runner.ts` | Executor Pyodide 0.28.3 + pandas dentro do Deno (avaliação e testes) |
| `sandbox/preludio.py` | Prelúdio estatístico (`teste_t_welch`, `teste_correlacao`; numpy e `math`, sem scipy), enviado no `python_pedido` e carregado também pelo Deno |
| `static/python.js` | Cliente do Python no navegador: worker novo por execução, reserva aquecida, prazos de 45 s e 30 s, corte da saída, `POST` do resultado com uma nova tentativa |
| `static/python-worker.js` | Worker de módulo: carrega Pyodide e pandas do jsDelivr, roda o código e devolve a saída |
| `static/` | `index.html`, `app.js`, `turno.js`, `graficos.js`, `stream.js`, `dom.js`, `marcas.js`, `style.css`, `fake-api.js`, `fake-stream.html` (além dos dois acima) |
| `scripts/gerar_exemplo.py` | Gera `data/pedidos.csv` e `data/perguntas.json` |
| `scripts/avaliar.py` | Avaliação com o LLM real, em uma ou várias rodadas (`--rodadas`); grava relatório, gravações e cassetes |
| `tests/` | Testes com LLM falso; regressão por cassetes |

## Telas

![Conversa com plano, SQL, gráfico e selo de números conferidos](img/conversa.png)

| Celular (tema escuro) | Trace do agente | Mapa de calor |
|---|---|---|
| ![Tendência no celular, tema escuro](img/m-escuro.png) | ![Trace com cascata de tempos](img/trace.png) | ![Mapa de calor de pedidos por dia e hora](img/mapa-calor.png) |

## Destaques de engenharia

- **Streaming real**: eventos SSE do plano ao último token do rascunho. Contrato em [docs/arquitetura.md](arquitetura.md).
- **Conferência determinística**: os números da resposta são checados por código, não por prompt ([decisão 4](decisoes.md)).
- **SQL validado pela árvore sintática**, com falha fechada e conexão somente leitura ([decisão 5](decisoes.md)).
- **Python no navegador**: Pyodide em Web Worker novo por execução, com CSP própria; o servidor pede a execução por SSE e aceita um único resultado por nonce ([decisão 13](decisoes.md)). O Deno sem permissões ([decisão 3](decisoes.md)) continua só na avaliação e nos testes.
- **Prelúdio estatístico**: `teste_t_welch` e `teste_correlacao` em numpy e `math`, sem scipy (`sandbox/preludio.py`). Citar significância exige um p-valor que bata com uma saída de Python.
- **Memória curta**: 3 turnos, com resumo, para perguntas de acompanhamento.
- **Grounding e LGPD**: perfil dos dados, valores categóricos no prompt e colunas com CPF, e-mail ou telefone marcadas e fora do perfil enviado à IA. A IA é instruída a só agregá-las, mas os resultados das consultas não são mascarados: não envie dados pessoais reais.
- **Trace e métricas**: cascata de tempos por pergunta, painel de métricas da demo, log JSON sem conteúdo.
- **Avaliação, gravações e cassetes**: casos com resposta esperada calculada em pandas, e regressão offline sem chamar o LLM.
- **Red team**: 5 rodadas de revisão de segurança com achados, correções e testes em [seguranca.md](seguranca.md).
- **Tela sem build**: trilho de passos, selo "números conferidos", gráficos em ECharts (com mapa de calor), feedback 👍/👎. `static/fake-stream.html` abre a tela inteira contra um servidor falso que segue o contrato de eventos.

## Glossário

| Termo | Significado |
|---|---|
| SSE | Server-Sent Events: o servidor manda eventos ao navegador numa resposta HTTP aberta (decisão 6) |
| CSP | Content Security Policy: cabeçalho que diz ao navegador de onde a página ou o Worker pode carregar recursos e para onde pode enviar dados |
| Pyodide | Python compilado para WebAssembly, que roda no navegador (e, na avaliação, dentro do Deno) |
| Web Worker | Thread do navegador sem acesso à página; aqui, um novo a cada execução de Python |
| nonce | Código de uso único: o servidor o envia à página no `python_pedido` e só aceita um resultado com o mesmo código (decisão 13) |
| pass^N | Casos que passaram em todas as N rodadas da avaliação ([avaliacao.md](avaliacao.md)) |
| cassete | Respostas do LLM gravadas de um acerto, reproduzidas pelo teste de regressão sem chamar o modelo (decisão 10) |
| gravação | Stream de eventos de um caso que passou, reproduzido pela demo quando a cota acaba (marcado na tela) |
| prelúdio | `sandbox/preludio.py`: funções de estatística (`teste_t_welch`, `teste_correlacao`) em numpy e `math`, sem scipy |
| grounding | Dar ao modelo os valores reais das colunas (perfil dos dados) para ele filtrar pelo texto certo |

Decisões e alternativas: [decisoes.md](decisoes.md). Ameaças e revisões de segurança: [seguranca.md](seguranca.md).
