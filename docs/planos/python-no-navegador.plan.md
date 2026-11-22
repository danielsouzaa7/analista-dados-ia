# Plano: o Python da IA passa a rodar no navegador do visitante, mais os defeitos do scipy e da significância

## Revisão do architect — volta 1 (21/11/2026)

Veredito: APROVADO COM AJUSTES. Todos os achados foram incorporados.

| # | Achado | Onde foi incorporado |
|---|---|---|
| H1 | `valor[- ]p` casava com "valor por pedido" e `p[- ]?valor` com "SP valoriza" | §1.7: `\b` nas bordas; o corpus da fatia 2 traz essas frases |
| H2 | A regex disparava com a frase honesta "não foi possível calcular a significância" e não pegava "a diferença é significativa" | §1.7: só a forma assertiva dispara, avaliada frase a frase, com proteção para frases de incapacidade; a menção sozinha não dispara; fatia 2 com corpus real |
| H3 | Citar o p-valor reprovava a conferência de números ("0,001" e "1,2 × 10⁻⁵⁴") | §1.7: `_CITA_P` tira as citações de p-valor antes de `numeros_nao_conferidos`; o prompt pede "p < 0,001"; teste `test_p_valor_citado_em_formato_br_nao_reprova_numeros` |
| M1 | O Starlette não fecha o gerador síncrono, e o fechamento pelo GC pode travar o `_LOCK` | §1.1: `_RespostaSSE` guarda o gerador e chama `close()` no `finally`; o mecanismo de desconexão foi corrigido; fatia 7a com o teste no uvicorn real |
| M2 | Um surrogate solto derrubava o stream e contaminava o histórico | §1.1: validador em `ResultadoPythonIn`; §1.3: corte por `Array.from`; teste na fatia 5 |
| M3 | Um POST perdido deixava 80 s em "Rodando…" | §1.3: uma nova tentativa em erro de rede e `String(...)` nos campos; fatia 7b |
| M4 | O p-valor dos turnos anteriores era lido de `resultados`, que inclui o código | §1.7: `saidas_python` guardadas no turno por `_guardar_turno`; teste na fatia 2 |
| M5 | `_P_VALOR` não reconhecia o repr da tupla nem "p-valor bicaudal: 0.08" | §1.6: `namedtuple` com `p_valor` e floats do Python; §1.7: regex tolerante |
| M6 | A Spec prometia "sem acesso ao próprio site" antes do spike; worker sem cabeçalho fica sem CSP nenhuma | §4: a fatia 3 roda antes de fechar a fatia 0; teste da resposta real do `StaticFiles`, inclusive a 304; Spec escrita por motor se o plano B entrar |
| M7 | Ordem e tamanho das fatias | §4: testes de fuga na fatia 3; a 7 dividida em 7a, 7b e 7c; `MAX_BYTES_PYTHON` na fatia 5 |
| L1 | Nonce no worker não protege nada | §1.3: sem nonce no worker, correlação pela instância; o nonce fica só entre servidor e navegador |
| L2 | `'unsafe-eval'` não acrescenta risco no worker | §1.4: pode liberar, só na CSP do worker, se o Pyodide pedir |
| L3 | Exfiltração por query string e redirecionamento | §1.4 e fatia 3: conferir que nada sob o caminho redireciona |
| L4 | Gravações | §1.5: `_reproduzir` descarta `python_pedido` |
| L5 | Ler `resultado` e fazer `pop` na mesma seção crítica, sem `yield`/`return` no `finally` | §1.1, no esboço do executor |
| L6 | `FALHA_SIGNIFICANCIA` misturada ao aviso de números | §1.7: aviso e `passos[...]["numeros"]` separados |
| L7 | `deviceMemory` não existe no Firefox nem no Safari | Decisões e §1.3: `(navigator.deviceMemory ?? 0) < 4 \|\| matchMedia("(pointer: coarse)").matches` |
| L8 | Lentz com gl=1e7 precisa de cerca de 2,2 mil iterações | §1.6: `MAXIT = 10_000` e aproximação normal acima de gl 1e5 |
| L9 | O CSV no SSE gasta a banda do Render | §1.5 e fatia 7b: registrar os bytes do `python_pedido`; fatia 10: confirmar o limite real |
| L10 | Congelar o prompt na fatia 1 | §4: toda mudança de texto visto pelo LLM vai para a fatia 1, e o VERSAO sobe uma vez só |
| L11 | Spec e ADR divergiam (3 s contra cerca de 2 s) | Tudo vira "até 3 s"; medir também na URL publicada (fatia 9) |
| L12 | WebKit do Playwright não é Safari nem iOS; o job depende do jsDelivr | Fatia 7c e Spec (nota); fatia 9: job `e2e-navegador` com `continue-on-error` |

## Decisões tomadas (21/11/2026)

| Pergunta em aberto | Decisão |
|---|---|
| Rede de quem avalia bloqueia o jsDelivr | Aceitar: o Python falha, o agente responde com SQL e isso fica documentado (README e `docs/seguranca.md`) |
| Celular: reserva de cerca de 250 MB ociosa | Pular a reserva pré-aquecida quando `(navigator.deviceMemory ?? 0) < 4 \|\| matchMedia("(pointer: coarse)").matches` |
| Quando pré-aquecer o Pyodide | Ao carregar os dados (`definirSessao`), não ao abrir a página |
| Regravação de cassetes e gravações | Com a chave do `.env` (`EVAL_LLM_API_KEY` ou `LLM_API_KEY`), sem ler nem imprimir a chave |
| Vaga de pergunta presa até 80 s por um navegador lento | Aceitável |
| `MAX_BYTES_PYTHON` | Baixar de 20 MB para 5 MB (fatia 5) |

## Status das fatias

Ordem de execução: 0 (texto aplicado; só fecha depois da 3) → 3 → 1 → 2 → 4 → 5 → 6 → 7a → 7b → 7c → 8 → 9 → 10. Cada fatia é commitada no verde.

| Fatia | Assunto | Status |
|---|---|---|
| 0 | Spec e ADR | feita |
| 3 | Worker, CSP e testes de fuga (spike) | feita |
| 1 | Defeito 1: prelúdio estatístico, "sem scipy" e prompt congelado | feita |
| 2 | Defeito 2: significância sem p-valor, saída como dado, regravação | feita |
| 4 | Injeção do executor | feita |
| 5 | Protocolo no servidor | feita |
| 6 | Cliente `python.js` | feita |
| 7a | Servidor ligado e desconexão no uvicorn real | feita |
| 7b | Front ligado e e2e no Chromium | feita |
| 7c | Matriz Firefox/WebKit e medições | feita |
| 8 | Red team do navegador e rodada 5 | pendente |
| 9 | Imagem sem Deno e CI | feita |
| 10 | Documentação | pendente |

---

Li `app/agent.py`, `app/main.py`, `app/python_tool.py`, `sandbox/runner.ts`, `app/checker.py`, `app/prompts.py`, `app/sessions.py`, `static/{stream,turno,app,index.html}`, `Spec.md`, `docs/{decisoes,seguranca,arquitetura}.md`, `Dockerfile`, `render.yaml`, `ci.yml`, `scripts/avaliar.py`, `tests/test_{agent,python_tool,regressao}.py`, `tests/e2e/test_fluxo.py`, os cassetes e as gravações.

**Achado que muda o escopo:** `data/gravacoes/cupom_ticket.jsonl` já contém os dois defeitos. A linha 9 tem o `ferramenta_fim` em vermelho com o erro do scipy. A linha 12 tem uma saída com "Estatística t: -15.5570" e nenhum p-valor. A linha 44 traz a resposta dizendo "significativa". Essa gravação toca justamente quando a cota acaba, ou seja, é o que o avaliador veria. `tests/cassetes/cupom_ticket.json` tem a mesma resposta. Por isso, regravar cassetes e gravações entra no plano (fatia 2) e precisa da chave do Daniel.

---

## 1. Desenho

### 1.1 Protocolo entre servidor e navegador

