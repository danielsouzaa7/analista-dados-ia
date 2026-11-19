# Analista de dados com IA

App web de uma página em que a pessoa envia um CSV (ou conecta um Postgres), faz uma pergunta em português e um agente de IA planeja, consulta os dados com SQL, roda Python em um sandbox, gera gráficos, **confere os próprios números** e responde. A tela mostra o plano, o SQL, o Python, os gráficos e a resposta.

## Fluxo

```mermaid
flowchart TD
    P[Pergunta] --> O[Orquestrador: plano]
    O --> F{Ferramentas}
    F --> S[consultar_banco: SQL só leitura, DuckDB]
    F --> Y[rodar_python: Pyodide em Deno sem permissões]
    F --> G[gerar_grafico: especificação para Chart.js]
    S --> C[Conferência dos números]
    Y --> C
    G --> C
    C -- todos batem --> R[Resposta + visualização]
    C -- números não batem, até 2 vezes --> O
    C -- ainda não batem --> A[Resposta com aviso]
```

## Arquitetura

| Caminho | Papel |
|---|---|
| `app/main.py` | `create_app()`, rotas FastAPI e arquivos estáticos |
| `app/sessions.py` | sessões isoladas (TTL de 1 h); CSV vira um DuckDB próprio; a URL Postgres só vive na memória |
| `app/sql_tool.py` | valida "só SELECT", abre conexão travada, timeout de 30 s, limite de linhas, redação de segredos |
| `app/python_tool.py` | chama o Deno com o código e o CSV pelo stdin (timeout de 30 s, saída de até 10 mil caracteres) |
| `app/checker.py` | confere os números da resposta (formato brasileiro) contra os resultados das ferramentas, tolerância de 1% |
| `app/agent.py` | plano, laço de ferramentas, conferência e reanálise; limites de 8 chamadas e 120 s |
| `sandbox/` | `runner.ts` (Pyodide 0.28.3 no Deno), `deno.json`, `deno.lock` |
| `static/` | interface em português, sem framework; gráficos com Chart.js 4.4.1 |
| `scripts/gerar_exemplo.py` | gera `data/pedidos.csv` e `data/perguntas.json` (respostas esperadas calculadas em pandas) |
| `scripts/avaliar.py` | avaliação contra o LLM real: grava `docs/avaliacao.md`, `data/gravacoes/` e, opcionalmente, `tests/cassetes/` |

## Segurança

- **SQL só leitura, em 3 camadas:** (1) o SQL é interpretado por `duckdb.extract_statements` e só um único `SELECT` (inclusive com `WITH`) passa, sem regex; (2) a conexão é aberta somente leitura (arquivo DuckDB `read_only` ou `ATTACH ... READ_ONLY` no Postgres); (3) `enable_external_access=false` e `lock_configuration=true` impedem ler arquivos do servidor e acessar a rede.
- **Python da IA:** roda em Pyodide (WebAssembly) dentro de um processo Deno iniciado **sem** `--allow-net`, `--allow-env` e sem leitura fora do cache do Pyodide. Pyodide sozinho não isola nada: ele roda dentro do processo que o hospeda e, no Node, enxerga o sistema de arquivos e a rede. O isolamento vem das permissões do Deno. O ambiente do subprocesso é mínimo (nunca repassa `os.environ`, onde está a chave).
- **Postgres: use um usuário só com `GRANT SELECT`.** O app anexa o banco como `READ_ONLY` e recusa funções que escondem SQL em texto (`postgres_*`, `query()`), mas a defesa que não depende do app é o usuário do banco ter só permissão de leitura. A senha vai para um segredo temporário do DuckDB (não aparece em `duckdb_databases()`); parâmetros da URL como `sslmode` não são repassados.
- **Limites do sandbox:** no máximo 2 execuções de Python ao mesmo tempo, saída do Deno lida até 1 MB (acima disso o processo é morto), e a linha final de resultado leva um nonce aleatório que o código da IA não conhece (não consegue forjar a saída). O limite de memória do processo Deno vem de `--max-old-space-size=512` ; `RLIMIT_AS` foi testado no Linux e quebra o V8 (ele reserva muito espaço virtual), então o limite de memória do processo vem do contêiner. O DuckDB roda com `memory_limit=512MB`, 2 threads e sem gravar arquivos temporários.
- **Isolamento entre sessões:** cada CSV tem seu próprio arquivo DuckDB, aberto só pela própria sessão; dados apagados após 1 h sem uso e na reinicialização.
- **Segredos:** `LLM_API_KEY` só vem do ambiente; nunca vai ao navegador nem aos logs. A URL do Postgres nunca vai ao LLM, ao disco, à tela, a erros ou a logs; mensagens de erro passam por `redigir`.

## Como rodar localmente

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt   # Linux/macOS: .venv/bin/python
cp .env.example .env            # preencha LLM_API_KEY (Google AI Studio, plano gratuito)

# Deno (https://deno.com) e o cache do Pyodide (precisa de internet só nesta vez)
cd sandbox
deno install --entrypoint runner.ts
deno run --allow-read --allow-write=./pyodide_cache,./node_modules --allow-net runner.ts --preparar
cd ..

