import { assertEquals } from "jsr:@std/assert@1";
import { fmtValor, ehMoeda, rotuloFalha, latexSimples } from "../../static/dom.js";
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

Deno.test("LaTeX em linha: cifrões somem, comandos e expoentes viram Unicode", () => {
  assertEquals(latexSimples("p-valor de $1,58 \\times 10^{-52}$"), "p-valor de 1,58 × 10⁻⁵²");
  assertEquals(latexSimples("$a \\cdot b$ e $x \\le 3$, $y \\leq 4$, $z \\ge 1$, $w \\geq 2$, $u \\approx 5$"),
    "a · b e x ≤ 3, y ≤ 4, z ≥ 1, w ≥ 2, u ≈ 5");
  assertEquals(latexSimples("$10^-52$ e $10^{-3}$ e $10^{12}$"), "10⁻⁵² e 10⁻³ e 10¹²");
});

Deno.test("LaTeX em linha: o cifrão de R$ nunca é delimitador", () => {
  assertEquals(latexSimples("R$ 52,01 e R$ 63,90"), "R$ 52,01 e R$ 63,90");
  assertEquals(latexSimples("R$ 52,01, com $p < 0,001$"), "R$ 52,01, com p < 0,001");
});

Deno.test("LaTeX em linha: texto sem LaTeX não muda", () => {
  const s = "O ticket médio foi de 52,01 (p < 0,001); 10 pedidos, x^2 e {chaves}.";
  assertEquals(latexSimples(s), s);
});
