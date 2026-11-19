# Plano: Agente analista de dados de IA (MVP completo)

**Spec**: `Spec.md` (raiz) — leia inteira antes de começar; os critérios de aceite numerados 1–11 são o contrato.
**Marcos**: todos (1 Ferramentas seguras, 2 Agente, 3 Interface + exemplo, 4 README/Docker; o deploy fica para depois da aprovação do Daniel).
**Complexidade**: Média.

## Resumo
App web FastAPI de uma página. O visitante carrega um CSV (ou o de exemplo) ou conecta um Postgres, faz uma pergunta em português e o agente: planeja → chama ferramentas (SQL só leitura via DuckDB, Python em sandbox Pyodide+Deno, gráfico Chart.js) → confere os números da resposta contra os resultados das ferramentas (refaz até 2×) → devolve plano, SQL, Python, gráficos e resposta.

## Decisões já tomadas (não reabrir)
- **LLM**: Google Gemini, plano gratuito, pela API compatível com OpenAI, usando o SDK `openai` de Python. Variáveis: `LLM_API_KEY` (obrigatória, já está no `.env` — **nunca leia, imprima ou registre o valor**), `LLM_BASE_URL` (padrão `https://generativelanguage.googleapis.com/v1beta/openai/`), `LLM_MODEL` (padrão definido no fim deste plano). Carregue o `.env` com `python-dotenv`.
- **Gemini via OpenAI compat — mensagens de ferramenta**: ao devolver a mensagem do assistente com `tool_calls` para o histórico, use `msg.model_dump(exclude_none=True)` (preserva campos extras como as assinaturas de pensamento que os modelos Gemini 3 exigem). Responda cada `tool_call` com `{"role": "tool", "tool_call_id": id, "content": texto}`.
- **SQL**: DuckDB. **Python da IA**: Pyodide 0.28.3 dentro de Deno sem permissões (viabilidade já testada: pandas carrega offline do cache; `fetch`, `Deno.env` e leitura de arquivo fora da pasta liberada são bloqueados com `NotCapable`).
- **Gráficos**: ferramenta própria que devolve uma especificação; o navegador desenha com Chart.js (cdnjs, versão fixa `4.4.1`). Nada de matplotlib.
- **Hospedagem**: Hugging Face Spaces (Docker, porta 7860, usuário 1000).
- Endpoints síncronos (`def`), porque DuckDB e subprocess são bloqueantes; o FastAPI os roda no threadpool.

## Padrões a seguir
Projeto novo: não há código existente para espelhar. Seguir as regras do ECC em `.claude/rules/ecc/python/` (coding-style, fastapi, security, testing): anotações de tipo em todas as funções, PEP 8, `create_app()`, schemas Pydantic de request/response separados, `response_model` nos endpoints, nunca registrar segredos, pytest. Textos visíveis ao usuário em português do Brasil.

## Arquivos
| Arquivo | Ação | Por quê |
|---|---|---|
| `requirements.txt` | CREATE | fastapi, uvicorn, python-multipart, duckdb, openai, python-dotenv (versões fixas). pandas não entra aqui: o app não usa; só o script de exemplo e os testes |
| `requirements-dev.txt` | CREATE | `-r requirements.txt`, pytest, httpx, pandas |
| `app/config.py` | CREATE | lê env (`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`), caminhos (`DATA_DIR`, pasta de sessões, pasta do sandbox) |
| `app/sessions.py` | CREATE | sessões isoladas, TTL 1 h, limpeza na inicialização |
| `app/sql_tool.py` | CREATE | validação "só SELECT", conexão só leitura, timeout, limite de linhas, redação de segredos |
| `app/python_tool.py` | CREATE | chama o Deno com o código + CSV pelo stdin, timeout 30 s, saída cortada em 10 mil caracteres |
| `app/checker.py` | CREATE | conferência dos números (critério 7) |
| `app/agent.py` | CREATE | orquestrador: plano → laço de ferramentas → conferência → reanálise |
| `app/main.py` | CREATE | `create_app()`, rotas, arquivos estáticos |
| `static/index.html`, `static/app.js`, `static/style.css` | CREATE | interface pt-BR responsiva |
| `sandbox/runner.ts`, `sandbox/deno.json`, `sandbox/deno.lock` | CREATE | executor Pyodide |
| `scripts/gerar_exemplo.py` | CREATE | gera `data/vendas.csv` e `data/perguntas.json` (com respostas esperadas calculadas em pandas) |
| `data/vendas.csv`, `data/perguntas.json` | CREATE (gerados) | dados de exemplo |
| `tests/…` | CREATE | ver Tarefas |
| `Dockerfile`, `.dockerignore` | CREATE | imagem para o HF Spaces |
| `README.md` | CREATE | arquitetura (diagrama Mermaid do fluxo), segurança, como rodar, como publicar |