**Eventos SSE novos.** Os dois são emitidos pelo executor, entre `ferramenta_inicio` e `ferramenta_fim`, e só existem na web ao vivo:
- `python_pedido`: `{id, nonce, codigo, csv, preludio}`.
  - `id` é o id da tool_call. O front usa para achar o passo na tela.
  - `nonce` vem de `secrets.token_hex(16)` e vale para uma execução só. Ele fica entre o servidor e a página; não vai para o worker (§1.3).
  - `preludio` são as funções estatísticas (seção 1.6). Vai junto para que haja uma única fonte em disco para os dois executores.
- `python_aguardando`: `{id}`, a cada 2 s enquanto o servidor espera. O `turno.js` ignora (o `default: break` já existe). A batida faz o `next()` do gerador terminar a cada 2 s, e só assim o cancelamento do Starlette consegue entrar (ver "Aba fechada" abaixo).

**Rota nova.** `POST /api/python/resultado` com corpo `{sessao, id, nonce, saida, erro}`. Modelo Pydantic `ResultadoPythonIn`:
- `sessao`: até 64 caracteres;
- `id`: até 128;
- `nonce`: `pattern=r"^[0-9a-f]{32}$"`;
- `saida`: até `python_tool.MAX_CHARS` (10.000);
- `erro`: até 2.000, ou nulo.
- Validador (`field_validator` em `saida` e `erro`) que faz `s.encode("utf-8", "replace").decode()`. Motivo: um surrogate solto (`"\ud800"`), vindo de um corte errado ou de um cliente malicioso, faria `_sse(...).encode()` levantar `UnicodeEncodeError`, derrubaria o stream e contaminaria `historico`.

Responde 204 quando aceita. Responde 400 com uma mensagem única ("Não há execução de Python esperando esse resultado.") em todos os casos de recusa: sem pendente, outra sessão, outro id, nonce errado ou já respondido. Em `_corpo_grande_demais` entra o limite próprio da rota, `LIMITE_RESULTADO_PYTHON = 80 * 1024`. Conta: 10 mil caracteres no pior caso de escape JSON, mais o erro. O limite geral de 16 KB recusaria saídas legítimas.

**Módulo novo `app/python_navegador.py`** (cerca de 80 linhas), com primitivas de `threading` coerentes com o gerador síncrono que roda no threadpool:

```python
PRAZO_S = 80   # 45 s de carga do Pyodide + 30 s de execução (prazos do front) + 5 s de folga para o POST
BATIDA_S = 2   # python_aguardando: devolve o controle ao Starlette a cada 2 s
MAX_ERRO = 2000
ERRO_PRAZO = {"saida": "", "erro": "O navegador não devolveu o resultado do Python a tempo."}

@dataclass
class _Pendente:
    id: str
    nonce: str
    pronto: threading.Event = field(default_factory=threading.Event)
    resultado: dict | None = None

_PENDENTES: dict[str, _Pendente] = {}   # por sessão: o agente roda uma ferramenta por vez
_LOCK = threading.Lock()

def executor(sessao_id: str) -> ExecutorPython:
    def rodar(id_, codigo, csv, restante):
        pend = _Pendente(id_, secrets.token_hex(16))
        with _LOCK:
            _PENDENTES[sessao_id] = pend
        try:
            yield {"evento": "python_pedido", "id": id_, "nonce": pend.nonce, "codigo": codigo,
                   "csv": csv, "preludio": python_tool.PRELUDIO}
            fim = time.monotonic() + min(PRAZO_S, restante)
            while not pend.pronto.wait(min(BATIDA_S, max(0.0, fim - time.monotonic()))):
                if time.monotonic() >= fim:
                    break
                yield {"evento": "python_aguardando", "id": id_}
        finally:  # sem yield nem return aqui: o GeneratorExit precisa atravessar
            with _LOCK:
                if _PENDENTES.get(sessao_id) is pend:
                    del _PENDENTES[sessao_id]
                resultado = pend.resultado   # ler e remover na MESMA seção crítica
        return resultado or ERRO_PRAZO
    return rodar

def entregar(sessao_id: str, id_: str, nonce: str, saida: str, erro: str | None) -> bool: ...
```

O que `entregar` faz:
1. Sob o lock, faz `get` (não `pop`) do pendente da sessão.
2. Confere `id`, `secrets.compare_digest(nonce)` e `resultado is None`.
3. Só então, ainda sob o lock, grava o resultado, faz `pop` e chama `pronto.set()`.

Um nonce errado não derruba o pendente. Um segundo POST encontra o pendente já removido e recebe 400. Como o executor lê `resultado` e remove o pendente na mesma seção crítica, um POST que chega junto com o fim do prazo cai em um de dois casos: ou entra antes (e o resultado é usado), ou depois (e recebe 400). Nunca recebe 204 e tem o resultado descartado.

O executor também registra no log os bytes do `python_pedido` (tamanho do CSV mais o código), para medir a banda do Render (§1.5).

**Prazos:**

| Onde | Valor | O que acontece |
|---|---|---|
| Carga do Pyodide (front) | 45 s, contados a partir do pedido | Encerra o worker; erro "Não consegui carregar o Python no seu navegador em 45 s." |
| Execução (front) | 30 s, contados depois de carregar | `worker.terminate()`; erro "Tempo limite de 30 s excedido." (o mesmo texto do Deno) |
| Espera do servidor | `min(80 s, restante dos 120 s)` | Erro de prazo; um POST atrasado recebe 400 |
| Batida | 2 s | Abre a janela para o cancelamento |
| Pergunta e SSE | 120 s / 135 s | Sem mudança |

O front sempre responde antes do prazo do servidor. Assim o visitante vê o erro específico do front, e não o genérico do servidor.

**Aba fechada ou "Parar".** Mecanismo conferido na versão instalada:
- O uvicorn 0.54 anuncia `spec_version "2.3"`. Por isso o Starlette 1.10 usa `listen_for_disconnect` e cancela o task group quando o cliente sai (`responses.py:278-285`).
- No uvicorn, um `send` depois da desconexão **retorna em silêncio** (`h11_impl.py:459-460`). Não há escrita que falhe.
- `anyio.to_thread.run_sync` roda com `abandon_on_cancel=False`. O cancelamento espera o `next()` em curso terminar, o que leva no máximo 2 s graças à batida.
- `iterate_in_threadpool` (`concurrency.py:51-59`) **não fecha o gerador**. Sem intervenção, o `GeneratorExit` só chegaria quando o GC soltasse o gerador: numa thread qualquer e num momento qualquer. Se fosse o GC de ciclos rodando dentro de `entregar` com `_LOCK` preso, haveria deadlock, porque o lock não é reentrante.
- **Correção:** `_RespostaSSE` guarda o gerador (`self._gerador`) e, no `finally` que já devolve a vaga, chama `self._gerador.close()`, protegido contra `ValueError` (gerador em execução). O `close()` lança `GeneratorExit` na thread do evento, de forma determinística: atravessa `_ferramenta` (que só captura `ErroUsuario`, `KeyError`, `TypeError` e `JSONDecodeError`), roda o `finally` do executor (o pendente sai) e chega ao `_ao_vivo`, que registra `erro_tipo = "cancelado"` (o caminho já verificado na 4.10).
- Resultado: a vaga volta e o pendente sai em até 3 s. O `test_fechar_o_gerador_remove_a_pendente` (fatia 5) chama `close()` à mão. A prova do caminho real é o teste no uvicorn real da fatia 7a.

Do lado do front, "Parar", "Nova conversa" e carregar dados novos já chamam `estado.abort.abort()`. O mesmo sinal encerra o worker, e nada é postado depois do abort.

### 1.2 Injeção de dependência

Em `app/agent.py`:

