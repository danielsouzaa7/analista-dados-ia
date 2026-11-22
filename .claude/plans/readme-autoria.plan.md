# Plano: README de uma tela, animado, e docs/autoria.md

Origem: avaliação independente (8/10 e 7/10) e pedido do Daniel em 21/11/2026 por um README de uma tela, animado, e um documento de autoria; a avaliação de 25 a 30 casos virou trabalho futuro.

## Decisões do Daniel para este plano (21/11/2026)

| Pergunta | Decisão |
|---|---|
| Escopo | Só README e autoria. A avaliação de 25–30 casos fica como "trabalho futuro" numa linha da Spec |
| Hospedagem na autoria | Contar tudo, com a frase literal: escolheu o Cloud Run; o Google pediu pré-pagamento único de R$180; ele recusou qualquer custo: "acho um absurdo pagar pra expor portfólio" |
| Dataset de delivery | Foi decisão dele (por causa do iFood): entra na tabela de decisões |
| Ícones dos 4 diferenciais | Ícones SVG próprios, na paleta do herói, com versões clara e escura |
| Script de gravação do GIF | Fica no scratchpad; o método vai descrito em `docs/como-rodar.md` |
| Voz em primeira pessoa e "O que eu faria diferente" | Rascunho na voz dele; ele aprova na etapa 8 |
| Card do perfil (repositório danielsouzaa7/danielsouzaa7) | Opcional; preparar no scratchpad; só sobe com aprovação explícita na etapa 8 |

## Fatos que guiam o plano