## Tarefas (testes primeiro em cada uma)

### 1. Ambiente
- `uv venv .venv --python 3.12` (o Python global é 3.14; use 3.12 para bater com o Docker) e `uv pip install -r requirements-dev.txt`.
- **Validar**: `.venv/Scripts/python -c "import duckdb, fastapi, openai"`.

### 2. Dados de exemplo (`scripts/gerar_exemplo.py`)
- `random.seed(42)`, ~600 vendas de 2024. Colunas: `data` (AAAA-MM-DD), `regiao` (Norte, Nordeste, Centro-Oeste, Sudeste, Sul), `produto`, `categoria` (Eletrônicos, Casa, Moda, Esportes), `quantidade` (int), `preco_unitario` (2 casas), `receita` (= quantidade × preço, 2 casas). Faça preço e quantidade terem correlação negativa moderada para a pergunta 5 ser interessante.
- `data/perguntas.json`: lista de 5 `{pergunta, usa: [sql|python|grafico], esperado}` com `esperado` calculado em pandas:
  1. "Qual foi a receita total por região?" (SQL + gráfico de barras)
  2. "Como a receita evoluiu mês a mês em 2024?" (SQL + gráfico de linha)
  3. "Qual a participação de cada categoria na receita total?" (SQL + gráfico de pizza)
  4. "Qual a média, a mediana e o desvio padrão da receita por venda?" (Python)
  5. "Existe correlação entre o preço unitário e a quantidade vendida?" (Python)
- **Validar**: rodar o script; arquivos gerados e determinísticos (rodar 2× dá o mesmo hash).

### 3. Sessões (`app/sessions.py`) — critério 1, 2, 3
- `Sessao` (dataclass): `id` (`secrets.token_urlsafe(16)`), `tipo` (`"csv"`|`"postgres"`), `caminho_db` (CSV) ou `pg_url` (só em memória, **nunca em disco nem em log**), `ultimo_uso`, `tabelas` (descrição do esquema).
- `criar_de_csv(nome_arquivo, bytes)`: valida tamanho ≤ 20 MB; grava o CSV temporário dentro de `DATA_DIR/sessions/<id>/`; abre uma conexão **gravável** só para `CREATE TABLE <nome> AS SELECT * FROM read_csv_auto(?)`; apaga o CSV; fecha. Nome da tabela = nome do arquivo sem extensão, minúsculo, só `[a-z0-9_]`, começando por letra; se vazio, `dados`. CSV ilegível → `ErroUsuario("Não consegui ler esse CSV…")`.
- `criar_de_postgres(url)`: testa a conexão (ver tarefa 4), lista tabelas/colunas do schema `public` e guarda a URL só no objeto.
- `obter(id)`: devolve a sessão e atualiza `ultimo_uso`; id desconhecido → `ErroUsuario("Sessão expirada…")`. `limpar_expiradas()` remove sessões com mais de 1 h sem uso (apaga a pasta); chame em cada requisição. Na inicialização do app, apague `DATA_DIR/sessions/` inteira.
- Esquema devolvido: `[{"nome": str, "colunas": [{"nome": str, "tipo": str}], "linhas": int | None}]`.
- **Testes**: duas sessões com CSVs diferentes — o SQL de uma não enxerga a tabela da outra (nem por `read_csv` no caminho da outra, nem por `ATTACH`); CSV > 20 MB recusado; CSV inválido recusado; expiração apaga a pasta (simule o relógio).