```python
# (id da tool_call, código, csv, segundos restantes da pergunta) -> eventos ao vivo; devolve {"saida", "erro"}
ExecutorPython = Callable[[str, str, str, float], Generator[dict, None, dict]]

def python_deno(id_: str, codigo: str, csv: str, restante: float) -> Generator[dict, None, dict]:
    """Executor padrão (avaliação, testes, regressão): sandbox Deno no servidor, sem eventos próprios."""
    yield from ()
    return python_tool.rodar(codigo, csv, timeout=min(30, restante))   # lookup no módulo: o monkeypatch dos testes continua valendo
```

- `executar(pergunta, sessao, llm, saida=None, python: ExecutorPython = python_deno)`. O parâmetro desce por `_loop`, `_lote` e `_ferramenta` até `_rodar`.
- `_rodar` vira gerador, com a assinatura `_rodar(tc_id, nome, args, sessao, restante, python)`:
  - os três `sql_tool.executar` usam `min(30, restante)`, que é o que `_ferramenta` passa hoje;
  - o caminho Python faz `res = yield from python(tc_id, args["codigo"], dados, restante)`;
  - `_ferramenta` faz `texto, extra = yield from _rodar(...)`.
- O teste `test_limite_de_tempo_dentro_do_lote` continua dando `[30, 30, 20]`.
- `main._ao_vivo` passa `python=python_navegador.executor(sessao.id)`. O agente não importa `python_navegador`.
- `scripts/avaliar.py`, `test_agent.py` e `test_regressao.py` não mudam: usam o padrão Deno.
- O uvicorn local usa o navegador, igual à produção, para o desenvolvimento pegar os mesmos bugs. "Uso local com Deno" fica só para os scripts e os testes.

**Dockerfile: remover o Deno.**
- Saem `COPY --from=denoland/deno...`, `deno install` e `runner.ts --preparar`, e o `chown` passa a valer só para `data`. O `INSTALL postgres` fica.
- Ganho: sai o binário do Deno (cerca de 100 MB), mais `node_modules` e `pyodide_cache` (algumas dezenas de MB), e o build no Render não baixa mais o Pyodide.
- A produção não chama `python_deno`. Mesmo que chamasse, `python_tool.rodar` já devolve um erro amigável quando não há Deno.
- O CI mantém o Deno: `test_python_tool`, a regressão com cassetes de `rodar_python` e `deno test tests/js/` precisam dele.
- `sandbox/preludio.py` continua na imagem, pelo `COPY . .`. O `.dockerignore` já exclui `sandbox/node_modules` e `sandbox/pyodide_cache`.

### 1.3 Front

- **`static/python-worker.js`** (cerca de 50 linhas), worker de módulo.
  - Faz `import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs"`, a mesma versão de `sandbox/deno.json`, para a avaliação e a web terem o mesmo pandas e numpy.
  - Carrega `pandas` com `messageCallback` mudo, para o console ficar limpo para o e2e.
  - Avisa `{tipo: "pronto"}` ou `{tipo: "falhou"}`.
  - Ao receber `{codigo, csv, preludio}`, roda prelúdio, depois `df = pd.read_csv(...)`, depois o código, capturando stdout e stderr como em `runner.ts`. Responde `{tipo: "resultado", saida, erro}`.
  - **Sem nonce no worker.** O código da IA já controla o próprio stdout, então forjar a mensagem de resultado equivale a imprimir uma mentira. Ele também poderia trocar `Array.prototype`/`String.prototype`, que o worker usa depois. Um nonce no closure não protegeria nada e ainda complicaria o código. A correlação é pela instância: um worker por execução; a primeira mensagem `resultado` daquela instância vale, e as seguintes são ignoradas.
  - O erro fica com as 6 últimas linhas.
- **`static/python.js`** (cerca de 90 linhas, sem efeito colateral no import):
  - `preaquecer()`, `estaPronto()`;
  - `executarPython(pedido, {signal, criar = criarWorker, cargaMs = 45_000, execucaoMs = 30_000})` devolve `{saida, erro}`;
  - aceita só mensagens do worker desta execução (correlação pela instância); mensagens de um worker antigo são ignoradas;
  - corta por pontos de código, não por unidades UTF-16: `Array.from(s).slice(0, 10000).join("")` na saída e o mesmo com 2.000 no erro. Assim não parte um par surrogate ao meio;
  - no `finally`, faz `terminate()` e cria a reserva, salvo quando o critério de memória pede para pular;
  - o parâmetro `criar` existe para os testes com workers falsos (dois usos reais: o worker de verdade e os testes).
- **Um worker novo por execução, com uma reserva pré-aquecida.**
  - Reaproveitar o worker na sessão economizaria de 2 a 4 s por chamada, mas código injetado pelo CSV poderia trocar funções do pandas e falsificar resultados seguintes, que a conferência aprovaria.
  - Com o worker novo, o boot da reserva acontece enquanto o LLM pensa, então a latência fica escondida na maioria dos casos.
  - A nova reserva só é criada depois do `terminate()` da anterior, para não manter 2 × cerca de 250 MB.
  - **Pular a reserva** quando `(navigator.deviceMemory ?? 0) < 4 || matchMedia("(pointer: coarse)").matches`. `deviceMemory` não existe no Firefox nem no Safari, e o `pointer: coarse` cobre o iPhone.
- **Pré-aquecimento** em `definirSessao` (dados carregados), pulado se `navigator.connection?.saveData` for verdadeiro ou se o critério de memória pedir. Ao abrir a página seria cedo demais: custaria cerca de 20 MB a quem só lê. Entre carregar os dados, montar o plano e chegar à primeira ferramenta, passam de 3 a 10 s, o que basta no desktop.
- **CDN jsDelivr com versão fixa**, e não arquivos servidos pelo próprio servidor. Cerca de 20 MB por visitante novo contra os 5 GB/mês do Render daria uns 250 visitantes frios. O jsDelivr não custa nada e o caminho é imutável. O preço é ficar sem SRI (seção 1.4).
- **`app.js`**: em `enviar`, captura `sessao` e `signal` no começo. No callback do stream: se `tipo === "python_pedido" && !dados.gravacao`, chama `responderPython(...)`, sem `await` no laço do SSE. `responderPython`:
  - roda `executarPython`;
  - converte com `String(...)` os campos vindos do worker (`saida` e, se não for nulo, `erro`), porque um objeto daria 422;
  - faz `postJson("/api/python/resultado", ...)`;
  - em erro de **rede**, tenta mais uma vez; num 400 ou 422, não tenta de novo (o servidor já fechou a execução);
  - não posta nada depois do abort.
  Sem a nova tentativa, um POST perdido deixaria o visitante 80 s olhando "Rodando o Python…", porque a batida não ajuda enquanto o cliente continua conectado.
- **`turno.js`**, no `case "python_pedido"`:
  - status "Carregando o Python no seu navegador (só na primeira vez)…" ou "Rodando o Python no seu navegador…", conforme `estaPronto()`;
  - selo "no seu navegador" no passo.
- Sem SharedArrayBuffer, COOP ou COEP: a interrupção é por `terminate()`.

### 1.4 Segurança: modelo de ameaça novo

**CSP da página.** A string atual de `CABECALHOS` mais `worker-src 'self' https://cdn.jsdelivr.net/pyodide/v0.28.3/full/`. O spike (fatia 3) mostrou que o Chromium confere o `import` do worker contra o `worker-src` da página; sem o caminho do Pyodide ali, o worker não carrega.

**CSP do worker.** Pela especificação, um worker http(s) usa a CSP da **própria resposta**, não a da página. **Se o cabeçalho faltar, o worker fica sem CSP nenhuma.** Por isso a resposta de `/static/python-worker.js` precisa sempre do cabeçalho, inclusive na 304 do `StaticFiles` (requisição condicional). No middleware `protecoes`, depois do `headers.update(CABECALHOS)`, a CSP é sobrescrita quando `request.url.path` é esse:

```
default-src 'none'; script-src https://cdn.jsdelivr.net/pyodide/v0.28.3/full/ 'wasm-unsafe-eval';
connect-src https://cdn.jsdelivr.net/pyodide/v0.28.3/full/; worker-src https://cdn.jsdelivr.net/pyodide/v0.28.3/full/; base-uri 'none'
```

