import { assertEquals } from "jsr:@std/assert@1";
import { fmtValor, ehMoeda, rotuloFalha } from "../../static/dom.js";
import { marcas } from "../../static/marcas.js";

// Intl usa espaço não separável entre "R$" e o número.
const n = (s) => s.replace(/\s/g, " ");

Deno.test("M6: moeda em reais", () => {
  assertEquals(n(fmtValor(482310.5, "receita")), "R$ 482.310,50");
  assertEquals(n(fmtValor(482310.5, "receita", true)), "R$ 482,3 mil");
  assertEquals(n(fmtValor(1312301, "faturamento", true)), "R$ 1,3 mi");
  assertEquals(n(fmtValor(9.3, "ticket_medio")), "R$ 9,30");
});

Deno.test("M6: colunas que não são dinheiro", () => {
  for (const c of ["avaliacao", "pedidos", "tempo_entrega_min", "pedido_id"]) {
    assertEquals(ehMoeda(c), false, c);
    assertEquals(fmtValor(1234, c).includes("R$"), false, c);
  }
});

Deno.test("M6: valor inválido vira traço", () => {
  assertEquals(fmtValor(NaN, "receita"), "–");
  assertEquals(fmtValor(null, "receita"), "–");
});

Deno.test("H4: marcas usam coord [índice, valor] (eixo de categoria)", () => {
  const t = { ink: "#000" };
  const m = marcas([5, 9, 2, 4], t);
  assertEquals(m.map((p) => p.coord), [[3, 4], [1, 9], [2, 2]]);
});

Deno.test("N1: percentuais, contagens e taxas de desconto não são moeda", () => {
  for (const c of ["pct_receita", "receita_pct", "participacao_receita", "percentual_receita", "share_receita", "pct_desconto", "taxa_desconto", "proporcao_desconto", "pedidos_com_desconto", "qtd_desconto", "n_desconto", "count_desconto", "p_valor", "valor_p", "Participação na receita (%)"]) {
    assertEquals(ehMoeda(c), false, c);
  }
});

Deno.test("N1: nomes de dinheiro continuam sendo moeda", () => {
  for (const c of ["valor_pedido", "taxa_entrega", "desconto", "receita_total", "ticket_medio", "receita (R$)", "preco_unitario"]) {
    assertEquals(ehMoeda(c), true, c);
  }
});

Deno.test("conferência: só a significância falhando não diz que números não bateram", () => {
  const sig = { ok: false, falhas: [], significancia: true };
  assertEquals(rotuloFalha(sig), "A afirmação de significância estatística não tem um teste que a sustente.");
  assertEquals(rotuloFalha({ ok: false, conferencia: { significancia: true }, falhas: [] }), rotuloFalha(sig));
  assertEquals(rotuloFalha({ ok: false, falhas: ["x"], significancia: true }), "alguns números não bateram");
  assertEquals(rotuloFalha({ ok: false, falhas: ["x"] }), "alguns números não bateram");
  assertEquals(rotuloFalha({ ok: false }), "alguns números não bateram");
});