### 4. Ferramenta SQL (`app/sql_tool.py`) — critério 5, 2
- `validar_sql(sql) -> str`: `duckdb.extract_statements(sql)`; exatamente 1 comando e `statement.type == duckdb.StatementType.SELECT`; senão `ErroUsuario` em pt-BR explicando que só leitura é permitida. (Não use regex para isso.)
- Conexão CSV: `duckdb.connect(caminho, read_only=True, config={"enable_external_access": False, "autoinstall_known_extensions": False, "autoload_known_extensions": False, "lock_configuration": True})`. Confirme em teste que abrir o arquivo funciona com essa config.
- Conexão Postgres: `duckdb.connect()`; `LOAD postgres`; `ATTACH '<url com aspas simples duplicadas>' AS pg (TYPE postgres, READ_ONLY)`; `USE pg`; depois trave: tente `SET enable_external_access=false`; **teste** se a consulta ao Postgres continua funcionando depois disso. Se não funcionar, use `SET disabled_filesystems='LocalFileSystem'` + `SET autoload_known_extensions=false` + `SET autoinstall_known_extensions=false` no lugar. Por fim `SET lock_configuration=true`. Acrescente `connect_timeout=10` na URL (como parâmetro de query, respeitando se já houver `?`).
- `executar(sessao, sql, limite=1000) -> Resultado(colunas, linhas, truncado)`: valida, abre, roda com timeout de 30 s (`threading.Timer(30, con.interrupt)`), `fetchmany(limite+1)`, fecha sempre (`finally`).
- `para_texto(resultado, max_linhas=50)`: CSV com cabeçalho das primeiras 50 linhas + "(N linhas no total)" — é isso que vai para o LLM; corte em 10 mil caracteres.
- `redigir(texto, sessao)`: troca a URL do Postgres e a senha dela por `***` em qualquer mensagem de erro. **Toda** exceção que sai desta camada passa por aqui.
- **Testes** (um por caso): SELECT ok; WITH ok; INSERT/UPDATE/DELETE/DROP/CREATE/COPY/ATTACH/PRAGMA/SET recusados; `SELECT 1; DROP TABLE x` recusado; `SELECT * FROM read_csv('<caminho de um arquivo existente fora da sessão>')` falha; `SELECT * FROM read_csv('https://example.com/x.csv')` falha; timeout (consulta pesada, ex. `SELECT count(*) FROM range(1e12) a`, com timeout reduzido via parâmetro) interrompe; URL Postgres inválida com senha falsa `senhaSecreta123` → mensagem de erro sem a senha e sem a URL (este teste roda sempre); teste de consulta real em Postgres local marcado `@pytest.mark.skipif` sem `PG_TEST_URL` — rode-o uma vez com `docker run --rm -d -e POSTGRES_PASSWORD=teste -p 55432:5432 postgres:16` e registre o resultado.

