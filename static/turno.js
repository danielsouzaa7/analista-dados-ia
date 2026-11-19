// Um turno da conversa: pergunta, linha do tempo ao vivo, rascunho, resposta, feedback e trace.
// Todo texto que vem do servidor/LLM/CSV entra por textContent (via el()).
import { el, botao, icone, fmtNum, fmtMs, fmtCelula, baixarCsv, copiar, renderTexto } from "./dom.js";
import { desenharGrafico } from "./graficos.js";

const LINHAS_VISIVEIS = 100;
const ROTULO_FASE = { plano: "plano", ferramentas: "ferramentas", resposta: "resposta" };
const MOTIVOS = [
  ["numeros_errados", "Números errados"],
  ["nao_entendeu", "Não entendeu a pergunta"],
  ["grafico_ruim", "Gráfico ruim"],
  ["lento", "Lento"],
  ["outro", "Outro"],
];
const TIPO_PASSO = { sql: "SQL", python: "Python", grafico: "Gráfico" };

function blocoCodigo(linguagem, texto) {
  const caixa = el("div", null, "codigo");
  const cab = el("div", null, "codigo-cab");
  cab.append(el("span", linguagem, "codigo-lang"));
  const b = botao("Copiar", "btn-mini", null, "copiar");
  b.setAttribute("aria-label", `Copiar ${linguagem}`);
  b.addEventListener("click", async () => {
    const ok = await copiar(texto);
    b.lastChild.textContent = ok ? "Copiado" : "Não copiou";
    setTimeout(() => { b.lastChild.textContent = "Copiar"; }, 1600);
  });
  cab.append(b);
  const pre = el("pre", null, null, { tabindex: "0" });
  pre.append(el("code", texto));
  caixa.append(cab, pre);
  return caixa;
}

function tabelaResultado(colunas, linhas, total) {
  const caixa = el("div", null, "resultado");
  const wrap = el("div", null, "tabela-wrap", { tabindex: "0", role: "region", "aria-label": "Resultado da consulta" });
  const t = el("table", null, "tabela");
  const cabeca = el("thead");
  const tr0 = el("tr");
  colunas.forEach((c, i) => tr0.append(el("th", c, linhas.some((l) => typeof l[i] === "number") ? "num" : null, { scope: "col" })));
  cabeca.append(tr0);
  const corpo = el("tbody");
  linhas.slice(0, LINHAS_VISIVEIS).forEach((l) => {
    const tr = el("tr");
    l.forEach((v, i) => tr.append(el("td", fmtCelula(v, colunas[i]), typeof v === "number" ? "num" : null)));
    corpo.append(tr);
  });
  t.append(cabeca, corpo);
  wrap.append(t);
  const rodape = el("div", null, "resultado-rodape");
  const totalReal = total ?? linhas.length;
  let info = `${fmtNum(totalReal)} ${totalReal === 1 ? "linha" : "linhas"}`;
  if (linhas.length > LINHAS_VISIVEIS) info += `, mostrando ${LINHAS_VISIVEIS}`;
  rodape.append(el("span", info, "nota"));
  const b = botao("Baixar CSV", "btn-mini", () => baixarCsv("resultado.csv", colunas, linhas), "baixar");
  rodape.append(b);
  if (totalReal > linhas.length) rodape.append(el("span", `O CSV traz as primeiras ${fmtNum(linhas.length)} linhas.`, "nota"));
  caixa.append(wrap, rodape);
  return caixa;
}