- Não há `'self'` no `connect-src`: o worker não alcança nem a API do próprio site, e de qualquer forma não conhece o id da sessão. Se o WebKit herdar a CSP da página (plano B do §5), o worker ganharia `connect-src 'self'` e alcançaria `/api/*`, por exemplo criando sessões com `POST /api/sessao/exemplo`, que não exige id. A fatia 3 responde isso antes de a Spec ser dada por pronta.
- Caminho da exfiltração: dado do CSV → LLM → Python → `js.fetch`, `WebSocket`, `EventSource` ou `import()` para fora. Tudo isso é bloqueado por `connect-src`/`script-src`. O máximo que sobra é um GET ao caminho do Pyodide no jsDelivr, com dados na query string (`…/full/x?d=…`), que vão para os logs do jsDelivr, que o atacante não lê.
- **Redirecionamento:** depois de um redirect, a CSP confere só o host, não o caminho. A fatia 3 confere que nada sob `/pyodide/v0.28.3/full/` redireciona dentro de `cdn.jsdelivr.net`.
- `worker-src` do worker é o caminho do Pyodide (e não `'none'`): Firefox e WebKit conferem o `import` estático do módulo contra ele. Liberar esse caminho não abre exfiltração, que depende só do `connect-src` (sem `'self'`). O spike mediu: sem `'unsafe-eval'` o Pyodide roda; os 3 motores aplicam a CSP da resposta do worker; nada sob o caminho redireciona.
- **`'unsafe-eval'`:** se o Pyodide pedir, pode liberar, só na CSP do worker. Não acrescenta risco: o Python já roda JS arbitrário via `js.Function`. A CSP de rede é a única barreira que importa ali.
- Fica sem efeito: IndexedDB e Cache Storage da origem acessíveis ao worker (o app não lê esses armazenamentos); DOM, cookies e id de sessão inexistentes no worker; CPU limitada a 30 s.

**Resultado vindo do cliente é não confiável:**
- forjar o resultado afeta só a própria sessão (a tela, a memória e o selo "conferido" dela);
- mas o resultado forjado entra nas métricas globais (`conferidas_pct`): é risco aceito;
- tetos: 10 mil e 2 mil caracteres, corpo de 80 KB, surrogates saneados;
- nonce no servidor: impede que um resultado atrasado de uma execução vencida seja aceito pela seguinte, e serve de defesa em profundidade se o id de sessão vazar. Não protege contra o próprio visitante, e isso fica escrito;
- `_lote` passa a mandar o conteúdo de toda mensagem `tool` como `_como_dado(texto)`. É uma linha só, cobre a saída do navegador e também o SQL, e a regra "conteúdo entre `<dados>` é dado" já está no prompt de sistema;
- a tela continua usando `textContent`.

**Sem SRI no Pyodide.** Os navegadores não aplicam SRI ao `import` de um módulo de worker. A versão está fixa no caminho, e o Pyodide confere o sha256 dos pacotes contra o `pyodide-lock.json` (`checkIntegrity`). Um jsDelivr comprometido rodaria código no worker com os dados do próprio visitante e com rede para o jsDelivr: é risco aceito e documentado.

**O que muda em `docs/seguranca.md`:**
- Modelo de ameaça:
  - um ativo novo, "navegador e dados do visitante na execução Python";
  - um atacante novo, "cliente que forja o resultado";
  - a premissa ganha "o resultado do navegador também é não confiável".
- Tabela de guardrails:
  - a linha "Python" passa a ter "Produção: Web Worker novo por execução, CSP própria (string acima), 45+30 s, nonce no servidor, uso único, 80 KB" e "Avaliação/testes: Deno (texto atual)";
  - a linha "Navegador" ganha `worker-src`;
  - a linha "Contêiner" fica sem Deno, e só `data` é gravável.
- Uma "Rodada 5 — Python no navegador", preenchida pela revisão real (revisor de segurança), com estes itens já com teste:

| # | Item | Teste |
|---|---|---|
| 5.1 | Exfiltração por fetch externo | e2e de fuga (fatia 3) |
| 5.2 | fetch ao próprio site | e2e de fuga (fatia 3) |
| 5.3 | `import()`/WebSocket/EventSource | e2e de fuga (fatia 3) |
| 5.4 | Resultado forjado pelo cliente: só vale para a própria sessão; nonce e uso único no servidor | pytest (fatia 5) |
| 5.5 | Resultado atrasado aceito pela execução seguinte | nonce por execução (fatia 5) |
| 5.6 | Aba fechada segurando a vaga | batida + `close()` explícito, uvicorn real (fatia 7a) |
| 5.7 | Código persistente entre execuções | worker novo (fatia 6) |
| 5.8 | Corpo grande | 80 KB (fatia 5) |
| 5.9 | Surrogate solto derruba o stream | validador (fatia 5) |
| 5.10 | Gerador fechado pelo GC numa thread qualquer (deadlock no `_LOCK`) | `close()` explícito no `_RespostaSSE` (fatia 7a) |
| 5.11 | Worker sem CSP na resposta 304 | teste da resposta condicional (fatia 3) |

- Verificação no uvicorn real, como na 4.1/4.10: fechar a conexão durante o `python_pedido`, e a vaga voltar em até 3 s. Atrás do proxy do Render isso não está verificado: medir na URL publicada (fatia 9).

**Testes antigos que mudam de lugar.** Continuam valendo, mas só protegem o executor Deno (avaliação, testes, regressão) e saem do caminho de produção: 1.3 `test_saida_gigante_do_deno_e_cortada`, 1.4 `test_semaforo_limita_concorrencia`, 1.7 `test_fugas_bloqueadas_pelo_deno`, 1.8 `test_saida_forjada_nao_vale` e `test_js_json_stringify_trocado_nao_forja_saida`, 2.10 `test_espera_final_tem_prazo`, e também `test_ambiente_sem_chave` e `test_timeout`. Os itens da seção "Verificado e correto" sobre o Deno ganham a mesma nota de escopo, e não são apagados. Os equivalentes de produção são os e2e de fuga, o teste da CSP do worker, os testes de prazo em JS e os testes do POST em pytest. Em "Riscos aceitos", "Memória do WASM até 4 GB" passa a ser no navegador do visitante, e entram o jsDelivr sem SRI e as métricas infláveis.

### 1.5 Gravações, cassetes e "cota esgotada reproduz gravação"

- **O protocolo não afeta nada disso.** `avaliar.py` usa o Deno, então nunca há `python_pedido` nas gravações. Mesmo assim, como defesa em profundidade, `_reproduzir` descarta qualquer `python_pedido` (teste na fatia 7a). Na reprodução, o passo Python mostra a `saida` do `ferramenta_fim` sem o selo "no seu navegador", o que é honesto. A troca para a gravação em `_ao_vivo` depende de `_SUBSTANTIVOS`, e o `python_pedido` vem depois de `ferramenta_inicio`, então nada muda.
- **Os defeitos afetam, sim.** As mudanças de prompt (VERSAO), do prelúdio e de `_como_dado` exigem regravar (decisão 10). O `cupom_ticket` vai quebrar a regressão de qualquer jeito: a checagem nova reprova a resposta gravada, o agente pede reanálise e o cassete se esgota. Regravar tudo numa rodada, com `python scripts/avaliar.py --gravar-cassetes`, no fim da fatia 2. **Depois da regravação, nenhuma mudança no texto visto pelo LLM**: qualquer aumento de VERSAO obriga a regravar de novo (por isso o prompt é congelado na fatia 1).
- **A avaliação passa a medir o Python do servidor, não o do navegador.** O tempo no navegador é medido pelo e2e. Isso fica anotado no relatório.
- **Banda.** O CSV vai sem compressão no `python_pedido` e conta contra o mesmo limite de banda do Render que serviu para descartar servir o Pyodide pelo app. Os bytes de cada `python_pedido` vão para o log (§1.1) e são medidos no e2e (fatia 7b); o limite real do Render grátis é confirmado na fatia 10.