### 5. Sandbox Python (`sandbox/runner.ts` + `app/python_tool.py`) — critério 6
- `sandbox/deno.json`: `{ "nodeModulesDir": "auto" }`. Import `npm:pyodide@0.28.3`. Gere `deno.lock` com `deno install --entrypoint runner.ts`.
- `runner.ts`: lê do stdin um JSON `{codigo, csv}`; `loadPyodide({ packageCacheDir: "./pyodide_cache" })`; `loadPackage(["pandas"], { messageCallback: () => {} })` (não deixe mensagens de carga sujarem a saída); captura stdout/stderr do Python com `setStdout`/`setStderr` (batched); coloca o CSV no Python e roda `import io, pandas as pd; df = pd.read_csv(io.StringIO(csv))`, depois o código do usuário; escreve **uma** linha JSON final `{"saida": str, "erro": str|null}` no stdout real. Modo `--preparar`: só carrega pandas (preenche o cache) e sai.
- `python_tool.rodar(codigo, csv) -> {"saida", "erro"}`: `subprocess.run([deno, "run", "--no-prompt", "--cached-only", f"--allow-read={sandbox/node_modules},{sandbox/pyodide_cache}", "--v8-flags=--max-old-space-size=512", "runner.ts"], input=json, cwd=sandbox, env=<mínimo>, timeout=30, capture_output=True)`. `env` mínimo = só `PATH`, `DENO_DIR` (se existir) e, no Windows, `SYSTEMROOT` — **nunca** repasse `os.environ` (lá está `LLM_API_KEY`). Deno via `shutil.which("deno")`. Timeout → `{"erro": "Tempo limite de 30 s excedido."}`. Parse da última linha do stdout; saída cortada em 10 mil caracteres.
- Preparar o cache: `deno run --allow-read --allow-write=./pyodide_cache,./node_modules --allow-net runner.ts --preparar` (documente no README; o Dockerfile faz isso no build).
- **Testes** (rodam de verdade com o Deno; marque `skipif` se `deno` não estiver no PATH): `print(df['a'].sum())` funciona; `import js; js.fetch(...)` → erro de rede; `import js; js.Deno.env.get('LLM_API_KEY')` → erro; `open('/etc/passwd')` e `js.Deno.readTextFileSync` de um arquivo real fora da pasta → erro; `while True: pass` → tempo limite (use timeout menor via parâmetro no teste); `import os; os.environ` não contém `LLM_API_KEY`; depois de cada fuga, uma execução normal ainda funciona.

### 6. Conferência dos números (`app/checker.py`) — critério 7
- `numeros_nao_conferidos(resposta: str, resultados: list[str], pergunta: str) -> list[str]`.
- Números da resposta no formato brasileiro: milhar com `.` e decimal com `,` (`1.234,56`, `15,3`, `1234`), opcionalmente seguidos de `%`. Números dos resultados no formato de máquina (`1234.56`, `-3`, `1.2e+06`).
- Ignorar: inteiros de 0 a 10 sem casas decimais; números que aparecem na pergunta.
- Bate se `abs(a - t) <= 0.01 * abs(t)` (ou ambos zero) para algum `t`. Se o número da resposta tem `%`, também vale comparar `a/100`.
- Devolve os textos originais dos números que não bateram.
- **Testes**: "R$ 1.234,56" vs `1234.56` ✔; "1.235" vs `1234.56` ✔ (1%); "15,3%" vs `0.153` ✔; "15,3%" vs `15.3` ✔; "999" vs `1234.56` ✘; "top 5" ignorado; número da pergunta ignorado; datas "2024" presentes em "2024-03-15" ✔.

### 7. Orquestrador (`app/agent.py`) — critérios 4, 7, 8
- Recebe uma função `chamar_llm(messages, tools) -> message` (injetável; produção usa `OpenAI(api_key, base_url).chat.completions.create(model=..., messages=..., tools=...)`; os testes passam um falso).
- Ferramentas (JSON schema, descrições em pt-BR):
  - `consultar_banco(sql)` → texto do resultado.
  - `rodar_python(sql, codigo)` → o resultado do `sql` vira o DataFrame `df`; devolve a saída do `print`.
  - `gerar_grafico(sql, tipo: barra|linha|pizza|dispersao, x: coluna, y: coluna, titulo)` → roda o SQL (até 500 pontos), guarda a especificação `{tipo, titulo, rotulos, series:[{nome, valores}]}` para a tela e devolve ao LLM "Gráfico criado com N pontos" + os dados em texto (para a conferência).
