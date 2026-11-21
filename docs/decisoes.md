# Decisões de projeto

Registros curtos (contexto, decisão, alternativas descartadas, consequências). Os números e nomes citados estão no código; veja [arquitetura.md](arquitetura.md).

## 1. Gemini no plano gratuito, via API compatível com OpenAI, provedor trocável

**Contexto.** O projeto é uma demo pública que não pode ter custo, e o agente precisa de chamada de ferramentas e streaming.
**Decisão.** Usar o Gemini (plano gratuito do Google AI Studio) pelo endpoint compatível com OpenAI e o SDK `openai`. `LLM_BASE_URL`, `LLM_MODEL` e `LLM_API_KEY` vêm do ambiente; trocar de provedor é trocar variáveis.
**Alternativas descartadas.** SDK nativo do Google (prende o código ao provedor); modelo local (não cabe na hospedagem gratuita); API paga (custo sem teto numa demo aberta).
**Consequências.** A cota é o recurso escasso, o que motivou as decisões 9 e 10. O Gemini manda `tool_call` inteira e sem `index`, e repete `usage`; `_normalizar` acumula por id e vale o último `usage` (`test_stream_sem_index_com_extra_content_e_usage_repetido`). O modelo do plano gratuito pode usar os dados enviados para melhorar produtos, e a tela avisa.

## 2. DuckDB como motor SQL único (CSV e Postgres)

**Contexto.** O visitante traz um CSV ou um Postgres, e o agente precisa de um único caminho de validação e execução.
**Decisão.** O CSV vira um arquivo `.duckdb` por sessão, aberto somente leitura. O Postgres é anexado ao DuckDB com `ATTACH ... READ_ONLY` e um `SECRET` temporário. As duas fontes passam pelo mesmo `sql_tool.executar`.
**Alternativas descartadas.** SQLite para o CSV mais driver Postgres separado (dois dialetos, duas validações); pandas como motor (sem SQL para mostrar); executar direto no Postgres do visitante (o app não controlaria timeout nem a lista de funções).
**Consequências.** Um dialeto só (DuckDB), que o prompt explica ao modelo (sem `PIVOT`, lambdas com `lambda x:`). Para o Postgres, a defesa que não depende do app continua sendo um usuário só com `GRANT SELECT` (ver [seguranca.md](seguranca.md)).

## 3. Pyodide dentro de Deno sem permissões

**Contexto.** O agente escreve Python arbitrário (estatística com pandas) a partir de uma pergunta de um desconhecido.
**Decisão.** Rodar o código em Pyodide (WebAssembly) dentro de um subprocesso Deno iniciado sem `--allow-net`, `--allow-env`, `--allow-run`, `--allow-ffi` nem escrita; leitura só de `node_modules` e `pyodide_cache`. O ambiente do subprocesso é mínimo e não repassa `os.environ`.
**Alternativas descartadas.** Pyodide sozinho em Node: ele não isola nada, porque o código Python faz `import js` e chega a `fetch`, ao sistema de arquivos e ao ambiente do hospedeiro; `exec` no próprio processo; contêiner por execução (não existe na hospedagem escolhida); RestrictedPython (contornável).
**Consequências.** O isolamento vem das permissões do Deno, e os testes exigem `NotCapable` (`test_fugas_bloqueadas_pelo_deno`). Cada execução leva alguns segundos (carregar Pyodide e pandas). O Pyodide é baixado no build (`runner.ts --preparar`) e o runtime usa `--cached-only`. `RLIMIT_AS` quebra o V8 no Linux, então o teto de memória do processo vem do contêiner. Desde a decisão 13, o Deno roda só na avaliação, nos testes e na regressão; a página publicada roda o Python no navegador.

## 4. Conferência de números determinística em código

