# Autoria

Sou o dono do produto, que dirigiu um time de agentes de IA (Claude Code com o framework ECC). Os agentes escreveram o código, os testes, a documentação, as revisões técnicas e o red team. Eu defini o quê, o porquê e os critérios de aprovação (custo zero, projeto completo, "fugir do óbvio"); os critérios de aceite da Spec foram redigidos pelos agentes e aprovados por mim. Escolhi entre as opções que os agentes prepararam e aprovei cada publicação.

## O fluxo de trabalho

O fluxo que defini para os agentes, montado sobre o ECC (um conjunto de agentes, comandos e regras para o Claude Code, de terceiros), tem 9 etapas: pedido, especificação, revisão da especificação, plano, implementação com testes primeiro, revisão independente do código, testes, minha aprovação e deploy. Se um laço de revisão passa de 3 voltas sem resolver, ele para e volta para mim. O modelo é escolhido por tarefa e o deploy só acontece depois da minha aprovação. Fonte: registro local da conversa.

## Decisões minhas

Datas em horário de Brasília. "Registro local da conversa" é a transcrição das sessões, que não está publicada. As opções e as recomendações técnicas vieram dos agentes.

| Data | Decisão do Daniel | Alternativas ou contexto | Fonte |
|---|---|---|---|
| 19/11 | Pediu um agente que responde em português sobre CSV ou banco, com SQL, Python e gráficos, e passou o diagrama de referência do fluxo (o arquivo não está no repositório) | - | [Spec](../Spec.md), "Fluxo do agente"; registro local da conversa |
| 19/11 | Dataset de pedidos de delivery de comida, de propósito, por causa do público-alvo (confirmado por ele em 21/11) | - | [Spec](../Spec.md), "Usuários" e critério 11; registro local da conversa |
| 19/11 | ECC como framework principal e o fluxo de 9 etapas | Superpowers (desativado) | registro local da conversa |
| 19/11 | LLM Gemini no plano gratuito; o valor da chave nunca é mostrado aos agentes; aviso de dados sensíveis na tela | Chave paga de outro provedor | [Spec](../Spec.md), critérios 9 e 10; registro local da conversa (chave) |
| 19/11 | Horas publicadas sem tempo parado nem as esperas por ele | - | [tempo de construção](tempo-de-construcao.md), "Como foi medido"; registro local da conversa |
| 19/11 | Pediu "um projeto completo" (onda 2, critérios 18 a 22) | - | [plano](../.claude/plans/experiencia-portfolio.plan.md), "Onda 2" |
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

77 agentes, com 17h44 de trabalho somado dos agentes (em paralelo), em 13h07 de tempo ativo de relógio (números de [tempo de construção](tempo-de-construcao.md), até 21/11/2026). Por categoria: implementação 37 agentes (10h32), revisão 21 (4h51), especificação e plano 8 (1h03), documentação 6 (0h21), testes 3 (0h46), outros 2 (0h10). Ficaram com eles o texto da Spec e dos planos, o código, os testes, as ADRs técnicas, o red team, a avaliação e a medição das horas.

## O que este documento não diz

Não escrevi o código nem fiz as revisões técnicas. As opções e as recomendações técnicas vieram dos agentes. Aqui só estão as decisões minhas que tenho como mostrar.

## Como verificar

[Spec](../Spec.md), [decisões](decisoes.md), [segurança](seguranca.md), [avaliação](avaliacao.md), [tempo de construção](tempo-de-construcao.md) e o histórico de commits do repositório.
