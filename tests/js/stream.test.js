import { assertEquals, assertThrows } from "jsr:@std/assert@1";
import { ParserSSE } from "../../static/stream.js";

const coletar = () => {
  const out = [];
  return { out, p: new ParserSSE((t, d) => out.push([t, d])) };
};

Deno.test("H2: exceção do handler propaga (não é engolida)", () => {
  const p = new ParserSSE(() => { throw new Error("bug no render"); });
  assertThrows(() => p.push('event: resposta\ndata: {}\n\n'), Error, "bug no render");
});

Deno.test("H2: JSON inválido continua sendo ignorado", () => {
  const { out, p } = coletar();
  p.push('event: a\ndata: {quebrado\n\nevent: b\ndata: {"x":1}\n\n');
  assertEquals(out, [["b", { x: 1 }]]);
});

Deno.test("L1: bloco sem a linha em branco final não é despachado", () => {
  const { out, p } = coletar();
  p.push('event: fim\ndata: {}');
  p.fim();
  assertEquals(out, []);
});

Deno.test("evento completo é despachado, mesmo cortado em pedaços de 1 caractere e com \r\n", () => {
  const { out, p } = coletar();
  for (const c of 'event: r\r\ndata: {"a":"ç"}\r\n\r\n') p.push(c);
  p.fim();
  assertEquals(out, [["r", { a: "ç" }]]);
});