export function criarTurno({ pergunta, aoSugestao, aoTentar, aoFeedback, extras = [] }) {
  const raiz = el("article", null, "turno");
  const quem = el("div", null, "turno-pergunta");
  quem.append(el("p", pergunta));
  const agente = el("div", null, "agente");
  const cab = el("div", null, "agente-cab");
  const status = el("p", "Enviando…", "status", { role: "status" });
  const ponto = el("span", null, "ponto");
  status.prepend(ponto);
  const selos = el("div", null, "selos");
  cab.append(status, selos);
  const trilha = el("ol", null, "trilha");
  const rascunhos = el("div", null, "rascunhos");
  const final = el("div", null, "final-area", { "aria-live": "polite" });
  const traceBox = el("div", null, "trace-area");
  agente.append(cab, trilha, rascunhos, final, traceBox);
  raiz.append(quem, agente);

  const passos = new Map();
  const drafts = new Map();
  const trace = [];
  let metricas = null;
  let temporizador = null;
  let gravacao = false;
  let turnoIdx = null;
  let terminou = false;
  let temResposta = false;
  let desenhoPendente = 0;

  const setStatus = (texto, parado = false) => {
    if (temporizador) { clearInterval(temporizador); temporizador = null; }
    status.querySelector(".contagem")?.remove();
    status.lastChild.textContent = texto;
    status.classList.toggle("parado", parado);
  };
  const selo = (texto, classe) => { const s = el("span", texto, `selo ${classe || ""}`); selos.append(s); return s; };

  function marcarGravacao() {
    if (gravacao) return;
    gravacao = true;
    const s = selo("gravação", "selo-gravacao");
    s.title = "Reprodução de uma execução real gravada";
  }

  function novoPasso(tipo, rotulo) {
    const li = el("li", null, `passo passo-${tipo}`);
    const cabPasso = el("div", null, "passo-cab");
    cabPasso.append(el("span", rotulo, "passo-tag"));
    const dur = el("span", null, "passo-dur");
    cabPasso.append(dur);
    const corpo = el("div", null, "passo-corpo");
    li.append(cabPasso, corpo);
    trilha.append(li);
    return { li, corpo, dur, cabPasso, tipo };
  }

  function passoFerramenta(d) {
    let p = passos.get(d.id);
    if (!p) {
      p = novoPasso(d.tipo || "ferramenta", TIPO_PASSO[d.tipo] || "Ferramenta");
      passos.set(d.id, p);
    }
    return p;
  }

  // Texto que o modelo escreve antes de chamar uma ferramenta é "anotação", não resposta: sai do rascunho e entra na linha do tempo.
  function recolherAnotacoes() {
    for (const [chave, r] of [...drafts.entries()]) {
      if (r.decidido || !r.buf.trim()) continue;
      const p = novoPasso("anotacao", "Anotação");
      const texto = el("div", null, "texto texto-anotacao");
      renderTexto(texto, r.buf);
      p.corpo.append(texto);
      r.caixa.remove();
      drafts.delete(chave);
    }
  }

  function aoInicioFerramenta(d) {
    recolherAnotacoes();
    const p = passoFerramenta(d);
    p.li.classList.add("rodando");
    p.dur.textContent = "rodando…";
    if (d.tipo === "python") p.corpo.append(blocoCodigo("Python", d.codigo || ""));
    else if (d.sql) p.corpo.append(blocoCodigo("SQL", d.sql));
    setStatus(d.tipo === "python" ? "Rodando código Python…" : d.tipo === "grafico" ? "Preparando o gráfico…" : "Consultando os dados…");
  }

  function aoFimFerramenta(d) {
    if (!passos.has(d.id)) recolherAnotacoes();
    const p = passoFerramenta(d);
    p.li.classList.remove("rodando");
    p.dur.textContent = fmtMs(d.ms);
    trace.push({ tipo: "ferramenta", rotulo: TIPO_PASSO[p.tipo] || "Ferramenta", ms: d.ms, erro: Boolean(d.erro) });
    if (d.erro) {
      p.li.classList.add("com-erro");
      p.corpo.append(el("p", d.erro, "erro-texto"));
    }
    if (Array.isArray(d.colunas) && Array.isArray(d.linhas)) p.corpo.append(tabelaResultado(d.colunas, d.linhas, d.total_linhas));
    if (d.saida) {
      p.corpo.append(el("p", "Saída", "rotulo-mini"));
      p.corpo.append(el("pre", d.saida, "saida", { tabindex: "0" }));
    }
    if (d.grafico) p.corpo.append(desenharGrafico(d.grafico));
    setStatus("Analisando os resultados…");
  }

  function escreverRascunho(r) {
    if (desenhoPendente) return;
    const agendar = window.requestAnimationFrame || ((f) => setTimeout(f, 16));
    desenhoPendente = agendar(() => { desenhoPendente = 0; renderTexto(r.texto, r.buf); });
  }

  function aoRascunho(d) {
    let r = drafts.get(d.tentativa);
    if (!r) {
      const caixa = el("section", null, "rascunho", { "aria-label": "Rascunho da resposta" });
      const rotulo = el("p", null, "rascunho-cab");
      rotulo.append(el("span", null, "ponto"), el("span", "rascunho · conferindo números…"));
      const texto = el("div", null, "texto");
      caixa.append(rotulo, texto);
      rascunhos.append(caixa);
      r = { caixa, rotulo, texto, buf: "", fim: false };
      drafts.set(d.tentativa, r);
    }
    r.buf += d.delta || "";
    escreverRascunho(r);
    setStatus("Escrevendo a resposta…");
  }

  function aoConferencia(d) {
    const r = drafts.get(d.tentativa);
    if (!r) return;
    renderTexto(r.texto, r.buf);
    r.decidido = true;
    if (d.ok) {
      r.rotulo.replaceChildren(icone("util"), el("span", "números conferidos"));
      r.caixa.classList.add("conferido");
      setStatus("Números conferidos.");
    } else {
      r.rotulo.replaceChildren(el("span", "alguns números não bateram"));
      setStatus("Alguns números não bateram. Decidindo o que fazer…");
    }
  }

  function aoDescartado(d) {
    const r = drafts.get(d.tentativa);
    const falhas = Array.isArray(d.falhas) ? d.falhas : [];
    if (r) {
      r.decidido = true;
      renderTexto(r.texto, r.buf);
      r.caixa.classList.add("descartado");
      r.rotulo.replaceChildren(el("span", "descartado"));
      if (falhas.length) {
        const ul = el("ul", null, "falhas");
        falhas.forEach((f) => ul.append(el("li", String(f))));
        r.caixa.append(el("p", "Números que não bateram com os dados:", "rotulo-mini"), ul);
      }
    }
    const p = novoPasso("reanalise", "Reanálise");
    p.corpo.append(el("p", `Refazendo a análise (tentativa ${(d.tentativa ?? 1) + 1}).`));
    setStatus("Reanalisando…");
  }

  function pedirFeedback(idx) {
    const caixa = el("div", null, "feedback");
    const linha = el("div", null, "feedback-linha");
    linha.append(el("span", "Esta resposta ajudou?", "feedback-pergunta"));
    const bUtil = botao("Útil", "btn-mini", null, "util");
    const bNao = botao("Não útil", "btn-mini", null, "nao_util");
    bUtil.setAttribute("aria-pressed", "false");
    bNao.setAttribute("aria-pressed", "false");
    linha.append(bUtil, bNao);
    const msg = el("p", null, "feedback-msg");
    const motivos = el("div", null, "feedback-motivos");
    motivos.hidden = true;

    msg.tabIndex = -1;
    const enviar = async (nota, motivo) => {
      [bUtil, bNao].forEach((b) => { b.disabled = true; });
      bUtil.setAttribute("aria-pressed", String(nota === "util"));
      bNao.setAttribute("aria-pressed", String(nota === "nao_util"));
      motivos.hidden = true;
      msg.focus(); // o foco estava num motivo que acabou de sumir
      try {
        await aoFeedback({ turno: idx, nota, motivo });
        msg.textContent = "Obrigado, anotado.";
      } catch (e) {
        [bUtil, bNao].forEach((b) => { b.disabled = false; b.setAttribute("aria-pressed", "false"); });
        msg.textContent = e && e.message ? e.message : "Não consegui enviar. Tente de novo.";
      }
    };
    bUtil.addEventListener("click", () => { bUtil.setAttribute("aria-pressed", "true"); enviar("util"); });
    bNao.addEventListener("click", () => {
      bNao.setAttribute("aria-pressed", "true");
      motivos.hidden = false;
      motivos.querySelector("button").focus();
    });
    motivos.append(el("span", "Quer dizer o motivo? (opcional)", "nota"));
    MOTIVOS.forEach(([cod, texto]) => motivos.append(botao(texto, "chip", () => enviar("nao_util", cod))));
    motivos.append(botao("Enviar sem motivo", "chip chip-neutro", () => enviar("nao_util")));
    caixa.append(linha, motivos, msg);
    return caixa;
  }

  function aoResposta(d) {
    temResposta = true;
    for (const r of drafts.values()) if (!r.caixa.classList.contains("descartado")) r.caixa.remove();
    const sec = el("section", null, "final", { "aria-label": "Resposta" });
    const topo = el("div", null, "final-selos");
    if (d.conferido) {
      const s = el("span", null, "selo selo-ok");
      s.append(icone("util"), el("span", "números conferidos"));
      topo.append(s);
    }
    if (d.reanalises > 0) topo.append(el("span", `reanalisou ${d.reanalises}×`, "selo"));
    if (topo.childNodes.length) sec.append(topo);
    const texto = el("div", null, "texto texto-final");
    renderTexto(texto, d.texto);
    sec.append(texto);
    if (d.aviso) sec.append(el("p", d.aviso, "aviso-conferencia", { role: "note" }));
    final.append(sec);
    turnoIdx = Number.isInteger(d.turno) ? d.turno : null;
    if (turnoIdx !== null && aoFeedback && !gravacao) final.append(pedirFeedback(turnoIdx));
    const sug = (d.sugestoes || []).filter((s) => typeof s === "string" && s.trim());
    if ((sug.length || extras.length) && aoSugestao) {
      const caixa = el("div", null, "sugestoes");
      caixa.append(el("p", "Continue perguntando", "rotulo-mini"));
      const lista = el("div", null, "sugestoes-lista");
      extras.forEach((x) => lista.append(botao(x.rotulo, "chip chip-sugestao", x.enviar)));
      sug.slice(0, 3).forEach((s) => lista.append(botao(s, "chip chip-sugestao", () => aoSugestao(s))));
      caixa.append(lista);
      final.append(caixa);
    }
    setStatus(d.conferido ? "Pronto. Números conferidos." : "Pronto, com aviso.", true);
  }

  function aoErro(d) {
    const caixa = el("div", null, "erro-caixa", { role: "alert" });
    caixa.append(el("p", d.mensagem || "Algo deu errado. Tente de novo."));
    if (aoTentar) caixa.append(botao("Tentar de novo", "btn-secundario", aoTentar, "recarregar"));
    agente.insertBefore(caixa, traceBox);
    setStatus("Não deu certo.", true);
    status.classList.add("erro");
  }

  // ---------- trace ----------
  function linhaChip(rotulo, valor) {
    const li = el("div", null, "kv");
    li.append(el("dt", rotulo), el("dd", valor));
    return li;
  }

  function montarTrace() {
    traceBox.replaceChildren();
    if (!metricas && !trace.length) return;
    const m = metricas || {};
    const soma = trace.reduce((s, x) => s + (Number.isFinite(x.ms) ? x.ms : 0), 0);
    const total = Math.max(m.ms_total || 0, soma) || 1;
    const det = el("details", null, "trace");
    det.append(el("summary", "Como o agente chegou aqui"));
    const corpo = el("div", null, "trace-corpo");
    const kv = el("dl", null, "kv-grade");
    const tok = (v) => (v === null || v === undefined ? "não informado" : fmtNum(v));
    kv.append(
      linhaChip("Tempo total", fmtMs(m.ms_total ?? soma)),
      linhaChip("Chamadas ao LLM", fmtNum(m.chamadas_llm ?? trace.filter((x) => x.tipo === "llm").length)),
      linhaChip("Chamadas de ferramenta", fmtNum(m.chamadas_ferramenta ?? trace.filter((x) => x.tipo === "ferramenta").length)),
      linhaChip("Tokens de entrada", tok(m.tokens_entrada)),
      linhaChip("Tokens de saída", tok(m.tokens_saida)),
      linhaChip("Reanálises", fmtNum(m.reanalises ?? 0)),
      linhaChip("Modelo", m.modelo || "–"),
      linhaChip("Custo", m.custo || "–"),
    );
    if (m.versao_prompt) kv.append(linhaChip("Versão do prompt", m.versao_prompt));
    if (m.trace_id) kv.append(linhaChip("ID do trace", m.trace_id));
    corpo.append(kv);

    const lista = el("ol", null, "onda");
    let acumulado = 0;
    trace.forEach((x) => {
      const li = el("li", null, "onda-linha");
      const nome = el("div", null, "onda-nome");
      nome.append(el("span", x.rotulo, "onda-rotulo"));
      const detalhe = [];
      if (x.modelo) detalhe.push(x.modelo);
      if (x.tipo === "llm") detalhe.push(`tokens ${x.tokens_entrada ?? "?"} → ${x.tokens_saida ?? "?"}`);
      if (x.erro) detalhe.push("com erro");
      if (detalhe.length) nome.append(el("span", detalhe.join(" · "), "onda-detalhe"));
      nome.append(el("span", fmtMs(x.ms), "onda-ms"));
      const trilhaBarra = el("div", null, "onda-trilha", { "aria-hidden": "true" });
      const barra = el("span", null, `onda-barra ${x.tipo === "llm" ? "llm" : "ferr"}`);
      barra.style.left = `${(acumulado / total) * 100}%`;
      barra.style.width = `max(3px, ${((x.ms || 0) / total) * 100}%)`;
      trilhaBarra.append(barra);
      acumulado += x.ms || 0;
      li.append(nome, trilhaBarra);
      lista.append(li);
    });
    corpo.append(el("p", "Cada barra começa quando a anterior termina. A largura é proporcional ao tempo.", "nota"), lista);
    det.append(corpo);
    traceBox.append(det);
  }

  function aoEvento(tipo, d) {
    const perto = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 260;
    if (d.gravacao) marcarGravacao();
    switch (tipo) {
      case "recebido":
        if (d.modelo) selo(d.modelo, "selo-modelo");
        setStatus("Recebido. Montando o plano…");
        break;
      case "plano": {
        const p = novoPasso("plano", "Plano");
        renderTexto(p.corpo, d.texto);
        setStatus("Executando o plano…");
        break;
      }
      case "llm":
        trace.push({ tipo: "llm", rotulo: `LLM · ${ROTULO_FASE[d.fase] || d.fase}`, ms: d.ms, tokens_entrada: d.tokens_entrada, tokens_saida: d.tokens_saida, modelo: d.modelo });
        break;
      case "aguardando_cota": {
        let s = Math.max(0, Math.round(d.segundos || 0));
        // só o início é anunciado; a contagem muda a cada segundo e fica fora do leitor de tela
        setStatus("Aguardando cota");
        const contagem = el("span", ` (${s} s)…`, "contagem", { "aria-hidden": "true" });
        status.append(contagem);
        temporizador = setInterval(() => {
          s = Math.max(0, s - 1);
          contagem.textContent = ` (${s} s)…`;
        }, 1000);
        break;
      }
      case "ferramenta_inicio": aoInicioFerramenta(d); break;
      case "ferramenta_fim": aoFimFerramenta(d); break;
      case "rascunho": aoRascunho(d); break;
      case "conferencia": aoConferencia(d); break;
      case "descartado": aoDescartado(d); break;
      case "resposta": aoResposta(d); break;
      case "metricas": metricas = d; montarTrace(); break;
      case "erro": aoErro(d); break;
      case "fim":
        terminou = true;
        if (temporizador) { clearInterval(temporizador); temporizador = null; }
        ponto.hidden = true;
        if (!metricas) montarTrace();
        if (!temResposta && status.classList.contains("parado") === false) setStatus("Terminou.", true);
        break;
      default: break;
    }
    if (perto) window.scrollTo(0, document.documentElement.scrollHeight);
  }

  /** Falha antes ou no meio do stream (JSON {"detail"} ou queda de conexão). */
  function falhar(mensagem) {
    if (terminou) return;
    terminou = true;
    ponto.hidden = true;
    for (const r of drafts.values()) {
      if (temResposta || r.caixa.classList.contains("descartado")) continue;
      r.caixa.classList.remove("conferido");
      r.caixa.classList.add("interrompido");
      r.rotulo.replaceChildren(el("span", "rascunho interrompido: a resposta não chegou ao fim"));
    }
    aoErro({ mensagem });
  }

  return {
    el: raiz,
    aoEvento,
    falhar,
    tirarSugestoes: () => raiz.querySelectorAll(".sugestoes").forEach((n) => n.remove()),
    get terminou() { return terminou; },
  };
}
