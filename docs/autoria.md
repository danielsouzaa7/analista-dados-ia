# Autoria

**Arquitetei este sistema e orquestrei 58 agentes de IA para construí-lo.** Em 10h06 de tempo ativo de relógio, defini as restrições, escolhi a arquitetura, impus os portões de qualidade e dirigi o time; nada foi aceito sem teste, revisão independente e número medido. Fui o dono do produto: decidi o quê, o porquê e o critério de aprovação (custo zero, projeto completo, "fugir do óbvio"), escolhi entre as opções que os agentes prepararam e aprovei cada publicação.

Eu não criei esses agentes: escolhi agentes especializados prontos e os configurei para o fluxo que desenhei. Eles escreveram o código, os testes, a documentação, as revisões técnicas e o red team; os critérios de aceite da Spec foram redigidos por eles e aprovados por mim.

## Meu papel: arquitetura e orquestração

- **Restrições que impus:** hospedagem de custo zero (o servidor gratuito tem 0,1 vCPU e estourou o Python da IA, que passou a rodar no navegador); a chave do LLM fora do alcance dos agentes; chave de avaliação num projeto Google separado do da demo, e as 5 rodadas de avaliação terminaram com 0 erros de infraestrutura.
- **Como distribuí o trabalho:** plano em fatias, cada agente com um conjunto de arquivos próprio, o modelo escolhido por tarefa e um contexto curto para cada um; 57 de 58 agentes ficaram até 300 mil tokens de pico ([orquestração](orquestracao.md)).
- **Portões de qualidade:** spec com critérios de aceite antes do código, revisão independente da spec, plano, testes primeiro, revisão de código por especialistas (Python, JavaScript, segurança), red team, teste em 3 navegadores, verificação de fatos da documentação e a minha aprovação antes de cada publicação; laço de revisão limitado a 3 voltas.
- **Arquitetura com trade-off, entre alternativas que o time preparou:** Python no navegador, sandbox aquecida ou só SQL ([ADR 13](decisoes.md)); Render grátis, HF PRO ou Cloud Run ([ADR 14](decisoes.md)); avaliação em 5 rodadas em vez de uma, que deu 35 de 40 respostas completas e 0 números inventados ([avaliação](avaliacao.md)); publicar os números reais.
- **Verificação em vez de confiança:** saída de IA só entra com prova. As revisões independentes acharam bugs reais (p-valor inventado passando como conferido, aba congelando com saída gigante, worker de cerca de 250 MB vazando), todos corrigidos com teste ([segurança](seguranca.md), 5.16 a 5.18).

## O fluxo de trabalho

O fluxo que defini para os agentes tem 9 etapas: pedido, especificação, revisão da especificação, plano, implementação com testes primeiro, revisão independente do código, testes, minha aprovação e deploy. Se um laço de revisão passa de 3 voltas sem resolver, ele para e volta para mim. O modelo é escolhido por tarefa e o deploy só acontece depois da minha aprovação. Fonte: registro local da conversa.

## O time, por papel

| Papel | O que fez aqui | Exemplo |
|---|---|---|
| Planejamento | Desenhou o plano e o protocolo do Python no navegador | O protocolo `python_pedido` / `POST /api/python/resultado`, com nonce e espera no servidor ([ADR 13](decisoes.md)) |
| Arquitetura e revisão da spec | Revisou o plano antes de haver código | Encontrou furos na regex de significância: casava com "valor por pedido" e disparava com "não foi possível calcular a significância" (H1 e H2 em `docs/planos/python-no-navegador.plan.md`) |
| Implementação com testes primeiro | Escreveu o teste antes do código, em lotes | Worker do Pyodide com CSP própria e testes de fuga nos três motores (commit `b140d08`; [decisão 13](decisoes.md)) |
| Revisão de código Python | Revisou o servidor e o conferidor | Um p-valor inventado passava como conferido (5.18 em [segurança](seguranca.md)) |
| Revisão de JavaScript | Revisou o worker e o cliente | Saída gigante congelava a aba (5.16) e execuções sobrepostas vazavam um worker de cerca de 250 MB (5.17) |
| Segurança (red team) | 6 rodadas de ataque ao código vigente (a 6ª, de injeção indireta, em testes automatizados com LLM falso) | Rodada 5: vetores de fuga do Worker (`fetch`, WebSocket, `importScripts`, `eval`) testados nos três motores ([segurança](seguranca.md)) |
| Testes de ponta a ponta | Rodou o fluxo real no navegador | Playwright em Chromium, Firefox e WebKit, com o CSV de exemplo (`tests/e2e/`) |
| Documentação | Manteve README e docs alinhados ao código | Relatório de red team e relatório de avaliação |
| Verificação de fatos independente | Conferiu a autoria e o README contra as fontes | Achados aplicados no commit `0f86d70` |

Por categoria, os números estão em "O que foi delegado".

