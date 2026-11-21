import { assert, assertEquals, assertRejects } from "jsr:@std/assert@1";
import { estaPronto, executarPython, preaquecer, responderPython, statusPython } from "../../static/python.js";
import { ambiente, fabrica, responde } from "./workers/falso.js";

const pedido = { codigo: "print(1)", csv: "a\n1", preludio: "" };
const rapido = { cargaMs: 30, execucaoMs: 30 };
const pausa = (ms = 5) => new Promise((r) => setTimeout(r, ms));
const ok = responde({ saida: "ok", erro: null });
// Sem reserva, a próxima execução consome a que sobrou e não cria outra: nada vaza para o teste seguinte.
const drenar = async (f) => { ambiente(); await executarPython(pedido, { criar: f.criar, ...rapido }); };

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
  const f = fabrica({ aoPedido: (w, m) => { recebido = m; ok(w); } });
  await executarPython({ ...pedido, preludio: "P" }, { criar: f.criar, ...rapido });
  assertEquals(recebido, { codigo: "print(1)", csv: "a\n1", preludio: "P" });
});

Deno.test("mensagens de um worker substituído por outra execução são ignoradas", async () => {
  ambiente({ deviceMemory: 8 });
  const f = fabrica({ aoPedido: (w) => setTimeout(() => responde({ saida: "novo", erro: null })(w), 20) });
  const primeira = executarPython(pedido, { criar: f.criar, ...rapido, cargaMs: 1000 });
  primeira.catch(() => {});
  const velho = f.workers[0];
  const handler = velho.onmessage; // acabar() anula o handler: guardamos o original
  const segunda = executarPython(pedido, { criar: f.criar, ...rapido, cargaMs: 1000 });
  const antes = f.workers.length;
  handler({ data: { tipo: "pronto" } });
  handler({ data: { tipo: "resultado", saida: "forjado", erro: null } });
  assertEquals((await segunda).saida, "novo");
  assertEquals(velho.pedidos, 0); // o pedido nunca chega ao worker que já foi encerrado
  assertEquals(f.workers.length, antes + 1); // só a reserva de depois da segunda; o forjado não criou nada
  await drenar(f);
});

Deno.test("só a primeira mensagem de resultado da instância vale", async () => {
  ambiente({ deviceMemory: 8 });
  const f = fabrica({
    aoPedido: (w) => {
      const handler = w.onmessage; // o worker real pode entregar duas mensagens antes do terminate
      ok(w);
      handler({ data: { tipo: "resultado", saida: "segundo", erro: null } });
    },
  });
  const r = await executarPython(pedido, { criar: f.criar, ...rapido });
  assertEquals(r.saida, "ok");
  assertEquals(f.workers.length, 2); // a execução e uma reserva: a segunda mensagem não criou outra
  await drenar(f);
});

Deno.test("abort durante a carga encerra o worker e o pronto que chega depois não manda o pedido", async () => {
  ambiente();
  const f = fabrica({ inicio: null });
  const ac = new AbortController();
  const p = executarPython(pedido, { criar: f.criar, signal: ac.signal, cargaMs: 1000, execucaoMs: 1000 });
  const handler = f.workers[0].onmessage;
  ac.abort();
  await assertRejects(() => p, DOMException);
  assert(f.workers[0].encerrado);
  handler({ data: { tipo: "pronto" } });
  await pausa();
  assertEquals(f.workers[0].pedidos, 0);
});

Deno.test("execução acima do prazo encerra o worker e devolve o erro do limite", async () => {
  ambiente();
  const f = fabrica({ aoPedido: () => {} });
  const r = await executarPython(pedido, { criar: f.criar, ...rapido });
  assertEquals(r, { saida: "", erro: "Tempo limite de 30 ms excedido." });
  assert(f.workers[0].encerrado);
});