### 1.6 Defeito 1 (scipy)

- **Sem scipy.** No Pyodide, ele é mais um pacote grande a baixar e a carregar a cada worker novo e a cada Deno, e o celular é o gargalo.
- **Prelúdio `sandbox/preludio.py`** (cerca de 50 linhas, só `numpy`, `math` e `collections`):
  - `p_bicaudal_t(t, gl)`, pela beta incompleta regularizada I_{gl/(gl+t²)}(gl/2, 1/2), com fração contínua de Lentz e `MAXIT = 10_000`. Com gl=1e7, o Lentz precisa de O(√a), cerca de 2,2 mil iterações; um MAXIT de 100 a 200 reprovaria o próprio teste. Acima de gl 1e5, usa a aproximação normal (erro desprezível nessa faixa). Abaixo disso é exata. A aproximação normal erra cerca de 0,009 em p=0,05 com gl=30, por isso não serve para todo gl;
  - `teste_t_welch(a, b)` devolve `ResultadoTeste(t, gl, p_valor)`;
  - `teste_correlacao(x, y)` devolve `ResultadoCorrelacao(r, gl, p_valor)`;
  - os dois tipos são `namedtuple` com valores `float` do Python, não `np.float64`. Assim `print(teste_t_welch(a, b))` imprime `ResultadoTeste(t=-2.0, gl=8.0, p_valor=0.0805)`, e o rótulo `p_valor=` aparece na saída e é reconhecido pelo conferidor (§1.7);
  - descartam NaN; levantam `ValueError` em português com n<2 ou variância zero.
- Ele cobre os dois exemplos que falam em significância: `cupom_ticket` e `tempo_nota`. `python_tool.PRELUDIO` lê o arquivo uma vez. `rodar` o manda no JSON de stdin, e `runner.ts` o executa antes do `df`. O executor do navegador manda o mesmo no `python_pedido`.
- **Prompt, congelado na fatia 1.** Todas as mudanças de texto que o LLM vê, dos dois defeitos, entram juntas aqui. `TOOLS["rodar_python"].description` e `SISTEMA` passam a dizer:
  - "só pandas, numpy e a biblioteca padrão (sem scipy, statsmodels nem sklearn)";
  - as duas funções prontas, com o retorno nomeado;
  - "imprima o p-valor, ex.: `print(f'p_valor = {r.p_valor:.3g}')`"; e, na resposta, "cite como p < 0,001 quando for menor que 0,001";
  - "Só diga que algo é (ou não é) estatisticamente significativo se uma saída mostrar o p-valor; cite-o.";
  - "Não use 'significativo' no sentido coloquial; diga 'grande', 'relevante' ou 'expressivo'.";
  - "se rodar_python falhar duas vezes, responda com SQL (DuckDB tem avg, stddev_samp, corr) e diga o que não pôde calcular";
  - o texto de `prompts.REANALISE_SIGNIFICANCIA` (usado na fatia 2) também nasce aqui.
- `VERSAO = "2026-11-21.1"`, subida uma vez só.

### 1.7 Defeito 2 (significância sem teste)

**Em `app/checker.py`:**

```python
FALHA_SIGNIFICANCIA = "significância estatística sem p-valor"
_SUJEITO = (r"diferen[çc]as?|efeitos?|associa[çc](?:ão|ões)|correla[çc](?:ão|ões)|rela[çc](?:ão|ões)|"
            r"impactos?|resultados?")
_AFIRMA = re.compile(
    r"\bestatisticamente\b"
    rf"|\b(?:{_SUJEITO})\b(?:\s+\S+){{0,3}}?\s+significativ\w*"   # o sujeito até 3 palavras antes
    r"|\b(?:é|são|foi|foram)\s+significativ\w*",                  # "é/não é significativa"
    re.I)
_INCAPACIDADE = re.compile(r"\bn[ãa]o\s+(?:foi|é|era)\s+poss[íi]vel\b|\bn[ãa]o\s+(?:consegui|pude)\b", re.I)
_ROTULO_P = r"\b(?:p[-_ ]?(?:valor|value)|valor[-_ ]?p|p)\b"
_P_VALOR = re.compile(_ROTULO_P + r"[^\d\n]{0,20}?[=:<≤≈]\s*-?\.?\d", re.I)    # nas saídas
_CITA_P = re.compile(_ROTULO_P + r"[^\d\n]{0,20}?[<≤=≈]\s*[\d.,]+(?:\s*[×x]\s*10\S*|e-?\d+)?", re.I)  # na resposta

def afirma_significancia(resposta: str) -> bool: ...   # frase a frase: _AFIRMA e não _INCAPACIDADE
def significancia_sem_p_valor(resposta: str, saidas: list[str]) -> bool: ...
def sem_citacoes_de_p(resposta: str) -> str: ...       # tira as citações de p-valor
```

- **Só a forma assertiva dispara.** Afirmar e negar exigem teste igualmente: "a diferença é significativa", "não é significativa", "a diferença entre os grupos não é significativa", "estatisticamente significativa". **A simples menção não dispara**: "significância" ou "p-valor" sozinhos, "aumento significativo", "quedas significativas" (já está em `tempo_nota.jsonl`), "valor por pedido", "valor pago", "SP valoriza".
- **Frase a frase:** a resposta é dividida em frases (`[.!?\n]`). Uma frase com `_INCAPACIDADE` não dispara, mesmo com "estatisticamente". Exemplo: "Não foi possível testar se a diferença é estatisticamente significativa." O prompt manda exatamente isso no caminho de reserva (Python falhou ou jsDelivr bloqueado), e disparar ali criaria um laço de reanálise com aviso falso.
- **`_P_VALOR` tolerante**: aceita até 20 caracteres sem dígito entre o rótulo e o comparador. Reconhece `p_valor = 0.08`, `p_valor=0.0805` (o repr do namedtuple), "p-valor bicaudal: 0.08", "p < 0.001" e "p = 1.2e-54".
- `saidas` são as saídas Python sem erro desta pergunta (`passos` do tipo python) mais as `saidas_python` dos turnos anteriores. **Não** usa `resultados`, porque eles incluem o código e o SQL: um `if p < 0.05:` no código passaria indevidamente.
- **`saidas_python` no turno:** `_guardar_turno` passa a guardar `saidas_python` (só as saídas Python sem erro). `anteriores` usa esse campo, e não `turno["resultados"]`.
- **Citação de p-valor não reprova números (H3):** quando `_P_VALOR` acha p em alguma saída, `_conferir` passa `sem_citacoes_de_p(corpo)` a `numeros_nao_conferidos`. Assim "p < 0,001" e "p = 1,2 × 10⁻⁵⁴" não viram números a conferir. O sobrescrito e o "0,001" de limiar não existem nas saídas.
- **Em `_loop`**, extrair `_conferir(corpo, fontes, saidas, pergunta) -> (faltam, sem_teste, pedido_reanalise, aviso)`, para manter a função abaixo de 50 linhas:
  - `faltam` continua sendo só a lista de números; `sem_teste` é booleano;
  - **`FALHA_SIGNIFICANCIA` não entra** no aviso "Alguns números não puderam ser conferidos: …" nem em `passos[...]["numeros"]`;
  - o pedido junta `prompts.REANALISE` (se houver números) e `prompts.REANALISE_SIGNIFICANCIA` (se `sem_teste`): "Sua resposta afirma ou nega significância estatística, mas nenhuma saída traz p-valor. Rode `teste_t_welch`/`teste_correlacao` e imprima o p-valor, ou retire a afirmação.";
  - o aviso final ganha, em frase separada, "A afirmação de significância estatística não tem um teste que a sustente.";
  - a conferência só é `ok` quando `not faltam and not sem_teste`.
- **Em `turno.js`**, o rótulo "Números que não bateram com os dados:" continua só para números; o aviso de significância aparece como frase própria.

---

## 2. Emenda da Spec

