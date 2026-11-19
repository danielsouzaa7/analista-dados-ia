// Gráficos (Apache ECharts) com tema próprio tirado das variáveis CSS --viz-*.
// Opções montadas só com valores primitivos; todo texto que o ECharts renderiza como HTML passa por esc().
import { el, esc, fmtNum, fmtCompacto, fmtValor, fmtPct, botao, fmtCelula, reduzMovimento } from "./dom.js";
import { marcas } from "./marcas.js";

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const MESES_LONGO = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const LARGURA_ESTREITA = 520;
const MAX_LINHAS_TABELA = 200;

// ---------- tema ----------
function tokens() {
  const cs = getComputedStyle(document.documentElement);
  const v = (n) => cs.getPropertyValue(n).trim();
  const lista = (p, n) => Array.from({ length: n }, (_, i) => v(`--viz-${p}${i + 1}`));
  return {
    ink: v("--viz-ink"), ink2: v("--viz-ink2"), muted: v("--viz-muted"), grid: v("--viz-grid"), axis: v("--viz-axis"),
    surface: v("--viz-surface"), acc: v("--viz-acc"), tint: v("--viz-tint"), outros: v("--viz-outros"),
    s: lista("s", 4), r: lista("r", 6), h: lista("h", 6), font: v("--viz-font") || "system-ui, sans-serif",
  };
}

function hexA(hex, a) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

const semHover = () => matchMedia("(hover: none)").matches;
const cortar = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1) + "…" : String(s));
const fmtV = (v, max, coluna) => (Math.abs(max) >= 1e6 ? fmtValor(v, coluna, true) : fmtValor(v, coluna));

function rotuloData(x, longo) {
  const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(String(x));
  const nome = m && MESES[Number(m[2]) - 1];
  if (!nome) return String(x);
  const [, ano, mes, dia] = m;
  if (!dia) return longo ? `${MESES_LONGO[Number(mes) - 1]} de ${ano}` : `${nome}/${ano.slice(2)}`;
  return longo ? `${Number(dia)} de ${nome} de ${ano}` : `${Number(dia)} ${nome}`;
}

function base(t, spec) {
  const animar = !reduzMovimento();
  return {
    animation: animar, animationDuration: animar ? 800 : 0, animationEasing: "cubicOut",
    textStyle: { fontFamily: t.font, color: t.ink2 },
    aria: { enabled: true, label: { description: spec.resumo || spec.titulo || "" } },
    tooltip: {
      confine: true, triggerOn: semHover() ? "click" : "mousemove|click",
      backgroundColor: t.surface, borderColor: t.axis, borderWidth: 1, padding: [8, 10],
      textStyle: { color: t.ink, fontFamily: t.font, fontSize: 13 },
      extraCssText: "border-radius:10px;box-shadow:none;",
    },
  };
}

// ---------- os 5 tipos ----------
function ranking(spec, t, larg) {
  const d = spec.dados || [];
  const max = Math.max(0, ...d.map((x) => x.valor || 0));
  const dados = d.map((x, i) => ({
    value: x.valor,
    itemStyle: { color: x.rotulo === "Outros" ? t.outros : i === 0 ? t.acc : t.tint, borderRadius: [0, 6, 6, 0] },
    label: i === 0 ? { fontWeight: 800 } : {},
  }));
  return {
    ...base(t, spec),
    grid: { left: 4, right: 64, top: 4, bottom: 4, containLabel: true },
    xAxis: { type: "value", show: false, max: "dataMax" },
    yAxis: {
      type: "category", inverse: true, data: d.map((x) => String(x.rotulo)), axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: t.ink2, fontSize: 12, interval: 0, width: Math.min(160, Math.round(larg * 0.38)), overflow: "truncate" },
    },
    tooltip: {
      ...base(t, spec).tooltip, trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: hexA(t.ink, 0.06) } },
      formatter: (ps) => `${esc(ps[0].name)}<br><b>${esc(fmtValor(ps[0].value, spec.y_nome))}</b> ${esc(spec.y_nome || "")}`,
    },
    series: [{
      type: "bar", data: dados, barWidth: 12,
      label: { show: true, position: "right", color: t.ink, fontSize: 12, fontWeight: 600, formatter: (p) => fmtV(p.value, max, spec.y_nome) },
    }],
  };
}

