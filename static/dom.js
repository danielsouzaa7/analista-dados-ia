// Ajudantes de DOM e formatação. Todo texto de servidor/LLM/CSV entra por textContent.
const NS_SVG = "http://www.w3.org/2000/svg";

/** Cria um elemento. `texto` vai por textContent; `attrs` só para valores que a página controla ou texto (setAttribute). */
export function el(tag, texto, classe, attrs) {
  const e = document.createElement(tag);
  if (texto !== undefined && texto !== null) e.textContent = texto;
  if (classe) e.className = classe;
  if (attrs) for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

// Ícones fixos (caminhos escritos aqui, sem dados dinâmicos).
const ICONES = {
  util: "M7 10v10M7 10l4-7c1.5 0 2.5 1 2.5 2.4V9h5.2a1.6 1.6 0 0 1 1.6 1.9l-1.3 7a2 2 0 0 1-2 1.6H7",
  nao_util: "M7 14V4M7 14l4 7c1.5 0 2.5-1 2.5-2.4V15h5.2a1.6 1.6 0 0 0 1.6-1.9l-1.3-7a2 2 0 0 0-2-1.6H7",
  copiar: "M9 9h10v11H9zM5 15V4h10",
  baixar: "M12 4v11m0 0l-4-4m4 4l4-4M5 20h14",
  tabela: "M4 5h16v14H4zM4 10h16M10 5v14",
  recarregar: "M20 12a8 8 0 1 1-2.4-5.7M20 4v5h-5",
};

export function icone(nome) {
  const s = document.createElementNS(NS_SVG, "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("aria-hidden", "true");
  s.setAttribute("class", "icone");
  const p = document.createElementNS(NS_SVG, "path");
  p.setAttribute("d", ICONES[nome] || "");
  s.append(p);
  return s;
}

/** Botão com ícone opcional. */
export function botao(rotulo, classe, onClick, nomeIcone) {
  const b = el("button", null, classe);
  b.type = "button";
  if (nomeIcone) b.append(icone(nomeIcone));
  b.append(el("span", rotulo));
  if (onClick) b.addEventListener("click", onClick);
  return b;
}

// ---------- números e tempo (pt-BR) ----------
const nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const nfCompacto = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });

export function fmtNum(v) {
  if (v === null || v === undefined || typeof v !== "number" || !Number.isFinite(v)) return "–";
  return Number.isInteger(v) ? nf0.format(v) : nf2.format(v);
}
export function fmtCompacto(v) {
  if (typeof v !== "number" || !Number.isFinite(v)) return "–";
  return Math.abs(v) < 1000 ? fmtNum(v) : nfCompacto.format(v);
}
// shortcut: moeda deduzida pelo nome da coluna; trocar por um campo "unidade" no contrato do gráfico.
const MOEDA = /(^|[^a-zà-ú])(valor|receita|faturamento|pre[cç]o|ticket|custo|gasto|taxa_entrega|desconto|frete)|r\$/i;
const nfMoeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const nfMoedaCompacta = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", notation: "compact", maximumFractionDigits: 1 });
// percentuais, contagens e taxas de desconto têm nome de dinheiro mas não são dinheiro
const NAO_MOEDA = /pct|percent|perc_|%|particip|share|propor|qtd|quantidade|contagem|count|_com_|(^|_)n_|p_?valor|valor_p($|[^a-z])|taxa_(?!entrega)|correl/i;
export const ehMoeda = (coluna) => { const c = String(coluna ?? ""); return !NAO_MOEDA.test(c) && MOEDA.test(c); };
export function fmtValor(v, coluna, compacto = false) {
  if (typeof v !== "number" || !Number.isFinite(v)) return "–";
  if (!ehMoeda(coluna)) return compacto ? fmtCompacto(v) : fmtNum(v);
  return compacto && Math.abs(v) >= 1000 ? nfMoedaCompacta.format(v) : nfMoeda.format(v);
}
export function fmtMs(ms) {
  if (typeof ms !== "number" || !Number.isFinite(ms)) return "–";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
}
export function fmtPct(v, digitos = 2) {
  return typeof v === "number" && Number.isFinite(v) ? `${v.toLocaleString("pt-BR", { maximumFractionDigits: digitos })}%` : "–";
}

/** Valor de célula de tabela. Colunas de identificador não ganham separador de milhar. */
export function fmtCelula(v, coluna) {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") return /(^|_)id$/i.test(coluna || "") ? String(v) : fmtValor(v, coluna);
  return String(v);
}

/** Escapa texto para o tooltip do ECharts, que renderiza HTML. */
export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------- CSV no navegador ----------
function celulaCsv(v) {
  if (v === null || v === undefined) return "";
  let s = String(v);
  // Evita injeção de fórmula ao abrir no Excel (só textos; números negativos seguem como estão).
  if (typeof v === "string" && /^[=+\-@\t\r]/.test(s) && Number.isNaN(Number(s))) s = "'" + s;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function montarCsv(colunas, linhas) {
  const corpo = [colunas, ...linhas].map((l) => l.map(celulaCsv).join(","));
  return "﻿" + corpo.join("\r\n") + "\r\n";
}

export function baixarCsv(nome, colunas, linhas) {
  const blob = new Blob([montarCsv(colunas, linhas)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function copiar(texto) {
  try {
    await navigator.clipboard.writeText(texto);
    return true;
  } catch {
    const t = document.createElement("textarea");
    t.value = texto;
    t.setAttribute("readonly", "");
    t.className = "sr-only";
    document.body.append(t);
    t.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    t.remove();
    return ok;
  }
}

// ---------- texto da resposta (mini-Markdown seguro: parágrafos, listas, **negrito**, `código`) ----------
function inline(pai, texto) {
  for (const parte of texto.split(/(\*\*[^*]+\*\*|`[^`]+`)/)) {
    if (!parte) continue;
    if (parte.startsWith("**") && parte.endsWith("**") && parte.length > 4) pai.append(el("strong", parte.slice(2, -2)));
    else if (parte.startsWith("`") && parte.endsWith("`") && parte.length > 2) pai.append(el("code", parte.slice(1, -1)));
    else pai.append(document.createTextNode(parte));
  }
}

export function renderTexto(alvo, texto) {
  const frag = document.createDocumentFragment();
  let par = null;
  let lista = null;
  for (const bruta of String(texto ?? "").split("\n")) {
    const linha = bruta.trim();
    const item = /^[-*•]\s+(.*)$/.exec(linha) || /^\d+[.)]\s+(.*)$/.exec(linha);
    const ordenada = /^\d+[.)]\s/.test(linha);
    if (!linha) { par = null; lista = null; continue; }
    if (item) {
      par = null;
      if (lista && lista.tagName !== (ordenada ? "OL" : "UL")) lista = null;
      if (!lista) { lista = el(ordenada ? "ol" : "ul"); frag.append(lista); }
      const li = el("li");
      inline(li, item[1]);
      lista.append(li);
      continue;
    }
    lista = null;
    const t = linha.replace(/^#{1,4}\s+/, "");
    if (!par) { par = el("p"); frag.append(par); } else par.append(document.createTextNode(" "));
    if (t !== linha) { par.append(el("strong", t)); par = null; continue; }
    inline(par, t);
  }
  alvo.replaceChildren(frag);
}

export const reduzMovimento = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
