import { assertEquals } from "jsr:@std/assert@1";
import { fmtValor, ehMoeda } from "../../static/dom.js";
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
  const xs = [1, 2, 3, 4]; // mês numérico: x não pode ir em coord
  const m = marcas(xs, [5, 9, 2, 4], t);
  assertEquals(m.map((p) => p.coord), [[3, 4], [1, 9], [2, 2]]);
});