function agruparSeries(pontos) {
  const xs = [];
  const vistos = new Set();
  const porSerie = new Map();
  for (const p of pontos) {
    if (!vistos.has(p.x)) { vistos.add(p.x); xs.push(p.x); }
    const nome = p.serie ?? "";
    if (!porSerie.has(nome)) porSerie.set(nome, new Map());
    porSerie.get(nome).set(p.x, p.valor);
  }
  return { xs, series: [...porSerie.entries()].slice(0, 4).map(([nome, m]) => ({ nome, valores: xs.map((x) => (Number.isFinite(m.get(x)) ? m.get(x) : null)) })) };
}

function tendencia(spec, t, larg) {
  const { xs, series } = agruparSeries(spec.dados || []);
  const unica = series.length <= 1;
  const todos = series.flatMap((s) => s.valores).filter((v) => v !== null);
  const max = Math.max(0, ...todos);
  const serieEc = series.map((s, i) => {
    const cor = t.s[i];
    const area = unica
      ? { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: hexA(cor, 0.34) }, { offset: 1, color: hexA(cor, 0.02) }] } }
      : { color: hexA(cor, 0.06) };
    return {
      name: s.nome || spec.y_nome || "valor", type: "line", data: s.valores, smooth: 0.15, showSymbol: false, symbolSize: 8,
      lineStyle: { width: 2.5, color: cor }, itemStyle: { color: cor, borderColor: t.surface, borderWidth: 2 }, areaStyle: area,
      emphasis: { focus: "none" },
      markPoint: unica ? { symbol: "circle", symbolSize: 10, itemStyle: { color: cor, borderColor: t.surface, borderWidth: 2 }, data: marcas(xs, s.valores, t, spec.y_nome), animation: false } : undefined,
    };
  });
  return {
    ...base(t, spec),
    legend: unica ? { show: false } : { top: 0, left: 0, icon: "roundRect", itemWidth: 14, itemHeight: 5, textStyle: { color: t.ink2, fontSize: 12 }, data: serieEc.map((s) => s.name) },
    grid: { left: 4, right: unica ? 64 : 30, top: unica ? 28 : 40, bottom: 4, containLabel: true },
    xAxis: {
      type: "category", data: xs, boundaryGap: false, axisTick: { show: false }, axisLine: { lineStyle: { color: t.axis } },
      axisLabel: { color: t.muted, fontSize: 11, hideOverlap: true, formatter: (x) => rotuloData(x, false) },
      axisPointer: { lineStyle: { color: t.axis } },
    },
    yAxis: {
      type: "value", min: (e) => Math.min(0, e.min), axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: t.grid } },
      axisLabel: { color: t.muted, fontSize: 11, formatter: (v) => fmtValor(v, spec.y_nome, true) },
    },
    tooltip: {
      ...base(t, spec).tooltip, trigger: "axis", axisPointer: { type: "line", lineStyle: { color: t.axis } },
      formatter: (ps) => `${esc(rotuloData(ps[0].axisValue, true))}` + ps.map((p) => `<br>${p.marker} ${esc(p.seriesName)}: <b>${esc(fmtV(p.value, max, spec.y_nome))}</b>`).join(""),
    },
    series: serieEc,
  };
}

function composicao(spec, t, larg) {
  const d = spec.dados || [];
  const total = d.reduce((s, x) => s + (Number.isFinite(x.valor) ? x.valor : 0), 0);
  const estreito = larg < LARGURA_ESTREITA;
  const pct = (v) => (total > 0 ? (v / total) * 100 : 0);
  const dados = d.map((x, i) => ({
    name: String(x.rotulo), value: x.valor,
    itemStyle: { color: x.rotulo === "Outros" ? t.outros : t.r[Math.min(i, t.r.length - 1)] },
  }));
  return {
    ...base(t, spec),
    tooltip: {
      ...base(t, spec).tooltip, trigger: "item",
      formatter: (p) => `${esc(p.name)}<br><b>${esc(fmtValor(p.value, spec.y_nome))}</b> · ${esc(fmtPct(pct(p.value), 1))}`,
    },
    graphic: [{
      type: "text", left: "center", top: "center", silent: true,
      style: { text: `{a|${fmtValor(total, spec.y_nome, true)}}\n{b|total}`, textAlign: "center", rich: { a: { fontSize: estreito ? 22 : 26, fontWeight: 800, fill: t.ink, fontFamily: t.font, lineHeight: 30 }, b: { fontSize: 12, fill: t.muted, fontFamily: t.font } } },
    }],
    series: [{
      type: "pie", radius: estreito ? ["56%", "86%"] : ["48%", "70%"], center: ["50%", "50%"], startAngle: 90, minAngle: 3,
      itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 5 },
      label: estreito
        ? { show: false }
        : { show: true, color: t.ink, fontSize: 12, lineHeight: 16, formatter: (p) => `${cortar(p.name, 18)}\n${fmtPct(pct(p.value), 1)}` },
      labelLine: { show: !estreito, length: 12, length2: 10, lineStyle: { color: t.axis } },
      labelLayout: { hideOverlap: true },
      data: dados, emphasis: { scaleSize: 4 },
    }],
  };
}