Deno.test("carga acima do prazo devolve erro em português", async () => {
  ambiente();
  const f = fabrica({ inicio: null });
  const r = await executarPython(pedido, { criar: f.criar, ...rapido });
  assertEquals(r, { saida: "", erro: "Não consegui carregar o Python no seu navegador em 30 ms." });
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

Deno.test("saída gigante é cortada em menos de 200 ms, sem partir um par surrogate", async () => {
  ambiente();
  const gigante = "x".repeat(5e7);
  const f = fabrica({ aoPedido: responde({ saida: gigante, erro: null }) });
  const t0 = performance.now();
  const r = await executarPython(pedido, { criar: f.criar, ...rapido });
  const ms = performance.now() - t0;
  assert(ms < 200, `levou ${ms} ms`);
  assertEquals(r.saida.length, 10_000);

  // o corte por unidades UTF-16 cai no meio de um emoji: a metade solta não pode sobrar
  const g = fabrica({ aoPedido: responde({ saida: "a" + "😀".repeat(15_000), erro: null }) });
  const emoji = await executarPython(pedido, { criar: g.criar, ...rapido });
  assertEquals(Array.from(emoji.saida).length, 10_000);
  assert(emoji.saida.isWellFormed());
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
  const f = fabrica({ aoPedido: ok });
  await executarPython(pedido, { criar: f.criar, ...rapido });
  assertEquals(f.workers.length, 2);
  await drenar(f);
});

Deno.test("sem reserva quando deviceMemory < 4, pointer coarse ou saveData", async () => {
  const casos = [{ deviceMemory: 2 }, { deviceMemory: undefined, grosso: true }, { deviceMemory: 8, grosso: true }, { deviceMemory: 8, saveData: true }];
  for (const amb of casos) {
    ambiente(amb);
    const f = fabrica({ aoPedido: ok });
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
  await drenar(f);
});

Deno.test("duas execuções vivas ao mesmo tempo terminam com no máximo 1 worker vivo, a reserva", async () => {
  ambiente({ deviceMemory: 8 });
  const f = fabrica({ aoPedido: (w) => setTimeout(() => ok(w), 20) });
  const primeira = executarPython(pedido, { criar: f.criar, cargaMs: 1000, execucaoMs: 1000 });
  primeira.catch(() => {});
  await executarPython(pedido, { criar: f.criar, cargaMs: 1000, execucaoMs: 1000 });
  await pausa();
  assertEquals(f.workers.filter((w) => !w.encerrado).length, 1);
  assert(estaPronto()); // o vivo é o que a reserva referencia
  await assertRejects(() => primeira, DOMException); // a substituída não fica pendurada
  await drenar(f);
});

Deno.test("reserva que falhou ao carregar não é reaproveitada: a execução abre um worker novo", async () => {
  ambiente({ deviceMemory: 8 });
  const ruim = fabrica({ inicio: "falhou" });
  preaquecer(ruim.criar);
  await pausa();
  assert(ruim.workers[0].encerrado);
  const bom = fabrica({ aoPedido: ok });
  const r = await executarPython(pedido, { criar: bom.criar, cargaMs: 1000, execucaoMs: 1000 });
  assertEquals(r, { saida: "ok", erro: null });
  await drenar(bom);
});

Deno.test("erro síncrono ao recriar a reserva não deixa a execução pendente", async () => {
  ambiente({ deviceMemory: 8 });
  const f = fabrica({ aoPedido: ok });
  let n = 0;
  const criar = () => { if (n++ > 0) throw new Error("sem memória"); return f.criar(); };
  const r = await Promise.race([executarPython(pedido, { criar, ...rapido }), pausa(200).then(() => "preso")]);
  assertEquals(r, { saida: "ok", erro: null });
  ambiente();
});

Deno.test("statusPython: pronto, carregando só na primeira vez, e sem essa promessa quando não há reserva", async () => {
  ambiente({ deviceMemory: 8 });
  assertEquals(statusPython(), "Carregando o Python no seu navegador (só na primeira vez)…");
  const f = fabrica({ aoPedido: ok });
  preaquecer(f.criar);
  await pausa();
  assertEquals(statusPython(), "Rodando o Python no seu navegador…");
  await drenar(f);
  for (const amb of [{ deviceMemory: 2 }, { deviceMemory: 8, saveData: true }]) {
    ambiente(amb);
    assertEquals(statusPython(), "Carregando o Python no seu navegador…");
  }
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
    sessao: "s", esperaMs: 1, executar: () => Promise.resolve({ saida: "", erro: "x" }),
    postar: () => { posts++; return posts === 1 ? Promise.reject(rede()) : Promise.resolve(); },
  });
  assertEquals(posts, 2);
});

Deno.test("responderPython desiste depois de duas falhas de rede", async () => {
  let posts = 0;
  await responderPython(chega, {
    sessao: "s", esperaMs: 1, executar: () => Promise.resolve({ saida: "", erro: null }),
    postar: () => { posts++; return Promise.reject(rede()); },
  });
  assertEquals(posts, 2);
});

Deno.test("responderPython espera antes da segunda tentativa e não tenta se abortarem nesse intervalo", async () => {
  const c = new AbortController();
  let posts = 0;
  setTimeout(() => c.abort(), 10);
  await responderPython(chega, {
    sessao: "s", signal: c.signal, esperaMs: 40, executar: () => Promise.resolve({ saida: "", erro: null }),
    postar: () => { posts++; return Promise.reject(rede()); },
  });
  assertEquals(posts, 1);
});

Deno.test("responderPython não tenta de novo num 400 ou 422", async () => {
  let posts = 0;
  await responderPython(chega, {
    sessao: "s", executar: () => Promise.resolve({ saida: "", erro: null }),
    postar: () => { posts++; return Promise.reject(new Error("400")); },
  });
  assertEquals(posts, 1);
});

Deno.test("responderPython converte erro inesperado do executor em erro em português e posta", async () => {
  const postados = [];
  await responderPython(chega, {
    sessao: "s", executar: () => Promise.reject(new Error("boom")),
    postar: (c) => { postados.push(c); return Promise.resolve(); },
  });
  assertEquals(postados.length, 1);
  assertEquals(postados[0].saida, "");
  assert(postados[0].erro.startsWith("O Python do seu navegador falhou"));
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
