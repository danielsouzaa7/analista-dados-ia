# Como rodar

Rodar localmente, em Docker, publicar, testar e a estrutura do repositório.

## Rodar localmente

Local (precisa de Python 3.12; o [Deno](https://deno.com) só é necessário para os testes do sandbox, a regressão com Python e a avaliação, não para rodar o app):

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt   # Linux/macOS: .venv/bin/python
cp .env.example .env            # preencha LLM_API_KEY (Google AI Studio, plano gratuito)

# só para testes e avaliação: cache do Pyodide para o Deno (precisa de internet só nesta vez; o sandbox roda sem rede)
cd sandbox
deno install --entrypoint runner.ts
deno run --allow-read --allow-write=./pyodide_cache,./node_modules --allow-net runner.ts --preparar
cd ..

.venv/Scripts/python -c "import duckdb; duckdb.sql('INSTALL postgres')"   # só se for usar Postgres
.venv/Scripts/python scripts/gerar_exemplo.py
.venv/Scripts/python -m uvicorn app.main:app --port 8000                   # http://localhost:8000
```

Docker (o build prepara a extensão do Postgres; a imagem não tem Deno nem prepara o Pyodide, porque o Python roda no navegador do visitante):

```bash
docker build -t analista-dados-ia .
docker run --rm -p 7860:7860 --env-file .env analista-dados-ia
```

Variáveis (`.env.example`):

| Variável | Papel |
|---|---|
| `LLM_API_KEY` | Obrigatória. Chave do Google AI Studio (plano gratuito) |
| `LLM_BASE_URL` | Padrão: API compatível com OpenAI do Gemini. Qualquer API compatível serve |
| `LLM_MODEL` | Padrão `gemini-3.5-flash-lite` |
| `LLM_MODEL_FALLBACK` | Modelo reserva. Padrão `gemini-flash-lite-latest` |
| `EVAL_LLM_API_KEY` | Chave de outro projeto, só para `scripts/avaliar.py` |
| `DEMO_TETO_DIARIO` | Teto diário de perguntas. Padrão 80 |

Publicação no Render (plano gratuito): no painel, *New → Blueprint*, escolha este repositório e informe a `LLM_API_KEY` quando o Render pedir. O `render.yaml` já define o Docker, a porta 7860 e o health check. A chave nunca entra na imagem. No plano gratuito o app dorme após uns 15 minutos sem uso e leva cerca de um minuto para acordar.

## Testes

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m pytest -q --cov=app --cov-report=term-missing   # cobertura
.venv/Scripts/python -m ruff check .
```

- Os testes usam um LLM falso. Os do sandbox rodam o Deno de verdade e são pulados sem `deno` no PATH. Os testes do sandbox levam alguns minutos.
- Testes do cliente (`static/python.js`, `stream.js`): `deno test --allow-read tests/js/`.
- E2E do Python no navegador (`tests/e2e/test_python_worker*.py`, `test_python_navegador.py`, `test_desconexao.py`): Playwright em Chromium, Firefox e WebKit, com o jsDelivr ao vivo; o job `e2e-navegador` do CI roda com `E2E_PYODIDE=1`. São 10 vetores de fuga bloqueados, testados em 3 motores; 3 vazamentos aceitos ficam registrados (query string ao jsDelivr, IndexedDB/Cache, BroadcastChannel).
- Regressão com cassetes: `tests/test_regressao.py` reproduz respostas gravadas do LLM pelo agente real, sem chamar o Gemini. Sem cassete, é pulado; os casos que usam Python também são pulados sem `deno`.
- E2E no navegador (Playwright): `tests/e2e/test_fluxo.py` só roda com o app no ar e `E2E_URL` definida (`pip install playwright && playwright install chromium`; com chave, gasta 1 pergunta da cota):

```bash
E2E_URL=http://127.0.0.1:8000 .venv/Scripts/python -m pytest -q tests/e2e
```
- Postgres real: o teste `test_postgres_real` só roda com `PG_TEST_URL`:

```bash
docker run --rm -d --name pgteste -e POSTGRES_PASSWORD=teste -p 55432:5432 postgres:16
docker exec pgteste psql -U postgres -c "create table vendas_pg(v int); insert into vendas_pg values (1),(2),(3);"
PG_TEST_URL=postgresql://postgres:teste@127.0.0.1:55432/postgres .venv/Scripts/python -m pytest -q tests/test_sql_tool.py
```

O CI (`.github/workflows/ci.yml`) roda ruff e pytest com cobertura, e um segundo job com `postgres:16` para o teste real. Não usa segredos nem chama o LLM. O job `e2e-navegador` (Playwright em Chromium, Firefox e WebKit, `test_python_worker.py`, `test_python_worker_fuga_extra.py` e `test_python_navegador.py`) depende do jsDelivr ao vivo e por isso não bloqueia o merge (`continue-on-error`).

## Dados de exemplo

`data/pedidos.csv` tem 8.000 pedidos fictícios de delivery de comida em 2025 (semente fixa; nenhuma marca ou empresa real): 7 cidades, 8 culinárias e 40 restaurantes com nomes inventados. Colunas: `pedido_id, data_hora, cidade, regiao, culinaria, restaurante, valor_pedido, taxa_entrega, cupom, desconto, distancia_km, tempo_entrega_min, avaliacao` (cerca de 30% das avaliações vazias).

Os dados têm padrões de propósito: picos no almoço (11h-14h) e no jantar (18h-22h), fim de semana mais forte, pico em dezembro, tempo de entrega que cresce com a distância e no horário de pico, nota que cai com o tempo de entrega e ticket menor nos pedidos com cupom. `data/perguntas.json` guarda os casos da avaliação (perguntas, um acompanhamento e um de segurança) com a resposta esperada e os `numeros_chave`, calculados em pandas por `scripts/gerar_exemplo.py`. O p-valor do teste t de Welch usa a aproximação normal, adequada porque os graus de liberdade passam de 1.000.

## Estrutura de pastas

```
app/          backend FastAPI e agente (main, agent, checker, sql_tool, python_navegador, python_tool, graficos, perfil, sessions, prompts)
sandbox/      preludio.py (estatística, sem scipy) e, só para avaliação e testes, runner.ts (Pyodide no Deno), deno.json, deno.lock
static/       tela sem build (index.html, app.js, turno.js, graficos.js, stream.js, python.js, python-worker.js, style.css) e fake-stream.html
scripts/      gerar_exemplo.py (dados) e avaliar.py (avaliação, gravações, cassetes)
data/         pedidos.csv, perguntas.json; gravacoes/ (gerado pela avaliação)
tests/        testes e tests/cassetes/
docs/         arquitetura, decisoes, seguranca, avaliacao, tempo-de-construcao, img/
.github/      workflows/ci.yml
```

## Como o GIF foi gravado

O GIF do README é uma gravação de tela do app real rodando localmente, com uma pergunta digitada (não um botão de exemplo, para nunca cair numa gravação de resposta). Método:

1. Subir o `uvicorn` local com a chave do LLM no ambiente e `SESSIONS_DIR` temporário.
2. Playwright em Chromium, janela de 1024×640, tema claro, com `record_video_dir`: "Usar CSV de exemplo", esperar o esquema, digitar a pergunta "O tempo de entrega afeta a nota do cliente?" e esperar a resposta final.
3. Converter o vídeo com ffmpeg (`fps=10`, `scale=800:-1`, paleta própria) e cortar a espera do carregamento inicial.

Gravado em 21/11/2026, rodando localmente (não no servidor publicado), com o modelo `gemini-3.5-flash-lite`, no commit `1f8cafe`. Pergunta: "O tempo de entrega afeta a nota do cliente?". É a tomada única (de até 3 permitidas) (a primeira já serviu, sem selo de gravação nem erro). A espera do carregamento inicial do Python foi cortada; o GIF não está acelerado.

Tempo da pergunta na tomada: cerca de 14 s (mediana de `/api/metricas` com 1 pergunta, 13,8 s); custo do LLM: R$ 0 (plano gratuito).