Aplicada em `Spec.md`, que passa a ser a fonte (critérios 6 e 7, Restrições, Métricas, Fora do escopo, Riscos, Perguntas em aberto, Marcos). Os ajustes da volta 1 da revisão também foram aplicados lá.

## 3. ADR

Aplicada como **ADR 13** em `docs/decisoes.md`, que passa a ser a fonte, com a frase acrescentada às Consequências da decisão 3. Os ajustes da volta 1 também foram aplicados lá.

---

## 4. task_list (fatias verticais, nesta ordem)

Ordem: **0 → 3 → 1 → 2 → 4 → 5 → 6 → 7a → 7b → 7c → 8 → 9 → 10**. Cada fatia é commitada no verde.

**Fatia 0 — Spec e ADR**
- Arquivos: `Spec.md`, `docs/decisoes.md`.
- Pronto quando: revisado por arquiteto (volta 1 feita) **e** a fatia 3 respondeu às perguntas do WebKit e do `'unsafe-eval'`. Se o plano B entrar, a Spec 6 é reescrita por motor antes de fechar.

**Fatia 3 — Worker, CSP e testes de fuga (spike; vem primeiro)**
- Testes primeiro:
  - `tests/test_api.py`:
    - `test_csp_da_pagina_libera_worker_self`;
    - `test_csp_do_worker_so_alcanca_o_pyodide` (a string exata, sem `'self'` em `connect-src`), sobre a resposta **real** do `StaticFiles`;
    - `test_csp_do_worker_vale_tambem_na_resposta_304` (requisição com `If-None-Match`/`If-Modified-Since`);
    - `test_versao_do_pyodide_igual_no_worker_no_runner_e_na_csp`.
  - `tests/e2e/test_python_worker.py`, com `E2E_PYODIDE=1`, Playwright em Chromium, Firefox e WebKit, carregando só o worker sob a CSP real (uvicorn numa thread):
    - smoke: o worker carrega e roda `print(1)`;
    - `test_worker_nao_alcanca_rede_externa_nem_o_proprio_site`: `await js.fetch('https://example.com')` e `await js.fetch('/api/status')` dão erro;
    - `test_worker_nao_carrega_script_de_fora` (`import()`), `test_websocket_bloqueado`, `test_eventsource_bloqueado`;
    - nenhuma violação de CSP inesperada no console durante o smoke.
  - Conferência manual registrada: nada sob `https://cdn.jsdelivr.net/pyodide/v0.28.3/full/` redireciona (`curl -I` nos arquivos que o Pyodide baixa).
- Arquivos: `static/python-worker.js` (novo), `app/main.py` (`CABECALHOS`, `CSP_WORKER`, middleware), `tests/e2e/test_python_worker.py` (novo).
- Pronto quando: houver medições anotadas na ADR (MB baixados, carga fria e quente) e respostas a: o Pyodide exige `'unsafe-eval'`? O WebKit respeita a CSP própria do worker? Há redirecionamento no caminho?

**Fatia 1 — Defeito 1: prelúdio estatístico, "sem scipy" e prompt congelado** (complexidade baixa)
- Testes primeiro:
  - `tests/test_preludio.py`, que roda em CPython via `runpy` (`pandas` dos requisitos de dev traz o numpy):
    - `test_p_bicaudal_bate_com_a_tabela_t`: (2,228139; 10) → 0,05; (2,042272; 30) → 0,05; (1,959964; 1e7) → 0,05; (0; 5) → 1, todos com tolerância de 1e-5;
    - `test_welch_bate_com_a_formula`: a=[1..5], b=[3..7] dão t=-2, gl=8 e p≈0,0805;
    - `test_resultado_e_namedtuple_com_floats_e_repr_com_p_valor`: `type(r.p_valor) is float` e `"p_valor=" in repr(r)`;
    - `test_t_enorme_da_p_minusculo_sem_erro`: t=15,557, gl=2976,68 dão 0 ≤ p < 1e-40;
    - `test_gl_gigante_nao_estoura_iteracoes`: gl=1e7 termina e bate com a normal;
    - `test_correlacao_perfeita_da_p_zero`, `test_ignora_nan`, `test_grupo_pequeno_ou_variancia_zero_levanta_erro_em_portugues`.
  - `tests/test_python_tool.py::test_preludio_disponivel_no_sandbox`: com Deno, `teste_t_welch` roda e bate com o CPython.
  - `tests/test_agent.py::test_prompt_diz_que_nao_ha_scipy_e_cita_as_funcoes` e `test_prompt_traz_regras_de_significancia_e_formato_do_p` (inclui "p < 0,001", o veto ao uso coloquial e `REANALISE_SIGNIFICANCIA`).
- Arquivos: `sandbox/preludio.py` (novo), `app/python_tool.py` (`PRELUDIO` no JSON), `sandbox/runner.ts`, `app/prompts.py` (todas as mudanças de texto dos dois defeitos e VERSAO), `app/agent.py` (`TOOLS`).
- Pronto quando: pytest e ruff verdes; o `cupom_ticket` local roda sem `ModuleNotFoundError`. **A partir daqui, o texto visto pelo LLM está congelado.**

**Fatia 2 — Defeito 2: significância sem p-valor, saída como dado e regravação**
- Testes primeiro:
  - `tests/test_checker.py`:
    - `test_significancia_afirmada_sem_p_valor_falha` ("a diferença é significativa", "estatisticamente significativa");
    - `test_significancia_negada_sem_p_valor_tambem_falha` ("não é significativa", "a diferença entre os grupos não é significativa");
    - `test_p_valor_impresso_passa` ("p_valor = 1.2e-54", "p < 0.001", "ResultadoTeste(t=-2.0, gl=8.0, p_valor=0.0805)", "p-valor bicaudal: 0.08");
    - `test_p_valor_so_no_codigo_nao_conta`;
    - `test_mencao_e_uso_coloquial_nao_disparam`: "Não foi possível calcular a significância estatística", "Não foi possível testar se a diferença é estatisticamente significativa", "um aumento significativo de receita", "quedas significativas", "valor por pedido", "valor pago", "SP valoriza";
    - `test_corpus_real_das_gravacoes_e_cassetes`: percorre as respostas finais de `data/gravacoes/*.jsonl` e `tests/cassetes/*.json` com uma **tabela explícita de esperado por caso** (o `cupom_ticket` antigo dispara; `tempo_nota` com "quedas significativas" não dispara; o resto não dispara). A tabela é atualizada junto com a regravação;
    - `test_p_valor_citado_em_formato_br_nao_reprova_numeros` ("p < 0,001" e "p = 1,2 × 10⁻⁵⁴" com p na saída: `numeros_nao_conferidos` de `sem_citacoes_de_p(...)` fica vazio).
  - `tests/test_agent.py`:
    - `test_afirmar_significancia_sem_teste_reanalisa` (descartado, depois resposta com p da saída Python falsa, `conferido=True`);
    - `test_significancia_sem_teste_tres_vezes_gera_aviso`;
    - `test_falha_de_significancia_fora_do_aviso_de_numeros` (nem no aviso de números, nem em `passos[...]["numeros"]`);
    - `test_p_valor_de_turno_anterior_so_vale_da_saida_python` (`saidas_python` guardadas; um `if p < 0.05` no código do turno anterior não conta);
    - `test_conteudo_das_ferramentas_vai_ao_llm_dentro_de_dados`.
- Arquivos: `app/checker.py`, `app/agent.py` (`_conferir`, `_guardar_turno` com `saidas_python`, `_lote` com `_como_dado`), `static/turno.js` (aviso de significância separado). `app/prompts.py` **não muda** (congelado na fatia 1).
- Depois, rodar `python scripts/avaliar.py --gravar-cassetes`. Precisa de `EVAL_LLM_API_KEY` (ou `LLM_API_KEY`) e Deno local. Isso atualiza `tests/cassetes/*.json`, `data/gravacoes/*.jsonl` e `docs/avaliacao.md`.
- Pronto quando: a regressão passa com os cassetes novos; `cupom_ticket.jsonl` não tem erro de Python e cita o p-valor; a tabela do corpus foi atualizada.

