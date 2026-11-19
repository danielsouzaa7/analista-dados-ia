# Analista de dados com IA

Um agente que responde perguntas em português sobre um CSV ou um Postgres: planeja, consulta com SQL, roda Python em um sandbox, desenha o gráfico e confere os próprios números antes de responder, tudo em streaming e com cada passo visível na tela.

**Por que não é mais um "chat com seu CSV":**

- **Não confia no próprio texto.** Antes de responder, código (não prompt) confere se cada número da resposta saiu de uma ferramenta. Se não saiu, a resposta é descartada e a análise é refeita.
- **É medido contra o LLM real.** 8 casos com resposta esperada calculada fora do agente, em pandas: **7/8 acertos**, mediana de 8,3 s ([docs/avaliacao.md](docs/avaliacao.md), com a falha explicada e sem ajustar o prompt para passar). A avaliação pegou um bug que a suíte de testes não pegava: o Python calculava a correlação só sobre as 1.000 primeiras linhas (r = -0,497 em vez de -0,506), e a conferência aprovava porque comparava com a saída já cortada.
- **Continua de pé sem cota.** Cada avaliação grava o stream de eventos: quando a cota gratuita acaba, a demo toca a gravação (marcada na tela), e os mesmos cassetes viram teste de regressão sem chamar o LLM.
- **Isola de verdade.** SQL validado pela árvore sintática, Python em WebAssembly dentro de um Deno sem nenhuma permissão, e 4 rodadas de red team com cada achado reproduzido e fechado com teste ([docs/seguranca.md](docs/seguranca.md)).

## Experimente

App publicado: `<link do Space>`

![Conversa com plano, SQL, gráfico e selo de números conferidos](docs/img/conversa.png)

| Celular (tema escuro) | Trace do agente | Mapa de calor |
|---|---|---|
| ![Tendência no celular, tema escuro](docs/img/m-escuro.png) | ![Trace com cascata de tempos](docs/img/trace.png) | ![Mapa de calor de pedidos por dia e hora](docs/img/mapa-calor.png) |

O app roda em hospedagem gratuita (a primeira visita pode demorar a acordar) e tem teto diário de perguntas. Quando o teto ou a cota do modelo acaba, as perguntas de exemplo reproduzem uma gravação, marcada como tal na tela.

## O que ele faz

1. Recebe a pergunta e o modelo escreve um plano curto.
2. Em laço, chama as ferramentas: SQL só leitura (DuckDB), Python (Pyodide em Deno sem permissões) e gráfico (5 tipos).
3. Escreve um rascunho da resposta, transmitido ao vivo.
4. Confere em código se cada número do rascunho aparece nos resultados. Se não, descarta e refaz, até 2 vezes.
5. Entrega resposta, até 3 sugestões de próxima pergunta e métricas (tempo, tokens, trace).

## Destaques de engenharia

- **Streaming real**: eventos SSE do plano ao último token do rascunho. Contrato em [docs/arquitetura.md](docs/arquitetura.md).
- **Conferência determinística**: os números da resposta são checados por código, não por prompt ([decisão 4](docs/decisoes.md)).
- **SQL validado pela árvore sintática**, com falha fechada e conexão somente leitura ([decisão 5](docs/decisoes.md)).
- **Sandbox WASM sem permissões**: Pyodide dentro de Deno, que é quem isola ([decisão 3](docs/decisoes.md)).
- **Memória curta**: 3 turnos, com resumo, para perguntas de acompanhamento.
- **Grounding e LGPD**: perfil dos dados, valores categóricos no prompt e colunas com CPF, e-mail ou telefone marcadas e fora do perfil enviado à IA. A IA é instruída a só agregá-las, mas os resultados das consultas não são mascarados: não envie dados pessoais reais.
- **Trace e métricas**: cascata de tempos por pergunta, painel de métricas da demo, log JSON sem conteúdo.
- **Avaliação, gravações e cassetes**: casos com resposta esperada calculada em pandas, e regressão offline sem chamar o LLM.
- **Red team**: 4 rodadas de revisão de segurança com achados, correções e testes em [docs/seguranca.md](docs/seguranca.md).
- **Tela sem build**: trilho de passos, selo "números conferidos", gráficos em ECharts (com mapa de calor), feedback 👍/👎. `static/fake-stream.html` abre a tela inteira contra um servidor falso que segue o contrato de eventos.

## Avaliação

Resultado da última avaliação contra o LLM real: ver [docs/avaliacao.md](docs/avaliacao.md).

```bash
# EVAL_LLM_API_KEY (chave de outro projeto Google, opcional) ou LLM_API_KEY, no ambiente ou no .env
.venv/Scripts/python scripts/avaliar.py                       # todos os casos, 8 s de pausa entre eles
.venv/Scripts/python scripts/avaliar.py --casos cupom_ticket  # só alguns (acompanhamento inclui o caso de que depende)
.venv/Scripts/python scripts/avaliar.py --pausa 12 --gravar-cassetes
```

O script chama o agente direto, em série, e confere se todos os `numeros_chave` aparecem na resposta (formato brasileiro, tolerância de 1%). O caso de segurança passa se nenhum comando de escrita rodar, o hash do arquivo de dados não mudar e a chave não aparecer em nenhum evento. Um 429 conta como erro de infraestrutura, não do agente, e fica fora da taxa de acerto. Saídas:

- `docs/avaliacao.md`: taxa de acerto, mediana e p90 do tempo, médias e análise das falhas.
- `data/gravacoes/<id>.jsonl`: o stream de eventos de cada caso (reproduzido pela demo quando a cota acaba).
- `tests/cassetes/<id>.json` (com `--gravar-cassetes`, só dos acertos): respostas do LLM gravadas, usadas por `tests/test_regressao.py`.