**Contexto.** Modelos erram ou inventam números, e o produto promete que cada número da resposta existe nos dados.
**Decisão.** `app/checker.py` extrai os números da resposta (formato brasileiro, `%`, "mil", "milhão", "bilhão") e confere cada um contra os números dos resultados das ferramentas, do SQL e código enviados, e dos turnos anteriores, com tolerância de 1%. Números inteiros de 0 a 10 e os que aparecem na pergunta são ignorados. Se algum falhar, o rascunho é descartado e o agente refaz (até 2 vezes); persistindo, a resposta sai com aviso listando os números.
**Alternativas descartadas.** Pedir ao modelo, no prompt, que confira (o mesmo modelo que erra); um segundo LLM como juiz (custa cota e também erra); sem conferência.
**Consequências.** Determinístico, testável e sem custo de LLM. Limites: confere a presença do número, não o significado (um número certo no lugar errado passa), e pode recusar um número legítimo derivado por conta (por isso as sugestões não podem ter dígitos, e o prompt manda usar as ferramentas para todo número).

## 5. Validação de SQL pela árvore sintática, com lista de proibição

**Contexto.** O SQL vem do LLM, que pode ter sido induzido por um prompt hostil ou por células do CSV. `postgres_execute` passou por uma validação por regex e permitiu escrita (ver [seguranca.md](seguranca.md), R1 e R3).
**Decisão.** Três passos: `duckdb.extract_statements` exige um único `SELECT`; `json_serialize_sql` numa conexão `:memory:` gera a árvore, e falha fechada se a análise der erro; todo `function_name` da árvore é comparado com uma lista de proibição (`query`, `query_table`, `json_execute_serialized_sql`, `json_deserialize_sql`, `json_serialize_plan` e `postgres_*`). Um regex residual em `postgres_(execute|query)` fica como segunda barreira.
**Alternativas descartadas.** Regex sobre o texto (contornado por comentário, aspas, nome qualificado e concatenação); lista de permissão de funções (o DuckDB tem centenas, e as extensões carregadas acrescentam outras; qualquer função legítima esquecida quebraria perguntas válidas e a lista envelheceria a cada versão).
**Consequências.** Funções novas que executem SQL de texto em versões futuras do DuckDB não estariam na lista. Por isso a validação não é a única camada: a conexão é somente leitura, `enable_external_access=false` e `lock_configuration=true` valem para o CSV, e o usuário do Postgres deve ter só `SELECT`. A enumeração de `duckdb_functions()` com as extensões carregadas foi feita na revisão e deve ser repetida ao atualizar o DuckDB.

## 6. SSE em vez de WebSocket

**Contexto.** A resposta tem dezenas de eventos em um sentido só (servidor para navegador) e a conversa é uma sequência de pedidos.
**Decisão.** SSE sobre `POST /api/perguntar`, com cliente próprio em `fetch` + `ReadableStream`, porque `EventSource` só faz GET e a pergunta vai no corpo.
**Alternativas descartadas.** WebSocket (bidirecional sem necessidade, mais estado no servidor, mais difícil de passar por proxies); polling (sem o efeito ao vivo).
**Consequências.** HTTP comum, cancelamento com `AbortController` e cabeçalhos `Cache-Control: no-cache` e `X-Accel-Buffering: no` contra buffering de proxy. Os eventos reproduzidos de gravação têm o mesmo formato dos ao vivo. A vaga única é segurada até o fim do stream.

## 7. Front sem build, ECharts por CDN com SRI

**Contexto.** Uma página só, mantida por uma pessoa, com gráficos de 5 tipos (inclusive mapa de calor).
**Decisão.** HTML, CSS e módulos ES servidos como arquivos estáticos. Apache ECharts 5.5.0 de cdnjs com `integrity` sha384 e `crossorigin`; a CSP só libera `script-src 'self'` e o cdnjs. O servidor entrega os dados já moldados por tipo (`app/graficos.py`) e o navegador só desenha.
**Alternativas descartadas.** Chart.js (a versão inicial do plano; sem mapa de calor nativo); framework com build (peso e passo de build sem ganho aqui); gráficos gerados no servidor com matplotlib (imagem sem interação nem acessibilidade).
**Consequências.** Nada para compilar, e a tela roda com `fake-stream.html` sem backend. Depende de CDN no carregamento; o SRI impede que uma troca do arquivo na CDN execute código.