- Toda entrada de `data/perguntas.json` vira botão na demo (`app/main.py` `_exemplos()`). Não mexer nesse arquivo.
- GIF: usar a pergunta de `tempo_nota`, "O tempo de entrega afeta a nota do cliente?" (cerca de 21,6 s e 6 chamadas ao LLM na gravação; mostra SQL, Python e dispersão). Digitar a pergunta em vez de clicar no chip, para não mandar `exemplo_id` e nunca cair em gravação.
- ffmpeg instalado pelo winget, fora do PATH: localizar com `Get-ChildItem $env:LOCALAPPDATAMicrosoftWinGetPackages -Recurse -Filter ffmpeg.exe`. Playwright e Chromium já estão no `.venv`.
- Chave para o GIF: wrapper no scratchpad que faz `os.environ["LLM_API_KEY"] = dotenv_values(".env")["EVAL_LLM_API_KEY"]`, define `SESSIONS_DIR` temporário e chama `uvicorn.run("app.main:app", port=8000)`. Nunca imprime a chave (o `load_dotenv` de `app/config.py` não sobrescreve variável já definida).
- ADR 13: o nonce fica entre o servidor e a PÁGINA; o Worker NÃO o recebe. O diagrama tem de respeitar isso.
- Tokens do app (`static/style.css`): claro `--accent #6250d6`, `--paper #f2f1ec`, `--ink #14121c`, `--ok #006300`; escuro `--accent #9085e9`, `--ok #6fd56f`; gráficos `--viz-s2 #eb6834`, `--viz-s3 #1baf7a`.
- Perfil do Daniel (danielsouzaa7/danielsouzaa7): SVGs de ~9 KB com paleta GitHub escura (#58A6FF, #39C5CF, #A371F7, #3FB950, #F85149, #F0F6FC, #C9D1D9, #8B949E; fundos #131C2E/#25324A), `system-ui`, CSS `@keyframes`, `prefers-reduced-motion`, variante mobile via `<picture><source media="(max-width: 600px)">`, `alt` narrativo. Aqui a coreografia sobe um nível.
- Diferenciação do Pulse (outro projeto dele, cuja manchete é "o motor decide, o modelo explica; um validador confere cada número"): aqui a manchete é **"o agente pensa no servidor; o Python roda no seu navegador, ao vivo"**. A conferência de números é apoio, não manchete.
- Vídeos e GIFs intermediários ficam no scratchpad e são apagados depois da conversão.

## 1. Emenda da Spec.md (fatia 0)

- Critério 11: trocar "`README.md` com a arquitetura, o resultado da avaliação e como rodar" por "`README.md` de uma tela (critério 23), com links para a arquitetura, a avaliação, como rodar e a autoria (critério 24)".
- Critério 10: acrescentar, depois do aviso, "(pedido do Daniel em 19/11/2026)".
- **Critério 23, README de uma tela, animado:**
  - **Ordem:** título; herói em SVG animado; uma frase de valor; link "Experimente" em destaque; 4 diferenciais com ícone SVG próprio, cada um com fato verificável e link para `docs/`; diagrama animado do fluxo servidor ↔ navegador; GIF do app real; "Como foi construído" com link para `docs/autoria.md`; e, em `<details>`, "Rodar localmente" (3 comandos), "O que eu faria diferente" e limitações.
  - **Tamanho:** no máximo 80 linhas; renderizado como no GitHub a 1280×800, título, herói, frase, link e diferenciais cabem na primeira tela.
  - **SVGs:** em `docs/img/`, com variantes clara e escura (`<picture>` com `prefers-color-scheme`) e de celular (`max-width: 600px`); até 30 KB cada (meta 15–25 KB; ícones bem menores); só fontes do sistema; sem script, sem `foreignObject`, sem recurso externo; `role="img"`, `<title>`, `<desc>` e `alt` narrativo; `prefers-reduced-motion` mostra o quadro final parado; as versões clara e escura só diferem no bloco de cores.
  - **GIF:** 15–25 s, até 5 MB, gravado de pergunta real (nem gravação nem servidor falso), com o código publicado e o modelo de produção; mostra a pergunta, o plano, o SQL, o Python com o selo "no seu navegador", o gráfico e o selo "números conferidos". Aceleração, se houver, escrita na legenda. Data, modelo e pergunta registrados em `docs/como-rodar.md`.
  - **Números:** todo número do README e dos SVGs vem de `docs/avaliacao.md`, de `docs/tempo-de-construcao.md`, de `data/perguntas.json` ou da execução gravada no GIF.
  - **Jargão:** pass^N, cassete, prelúdio e grounding não aparecem no README; nonce só com a explicação "(código de uso único)".
  - **Nada se perde:** o conteúdo do README antigo continua em `docs/` (teste com frases-sentinela); todo link ou imagem relativa do README e de `docs/` existe (teste).
- **Critério 24, autoria:** `docs/autoria.md` com até cerca de 80 linhas, linkado no README. Diz com todas as letras que o código, os testes, as revisões técnicas e o red team foram feitos por agentes de IA. Tabela das decisões do Daniel (data, decisão, alternativas, onde está registrada); cada linha com fonte pública no repositório ou a marca "registro local da conversa". Nenhuma ideia técnica de agente atribuída ao Daniel; quando as opções vieram dos agentes, isso está escrito. Números iguais aos de `docs/tempo-de-construcao.md` (teste). Um agente independente, só leitura, confere cada linha contra a fonte.
- **Fora do escopo:** JS ou CSS executável no README; vídeo com narração; Lottie; site de documentação; tradução para inglês; mudança no app, na API ou no prompt; nova rodada de avaliação; reescrever `docs/` além de receber as seções movidas.
- **Trabalho futuro:** avaliação com 25–30 casos (ambíguos, sem resposta nos dados, armadilhas analíticas) e checagem de "número certo no lugar errado" contra o gabarito, num arquivo só da avaliação, sem mudar os botões da demo. Adiado por decisão do Daniel em 21/11/2026.
- **Entrega opcional:** card SVG do analista-dados-ia para o README do perfil (outro repositório). Só com aprovação explícita na etapa 8.
- **Marcos:** `| 7 | README e autoria | README de uma tela com herói e diagrama animados, GIF real e docs/autoria.md | pending | .claude/plans/readme-autoria.plan.md |`

## 2. Desenho

### 2.1 Para onde vai cada parte do README atual

| Trecho atual de `README.md` | Destino |
|---|---|
| "Por que não é mais um chat…" | Vira os 4 diferenciais. O bug da correlação nas 1.000 primeiras linhas vai para a seção nova "O que a avaliação pegou" em `docs/avaliacao.md` |
| Experimente + galeria de screenshots | Link no README; galeria `docs/img/*.png` em "Telas" de `docs/arquitetura.md` |
| O que ele faz | "Visão geral" de `docs/arquitetura.md` |
| Destaques de engenharia | Seção nova "Destaques de engenharia" em `docs/arquitetura.md` |
| Avaliação (comandos e explicação) | Junta com "Como reproduzir" de `docs/avaliacao.md`, sem repetição |
| Mermaid | Já está, mais completo, em "Componentes" de `docs/arquitetura.md`: remover a cópia |
| Como rodar, Docker, Variáveis, Render, Testes, Postgres, CI, Estrutura de pastas, Dados de exemplo | **Novo** `docs/como-rodar.md`, com a seção "Como o GIF foi gravado" |
| Limitações conhecidas | **Novo** `docs/limitacoes.md` (todos os itens + "meta da Spec não batida") |
| Jargão | "Glossário" no fim de `docs/arquitetura.md`: SSE, CSP, Pyodide, Web Worker, nonce, pass^N, cassete, gravação, prelúdio, grounding |

Frases-sentinela (procuradas só em `docs/`): `DEMO_TETO_DIARIO`, `LLM_MODEL_FALLBACK`, `PG_TEST_URL`, `E2E_URL`, `INSTALL postgres`, `New → Blueprint`, `10 vetores de fuga`, `BroadcastChannel`, `1.000 primeiras linhas`, `fake-stream.html`, `SSRF`, `150 s`, `deno test --allow-read tests/js/`. Confira cada uma no README atual antes de usá-la; troque a que não existir.

### 2.2 Paleta e fontes

| Papel | Escuro | Claro | Origem |
|---|---|---|---|
| Fundo do cartão / borda | `#131C2E` / `#25324A` | `#F6F8FA` / `#D0D7DE` | perfil / GitHub claro |
| Texto / secundário | `#F0F6FC` / `#8B949E` | `#1F2328` / `#59636E` | GitHub |
| Assinatura, passo Plano | `#9085e9` | `#6250d6` | `--accent` do app |
| SQL | `#58A6FF` | `#0969DA` | perfil |
| Python no navegador | `#39C5CF` | `#1B7C83` | perfil |
| Gráfico | `#F0883E` | `#BC4C00` | próximo de `--viz-s2` |
| Selo conferido | `#3FB950` | `#1A7F37` | perfil / `--ok` |
| Bloqueio (rede) | `#F85149` | `#CF222E` | perfil |

Fontes: `system-ui, -apple-system, "Segoe UI", sans-serif`; código `ui-monospace, "Cascadia Mono", Consolas, monospace`. Na versão clara, todo texto colorido com contraste de pelo menos 4,5:1 sobre `#F6F8FA`.

### 2.3 Herói (`docs/img/heroi-{escuro,claro}.svg` e `heroi-celular-{escuro,claro}.svg`)

viewBox desktop 1200×420; celular 600×760 (passos empilhados). Loop de 12 s numa linha do tempo única: todas as animações com `animation: 12s infinite`, sequenciadas por porcentagem nos `@keyframes` (nunca por `animation-delay`, para não perder a sincronia entre voltas).

| Tempo | Cena |
|---|---|
| 0–2,6 s | Pergunta digitada: "O tempo de entrega afeta a nota do cliente?". `<text textLength lengthAdjust="spacingAndGlyphs">` fixa a largura; máscara com `steps(N)` revela letra a letra; cursor pisca |
| 2,6–3,6 s | Cartão "Plano" desliza; 3 linhas se desenham (`stroke-dashoffset`) |
| 3,6–5,0 s | Cartão SQL: `SELECT tempo_entrega_min, avaliacao FROM pedidos …`, revelado por linhas |
| 5,0–7,0 s | Cartão Python com selo "no seu navegador" e ícone de janela; barra de progresso; saída `r = -0,506 · n = 5.501` (confira os valores em `data/perguntas.json` e em `docs/avaliacao.md`) |
| 7,0–8,4 s | Mini dispersão: cerca de 12 pontos surgem e a reta de tendência se desenha |
| 8,4–9,4 s | Selo "números conferidos" carimba (escala 1,15→1, anel que pulsa uma vez); faixa "N chamadas ao LLM · R$ 0", com N tirado da tomada real do GIF (até lá, use o valor da gravação `tempo_nota`) |
| 9,4–12 s | Pausa e fade para recomeçar |

Movimento reduzido: o estado base de cada elemento é o quadro final visível; `@media (prefers-reduced-motion: reduce){*{animation:none!important}}`. Um `<style>` só, com as cores num bloco `/* cores */ … /* fim cores */`; a variante clara é cópia da escura trocando só esse bloco (teste). Formas simples, sem filtros pesados.

### 2.4 Diagrama (`docs/img/fluxo-{escuro,claro}.svg` e `fluxo-celular-{…}.svg`)

viewBox desktop 1200×420; celular 600×820. À esquerda, "Servidor: FastAPI + agente", com "Gemini" acima; à direita, "Navegador do visitante", contendo "Página" e, dentro dela, "Web Worker · Pyodide · sem rede", com globo riscado. Loop de 10 s:
1. Pacote "python_pedido: código + dados + nonce" vai do servidor até a **Página**.
2. A Página passa "código + dados" ao Worker, **sem nonce**.
3. O Worker pulsa "rodando Python"; uma seta para a internet bate num X vermelho: "fetch bloqueado (CSP)".
4. A saída volta do Worker para a Página.
5. A Página manda "resultado + mesmo nonce, aceito uma vez" ao servidor.
6. No servidor acende em verde a conferência "cada número tem fonte?".

Legenda fixa: "O servidor nunca executa o Python da IA." Mesmas regras de peso, cores e acessibilidade do herói.

### 2.5 Ícones dos diferenciais (`docs/img/icone-{navegador,ao-vivo,avaliacao,seguranca}-{escuro,claro}.svg`)

48×48, traço simples na paleta (Python/navegador ciano, ao vivo roxo, avaliação verde, segurança vermelho ou azul), sem texto, `role="img"` e `<title>`. Animação sutil opcional (uma pulsação de 2–3 s), com reduced-motion. Até 3 KB cada. No README, cada diferencial é uma linha com `<picture>` do ícone (24–28 px) + texto.

### 2.6 GIF do app real

- Gravar contra o uvicorn local com o wrapper da chave (ver "Fatos"). Ensaiar antes de graça contra `/static/fake-stream.html` para acertar seletores e enquadramento.
- Script Playwright no scratchpad, com os seletores de `tests/e2e/test_fluxo.py`: viewport 1024×640, `record_video_dir`, tema claro; "Usar CSV de exemplo", esperar `#esquema` e o Python pré-aquecido; digitar a pergunta (`press_sequentially(delay=35)`) e Enter; esperar `.final` e `.status.parado`. Descartar a tomada se aparecer o selo de gravação, se faltar "números conferidos" ou o selo "no seu navegador". Rolar até o gráfico, segurar 2 s, fechar o contexto.
- Conversão (ffmpeg pelo caminho completo): `fps=10,scale=800:-1:flags=lanczos` com `palettegen=stats_mode=diff` e `paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle`, `-loop 0`, recortando 15–25 s. Acima de 5 MB: 8 fps, depois 720 px, depois recortar só a coluna da conversa; último recurso, WebP animado. Acima de 25 s: acelerar (`setpts=PTS/1.25`) e escrever na legenda e no `alt`.
- Cota: até 3 tomadas reais de cerca de 6 chamadas (esperado ~18, máximo 36). Depois de 3 tomadas, ficar com a melhor.
- Formato: GIF versionado (toca sozinho, em loop, em qualquer lugar do GitHub). MP4 descartado (só toca se enviado pelo editor web, sem autoplay em loop).

### 2.7 Rascunho do README (até 80 linhas)

```html
<h1 align="center">Analista de dados com IA</h1>
<picture>
  <source media="(max-width: 600px) and (prefers-color-scheme: dark)" srcset="docs/img/heroi-celular-escuro.svg">
  <source media="(max-width: 600px)" srcset="docs/img/heroi-celular-claro.svg">
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/heroi-escuro.svg">
  <img src="docs/img/heroi-claro.svg" width="100%" alt="(alt narrativo)">
</picture>
<h3 align="center">Pergunte em português. O agente planeja no servidor, roda o Python no seu navegador e mostra cada passo ao vivo.</h3>
<p align="center"><a href="https://analista-dados-ia.onrender.com"><b>Experimente ao vivo →</b></a> · <a href="docs/arquitetura.md">Como funciona</a> · <a href="docs/autoria.md">Como foi construído</a><br>
<img src="https://github.com/danielsouzaa7/analista-dados-ia/actions/workflows/ci.yml/badge.svg" alt="CI"></p>
```

Os 4 diferenciais (ícone + texto curto + link):
1. **O Python da IA roda no seu navegador, não no servidor.** O agente pensa no servidor; o código que ele escreve roda num Web Worker do navegador (Pyodide: Python em WebAssembly), sem acesso à rede. O servidor grátis (0,1 vCPU) nunca executa esse código. → [Decisão 13](docs/decisoes.md)
2. **Cada passo aparece ao vivo, com tempo e custo.** Plano, SQL, Python, gráfico e conferência chegam em streaming, com duração e custo de cada chamada. Antes de virar resposta, cada número é conferido contra os resultados. → [Arquitetura](docs/arquitetura.md)
3. **Avaliação honesta, em várias rodadas.** 8 casos com resposta calculada à parte em pandas; 5 rodadas contra o modelo real: média 7,0/8 (faixa 6–8), 6/8 certos em todas, nenhum número sem fonte. A meta era 8/8; não foi batida, e está escrito. → [Avaliação](docs/avaliacao.md)
4. **Red team com histórico.** 5 rodadas de ataque (SQL, sandbox, API, streaming, Python no navegador); cada achado reproduzido, fechado e coberto por teste. → [Segurança](docs/seguranca.md)

Depois: `<picture>` do fluxo com legenda "O servidor nunca executa o Python da IA"; o GIF com legenda "App real, pergunta ao vivo, gravado em dd/mm/2026 com gemini-3.5-flash-lite"; "Como foi construído" ("Eu defini o produto, os critérios e o processo e tomei as decisões de custo e risco; o código, os testes e as revisões foram feitos por agentes de IA (N agentes, Xh de trabalho ativo)" → [Autoria](docs/autoria.md) · [Tempo de construção](docs/tempo-de-construcao.md)); `<details>` "Rodar localmente (3 comandos)" (`cp .env.example .env`, `docker build -t analista-dados-ia .`, `docker run --rm -p 7860:7860 --env-file .env analista-dados-ia`, link para `docs/como-rodar.md`); `<details>` "O que eu faria diferente · limitações" ((a) avaliação maior com casos ambíguos, sem resposta e conferência contra o gabarito; (b) medir a CPU da hospedagem antes de escolher onde roda o Python; limitações curtas e link para `docs/limitacoes.md`).

### 2.8 docs/autoria.md

1. **Resumo em 3 linhas, na voz do Daniel:** dono do produto e tech lead de um time de agentes de IA (Claude Code com o framework ECC). Os agentes escreveram o código, os testes, a documentação e as revisões; ele definiu o quê, o porquê e os critérios, desenhou o processo, escolheu entre as opções que os agentes prepararam e aprovou cada publicação.
2. **O processo que ele desenhou** (resumo das regras globais dele, sem copiar o arquivo privado): 9 etapas (pedido → spec → revisão da spec → plano → testes primeiro → revisão independente → teste → aprovação dele → deploy); laço de revisão que passa de 3 voltas para e volta para ele; modelo escolhido por tarefa (mais forte para planejar e revisar, mais rápido para implementar); deploy só depois da aprovação dele.
3. **Tabela de decisões** (abaixo).
4. **O que foi delegado**, com os números de `docs/tempo-de-construcao.md` (agentes, horas somadas, por categoria): o texto da Spec, todas as ADRs técnicas, o red team, a avaliação, a medição de horas e o design dos SVGs.
5. **O que este documento não diz:** "Não escrevi o código nem fiz as revisões técnicas. As opções e as recomendações técnicas vieram dos agentes."
6. **Como verificar:** links para a Spec, as ADRs, `docs/avaliacao.md`, `docs/tempo-de-construcao.md` e o histórico de commits.

Tabela de decisões (horário de Brasília; "T" = transcrição local, não publicada):

| Data | Decisão do Daniel | Alternativas / contexto | Fonte pública | Fonte local |
|---|---|---|---|---|
| 19/11 | Pedido inicial do produto (CSV ou banco, perguntas em português, SQL, Python, gráficos) e o diagrama de referência do fluxo | — | `Spec.md` "Fluxo do agente (do diagrama de referência)"; `referência.png` (conferir se está no git) | registro local da conversa |
| 19/11 | Dataset de pedidos de delivery, de propósito, pelo público-alvo (confirmado pelo Daniel em 21/11) | — | `Spec.md` "Usuários" | confirmação do Daniel |
| 19/11 | ECC como framework e o fluxo de 9 etapas; modelo por tarefa | Superpowers (desativado) | o próprio `autoria.md` | regras globais dele |
| 19/11 | LLM grátis (Gemini) em vez de chave paga; a chave nunca é lida pelos agentes; `.env.example`; aviso de dados sensíveis na tela | Chave paga de outro provedor | Spec crit. 9 ("decisão do Daniel em 19/11/2026"); crit. 10 (acrescentar atribuição) | registro local da conversa |
| 19/11 | Horas publicadas sem tempo parado nem esperas por ele | — | `docs/tempo-de-construcao.md` (acrescentar "medido a pedido do Daniel") | memória |
| 19/11 | "Projeto completo, não MVP" e "fugir do óbvio" → onda 2 (critérios 18–22) | MVP | `.claude/plans/experiencia-portfolio.plan.md` (conferir se está no git) | registro local da conversa |
| 19/11 | Commit a cada lote verde; push e deploy só depois da etapa 8 | — | — | memória |
| 19/11 | Aprovação da etapa 8 condicionada a "ter fugido do óbvio" aos olhos de quem avalia GenAI | — | — | registro local da conversa |
| 21/11 | Render grátis | Railway (~US$5/mês), HF PRO (~US$9/mês), sem deploy | Spec; commit do `render.yaml` | registro local da conversa |
| 21/11 | Escolheu o Cloud Run; quando o Google pediu pré-pagamento único de R$180, recusou qualquer custo: "acho um absurdo pagar pra expor portfólio" | HF PRO ~US$9/mês, Render Starter US$7/mês, Cloud Run R$180 | **criar ADR 14** | registro local da conversa |
| 21/11 | Python da IA no navegador, entre 3 opções preparadas pelos agentes | Sandbox aquecida no servidor; só SQL | Spec; ADR 13 | registro local da conversa |
| 21/11 | Público-alvo explícito (time de tecnologia do iFood); "sempre fugindo do óbvio" como critério | — | Spec "Usuários" | memória |
| 21/11 | Chave de avaliação num projeto Google próprio (criada por ele) | Cortar o cassete; regravar no dia seguinte | `docs/avaliacao.md` (acrescentar atribuição) | registro local da conversa |
| 21/11 | Autorizou cortar as 2 respostas não usadas do cassete do `cupom_ticket` | Regravar no dia seguinte | `docs/avaliacao.md` (acrescentar "autorizado pelo Daniel") | registro local da conversa |
| 21/11 | Push e publicação depois da etapa 8; horas sem tempo parado nem esperas por ele; pediu para conferir se fugiu do óbvio | — | `docs/tempo-de-construcao.md` | registro local da conversa |
| 21/11 | Pediu uma avaliação independente (8/10 fugir do óbvio, 7/10 profundidade) | — | — | registro local da conversa |
| 21/11 | Pediu as 3 melhorias; cortou a avaliação de 25–30 casos para trabalho futuro; pediu README animado | — | emenda da Spec | — |

Tornar fontes públicas: **ADR 14** "Hospedagem sem custo: Render grátis" (alternativas e preços "como apresentados em 21/11/2026; os ~US$ eram estimativas dos agentes; os R$180, a tela do Google"); "(pedido do Daniel em 19/11/2026)" no crit. 10 da Spec; atribuições em `docs/avaliacao.md`; "medido a pedido do Daniel" em `docs/tempo-de-construcao.md` (é gerado por `scripts/tempo_construcao.py`: se for texto do script, mexer no script).

### 2.9 Card do perfil (opcional)

`assets/projects/analista-dados-ia.svg` e `-mobile.svg` (~9–15 KB, paleta escura do perfil, coreografia resumida do herói, `alt` narrativo, link para o repositório). Texto no estilo do perfil: **Problema** (quem tem dados mas não sabe SQL nem Python depende de um analista para cada pergunta); **Diferencial** (o agente pensa no servidor e o Python gerado pela IA roda no navegador de quem pergunta, num Worker sem rede; cada passo ao vivo, com tempo e custo); **Prova** (5 rodadas contra o modelo real, média 7,0/8, meta 8/8 não batida e publicada; 5 rodadas de red team com teste para cada achado; app no ar); **Stack** (FastAPI, DuckDB, Gemini via API compatível com OpenAI, Pyodide em Web Worker, SSE, ECharts, pytest, Playwright); **Status** (no ar no Render grátis). Primeiro ler, só leitura, os cards do Pulse e do Event Operations OS (`gh api`) para copiar a estrutura. Preparar no scratchpad; nada de clone, commit ou push sem aprovação explícita.

### 2.10 Skills e teste visual

- Skills, nesta ordem: `ecc:frontend-design-direction` (tokens, tipografia, princípios de movimento) → `design-motion` / `animate` (roteiro de tempos, easing, encadeamento, reduced-motion) → `frontend-design` (composição) → `ui-ux-pro-max` (contraste, acessibilidade, leitura em 10 s).
- Render como o GitHub: `gh api -X POST /markdown -f mode=gfm -f context=danielsouzaa7/analista-dados-ia -F text=@README.md` devolve o HTML saneado. Página local com github-markdown-css (só no teste), servida por `python -m http.server` na raiz; Playwright tira capturas a 1280×800 e 390×844, claro e escuro.
- SVGs como `<img>`: capturas em t = 0, 3, 6 e 9 s em Chromium, Firefox e WebKit, e uma com `reduced_motion="reduce"` (quadro final).

## 3. task_list (testes primeiro; um commit por lote verde; sem push até a etapa 8)

| # | Fatia | Arquivos | Testes primeiro (RED) | Pronto quando | Cota |
|---|---|---|---|---|---|
| 0 | Emenda da Spec + revisão (architect) | `Spec.md` | — | Crit. 23 e 24, fora do escopo, trabalho futuro e marco 7 no arquivo; revisão sem bloqueio | 0 |
| 1 | Testes de docs | **novo** `tests/test_docs.py` | `test_readme_cabe_em_uma_tela`; `test_links_e_imagens_relativos_existem` (`](…)`, `src=`, `srcset=` no README e em `docs/*.md`); `test_conteudo_do_readme_antigo_continua_em_docs`; `test_readme_sem_jargao_solto`; `test_readme_linka_app_autoria_e_avaliacao`; `test_numeros_do_readme_e_da_autoria_batem_com_docs` | Falham pelo motivo certo | 0 |
| 2 | Mover conteúdo | **novos** `docs/como-rodar.md`, `docs/limitacoes.md`; `docs/arquitetura.md`; `docs/avaliacao.md` | — | Sentinelas e links verdes | 0 |
| 3 | README novo (texto) | `README.md` (com `docs/img/conversa.png` provisório no lugar do herói) | — | Fatia 1 verde, exceto o link de autoria | 0 |
| 4 | Autoria | **novo** `docs/autoria.md`; `docs/decisoes.md` (ADR 14); atribuições em `docs/avaliacao.md`, `docs/tempo-de-construcao.md`, `Spec.md` | teste de números | Verde; agente independente só leitura confere cada linha | 0 |
| 5 | Direção visual + herói + ícones | **novos** `docs/img/heroi-*.svg`, `docs/img/icone-*.svg` | `test_svgs_leves_acessiveis_e_sem_recurso_externo` (≤ 30 KB, XML válido, `role="img"`, `<title>`, `<desc>` (ícones: `<title>`), `prefers-reduced-motion` nos animados, sem `<script>`, `foreignObject`, `http` em `href`/`url(`/`@import`); `test_variantes_clara_e_escura_so_mudam_as_cores` | Verde; capturas nos 3 motores e nos dois temas | 0 |
| 6 | Diagrama | **novos** `docs/img/fluxo-*.svg` | os mesmos | Verde; revisor confere que o nonce não entra no Worker | 0 |
| 7 | GIF real | `docs/img/demo.gif`; `docs/como-rodar.md`; `README.md` | `test_demo_animada_existe_e_pesa_menos_de_5_mb` | Ensaio de graça; até 3 tomadas reais; ≤ 5 MB; legenda honesta; trace do herói com os números da tomada | ~18, máx. 36 |
| 8 | Revisão (até 3 voltas) | — | — | `ecc:code-review` em `tests/test_docs.py`; `ui-ux-pro-max` em contraste e leitura; verificador de fatos na autoria; sem CRITICAL nem HIGH | 0 |
| 9 | Verificação | — | — | `ruff`, suíte inteira, render pela API do GitHub com capturas desktop/celular × claro/escuro, pesos | 0 |
| 10 | Card do perfil (opcional) | scratchpad | critérios de SVG à mão | Pronto no scratchpad; sobe só com aprovação | 0 |
| 11 | Etapa 8 | — | — | Mostrar render, GIF, autoria e card ao Daniel | 0 |

## 4. Riscos

- `srcset` relativo dentro de `<source>` e media query composta podem não ser reescritos pelo GitHub. Reserva: URLs absolutas `raw.githubusercontent.com/danielsouzaa7/analista-dados-ia/main/docs/img/...` (só funcionam depois do push). Conferir na verificação.
- `prefers-color-scheme` dentro do SVG segue o sistema operacional, não o tema do GitHub: o tema fica no `<picture>`, não no SVG.
- Peso dos SVGs: formas simples, um `<style>`, sem filtros, teto de 30 KB no teste.
- Números desatualizados ao regerar `docs/tempo-de-construcao.md`: o teste obriga README e autoria a acompanhar.
- Atribuição errada: verificador independente, coluna de fonte e a frase "o que este documento não diz".
- Disco: manter vídeos intermediários no scratchpad e apagá-los depois da conversão.

## Status das fatias

| Fatia | Status |
|---|---|
| 0 | em andamento |
| 1 | feita (tests/test_docs.py, 37 testes verdes) |
| 2 | feita (docs/como-rodar.md, docs/limitacoes.md, seções novas em arquitetura e avaliação) |
| 3 | feita (README de 48 linhas, marcadores de imagem; herói provisório conversa.png) |
| 4 | feita (docs/autoria.md, ADR 14, atribuições em avaliacao.md); falta a conferência por agente independente |
| 5–11 | pendentes |

---

## Revisão do architect — volta 1 (21/11/2026): APROVADO COM AJUSTES

Os itens abaixo **prevalecem sobre o texto acima**.

| # | Achado | Decisão |
|---|---|---|
| H1 | O teste de números aceitava só 4 fontes e uma regex que pegaria "600px", "3 comandos" | Fontes = qualquer `docs/*.md`, `data/perguntas.json` ou a tomada do GIF. O teste confere uma **lista explícita** de pares (número literal → arquivo onde aparece), sem regex genérica |
| H2 | "Cabe na primeira tela a 1280×800" é inviável | Critério 23: "medido do topo do README renderizado". Cada diferencial em **uma linha** (cerca de 15 palavras), com o detalhe no link |
| H3 | Digitação com `textLength` + `steps()` não alinha com fonte proporcional | A pergunta do herói usa `ui-monospace, "Cascadia Mono", Consolas, monospace`, com `textLength`. Se não ficar bom, revelar letra a letra com `<tspan>` |
| H4 | A autoria atribuía ao Daniel o desenho de um processo que espelha o ECC (terceiros); "tech lead" contradiz "as opções técnicas vieram dos agentes" | "O fluxo de trabalho que ele definiu para os agentes, montado sobre o ECC" (com crédito ao ECC). Papel: "dono do produto, que dirigiu um time de agentes de IA" |
| H5 | "Sem acesso à rede" é exagero (a CSP libera o caminho do Pyodide; há 3 vazamentos aceitos) | Em todo lugar (README, SVGs, `alt`): "sem rede além do caminho fixo do Pyodide", com link para `docs/seguranca.md` |
| H6 | Privacidade | O plano foi limpo (sem caminhos locais, IDs de sessão nem detalhes pessoais). Em `autoria.md`, a coluna de fonte local usa só "registro local da conversa" e só a data, sem hora. Nunca citar o caminho das regras globais do Daniel |
| M7 | "A chave nunca é lida pelos agentes" fica falsa com o script do GIF | Escrever "o valor da chave nunca é mostrado aos agentes". O script do GIF e o `avaliar.py` leem do `.env` sem imprimir. Se o classificador de permissões bloquear o agente, o Daniel roda com `!` |
| M8 | Legenda do GIF | "Pergunta real, rodando localmente no commit `<sha>`; melhor de até 3 tomadas; espera do carregamento inicial cortada". Nunca "código publicado". Não descartar tomada por número omitido (só por gravação, erro ou ausência do Python no navegador). Meta: **3 MB** (máximo 5 MB). Cortar a espera do aquecimento em vez de acelerar |
| M9 | Claro/escuro via `<picture>` com query composta não se prova sem push | **Herói e diagrama viram cartões com fundo próprio escuro** (como os cards do perfil do Daniel), legíveis nos dois temas do GitHub. O `<picture>` só usa `max-width: 600px` para a variante de celular (padrão já provado no perfil). Arquivos: `heroi.svg`, `heroi-celular.svg`, `fluxo.svg`, `fluxo-celular.svg`. Cai o teste "claro e escuro só mudam as cores" |
| M10 | Diagrama | Passo 6: "o agente continua; antes de responder, confere cada número". A regra de jargão vale também para o texto dos SVGs e dos `alt`: "nonce" vira "código de uso único" |
| M11 | Os números de tempo mudam por causa desta entrega | Congelar no README e na autoria como "até 21/11/2026, 20h01" (10h05 ativas, 58 agentes), ou regerar o relatório uma única vez na fatia 9 e atualizar tudo junto. Escolha: regerar uma vez na fatia 9 |
| M12 | Ordem e tamanho das fatias | GIF (fatia 7) **antes** do herói, porque o herói usa o número de chamadas da tomada. A fatia 5 vira: 5a herói desktop, 5b herói celular, 5c ícones. A fatia 4 não mexe em `scripts/tempo_construcao.py`: a frase "a pedido do Daniel" fica só em `autoria.md` |
| L13 | Ícones | **Uma versão só**, em tom médio com contraste ≥ 3:1 sobre `#ffffff` e sobre `#0d1117`. No README, `alt=""` (decorativos ao lado do texto). O teste confere o `alt` no README, não o `<title>` do SVG |
| L14 | `<h3>` na frase de valor | `<p align="center"><b>…</b></p>` |
| L15 | `<details>` | Linha em branco depois de `<summary>` e antes de `</details>` |
| L16 | Spec | Alinhar o marco 5 (README com arquitetura e avaliação), que fica redundante, e o critério 11, que fala em "6 perguntas" quando a avaliação tem 8 casos |
| L17 | Tabela da autoria | Cortar as três últimas linhas de 21/11 (falam do próprio trabalho de README; "7/10" é opinião de agente). Manter a citação dos R$180 |
| L18 | Testes de docs | O limite de linhas é completado pela captura de tela na verificação. As sentinelas foram conferidas e existem no README atual |

### Nova ordem das fatias

0 (Spec) → 1 (testes de docs) → 2 (mover conteúdo) → 3 (README texto) → 4 (autoria) → 7 (GIF) → 5a/5b/5c (herói e ícones) → 6 (diagrama) → 8 (revisão) → 9 (verificação e regerar o tempo uma vez) → 10 (card do perfil, opcional) → 11 (etapa 8).
