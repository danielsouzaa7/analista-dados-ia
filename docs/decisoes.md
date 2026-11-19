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
**Consequências.** O isolamento vem das permissões do Deno, e os testes exigem `NotCapable` (`test_fugas_bloqueadas_pelo_deno`). Cada execução leva alguns segundos (carregar Pyodide e pandas). O Pyodide é baixado no build (`runner.ts --preparar`) e o runtime usa `--cached-only`. `RLIMIT_AS` quebra o V8 no Linux, então o teto de memória do processo vem do contêiner.

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