**Fatia 4 — Injeção do executor (refatoração, sem mudança de comportamento)**
- Testes primeiro, em `tests/test_agent.py`:
  - `test_executor_injetado_recebe_id_codigo_csv_e_restante`;
  - `test_eventos_do_executor_saem_entre_inicio_e_fim_da_ferramenta`;
  - `test_padrao_continua_sendo_o_deno` (os testes atuais com monkeypatch de `python_tool.rodar` seguem verdes, incluindo `[30, 30, 20]`).
- Arquivos: `app/agent.py`.
- Pronto quando: a suíte toda e a regressão estão verdes.

**Fatia 5 — Protocolo no servidor (inerte)**
- Testes primeiro:
  - `tests/test_python_navegador.py` (com `BATIDA_S` reduzido por monkeypatch):
    - `test_pedido_traz_id_nonce_codigo_csv_e_preludio`;
    - `test_resultado_entregue_destrava_e_vira_retorno` (com thread);
    - `test_resultado_aceito_uma_unica_vez`;
    - `test_nonce_sessao_ou_id_errados_recusados_sem_derrubar_a_pendente`;
    - `test_sem_pendente_recusa`;
    - `test_prazo_estourado_devolve_erro_e_recusa_resultado_atrasado`;
    - `test_post_no_fim_do_prazo_nunca_recebe_204_e_some` (corrida: 204 implica que o resultado foi usado);
    - `test_fechar_o_gerador_remove_a_pendente`;
    - `test_batidas_saem_a_cada_intervalo`;
    - `test_prazo_respeita_o_restante_da_pergunta`;
    - `test_bytes_do_pedido_vao_para_o_log`.
  - `tests/test_api.py`:
    - `test_resultado_python_valida_corpo` (422 com nonce mal formado, 400 sem pendente);
    - `test_corpo_do_resultado_python_tem_limite_proprio` (413 acima de 80 KB, 204 com 10 mil caracteres);
    - `test_surrogate_solto_no_resultado_nao_derruba_o_stream` (o validador saneia `"\ud800"`).
  - `tests/test_agent.py::test_csv_do_python_respeita_5_mb` (`MAX_BYTES_PYTHON` baixado para 5 MB).
- Arquivos: `app/python_navegador.py` (novo), `app/main.py` (rota, `ResultadoPythonIn` com validador, `LIMITE_RESULTADO_PYTHON`), `app/agent.py` (`MAX_BYTES_PYTHON`).
- Pronto quando: os testes estão verdes e nada liga o executor na web ainda.

**Fatia 6 — Cliente `python.js` (inerte)**
- Testes primeiro, em `tests/js/python.test.js`, com workers falsos em `tests/js/workers/`:
  - "resultado do worker desta execução é devolvido e o worker é encerrado";
  - "mensagem de um worker antigo é ignorada" (correlação pela instância);
  - "só a primeira mensagem de resultado da instância vale";
  - "execução acima do prazo encerra o worker e devolve 'Tempo limite de 30 s excedido.'";
  - "carga acima do prazo devolve erro em português";
  - "abort encerra o worker e não devolve resultado";
  - "saída cortada em 10 mil pontos de código sem partir um emoji; erro com as 6 últimas linhas";
  - "depois de cada execução fica um worker novo de reserva";
  - "sem reserva quando deviceMemory < 4 ou pointer coarse".
- Arquivos: `static/python.js` (novo); `ci.yml`, onde `deno test --allow-read tests/js/` passa a ter permissão de leitura porque os workers são arquivos locais.
- Pronto quando: os testes JS estão verdes.

**Fatia 7a — Servidor ligado e desconexão no uvicorn real**
- Testes primeiro:
  - `tests/test_api.py::test_pergunta_com_python_roda_pelo_navegador_ponta_a_ponta`: uma thread lê o stream; ao ver `python_pedido`, faz o POST; confere que `ferramenta_fim.saida` é a postada e que `conferencia.ok` é verdadeiro.
  - `tests/test_api.py::test_resposta_sse_fecha_o_gerador_no_fim` (`close()` explícito, inclusive com o gerador já terminado; `ValueError` protegido).
  - `tests/test_api.py::test_python_pedido_descartado_na_reproducao` (`_reproduzir`).
  - `tests/e2e/test_desconexao.py::test_fechar_a_aba_devolve_a_vaga`: uvicorn real numa thread; um cliente httpx em streaming desconecta durante o `python_pedido`. Em até 3 s, o pendente sai, o "cancelado" é registrado e `/api/perguntar` volta a aceitar.
- Arquivos: `app/main.py` (`_ao_vivo` passa o executor; `_RespostaSSE` guarda o gerador e chama `close()` no `finally`; `_reproduzir` descarta `python_pedido`).
- Pronto quando: os testes estão verdes e a gravação continua tocando quando a cota acaba (`test_fluxo.py`).

**Fatia 7b — Front ligado e e2e no Chromium**
- Testes primeiro:
  - `tests/e2e/test_python_navegador.py`, com `E2E_PYODIDE=1`, no Chromium. Sobe um uvicorn numa thread com `dependency_overrides[obter_llm]` roteirizado: `rodar_python` com `SELECT valor_pedido FROM pedidos` e `print(len(df)); r = teste_t_welch(df.valor_pedido[:4000], df.valor_pedido[4000:]); print(f"p_valor = {r.p_valor:.3g}")`; resposta final "8.000 pedidos". O teste verifica: selo "no seu navegador", saída com "8000", `.final` com "números conferidos", nenhum erro no console e nenhuma violação de CSP. O tempo do passo e os bytes do `python_pedido` são registrados.
  - `tests/js/` (ou o e2e): `responderPython` tenta mais uma vez em erro de rede e não tenta de novo num 400/422; os campos vão como `String`.
- Arquivos: `static/app.js` (`responderPython`, `preaquecer` em `definirSessao` com o critério de memória), `static/turno.js` (status e selo), `static/fake-api.js` (o cenário `tempo_nota` emite `python_pedido` e aceita `POST /api/python/resultado`).
- Pronto quando: o e2e passa no Chromium.

**Fatia 7c — Matriz Firefox/WebKit e medições**
- Testes primeiro: o mesmo `tests/e2e/test_python_navegador.py` parametrizado em chromium, firefox e webkit.
- Medições por motor: carga fria, carga quente (com reserva), tempo da execução e bytes baixados. Vão para a ADR 13 e para o README.
- Nota obrigatória onde os números aparecerem: **o WebKit do Playwright no Linux não é o Safari nem o iOS.**
- Pronto quando: os três motores passam e as medições estão anotadas.

**Fatia 8 — Red team do navegador e rodada 5**
- Os testes de fuga já estão na fatia 3; os de protocolo, nas fatias 5 e 7a.
- Revisão de segurança sobre as fatias 3 a 7c. Cada achado novo ganha teste antes da correção.
- Arquivos: `docs/seguranca.md` (seção 1.4, tabela da rodada 5 com 5.1 a 5.11 e o que mais a revisão achar).
- Pronto quando: a rodada 5 está escrita com achados reais e testes.

**Fatia 9 — Imagem sem Deno e CI**
- Testes primeiro: `docker build` mais `docker run`, depois `GET /api/status` 200, depois o e2e da fatia 7b apontado para o contêiner. Anotar o tamanho da imagem antes e depois e o tempo de build.
- Arquivos: `Dockerfile`. Novo job `e2e-navegador` no `ci.yml`, com `continue-on-error: true` porque depende do jsDelivr ao vivo, e com cache dos navegadores do Playwright: `pip install playwright`, `playwright install --with-deps chromium firefox webkit`, `E2E_PYODIDE=1 pytest tests/e2e/test_python_worker.py tests/e2e/test_python_navegador.py`.
- Depois do deploy (só após a aprovação da etapa 8): medir na URL publicada a devolução da vaga ao fechar a aba (o proxy do Render não está verificado).
- Pronto quando: o contêiner roda o fluxo Python pelo navegador.