## 8. Memória de 3 turnos com resumo

**Contexto.** Perguntas como "e só em São Paulo?" exigem contexto, mas a cota do modelo é pequena.
**Decisão.** Guardar os últimos 3 turnos por sessão, só no servidor. No prompt entra um resumo por turno (pergunta, resposta e SQLs, até 2.000 caracteres). Os resultados das ferramentas (até 10.000 caracteres por turno) alimentam só a conferência.
**Alternativas descartadas.** Histórico completo (estoura a cota e o contexto); memória entre sessões (dado do visitante guardado sem necessidade); sem memória.
**Consequências.** Acompanhamento funciona e continua verificável. O custo em tokens por pergunta cresce com o resumo. "Nova conversa" apaga tudo.

## 9. Uma pergunta por vez, teto diário e gravações, em vez de limite por IP

**Contexto.** A hospedagem gratuita põe um proxy na frente, então o IP que o app vê não é o do visitante, e a cota do Gemini é global.
**Decisão.** Um semáforo de 1 pergunta simultânea, um teto diário global (80 por padrão, `DEMO_TETO_DIARIO`) e, para as perguntas de exemplo, a reprodução de uma gravação quando não há vaga, o teto acabou ou o provedor devolveu 429 antes do conteúdo. A gravação é marcada como tal na tela.
**Alternativas descartadas.** Rate limit por IP (todos pareceriam o mesmo IP, ou o cabeçalho `X-Forwarded-For` seria forjável); fila de espera (conexões abertas e estado); login (atrito para quem avalia o portfólio).
**Consequências.** Proteção simples da cota, com o custo de que uma pessoa pode ocupar a vaga por até 120 s e o teto esgotar para todos. Contadores em memória: 1 worker, reiniciam com o processo. Quem chega com a cota esgotada ainda vê o produto, em gravação.

## 10. Cassetes de LLM para regressão offline

**Contexto.** Testar o agente de ponta a ponta com o LLM real é lento, usa a cota e não é determinístico.
**Decisão.** `scripts/avaliar.py --gravar-cassetes` grava as respostas do LLM dos casos que acertaram em `tests/cassetes/<id>.json`; `tests/test_regressao.py` as reproduz pelo agente real e exige que os números-chave apareçam e que todas as respostas gravadas sejam consumidas.
**Alternativas descartadas.** Só LLM falso com roteiro à mão (não pega mudança no prompt nem no formato real); chamar o LLM no CI (usa a cota, exige segredo, é instável).
**Consequências.** O CI roda a regressão sem segredo. Uma mudança de prompt ou de ferramenta exige regravar os cassetes. Sem cassete, o teste é pulado.

## 11. Prompts versionados

**Contexto.** Uma resposta ruim precisa ser ligada ao texto que a gerou.
**Decisão.** `app/prompts.py` concentra os prompts e tem `VERSAO`, que aparece no evento `metricas` e no log estruturado.
**Alternativas descartadas.** Prompts espalhados no código; arquivos externos lidos em runtime (mais uma superfície de erro).
**Consequências.** O número da versão é manual: quem altera o texto precisa atualizá-lo.

## 12. Modelo reserva

**Contexto.** O modelo principal pode sumir ou falhar (404, 5xx) no plano gratuito.
**Decisão.** Em `NotFoundError` ou `InternalServerError`, o cliente troca para `LLM_MODEL_FALLBACK` (padrão `gemini-flash-lite-latest`) e continua; se a reserva também falhar, o erro vira "O serviço de IA não respondeu agora". O 429 é outro caminho: espera de 5 s e 10 s (ou o `retry-after`), se couber no prazo de 120 s, com o evento `aguardando_cota`.
**Alternativas descartadas.** Falhar direto; repetir indefinidamente o modelo principal.
**Consequências.** O evento `llm` e as métricas mostram o modelo realmente usado. A reserva pode ter qualidade diferente da do principal. Testes: `test_modelo_reserva_quando_o_principal_falha`, `test_429_por_minuto_espera_e_tenta_de_novo`.

## 13. Python da IA no navegador do visitante (Pyodide em Web Worker)