## Decisões minhas (de produto e de engenharia)

Datas em horário de Brasília. "Registro local da conversa" é a transcrição das sessões, que não está publicada. As opções e as recomendações técnicas vieram dos agentes.

| Data | Decisão do Daniel | Alternativas ou contexto | Fonte |
|---|---|---|---|
| 19/11 | Pediu um agente que responde em português sobre CSV ou banco, com SQL, Python e gráficos, e passou o diagrama de referência do fluxo (o arquivo não está no repositório) | - | [Spec](../Spec.md), "Fluxo do agente"; registro local da conversa |
| 19/11 | Dataset de pedidos de delivery de comida, de propósito, por causa do público-alvo (confirmado por ele em 21/11) | - | [Spec](../Spec.md), "Usuários" e critério 11; registro local da conversa |
| 19/11 | O fluxo de 9 etapas e a escolha de agentes especializados prontos para segui-lo | Outro conjunto de agentes (desativado) | registro local da conversa |
| 19/11 | LLM Gemini no plano gratuito; o valor da chave nunca é mostrado aos agentes; aviso de dados sensíveis na tela | Chave paga de outro provedor | [Spec](../Spec.md), critérios 9 e 10; registro local da conversa (chave) |
| 19/11 | Horas publicadas sem tempo parado nem as esperas por ele | - | [tempo de construção](tempo-de-construcao.md), "Como foi medido"; registro local da conversa |
| 19/11 | Pediu "um projeto completo" (onda 2, critérios 18 a 22) | - | [plano](planos/experiencia-portfolio.plan.md), "Onda 2" |
| 19/11 | Aprovação da etapa 8 condicionada a ter "fugido do óbvio" aos olhos de quem avalia IA generativa | - | registro local da conversa |
| 19/11 | Commit a cada lote de testes verde; push e deploy só depois da aprovação | - | registro local da conversa |
| 21/11 | Publicar no Render gratuito | Railway, HF PRO, sem publicar | [ADR 14](decisoes.md); [Spec](../Spec.md), "Onde publicar?" |
| 21/11 | Escolheu o Cloud Run; ao saber do pré-pagamento de R$180, recusou qualquer custo (história abaixo) | HF PRO (~US$9/mês), Render Starter (US$7/mês), pagar os R$180 | [ADR 14](decisoes.md) |
| 21/11 | Python da IA no navegador do visitante, entre as opções que os agentes prepararam | Deno no servidor (por chamada ou de longa duração), hospedagem paga, só SQL | [ADR 13](decisoes.md); [Spec](../Spec.md), "Perguntas em aberto" |
| 21/11 | Chave de avaliação num projeto Google separado do da demo, criado por ele | - | [avaliação](avaliacao.md) |
| 21/11 | Autorizou cortar as 2 respostas não usadas do cassete de `cupom_ticket` | Regravar no dia seguinte (registro local) | [avaliação](avaliacao.md) |

### Hospedagem: a história completa

Eu escolhi o Cloud Run. O Google pediu um pré-pagamento único de R$180, e eu recusei qualquer custo: "acho um absurdo pagar pra expor portfólio". O projeto ficou no plano gratuito do Render. Isso trouxe um servidor de 0,1 vCPU, e foi por isso que o Python da IA passou a rodar no navegador. Preços e alternativas, como apresentados em 21/11/2026 (os ~US$ eram estimativas dos agentes; os R$180, a tela do Google): [ADR 14](decisoes.md).

## O que foi delegado

58 agentes, com 14h12 de trabalho somado dos agentes (em paralelo), em 10h06 de tempo ativo de relógio (números de [tempo de construção](tempo-de-construcao.md), até 21/11/2026, commit `cec40ed`; o trabalho de apresentação feito depois não está incluído). Por categoria: implementação 27 agentes (8h15), revisão 19 (4h37), especificação e plano 5 (0h35), documentação 3 (0h18), testes 2 (0h16), outros 2 (0h10); a classificação de [orquestração](orquestracao.md) conta 26 implementadores e 3 agentes gerais porque trata o tipo genérico à parte. Ficaram com eles o texto da Spec e dos planos, o código, os testes, as ADRs técnicas, o red team, a avaliação e a medição das horas.

## O que este documento não diz

Atuei como dono do produto e diretor técnico: defini o problema, o fluxo de trabalho e os critérios de qualidade, tomei as decisões de custo e de arquitetura e dirigi um time de agentes de IA que implementou, testou e revisou cada parte (o código, os testes, as revisões técnicas e o red team são dos agentes). As opções e as recomendações técnicas vieram dos agentes; aqui estão as decisões minhas que tenho como mostrar.

## Como verificar

[Spec](../Spec.md), [decisões](decisoes.md), [segurança](seguranca.md), [avaliação](avaliacao.md), [tempo de construção](tempo-de-construcao.md) e o histórico de commits do repositório.