**Fatia 10 — Documentação**
- `README.md`:
  - o destaque "Isola de verdade" passa a falar do Worker sem rede;
  - "Como rodar": o Deno só para testes e avaliação; o Docker não prepara mais o Pyodide;
  - limitações: cerca de 20 MB na primeira vez e CDN bloqueada;
  - os números novos da avaliação e os tempos do e2e por motor, com a nota do WebKit.
- `docs/arquitetura.md`:
  - diagrama de componentes: navegador com Worker, e o Deno marcado "avaliação e testes";
  - contrato SSE com `python_pedido` e `python_aguardando`;
  - a rota nova e a tabela de limites (45/30/80 s, batida de 2 s, 80 KB, CSV de 5 MB);
  - módulos novos;
  - corrigir a linha 123, que diz que não há gravações.
- `static/index.html`, em "Como funciona": "Python isolado: roda no seu navegador, em WebAssembly, num Worker sem rede e sem acesso à página. Limite de 30 s." O SVG troca "sandbox, sem rede" por "no seu navegador".
- `docs/avaliacao.md`: uma nota de que o tempo medido é o do Python no servidor.
- Confirmar o limite real de banda do Render grátis e registrar, junto com os bytes medidos do `python_pedido`.
- Pronto quando: atualizador de documentação e a revisão final não acham divergência com o código.

---

## 5. Riscos e perguntas em aberto

- **`'unsafe-eval'`**: pode ser que o Pyodide 0.28.3 precise dele. A fatia 3 responde; se precisar, entra só na CSP do worker (sem risco a mais, ver §1.4).
- **WebKit/Safari** pode aplicar a CSP da página ao worker, e o Pyodide falharia ali. Plano B: a página libera o caminho do Pyodide em `script-src` e `connect-src` e acrescenta `'wasm-unsafe-eval'`, mantendo a CSP estrita do worker para os outros motores. Nesse caso o worker do WebKit alcançaria `'self'`, e a Spec 6 passa a ser escrita por motor. A fatia 3 decide antes de fechar a fatia 0.
- **Rede corporativa do iFood bloqueando o jsDelivr**: o Python falha e o agente responde com SQL. *(Decidido: aceitar e documentar.)*
- **Celular**: cerca de 250 MB por worker, e a aba em segundo plano estrangula o worker (prazos estouram). *(Decidido: pular a reserva com `(navigator.deviceMemory ?? 0) < 4 || matchMedia("(pointer: coarse)").matches`.)*
- **Pré-aquecimento**: ao carregar os dados. *(Decidido.)*
- **Regravação**: cassetes e gravações precisam da chave e da cota do Daniel. Sem regravar, a regressão do `cupom_ticket` quebra a partir da fatia 2. *(Decidido: usar a chave do `.env` sem lê-la.)*
- **Vaga presa até 80 s** por um navegador lento, com uma pergunta por vez para todos. *(Decidido: aceitável.)*
- **Desconexão atrás do proxy do Render**: o caminho no uvicorn local foi conferido pelo código e é testado na fatia 7a; atrás do proxy do Render (HTTP/2, `abort()`), só medindo na URL publicada (fatia 9).
- **Banda do CSV no SSE**: medida na fatia 7b; o limite real do Render é confirmado na fatia 10.

Arquivos relevantes: `app/agent.py`, `app/main.py`, `app/python_tool.py`, `app/checker.py`, `app/prompts.py`, `sandbox/runner.ts`, `static/app.js`, `static/turno.js`, `static/fake-api.js`, `Dockerfile`, `.github/workflows/ci.yml`, `Spec.md`, `docs/decisoes.md`, `docs/seguranca.md`, `docs/arquitetura.md`, `data/gravacoes/cupom_ticket.jsonl`, `tests/cassetes/cupom_ticket.json`. Novos: `app/python_navegador.py`, `sandbox/preludio.py`, `static/python.js`, `static/python-worker.js`, `tests/test_python_navegador.py`, `tests/test_preludio.py`, `tests/js/python.test.js`, `tests/e2e/test_python_worker.py`, `tests/e2e/test_python_navegador.py`, `tests/e2e/test_desconexao.py`.

**O que não foi verificado no planejamento:** nada foi rodado. Continuam como suposições, a confirmar nas fatias 3, 7a e 9:
- se o Firefox e o WebKit aplicam ao worker de módulo a CSP da resposta;
- se o Pyodide 0.28.3 exige `'unsafe-eval'`;
- se há redirecionamentos no caminho do jsDelivr;
- os tamanhos e os tempos de download;
- se o proxy do Render repassa a desconexão.

O mecanismo de desconexão do Starlette e do uvicorn foi lido no código-fonte instalado, mas não medido. Os valores de referência dos testes do prelúdio vêm de tabela t padrão e devem ser conferidos uma vez na implementação.
**Risco principal:** se o jsDelivr estiver bloqueado na rede de quem avalia, a demo ao vivo fica sem Python. O agente cai para SQL, mas a tela mostra o passo Python com erro.

---

## Revisão do architect — volta 2 (21/11/2026): APROVADO COM AJUSTES PEQUENOS

Os achados da volta 1 foram verificados como incorporados. O laço de revisão da spec fechou na 2ª volta. Os ajustes abaixo **prevalecem sobre o texto acima** quando houver conflito:

| # | Achado | Onde entra |
|---|---|---|
| V2-M1 | Uma afirmação escondida atrás de uma frase de incapacidade ("Não foi possível calcular o p-valor, mas a diferença é estatisticamente significativa.") passa | Fatia 2: dividir as frases também em `;` e em `\b(mas\|porém\|contudo\|entretanto\|no entanto)\b`; incluir a frase em `test_significancia_afirmada_sem_p_valor_falha` |
| V2-M2 | `_INCAPACIDADE` é estreita: "Não posso afirmar…", "Não dá para dizer…", "Não testei…", "Seria preciso um teste…" disparam | (a) Fatia 1: constante `prompts.INCAPACIDADE_SIGNIFICANCIA = "Não foi possível testar se a diferença é estatisticamente significativa."`, citada pelo SISTEMA. (b) Fatia 2: ampliar para `\bn[ãa]o\s+(?:posso\|podemos\|d[áa]\s+para\|h[áa]\s+como\|test(?:ei\|amos)\|calcul(?:ei\|amos))\b\|\bseria\s+(?:preciso\|necess[áa]rio)\b\|\bsem\s+(?:um\s+)?teste\b`. (c) Fatia 2: `test_modelo_de_incapacidade_do_prompt_nao_dispara` |
| V2-M3 | "resultado(s)" no `_SUJEITO` faz disparar "O resultado foi um aumento significativo" e "Os resultados mostram um crescimento significativo" | Fatia 2: tirar `resultados?` do `_SUJEITO`, janela `{0,2}`; as duas frases no corpus como "não dispara" |
| V2-L1 | "quedas significativas" só aparece num `rascunho` partido de `tempo_nota.jsonl`, não numa resposta final | Fatia 2: manter como frase escrita à mão; o teste do corpus real lê só respostas finais |
| V2-L2 | O prazo do executor começa depois do `yield` do `python_pedido` (envio de até 5 MB) | Fatia 5: calcular `fim` ANTES do primeiro `yield` |
| V2-L3 | `_CITA_P`, com `[^\d\n]{0,20}?`, pode engolir números que não são p-valor ("o p-valor e o ticket = 45,90") | Fatia 2: no `_CITA_P` (aplicado à resposta), aceitar entre rótulo e comparador só espaço ou uma palavra curta ("bicaudal", "(Welch)"); o intervalo tolerante fica só no `_P_VALOR` (aplicado às saídas) |
| V2-L4 | Redação da Spec 6: "fecha o stream" deve ser "encerra o gerador da execução (`close()`)", e falta o EventSource na lista de testes de navegador | No fechamento da fatia 0, depois da fatia 3 |
