// Marcas de último/máx./mín. da tendência. Fora de graficos.js para poder ser testada sem DOM.
import { fmtValor } from "./dom.js";

export function marcas(xs, valores, t, coluna) {
  const ok = valores.map((v, i) => [v, i]).filter(([v]) => v !== null);
  if (!ok.length) return [];
  const ultimo = ok[ok.length - 1][1];
  const maior = ok.reduce((a, b) => (b[0] > a[0] ? b : a))[1];
  const menor = ok.reduce((a, b) => (b[0] < a[0] ? b : a))[1];
  const ponto = (i, rotulo, pos) => ({
    // índice, não xs[i]: no eixo de categoria do ECharts uma coord numérica é lida como índice (x = mês 1..12, ano)
    coord: [i, valores[i]], value: valores[i],
    label: { show: true, position: pos, formatter: () => `${rotulo}${fmtValor(valores[i], coluna)}`, color: t.ink, fontWeight: 700, fontSize: 12, distance: 6 },
  });
  const out = [ponto(ultimo, "", "right")];
  if (maior !== ultimo) out.push(ponto(maior, "máx. ", "top"));
  if (menor !== ultimo && menor !== maior) out.push(ponto(menor, "mín. ", "bottom"));
  return out;
}