**Contexto.** No Render gratuito (0,1 vCPU, 512 MB), cada `rodar_python` abria um subprocesso Deno novo com Pyodide e pandas: cerca de 5 s e 248 MB por chamada na máquina local, quase tudo carregamento. Em produção, três chamadas seguidas estouraram o limite de 30 s e apareceram como erro na conversa. Não há hospedagem gratuita com mais CPU sem cartão ou pré-pagamento, e o dono não paga.
**Decisão.** Na web, o agente recebe um executor de Python "navegador" (`app/python_navegador.py`). Ele emite `python_pedido` pelo SSE (id da chamada, nonce de 128 bits, código, CSV e o prelúdio estatístico), espera num `threading.Event` com o evento `python_aguardando` a cada 2 s e aceita um único `POST /api/python/resultado` da mesma sessão, com o mesmo id e nonce, enquanto a execução está pendente (até 80 s ou o que resta dos 120 s; corpo até 80 KB; caracteres inválidos saneados). O resultado é lido e o pendente removido na mesma seção crítica. O nonce fica entre o servidor e a página: o worker não o recebe, porque o código da IA já controla a própria saída e um nonce ali não protegeria nada; a página correlaciona a resposta pela instância do worker. O navegador roda o código num Web Worker de módulo novo a cada execução, com Pyodide 0.28.3 do jsDelivr e CSP própria na resposta do script do worker, inclusive na 304 (`script-src` e `connect-src` só no caminho do Pyodide, `'wasm-unsafe-eval'`, sem `'self'`), 45 s para carregar e 30 s para executar, encerrado com `terminate()`. Como o Starlette não fecha o gerador síncrono quando o cliente sai, `_RespostaSSE` chama `close()` no gerador explicitamente, no mesmo `finally` que devolve a vaga. Um worker de reserva é aquecido quando os dados são carregados e recriado depois de cada execução. `agent.executar` tem o executor Deno (`python_tool`) como padrão: a avaliação, os testes e a regressão continuam no servidor. A imagem de produção deixa de ter Deno.
**Alternativas descartadas.** Manter o Deno por chamada (não cabe em 0,1 vCPU); um Deno de longa duração reaproveitado (cerca de 248 MB residentes num contêiner de 512 MB junto com o DuckDB, e o estado de uma execução vazaria para a seguinte); hospedagem paga ou com cartão (recusada pelo dono); Python no processo do servidor (sem isolamento); worker reaproveitado na sessão (código injetado pelo CSV persistiria e poderia falsificar resultados seguintes, que a conferência aprovaria); Pyodide servido pelo próprio app (cerca de 20 MB por visitante novo contra 5 GB/mês de banda do Render); scipy no Pyodide (download e memória a mais em cada carga; teste t e correlação cabem num prelúdio de numpy e `math`); WebSocket (decisão 6: um POST curto basta); SharedArrayBuffer para interromper o Python (exigiria COOP/COEP em todas as respostas e recursos de terceiros compatíveis; `terminate()` resolve).
**Consequências.** O servidor não executa código da IA em produção: as fugas que importavam (chave do LLM, outras sessões, disco) deixam de existir nesse caminho. O risco passa para o navegador do visitante, com os próprios dados; a CSP do worker fecha a rede, e o resultado do cliente é dado não confiável: um visitante pode forjá-lo, mas só na própria sessão (e ele entra nas métricas globais). A primeira execução baixa cerca de 20 MB do jsDelivr; redes que bloqueiam a CDN ficam sem Python, e o agente responde com SQL. O Pyodide não tem SRI (os navegadores não o aplicam a módulos de worker): a versão está fixa no caminho e o Pyodide confere o sha256 dos pacotes. A vaga de pergunta pode ficar presa até 80 s esperando um navegador lento, mas é devolvida em até 3 s se a aba fechar: a batida faz o `next()` do gerador terminar a cada 2 s, o cancelamento do Starlette entra e o `close()` explícito leva o `GeneratorExit` ao executor, que remove o pendente. Sem esse `close()`, o gerador só seria fechado pelo coletor de lixo, numa thread e num momento quaisquer. Atrás do proxy do Render, esse tempo é medido na URL publicada. A avaliação mede o Python do servidor; o tempo no navegador vem do e2e. Testes: `test_fechar_o_gerador_remove_a_pendente`, `test_fechar_a_aba_devolve_a_vaga` (uvicorn real), `test_resultado_aceito_uma_unica_vez`, `test_csp_do_worker_so_alcanca_o_pyodide`, `test_csp_do_worker_vale_tambem_na_resposta_304`, `test_worker_nao_alcanca_rede_externa_nem_o_proprio_site` (e2e).

