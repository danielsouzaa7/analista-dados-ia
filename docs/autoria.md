# Autoria

Sou o dono do produto, que dirigiu um time de agentes de IA (Claude Code com o framework ECC). Os agentes escreveram o código, os testes, a documentação, as revisões técnicas e o red team. Eu defini o quê, o porquê e os critérios, escolhi entre as opções que os agentes prepararam e aprovei cada publicação.

## O fluxo de trabalho

O fluxo que defini para os agentes, montado sobre o ECC (um conjunto de agentes, comandos e regras para o Claude Code, de terceiros), tem 9 etapas: pedido, especificação, revisão da especificação, plano, implementação com testes primeiro, revisão independente do código, testes, minha aprovação e deploy. Se um laço de revisão passa de 3 voltas sem resolver, ele para e volta para mim. O modelo é escolhido por tarefa e o deploy só acontece depois da minha aprovação. Fonte: registro local da conversa.

## Decisões minhas

Datas em horário de Brasília. "Registro local da conversa" é a transcrição das sessões, que não está publicada. As opções e as recomendações técnicas vieram dos agentes.

| Data | Decisão do Daniel | Alternativas ou contexto | Fonte |
|---|---|---|---|
| 19/11 | Pediu um agente que responde em português sobre CSV ou banco, com SQL, Python e gráficos, e passou o diagrama de referência do fluxo (o arquivo não está no repositório) | - | [Spec](../Spec.md), "Fluxo do agente"; registro local da conversa |
| 19/11 | Dataset de pedidos de delivery de comida, de propósito, por causa do público-alvo (confirmado por ele em 21/11) | - | [Spec](../Spec.md), "Usuários" e critério 11; registro local da conversa |
| 19/11 | ECC como framework principal e o fluxo de 9 etapas | Superpowers (desativado) | registro local da conversa |
| 19/11 | LLM Gemini no plano gratuito; o valor da chave nunca é mostrado aos agentes; aviso de dados sensíveis na tela | Modelo local ou API paga (descartados na [decisão 1](decisoes.md)) | [Spec](../Spec.md), critérios 9 e 10 |
| 19/11 | Horas publicadas sem tempo parado nem as esperas por ele | - | [tempo de construção](tempo-de-construcao.md), "Como foi medido" |
| 19/11 | Pediu um projeto completo, não só um MVP (onda 2, critérios 18 a 22) | MVP | [plano](../.claude/plans/experiencia-portfolio.plan.md), "Onda 2" |
| 19/11 | Aprovação da etapa 8 condicionada a ter "fugido do óbvio" aos olhos de quem avalia IA generativa | - | registro local da conversa |
| 19/11 | Commit a cada lote de testes verde; push e deploy só depois da aprovação | - | registro local da conversa |
| 21/11 | Publicar no Render gratuito | Railway, HF PRO, sem publicar | [ADR 14](decisoes.md); [Spec](../Spec.md), "Onde publicar?" |
| 21/11 | Escolheu o Cloud Run; ao saber do pré-pagamento de R$180, recusou qualquer custo (história abaixo) | HF PRO, Render Starter, Cloud Run | [ADR 14](decisoes.md) |
| 21/11 | Python da IA no navegador do visitante, entre as opções que os agentes prepararam | Deno no servidor (por chamada ou de longa duração), hospedagem paga | [ADR 13](decisoes.md); [Spec](../Spec.md), "Perguntas em aberto" |
| 21/11 | Chave de avaliação num projeto Google próprio, criado por ele | - | [avaliação](avaliacao.md) |
| 21/11 | Autorizou cortar as 2 respostas não usadas do cassete de `cupom_ticket` | Regravar no dia seguinte (registro local) | [avaliação](avaliacao.md) |

### Hospedagem: a história completa

Eu escolhi o Cloud Run. O Google pediu um pré-pagamento único de R$180, e eu recusei qualquer custo: "acho um absurdo pagar pra expor portfólio". O projeto ficou no plano gratuito do Render. Isso trouxe um servidor de 0,1 vCPU, e foi por isso que o Python da IA passou a rodar no navegador. Preços e alternativas, como apresentados em 21/11/2026 (os ~US$ eram estimativas dos agentes; os R$180, a tela do Google): [ADR 14](decisoes.md).

## O que foi delegado

58 agentes, somando 14h12 de trabalho, em 10h05 de tempo ativo (números de [tempo de construção](tempo-de-construcao.md), até 21/11/2026). Por categoria: implementação 27 agentes (8h15), revisão 19 (4h37), especificação e plano 5 (0h35), documentação 3 (0h18), testes 2 (0h16), outros 2 (0h10). Ficaram com eles o texto da Spec e dos planos, o código, os testes, as ADRs técnicas, o red team, a avaliação e a medição das horas.

## O que este documento não diz

Não escrevi o código nem fiz as revisões técnicas. As opções e as recomendações técnicas vieram dos agentes. Aqui só estão as decisões minhas que tenho como mostrar.

## Como verificar

[Spec](../Spec.md), [decisões](decisoes.md), [segurança](seguranca.md), [avaliação](avaliacao.md), [tempo de construção](tempo-de-construcao.md) e o histórico de commits do repositório.