- Fluxo de `responder(pergunta, sessao) -> dict`:
  1. Chamada de **plano** (sem ferramentas): system prompt com regras + esquema das tabelas; pede "o plano em até 4 passos curtos". Passo `{"tipo": "plano", "texto"}`.
  2. Laço com ferramentas: cada `tool_call` vira um passo (`{"tipo": "sql", "sql", "resultado": {colunas, linhas (até 20)}}`, `{"tipo": "python", "sql", "codigo", "saida", "erro"}`, `{"tipo": "grafico", "sql", "spec"}`). Erros de ferramenta voltam ao LLM como texto (para ele corrigir) e aparecem no passo.
  3. Quando vem resposta sem `tool_calls`: `numeros_nao_conferidos(...)` contra todos os textos de resultado. Se faltar e reanálises < 2: passo `{"tipo": "reanalise", "numeros": [...]}` e mensagem ao LLM listando os números e pedindo para refazer com as ferramentas. Se ainda faltar após 2: devolve com `aviso = "Alguns números não puderam ser conferidos: …"`.
  4. Limites: no máximo 8 chamadas de ferramenta e 120 s no total → encerra com mensagem clara em pt-BR. `openai.RateLimitError` → "O limite gratuito do modelo de IA foi atingido. Espere um minuto e tente de novo."; outros `openai.APIError` → mensagem genérica (sem detalhes internos).
  - Retorno: `{"passos": [...], "resposta": str, "reanalises": int, "aviso": str|None}`.
- System prompt (pt-BR): use as ferramentas para todo número; nunca invente números; responda em português com números no formato brasileiro (1.234,56) e só números que vieram das ferramentas; use `rodar_python` para estatística (média, mediana, desvio, correlação); use `gerar_grafico` quando a pergunta envolver comparação, evolução ou participação; nomes de tabelas e colunas exatamente como no esquema. **Não** coloque a URL do Postgres no prompt — só o esquema.
- **Testes** com LLM falso (roteiro de respostas): caminho feliz com SQL + gráfico; número inventado → reanálise → corrigido; número inventado 3× → aviso; limite de 8 chamadas; `RateLimitError` → mensagem pt-BR; ferramenta com erro volta ao LLM; o prompt enviado ao LLM nunca contém a URL do Postgres.

### 8. API (`app/main.py`) — critérios 1, 2, 4, 9
- `create_app()`. Rotas:
  - `GET /` → `static/index.html`; `/static` montado.
  - `POST /api/sessao/csv` (multipart `arquivo`) → `{sessao, tabelas}`; leia no máximo 20 MB + 1 byte e recuse acima.
  - `POST /api/sessao/exemplo` → `{sessao, tabelas, perguntas}` (as 5 de `data/perguntas.json`, só o texto).
  - `POST /api/sessao/postgres` `{url}` → `{sessao, tabelas}`.
  - `POST /api/perguntar` `{sessao, pergunta (1–500 caracteres)}` → resultado do agente.
- `ErroUsuario` → HTTP 400 `{"detail": msg}`; exceção inesperada → 500 com mensagem genérica em pt-BR, log sem segredos.
- Logs: nunca registre a URL do Postgres, a chave, nem o corpo das requisições.
- Se `LLM_API_KEY` não estiver definida, o app sobe mas `/api/perguntar` responde 503 com mensagem clara.
- **Testes** (`TestClient` + LLM falso via override): upload → pergunta; sessão inexistente → 400; pergunta vazia/longa → 422; CSV grande → 400; URL Postgres inválida com senha falsa → 400 e a senha não aparece na resposta nem nos logs (`caplog`).