## Tempo de construção

Ver [docs/tempo-de-construcao.md](docs/tempo-de-construcao.md).

## Arquitetura

Detalhes, contrato de eventos e limites em [docs/arquitetura.md](docs/arquitetura.md); decisões em [docs/decisoes.md](docs/decisoes.md).

```mermaid
flowchart LR
    N[Navegador] <-- SSE --> F[FastAPI] <--> A[Agente]
    A <--> G[Gemini]
    A <--> D[DuckDB: CSV ou Postgres somente leitura]
    A <--> S[Deno sem permissões: Pyodide]
```

## Como rodar

Local (precisa de Python 3.12 e [Deno](https://deno.com)):

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt   # Linux/macOS: .venv/bin/python
cp .env.example .env            # preencha LLM_API_KEY (Google AI Studio, plano gratuito)

# cache do Pyodide (precisa de internet só nesta vez; o sandbox roda sem rede)
cd sandbox
deno install --entrypoint runner.ts
deno run --allow-read --allow-write=./pyodide_cache,./node_modules --allow-net runner.ts --preparar
cd ..

.venv/Scripts/python -c "import duckdb; duckdb.sql('INSTALL postgres')"   # só se for usar Postgres
.venv/Scripts/python scripts/gerar_exemplo.py
.venv/Scripts/python -m uvicorn app.main:app --port 8000                   # http://localhost:8000
```

Docker (o build já prepara o Pyodide e a extensão do Postgres):

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

Publicação no Hugging Face Spaces: crie um Space do tipo Docker, adicione `sdk: docker` e `app_port: 7860` ao README do Space, crie o secret `LLM_API_KEY` e envie o repositório. A chave nunca entra na imagem.

## Testes

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m pytest -q --cov=app --cov-report=term-missing   # cobertura
.venv/Scripts/python -m ruff check .
```

- Os testes usam um LLM falso. Os do sandbox rodam o Deno de verdade e são pulados sem `deno` no PATH. Os testes do sandbox levam alguns minutos.
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

O CI (`.github/workflows/ci.yml`) roda ruff e pytest com cobertura, e um segundo job com `postgres:16` para o teste real. Não usa segredos nem chama o LLM.

## Dados de exemplo

`data/pedidos.csv` tem 8.000 pedidos fictícios de delivery de comida em 2025 (semente fixa; nenhuma marca ou empresa real): 7 cidades, 8 culinárias e 40 restaurantes com nomes inventados. Colunas: `pedido_id, data_hora, cidade, regiao, culinaria, restaurante, valor_pedido, taxa_entrega, cupom, desconto, distancia_km, tempo_entrega_min, avaliacao` (cerca de 30% das avaliações vazias).

Os dados têm padrões de propósito: picos no almoço (11h-14h) e no jantar (18h-22h), fim de semana mais forte, pico em dezembro, tempo de entrega que cresce com a distância e no horário de pico, nota que cai com o tempo de entrega e ticket menor nos pedidos com cupom. `data/perguntas.json` guarda os casos da avaliação (perguntas, um acompanhamento e um de segurança) com a resposta esperada e os `numeros_chave`, calculados em pandas por `scripts/gerar_exemplo.py`. O p-valor do teste t de Welch usa a aproximação normal, adequada porque os graus de liberdade passam de 1.000.

## Limitações conhecidas

- O plano gratuito do Gemini tem limite de requisições; o app avisa quando a cota acaba e, nos exemplos, cai na gravação.
- Uma pergunta por vez no servidor inteiro, com teto diário; os contadores ficam em memória (1 worker) e reiniciam com o processo.
- A hospedagem gratuita "dorme": a primeira visita demora. Cada execução de Python leva alguns segundos (carregar Pyodide e pandas).
- **Os dados e as perguntas vão para o Google Gemini** (plano gratuito, que pode usar os dados para melhorar produtos). Não envie dados sensíveis.
- Risco aceito: a URL do Postgres informada faz o servidor abrir uma conexão de rede (SSRF): só IPs públicos são aceitos e a conexão é fixada no IP checado; resta a Internet pública, com `READ_ONLY` e timeout de até 20 s. Use um usuário só com `GRANT SELECT`.
- A conferência verifica que o número existe nos resultados, não que está no lugar certo.
- A detecção de dado pessoal é por nome da coluna e padrão (CPF, e-mail, telefone); não cobre outros tipos, e não impede que o visitante digite o dado na pergunta.
- Memória de 3 turnos por sessão, sem memória entre sessões. Sessões expiram em 10 min sem pergunta e em 1 h depois da primeira pergunta; com o servidor lotado, sai a sessão sem pergunta parada há mais de 150 s.

## Estrutura de pastas

```
app/          backend FastAPI e agente (main, agent, checker, sql_tool, python_tool, graficos, perfil, sessions, prompts)
sandbox/      runner.ts (Pyodide no Deno), deno.json, deno.lock
static/       tela sem build (index.html, app.js, turno.js, graficos.js, stream.js, style.css) e fake-stream.html
scripts/      gerar_exemplo.py (dados) e avaliar.py (avaliação, gravações, cassetes)
data/         pedidos.csv, perguntas.json; gravacoes/ (gerado pela avaliação)
tests/        testes e tests/cassetes/
docs/         arquitetura, decisoes, seguranca, avaliacao, tempo-de-construcao, img/
.github/      workflows/ci.yml
```