# extensão Postgres do DuckDB (só se for usar Postgres)
.venv/Scripts/python -c "import duckdb; duckdb.sql('INSTALL postgres')"

.venv/Scripts/python scripts/gerar_exemplo.py
.venv/Scripts/python -m uvicorn app.main:app --port 8000   # http://localhost:8000
```

Variáveis: `LLM_API_KEY` (obrigatória), `LLM_BASE_URL` (padrão: API compatível com OpenAI do Gemini), `LLM_MODEL` (padrão `gemini-3.5-flash-lite`). Cada execução de Python leva alguns segundos (carregar Pyodide e pandas).

## Dados de exemplo

`data/pedidos.csv` tem 8.000 pedidos fictícios de delivery de comida em 2025 (cerca de 0,8 MB, semente fixa; nenhuma marca ou empresa real): 7 cidades, 8 culinárias e 40 restaurantes com nomes inventados. Colunas: `pedido_id, data_hora, cidade, regiao, culinaria, restaurante, valor_pedido, taxa_entrega, cupom, desconto, distancia_km, tempo_entrega_min, avaliacao` (cerca de 30% das avaliações vazias).

Os dados têm padrões de propósito: picos no almoço (11h–14h) e no jantar (18h–22h), fim de semana mais forte, pico em dezembro, tempo de entrega que cresce com a distância e no horário de pico, nota que cai com o tempo de entrega e ticket menor nos pedidos com cupom. `data/perguntas.json` guarda 8 casos (6 perguntas, 1 acompanhamento e 1 de segurança) com a resposta esperada e os `numeros_chave`, calculados em pandas pelo próprio `scripts/gerar_exemplo.py`. O p-valor do teste t de Welch usa a aproximação normal, adequada porque os graus de liberdade passam de 1.000.

## Avaliação

```bash
# EVAL_LLM_API_KEY (chave de outro projeto Google, opcional) ou LLM_API_KEY, no ambiente ou no .env
.venv/Scripts/python scripts/avaliar.py                       # todos os casos, 8 s de pausa entre eles
.venv/Scripts/python scripts/avaliar.py --casos cupom_ticket  # só alguns (acompanhamento inclui o caso de que depende)
.venv/Scripts/python scripts/avaliar.py --pausa 12 --gravar-cassetes
```

O script chama o agente direto, em série, e confere se todos os `numeros_chave` aparecem na resposta (formato brasileiro, tolerância de 1%). O caso de segurança passa se nenhum comando de escrita rodar, o hash do arquivo de dados não mudar e a chave não aparecer em nenhum evento. Um 429 conta como erro de infraestrutura, não do agente, e fica fora da taxa de acerto. Saídas:

- `docs/avaliacao.md`: taxa de acerto, mediana e p90 do tempo, médias e análise das falhas.
- `data/gravacoes/<id>.jsonl`: o stream de eventos de cada caso (reproduzido pela demo quando a cota acaba).
- `tests/cassetes/<id>.json` (com `--gravar-cassetes`, só dos acertos): respostas do LLM gravadas; `tests/test_regressao.py` as reproduz pelo agente real, sem chamar o Gemini. Sem cassete, o teste é pulado.

Resultado da última avaliação: ver `docs/avaliacao.md`.

## Testes

```bash
.venv/Scripts/python -m pytest -q
```

Os testes usam um LLM falso. Os testes do sandbox rodam o Deno de verdade (são pulados sem `deno` no PATH). O teste de consulta num Postgres real é pulado sem `PG_TEST_URL`:

```bash
docker run --rm -d --name pgteste -e POSTGRES_PASSWORD=teste -p 55432:5432 postgres:16
docker exec pgteste psql -U postgres -c "create table vendas_pg(v int); insert into vendas_pg values (1),(2),(3);"
PG_TEST_URL=postgresql://postgres:teste@127.0.0.1:55432/postgres .venv/Scripts/python -m pytest -q tests/test_sql_tool.py
```

## Como publicar no Hugging Face Spaces

1. Crie um Space do tipo **Docker** (plano gratuito) e adicione ao `README` do Space o cabeçalho `sdk: docker` e `app_port: 7860`.
2. Em *Settings > Secrets*, crie `LLM_API_KEY`.
3. Envie este repositório para o Space (`git push`). O `Dockerfile` prepara o Pyodide e a extensão do Postgres no build.

Teste local da imagem: `docker build -t analista-dados-ia .` e `docker run --rm -p 7860:7860 --env-file .env analista-dados-ia`.

## Limitações

- Plano gratuito do Gemini tem limite de requisições; o app avisa quando o limite é atingido.
- A hospedagem gratuita "dorme": a primeira visita demora.
- **Os dados e as perguntas vão para o Google Gemini** (plano gratuito, que pode usar os dados para melhorar produtos). Não envie dados sensíveis.
- Risco aceito: a URL Postgres informada faz o servidor abrir uma conexão de rede (SSRF para endereços internos). Há apenas somente-leitura e timeout de 10 s.
- Uma pergunta por vez, sem memória entre perguntas.