### 9. Interface (`static/`) — critérios 4, 10, 11
- Uma página, pt-BR, sem framework. Seções: título + subtítulo; **aviso de dados sensíveis** (texto exato da Spec, critério 10) acima da escolha da fonte; fonte de dados (input de arquivo `.csv`, botão "Usar CSV de exemplo", formulário com campo `type=password` para a URL Postgres); resumo das tabelas (nome, linhas, colunas); botões das 5 perguntas de exemplo; textarea + botão "Perguntar"; estado "Analisando…" com o botão desabilitado; resultado: plano, cada passo (SQL e Python em `<pre>` com rolagem própria, saída, gráficos em `<canvas>`), badge "Reanalisou N×" quando houver, aviso de conferência quando houver, resposta final em destaque; mensagens de erro em pt-BR.
- Todo texto vindo do servidor entra por `textContent` (nunca `innerHTML` com dados).
- Chart.js `https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js`; mapear barra→bar, linha→line, pizza→pie, dispersao→scatter.
- CSS: mobile first, 360 px sem rolagem horizontal da página, `pre { overflow-x: auto }`, alvos de toque ≥ 44 px, `font-size: 16px` nos inputs (evita zoom no iOS), cores com contraste AA, `:focus-visible`.

### 10. Docker + README
- `Dockerfile`: `python:3.12-slim`; Deno copiado de `denoland/deno:bin-2.9.8` (`COPY --from=denoland/deno:bin-2.9.8 /deno /usr/local/bin/deno`); usuário 1000 (`useradd -m -u 1000 user`), `HOME=/home/user`; `pip install -r requirements.txt`; como usuário 1000: `python -c "import duckdb; duckdb.sql('INSTALL postgres')"`, `deno install` e o comando de preparar o cache do Pyodide no `sandbox/`; `EXPOSE 7860`; `CMD uvicorn app.main:app --host 0.0.0.0 --port 7860`. A chave vem de secret do Space em runtime (nunca `ENV LLM_API_KEY` nem `COPY .env`). `.dockerignore` com `.env`, `.venv`, `.git`, `referência.png`, `sandbox/node_modules`, `sandbox/pyodide_cache`, `data/sessions`.
- `README.md` em pt-BR: o que é; diagrama Mermaid do fluxo (pergunta → orquestrador → 3 ferramentas → conferência → resposta, com a seta de reanálise); arquitetura (pastas e papel de cada módulo); segurança (SQL só leitura em 3 camadas, sandbox Deno+Pyodide e por que Pyodide sozinho não isola, isolamento de sessões, segredos); como rodar local (uv, deno, preparar o cache, `.env`); testes; como publicar no HF Spaces; limitações (plano gratuito, "dorme", risco aceito de SSRF via URL Postgres, dados vão para o Gemini).
- **Validar**: `docker build -t analista-dados-ia .` e `docker run --rm -p 7860:7860 --env-file .env analista-dados-ia` responde em `/`.

## Validação
```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python scripts/gerar_exemplo.py
.venv/Scripts/python -m uvicorn app.main:app --port 8000   # e abrir http://localhost:8000
docker build -t analista-dados-ia .
```

## Riscos
| Risco | Probabilidade | Mitigação |
|---|---|---|
| `enable_external_access=false` bloqueia o próprio scanner do Postgres | Média | Alternativa `disabled_filesystems` descrita na tarefa 4, decidida por teste |
| Gemini via OpenAI compat rejeita o histórico com tool calls | Média | `model_dump(exclude_none=True)` da mensagem do assistente; testar cedo com 1 chamada real |
| Pyodide demora (~3–5 s por execução) | Alta | Aceito no MVP (limite total de 120 s); README cita |
| Windows (dev) × Linux (Docker) | Média | Caminhos com `pathlib`, `shutil.which`, env mínimo com `SYSTEMROOT` no Windows |

## Modelo padrão (testado com a chave do Daniel em 19/11/2026)
`LLM_MODEL` padrão = **`gemini-3.5-flash-lite`** (respondeu em 1,8 s com a chamada de ferramenta correta). `gemini-2.5-flash` dá 404 para contas novas; `gemini-3.8-flash`, `gemini-3.5-flash` e `gemini-flash-latest` passaram de 60 s sem responder no plano gratuito. Cliente `OpenAI(..., timeout=60, max_retries=1)`.

## Aceite
- [ ] Todas as tarefas feitas
- [ ] `pytest` passando (incluindo os testes reais do sandbox com Deno)
- [ ] Critérios 1–11 da Spec cobertos (deploy fica para a etapa 9)