**Medições do spike (21/11/2026, Playwright 1.65.2: Chromium 1255, Firefox 1572, WebKit 2388; jsDelivr ao vivo).** (1) O Pyodide 0.28.3 com pandas **não exige `'unsafe-eval'`**: roda com `'wasm-unsafe-eval'` nos três motores, e `js.eval` dentro do worker é negado por isso. (2) **A CSP da resposta do worker é aplicada nos três motores** (fetch externo e ao próprio site, WebSocket e EventSource bloqueados; no WebKit o `fetch` bloqueado nunca rejeita a promessa, mas o servidor não recebe a requisição). (3) **A CSP prevista no plano (`worker-src 'none'` no worker, `worker-src 'self'` na página) não carregava o Pyodide em nenhum dos três**: o `import` estático de `pyodide.mjs` é checado contra `worker-src`. O Chromium confere contra o `worker-src` da **página** (só com `'self'` falha com `ERR_BLOCKED_BY_CSP`); Firefox e WebKit conferem contra o `worker-src` da CSP **do worker** (`'none'` bloqueia). Decisão: os dois `worker-src` passam a ter o caminho fixo `https://cdn.jsdelivr.net/pyodide/v0.28.3/full/` (a página mantém `'self'`). Isso não abre exfiltração: `worker-src` só governa de onde um worker ou módulo de worker pode ser carregado, e o caminho é o mesmo que o `script-src` do worker já libera; a saída de dados continua dependendo do `connect-src` do worker, que fica só com esse caminho, sem `'self'`. A página passa a poder criar workers desse caminho, mas ela não tem script inline nem de terceiros que o faça. Com a CSP real, os 15 testes de fuga passam nos três motores. Download: cerca de 21,4 MB decodificados em 10 requisições (pyodide.mjs, asm.js, wasm, stdlib, lock, numpy, pandas e dependências), todas com 200, **sem nenhum redirecionamento**. Carga a frio e a quente, no mesmo processo e com rede rápida: Chromium 4,5 s / 3,9 s, Firefox 6,4 s / 5,0 s, WebKit 4,5 s / 4,4 s (o custo é a instanciação do WASM e do pandas, não o download). O WebKit do Playwright não é o Safari nem o iOS.

**Medições do fluxo completo (21/11/2026, `tests/e2e/test_python_navegador.py`, Playwright 1.65.2, jsDelivr ao vivo, LLM roteirizado).** Página real, SSE, worker e POST do resultado, com o CSV de exemplo (8.000 linhas), uma pergunta com `teste_t_welch` e uma segunda logo em seguida. Tempo do passo Python, do aparecimento até a saída: 1ª execução, Chromium 4,5 a 5,5 s, Firefox 5,5 s, WebKit 5,1 s; execuções seguintes, Chromium 4,0 s, Firefox 4,8 s, WebKit 4,5 s. O `python_pedido` pesa 56.229 bytes (CSV mais código, sem compressão). Duas ressalvas. O LLM é falso e responde na hora, então o pré-aquecimento (feito ao carregar os dados) quase não tem tempo para esconder a carga: com um LLM real, a 1ª execução tende a cair para a parte restante da carga. O pré-aquecimento só roda onde `navigator.deviceMemory >= 4`; Firefox e WebKit não expõem esse campo, então ali cada execução paga a carga inteira (por isso os tempos do Firefox e do WebKit são parecidos nas duas execuções). O WebKit do Playwright não é o Safari nem o iOS.