function mapaCalor(spec, t) {
  const { xs = [], ys = [], celulas = [] } = spec.dados || {};
  const validas = celulas.filter((c) => Number.isFinite(c[2]));
  const vals = validas.map((c) => c[2]);
  const min = vals.length ? Math.min(...vals) : 0;
  const max = vals.length ? Math.max(...vals) : 1;
  const passo = (max - min || 1) / t.h.length;
  const pieces = t.h.map((cor, i) => (i === t.h.length - 1
    ? { gte: min + passo * i, lte: max, color: cor }
    : { gte: min + passo * i, lt: min + passo * (i + 1), color: cor }));
  return {
    ...base(t, spec),
    grid: { left: 4, right: 8, top: 6, bottom: 58, containLabel: true },
    xAxis: { type: "category", data: xs.map(String), splitArea: { show: false }, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: t.muted, fontSize: 11, hideOverlap: true } },
    yAxis: { type: "category", data: ys.map(String), inverse: true, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: t.muted, fontSize: 11, interval: 0, hideOverlap: true } },
    visualMap: {
      type: "piecewise", pieces, orient: "horizontal", left: "center", bottom: 4, itemWidth: 22, itemHeight: 12, itemGap: 3, itemSymbol: "roundRect",
      text: [fmtCompacto(max), fmtCompacto(min)], textGap: 8, textStyle: { color: t.ink2, fontSize: 12 }, inRange: {}, selectedMode: false,
    },
    tooltip: {
      ...base(t, spec).tooltip, trigger: "item",
      formatter: (p) => `${esc(xs[p.value[0]])} · ${esc(ys[p.value[1]])}<br><b>${esc(fmtNum(p.value[2]))}</b>`,
    },
    series: [{
      type: "heatmap", data: validas, progressive: 0,
      itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 4 },
      emphasis: { itemStyle: { borderColor: t.ink, borderWidth: 1.5 } },
    }],
  };
}

function dispersao(spec, t) {
  const { pontos = [], tendencia: reta } = spec.dados || {};
  const xv = pontos.map((p) => p[0]);
  const x0 = Math.min(...xv);
  const x1 = Math.max(...xv);
  const series = [{
    type: "scatter", data: pontos, symbolSize: 8,
    itemStyle: { color: hexA(t.acc, 0.32), borderColor: hexA(t.acc, 0.85), borderWidth: 1 },
    emphasis: { itemStyle: { color: t.acc, borderColor: t.ink, borderWidth: 1.5 } },
  }];
  if (reta && Number.isFinite(reta.a) && Number.isFinite(reta.b) && pontos.length > 1) {
    series.push({
      type: "line", data: [[x0, reta.a * x0 + reta.b], [x1, reta.a * x1 + reta.b]], showSymbol: false, silent: true, tooltip: { show: false },
      lineStyle: { color: t.ink, width: 2.5 }, z: 5,
      endLabel: { show: true, formatter: "tendência", color: t.ink2, fontSize: 12, distance: 6 },
    });
  }
  const eixo = (nome, gap, rot) => ({
    type: "value", scale: true, name: cortar(nome || "", 28), nameLocation: "middle", nameGap: gap, nameRotate: rot,
    nameTextStyle: { color: t.ink2, fontSize: 12 }, axisLine: { show: false }, axisTick: { show: false },
    splitLine: { lineStyle: { color: t.grid } }, axisLabel: { color: t.muted, fontSize: 11, formatter: (v) => fmtValor(v, nome, true) },
  });
  return {
    ...base(t, spec),
    grid: { left: 58, right: 70, top: 10, bottom: 46 },
    xAxis: eixo(spec.x_nome, 30, 0),
    yAxis: eixo(spec.y_nome, 44, 90),
    tooltip: {
      ...base(t, spec).tooltip, trigger: "item",
      formatter: (p) => `${esc(spec.x_nome || "x")}: <b>${esc(fmtValor(p.value[0], spec.x_nome))}</b><br>${esc(spec.y_nome || "y")}: <b>${esc(fmtValor(p.value[1], spec.y_nome))}</b>`,
    },
    series,
  };
}

