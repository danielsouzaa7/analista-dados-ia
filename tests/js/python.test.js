import { assert, assertEquals, assertRejects } from "jsr:@std/assert@1";
import { estaPronto, executarPython, preaquecer, responderPython } from "../../static/python.js";
import { ambiente, fabrica, responde } from "./workers/falso.js";

const pedido = { codigo: "print(1)", csv: "a\n1", preludio: "" };
const rapido = { cargaMs: 30, execucaoMs: 30 };
const pausa = (ms = 5) => new Promise((r) => setTimeout(r, ms));

Deno.test("devolve o resultado do worker desta execução e o encerra", async () => {
  ambiente();
  const f = fabrica({ aoPedido: responde({ saida: "1\n", erro: null }) });
  const r = await executarPython(pedido, { criar: f.criar, ...rapido });
  assertEquals(r, { saida: "1\n", erro: null });
  assert(f.workers[0].encerrado);
});

Deno.test("manda codigo, csv e preludio ao worker", async () => {
  ambiente();
  let recebido;
  const f = fabrica({ aoPedido: (w, m) => { recebido = m; responde({ saida: "", erro: null })(w); } });
  await executarPython({ ...pedido, preludio: "P" }, { criar: f.criar, ...rapido });
  assertEquals(recebido, { codigo: "print(1)", csv: "a\n1", preludio: "P" });
});

Deno.test("mensagem de um worker antigo é ignorada", async () => {
  ambiente();
  const velho = fabrica({ aoPedido: responde({ saida: "velho", erro: null }) });
  await executarPython(pedido, { criar: velho.criar, ...rapido });
  const novo = fabrica({
    aoPedido: (w) => {
      velho.workers[0].onmessage?.({ data: { tipo: "resultado", saida: "forjado", erro: null } });
      responde({ saida: "novo", erro: null })(w);
    },
  });
  const r = await executarPython(pedido, { criar: novo.criar, ...rapido });
  assertEquals(r.saida, "novo");
});

Deno.test("só a primeira mensagem de resultado da instância vale", async () => {
  ambiente();
  const f = fabrica({
    aoPedido: (w) => {
      responde({ saida: "primeiro", erro: null })(w);
      w.onmessage?.({ data: { tipo: "resultado", saida: "segundo", erro: null } });
    },
  });
  const r = await executarPython(pedido, { criar: f.criar, ...rapido });
  assertEquals(r.saida, "primeiro");
});

Deno.test("execução acima do prazo encerra o worker e devolve o erro do limite", async () => {
  ambiente();
  const f = fabrica({ aoPedido: () => {} });
  const r = await executarPython(pedido, { criar: f.criar, ...rapido });
  assertEquals(r, { saida: "", erro: "Tempo limite de 30 s excedido." });
  assert(f.workers[0].encerrado);
});

Deno.test("carga acima do prazo devolve erro em português", async () => {
  ambiente();
  const f = fabrica({ inicio: null });
  const r = await executarPython(pedido, { criar: f.criar, ...rapido });
  assertEquals(r, { saida: "", erro: "Não consegui carregar o Python no seu navegador em 45 s." });
  assert(f.workers[0].encerrado);
});

Deno.test("worker que falha ao carregar devolve erro em português", async () => {
  ambiente();
  const f = fabrica({ inicio: "falhou" });
  const r = await executarPython(pedido, { criar: f.criar, ...rapido });
  assertEquals(r.saida, "");
  assert(r.erro.startsWith("Não consegui carregar o Python"));
});

Deno.test("abort encerra o worker e não devolve resultado", async () => {
  ambiente();
  const f = fabrica({ aoPedido: () => {} });
  const ac = new AbortController();
  const p = executarPython(pedido, { criar: f.criar, signal: ac.signal, cargaMs: 1000, execucaoMs: 1000 });
  await pausa();
  ac.abort();
  await assertRejects(() => p, DOMException);
  assert(f.workers[0].encerrado);
});

Deno.test("sinal já abortado não cria worker", async () => {
  ambiente();
  const f = fabrica();
  await assertRejects(() => executarPython(pedido, { criar: f.criar, signal: AbortSignal.abort() }), DOMException);
  assertEquals(f.workers.length, 0);
});

Deno.test("saída cortada em 10 mil pontos de código sem partir um emoji", async () => {
  ambiente();
  const f = fabrica({ aoPedido: responde({ saida: "😀".repeat(10_001), erro: null }) });
  const r = await executarPython(pedido, { criar: f.criar, ...rapido });
  assertEquals(Array.from(r.saida).length, 10_000);
  assert(r.saida.isWellFormed());
});

Deno.test("erro fica com as 6 últimas linhas e até 2 mil caracteres", async () => {
  ambiente();
  const linhas = Array.from({ length: 10 }, (_, i) => `linha${i}`).join("\n");
  const f = fabrica({ aoPedido: responde({ saida: "", erro: linhas }) });
  const r = await executarPython(pedido, { criar: f.criar, ...rapido });
  assertEquals(r.erro, "linha4\nlinha5\nlinha6\nlinha7\nlinha8\nlinha9");

  const g = fabrica({ aoPedido: responde({ saida: "", erro: "😀".repeat(3000) }) });
  const longo = await executarPython(pedido, { criar: g.criar, ...rapido });
  assertEquals(Array.from(longo.erro).length, 2000);
  assert(longo.erro.isWellFormed());
});

Deno.test("com reserva quando deviceMemory é ausente (Firefox e Safari de desktop)", async () => {
  ambiente({ deviceMemory: undefined });
  const f = fabrica({ aoPedido: responde({ saida: "", erro: null }) });
  await executarPython(pedido, { criar: f.criar, ...rapido });
  assertEquals(f.workers.length, 2);
});

Deno.test("sem reserva quando deviceMemory < 4 ou pointer coarse", async () => {
  for (const amb of [{ deviceMemory: 2 }, { deviceMemory: undefined, grosso: true }, { deviceMemory: 8, grosso: true }]) {
    ambiente(amb);
    const f = fabrica({ aoPedido: responde({ saida: "", erro: null }) });
    await executarPython(pedido, { criar: f.criar, ...rapido });
    assertEquals(f.workers.length, 1);
    preaquecer(f.criar);
    assertEquals(f.workers.length, 1);
    assertEquals(estaPronto(), false);
  }
});

Deno.test("depois de cada execução fica um worker novo de reserva, criado depois do terminate", async () => {
  ambiente({ deviceMemory: 8 });
  const f = fabrica({ aoPedido: responde({ saida: "ok", erro: null }) });
  await executarPython(pedido, { criar: f.criar, ...rapido });
  assertEquals(f.workers.length, 2);
  assertEquals(f.encerradosNaCriacao[1], [true]); // o primeiro já estava encerrado
  await pausa();
  assert(estaPronto());

  await executarPython(pedido, { criar: f.criar, ...rapido }); // usa a reserva e cria outra
  assertEquals(f.workers.length, 3);
  assert(f.workers[1].encerrado);
  assertEquals(f.encerradosNaCriacao[2], [true, true]);

  ambiente(); // drena a reserva para não vazar para outros testes
  await executarPython(pedido, { criar: f.criar, ...rapido });
});

Deno.test("preaquecer respeita saveData", () => {
  ambiente({ deviceMemory: 8, saveData: true });
  const f = fabrica();
  preaquecer(f.criar);
  assertEquals(f.workers.length, 0);
});

const chega = { id: 7, nonce: 12, codigo: "print(1)", csv: "a\n1", preludio: "P", extra: "x" };
const rede = () => Object.assign(new Error("rede"), { rede: true });

Deno.test("responderPython manda os campos como String e só codigo, csv e preludio ao worker", async () => {
  let recebido;
  const postados = [];
  await responderPython(chega, {
    sessao: "s1",
    executar: (p) => { recebido = p; return Promise.resolve({ saida: { a: 1 }, erro: null }); },
    postar: (c) => { postados.push(c); return Promise.resolve(); },
  });
  assertEquals(recebido, { codigo: "print(1)", csv: "a\n1", preludio: "P" });
  assertEquals(postados, [{ sessao: "s1", id: "7", nonce: "12", saida: "[object Object]", erro: null }]);
});

Deno.test("responderPython tenta de novo uma vez em erro de rede", async () => {
  let posts = 0;
  await responderPython(chega, {
    sessao: "s", executar: () => Promise.resolve({ saida: "", erro: "x" }),
    postar: () => { posts++; return posts === 1 ? Promise.reject(rede()) : Promise.resolve(); },
  });
  assertEquals(posts, 2);
});

Deno.test("responderPython desiste depois de duas falhas de rede", async () => {
  let posts = 0;
  await responderPython(chega, {
    sessao: "s", executar: () => Promise.resolve({ saida: "", erro: null }),
    postar: () => { posts++; return Promise.reject(rede()); },
  });
  assertEquals(posts, 2);
});

Deno.test("responderPython não tenta de novo num 400 ou 422", async () => {
  let posts = 0;
  await responderPython(chega, {
    sessao: "s", executar: () => Promise.resolve({ saida: "", erro: null }),
    postar: () => { posts++; return Promise.reject(new Error("400")); },
  });
  assertEquals(posts, 1);
});

Deno.test("responderPython não posta nada depois do abort", async () => {
  let posts = 0;
  const postar = () => { posts++; return Promise.resolve(); };
  await responderPython(chega, {
    sessao: "s", postar,
    executar: () => Promise.reject(new DOMException("x", "AbortError")),
  });
  const c = new AbortController();
  await responderPython(chega, {
    sessao: "s", postar, signal: c.signal,
    executar: () => { c.abort(); return Promise.resolve({ saida: "", erro: null }); },
  });
  assertEquals(posts, 0);
});