const TIPOS = {
  ranking: { build: ranking, altura: (s) => Math.max(170, 40 + (s.dados || []).length * 30) },
  tendencia: { build: tendencia, altura: () => 300 },
  composicao: { build: composicao, altura: () => 300 },
  mapa_calor: { build: mapaCalor, altura: (s) => Math.min(620, Math.max(260, ((s.dados || {}).ys || []).length * 21 + 120)) },
  dispersao: { build: dispersao, altura: () => 340 },
};

// ---------- tabela alternativa ----------
function dadosDaTabela(spec) {
  const d = spec.dados;
  const xn = spec.x_nome || "x";
  const yn = spec.y_nome || "valor";
  switch (spec.tipo) {
    case "ranking": case "composicao":
      return { colunas: [xn, yn], linhas: (d || []).map((r) => [r.rotulo, r.valor]) };
    case "tendencia": {
      const comSerie = (d || []).some((r) => r.serie);
      return { colunas: comSerie ? [xn, "série", yn] : [xn, yn], linhas: (d || []).map((r) => (comSerie ? [r.x, r.serie ?? "", r.valor] : [r.x, r.valor])) };
    }
    case "mapa_calor":
      return { colunas: [xn, yn, "valor"], linhas: ((d || {}).celulas || []).map((c) => [d.xs[c[0]], d.ys[c[1]], c[2]]) };
    default:
      return { colunas: [xn, yn], linhas: ((d || {}).pontos || []) };
  }
}

function montarTabela(spec) {
  const { colunas, linhas } = dadosDaTabela(spec);
  const wrap = el("div", null, "tabela-wrap", { tabindex: "0", role: "region", "aria-label": `Dados do gráfico: ${spec.titulo || ""}` });
  const tb = el("table", null, "tabela");
  const cab = el("tr");
  colunas.forEach((c) => cab.append(el("th", c, null, { scope: "col" })));
  const cabeca = el("thead");
  cabeca.append(cab);
  tb.append(cabeca);
  const corpo = el("tbody");
  linhas.slice(0, MAX_LINHAS_TABELA).forEach((l) => {
    const tr = el("tr");
    l.forEach((v, i) => tr.append(el("td", fmtCelula(v, colunas[i]), typeof v === "number" ? "num" : null)));
    corpo.append(tr);
  });
  tb.append(corpo);
  wrap.append(tb);
  const frag = el("div");
  frag.append(wrap);
  if (linhas.length > MAX_LINHAS_TABELA) frag.append(el("p", `Mostrando ${MAX_LINHAS_TABELA} de ${fmtNum(linhas.length)} linhas.`, "nota"));
  return frag;
}

function subtituloCom(spec) {
  const r = spec.dados && spec.dados.tendencia && spec.dados.tendencia.r;
  if (spec.tipo !== "dispersao" || !Number.isFinite(r)) return spec.subtitulo || "";
  const forca = Math.abs(r) < 0.3 ? "fraca" : Math.abs(r) < 0.6 ? "moderada" : "forte";
  const sinal = r < 0 ? "negativa" : "positiva";
  const rTxt = `r = ${fmtNum(r)} (${sinal}, ${forca})`;
  return spec.subtitulo ? `${spec.subtitulo} · ${rTxt}` : rTxt;
}

// ---------- registro, tema e resize ----------
const REGISTRO = new Set();
const POR_ELEMENTO = new WeakMap();

function descartar(item) {
  if (item.chart) item.chart.dispose();
  item.chart = null;
  REGISTRO.delete(item);
  ro.unobserve(item.area);
}

function legendaComposicao(item, t) {
  const caixa = item.extra;
  if (!caixa) return;
  caixa.replaceChildren();
  if (item.larg >= LARGURA_ESTREITA) { caixa.hidden = true; return; }
  const d = item.spec.dados || [];
  const total = d.reduce((s, x) => s + (Number.isFinite(x.valor) ? x.valor : 0), 0);
  const ul = el("ul", null, "lista-composicao");
  d.forEach((x, i) => {
    const li = el("li");
    const marca = el("span", null, "marca");
    marca.style.background = x.rotulo === "Outros" ? t.outros : t.r[Math.min(i, t.r.length - 1)];
    li.append(marca, el("span", String(x.rotulo), "nome"), el("span", total > 0 ? fmtPct((x.valor / total) * 100, 1) : "–", "valor"));
    ul.append(li);
  });
  caixa.append(ul);
  caixa.hidden = false;
}

function montar(item) {
  if (!item.area.isConnected) return;
  const larg = item.area.clientWidth;
  if (!larg || !window.echarts) return;
  const t = tokens();
  if (!item.chart) item.chart = window.echarts.init(item.area, null, { renderer: "canvas" });
  item.larg = larg;
  item.chart.setOption(TIPOS[item.spec.tipo].build(item.spec, t, larg), true);
  if (item.spec.tipo === "composicao") legendaComposicao(item, t);
}

const ro = new ResizeObserver((entradas) => {
  for (const e of entradas) {
    const item = POR_ELEMENTO.get(e.target);
    if (!item) continue;
    if (!e.target.isConnected) { descartar(item); continue; }
    if (!item.chart) { montar(item); continue; }
    item.chart.resize();
    if ((e.contentRect.width < LARGURA_ESTREITA) !== (item.larg < LARGURA_ESTREITA)) montar(item);
  }
});

function remontarTodos() {
  for (const item of [...REGISTRO]) {
    if (!item.area.isConnected) descartar(item);
    else montar(item);
  }
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", remontarTodos);
new MutationObserver(remontarTodos).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
if (document.fonts && document.fonts.ready) document.fonts.ready.then(remontarTodos);

// ---------- API ----------
/** Devolve um <figure> com o gráfico do contrato. Texto vem do servidor: só textContent. */
export function desenharGrafico(spec) {
  const fig = el("figure", null, "grafico");
  if (!spec || !TIPOS[spec.tipo]) {
    fig.append(el("p", "Não consegui desenhar este gráfico.", "erro-texto"));
    return fig;
  }
  const idTab = `tab-${Math.random().toString(36).slice(2, 9)}`;
  const cap = el("figcaption", null, "grafico-cab");
  cap.append(el("h4", spec.titulo || "Gráfico", "grafico-titulo"));
  const sub = subtituloCom(spec);
  if (sub) cap.append(el("p", sub, "grafico-sub"));
  fig.append(cap);

  const area = el("div", null, "grafico-area", { role: "img", "aria-label": spec.resumo || spec.titulo || "Gráfico" });
  area.style.height = `${TIPOS[spec.tipo].altura(spec)}px`;
  fig.append(area);
  const extra = spec.tipo === "composicao" ? el("div", null, "grafico-extra") : null;
  if (extra) fig.append(extra);
  if (spec.resumo) fig.append(el("p", spec.resumo, "grafico-resumo"));

  const tab = el("div", null, "grafico-tabela", { id: idTab });
  tab.hidden = true;
  const b = botao("Ver tabela", "btn-texto", null, "tabela");
  b.setAttribute("aria-expanded", "false");
  b.setAttribute("aria-controls", idTab);
  const alternar = (abrir) => {
    if (abrir && !tab.firstChild) tab.append(montarTabela(spec));
    tab.hidden = !abrir;
    b.setAttribute("aria-expanded", String(abrir));
    b.lastChild.textContent = abrir ? "Ocultar tabela" : "Ver tabela";
  };
  b.addEventListener("click", () => alternar(tab.hidden));
  fig.append(el("div", null, "grafico-acoes"), tab);
  fig.querySelector(".grafico-acoes").append(b);

  if (!window.echarts) {
    area.replaceChildren(el("p", "Não consegui carregar a biblioteca de gráficos. Veja os dados na tabela.", "erro-texto"));
    area.style.height = "auto";
    alternar(true);
    return fig;
  }
  const item = { spec, area, extra, chart: null, larg: 0 };
  REGISTRO.add(item);
  POR_ELEMENTO.set(area, item);
  ro.observe(area);
  return fig;
}
