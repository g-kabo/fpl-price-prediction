// Plotly figures for the pages, built for the light surface only.
//
// Colours and type come from theme.js, so a chart is drawn in the same
// vocabulary as the page around it. Plotly is loaded by the page as a global.

import { fixed, seasonLabel } from "./format.js";
import {
  AUBERGINE, FALL, FONT, FONT_FIGURES, INK, INK_SOFT, LINE, POSITION_COLOURS,
  POSITION_SYMBOLS, RISE, SURFACE, money,
} from "./theme.js";

// Price history: one hue at two lightnesses for the two ends of a season,
// because they are the same measurement taken twice, and a different hue for
// the forecast, because it is a different kind of number.
const PRICE_START = "#c3a6cf";
const PRICE_FINAL = "#5a1f6b";
const PRICE_FORECAST = "#0091a8";

// Marker diameter in px, fixed for every view: a mark that changes size when
// a filter changes reads as an encoding when it means nothing of the kind.
const MARK_SIZE = 16;
const MARK_RING = 1.5;

/** What a current price can be. Against today's price the question is "is
 *  the model repricing him from where he is now?"; against August it is the
 *  like-for-like reading, since the forecast is itself a start price. */
export const X_FIELDS = { price_now: "Price today", start_cost: "Start price (August)" };
export const DEFAULT_X = "price_now";

const HOVER = {
  bgcolor: AUBERGINE, bordercolor: AUBERGINE,
  font: { family: FONT, size: 13, color: "#ffffff" }, align: "left",
};

const CONFIG = { displayModeBar: false, responsive: true };

function baseLayout(extra) {
  return {
    plot_bgcolor: SURFACE, paper_bgcolor: SURFACE,
    font: { family: FONT, color: INK, size: 13 },
    hoverlabel: HOVER, showlegend: false, ...extra,
  };
}

function draw(el, data, layout) {
  Plotly.react(el, data, layout, CONFIG);
}

/** One player's price at each end of every season, plus what is coming.
 *  `seasons` is [[season, start, final], ...]. Clustered rather than stacked:
 *  a start and a finishing price are two readings of the same thing. */
export function drawPriceHistory(el, seasons, forecastSeason, forecastPrice) {
  const labels = [...seasons.map(([s]) => seasonLabel(s)), seasonLabel(forecastSeason)];
  const starts = [...seasons.map((s) => s[1]), null];
  const finals = [...seasons.map((s) => s[2]), null];
  const forecast = [...seasons.map(() => null), forecastPrice];

  const traces = [["Start", starts, PRICE_START], ["End", finals, PRICE_FINAL],
    ["Forecast", forecast, PRICE_FORECAST]].map(([name, values, colour]) => ({
    type: "bar", name, x: labels, y: values,
    marker: { color: colour, line: { width: 0 } },
    text: values.map((v) => (v === null || v === undefined ? "" : v.toFixed(1))),
    textposition: "outside",
    textfont: { size: 12, color: INK_SOFT, family: FONT_FIGURES },
    cliponaxis: false,
    hovertemplate: `<b>%{x}</b><br>${name} £%{y:.1f}m<extra></extra>`,
  }));

  draw(el, traces, baseLayout({
    barmode: "group", bargap: 0.28, bargroupgap: 0.06,
    margin: { l: 8, r: 8, t: 30, b: 8 }, height: 230, showlegend: true,
    legend: { orientation: "h", yanchor: "bottom", y: 1.02, xanchor: "left", x: 0,
      font: { size: 12, color: INK_SOFT }, itemsizing: "constant" },
    xaxis: { tickfont: { size: 12, color: INK_SOFT }, showgrid: false, showline: true,
      linecolor: LINE, automargin: true },
    yaxis: { visible: false, rangemode: "tozero" },
  }));
}

/** Per-term contributions to one price, as a running total, sideways.
 *
 *  A waterfall: the model is linear, so the contributions sum to the
 *  prediction exactly, and the bridge from baseline to price is the thing
 *  worth seeing. Anchors are neutral -- the baseline and the total are not
 *  movements -- and `reference` draws the price he is already on as a dashed
 *  line, so the gap between it and the final bar is the predicted move.
 *  Drawn as floating bars (a `base` per bar) rather than Plotly's waterfall
 *  trace, which the lighter Plotly build the site loads does not include. */
export function drawContributionBars(el, steps, reference = null) {
  const labels = steps.map(([label]) => label);
  const amounts = steps.map(([, amount]) => amount);
  const measures = steps.map(([, , measure]) => measure);

  const lengths = [];
  const bases = [];
  const colours = [];
  const detail = [];
  const ends = [];
  let running = 0;
  steps.forEach(([, amount, measure]) => {
    if (measure === "relative") {
      bases.push(running);
      lengths.push(amount);
      running += amount;
      colours.push(amount >= 0 ? RISE : FALL);
      detail.push(`${money(amount, true, 2)} · running total £${fixed(running, 2)}m`);
    } else {
      running = amount;
      bases.push(0);
      lengths.push(amount);
      colours.push(AUBERGINE);
      detail.push(`£${fixed(amount, 2)}m`);
    }
    ends.push(running);
  });

  const text = amounts.map((amount, i) => (measures[i] !== "relative"
    ? `£${fixed(amount, 2)}m`
    : Math.abs(amount) < 0.005 ? "~0" : money(amount, true, 2)));

  const shapes = [];
  // Faint banding on alternate rows, so a value in the right-hand column
  // reads across to its own bar.
  for (let i = 0; i < labels.length; i += 2) {
    shapes.push({ type: "rect", xref: "paper", x0: 0, x1: 1, yref: "y", y0: i - 0.5, y1: i + 0.5,
      layer: "below", fillcolor: "#f7f3f9", line: { width: 0 } });
  }
  // Connectors: from the end of one bar to the start of the next.
  for (let i = 0; i < labels.length - 1; i++) {
    shapes.push({ type: "line", xref: "x", yref: "y", x0: ends[i], x1: ends[i],
      y0: i + 0.325, y1: i + 1 - 0.325, layer: "below", line: { color: "#cbbfd2", width: 1 } });
  }

  // Values in a column of their own at the right edge, rather than at the end
  // of each bar: there, the reference line runs straight through the labels
  // of every bar that finishes near it, which is most of them.
  const annotations = labels.map((label, i) => ({
    x: 1.0, xref: "paper", xanchor: "left", xshift: 10, y: label, yref: "y",
    text: measures[i] !== "relative" ? `<b>${text[i]}</b>` : text[i],
    showarrow: false, align: "left",
    font: { size: 13, family: FONT_FIGURES, color: measures[i] !== "relative" ? INK : INK_SOFT },
  }));

  if (reference && reference[1] !== null && Number.isFinite(reference[1])) {
    const [label, price] = reference;
    shapes.push({ type: "line", xref: "x", yref: "paper", x0: price, x1: price, y0: 0, y1: 1,
      layer: "below", line: { color: INK_SOFT, width: 1.5, dash: "dash" } });
    annotations.push({ x: price, xref: "x", y: 1, yref: "paper", yanchor: "bottom",
      text: `${label} £${price.toFixed(1)}m`, showarrow: false,
      font: { size: 12, color: INK_SOFT } });
  }

  const trace = {
    type: "bar", orientation: "h", y: labels, x: lengths, base: bases,
    marker: { color: colours, line: { width: 0 } }, customdata: detail,
    hovertemplate: "<b>%{y}</b><br>%{customdata}<extra></extra>", textposition: "none",
  };

  draw(el, [trace], baseLayout({
    margin: { l: 8, r: 78, t: 28, b: 8 }, height: 34 * steps.length + 60, bargap: 0.35,
    shapes, annotations,
    yaxis: { autorange: "reversed", tickfont: { size: 13, color: INK }, showgrid: false,
      automargin: true, ticksuffix: "  " },
    xaxis: { tickprefix: "£", ticksuffix: "m", tickfont: { size: 12, color: INK_SOFT },
      gridcolor: LINE, zeroline: true, zerolinecolor: "#cbbfd2", automargin: true },
  }));
}

function axis(title, bounds) {
  return {
    title: { text: title, font: { size: 13, color: INK_SOFT } },
    range: bounds, tickprefix: "£", ticksuffix: "m", tickfont: { size: 12, color: INK_SOFT },
    gridcolor: LINE, zeroline: false, showline: true, linecolor: LINE, constrain: "domain",
    automargin: true,
  };
}

/** A current price against the predicted one, one mark per player.
 *
 *  The dashed diagonal is the line of no change: above it the model wants
 *  him dearer, below it cheaper, and distance from it is the size of the
 *  call. Position is encoded in hue *and* marker shape, so colour is never
 *  the only cue. Every mark carries the player's code, so a click can open
 *  his card (`onPick(code)`). */
export function drawPriceScatter(el, rows, targetSeason, xField, positions, onPick) {
  xField = xField in X_FIELDS ? xField : DEFAULT_X;
  rows = rows.filter((r) => Number.isFinite(r[xField]) && Number.isFinite(r.pred));

  const span = rows.flatMap((r) => [r[xField], r.pred]);
  const spread = span.length ? Math.max(...span) - Math.min(...span) : 0;
  const pad = span.length ? Math.max(0.35, spread * 0.04) : 0.35;
  const bounds = span.length ? [Math.min(...span) - pad, Math.max(...span) + pad] : [0, 1];

  const traces = [{
    type: "scatter", mode: "lines", x: bounds, y: bounds, hoverinfo: "skip", showlegend: false,
    name: "no change", line: { color: INK_SOFT, width: 1.2, dash: "dash" },
  }];

  // Biggest group first, so the smallest lands on top rather than buried.
  const groups = positions.map((position) => [position, rows.filter((r) => r.element_type === position)]);
  groups.sort((a, b) => b[1].length - a[1].length);
  const reference = X_FIELDS[xField].split(" (")[0].toLowerCase();
  for (const [position, group] of groups) {
    if (!group.length) continue;
    traces.push({
      type: "scatter", mode: "markers", name: position, legendrank: positions.indexOf(position),
      x: group.map((r) => r[xField]), y: group.map((r) => r.pred),
      marker: { color: POSITION_COLOURS[position], symbol: POSITION_SYMBOLS[position],
        size: MARK_SIZE, opacity: 0.85, line: { width: MARK_RING, color: SURFACE } },
      customdata: group.map((r) => [r.web_name, r.team_name, r.element_type, r.code]),
      hovertemplate: "<b>%{customdata[0]}</b> · %{customdata[1]}<br>"
        + `${reference} £%{x:.1f}m → £%{y:.1f}m<br><i>click to open</i><extra></extra>`,
    });
  }

  const corner = bounds[1] - (bounds[1] - bounds[0]) * 0.02;
  draw(el, traces, baseLayout({
    margin: { l: 8, r: 16, t: 40, b: 8 }, height: 460, hovermode: "closest", showlegend: true,
    legend: { orientation: "h", yanchor: "bottom", y: 1.01, xanchor: "left", x: 0,
      font: { size: 13, color: INK }, itemsizing: "constant" },
    xaxis: axis(X_FIELDS[xField], bounds),
    yaxis: axis(`Predicted ${seasonLabel(targetSeason)} price`, bounds),
    annotations: [{ x: corner, y: corner, text: "no change", showarrow: false, xanchor: "right",
      yanchor: "top", yshift: -12, xshift: -4, font: { size: 12, color: INK_SOFT } }],
  }));

  if (!el.dataset.clickBound) {
    el.dataset.clickBound = "1";
    el.on("plotly_click", (event) => {
      const custom = event.points?.[0]?.customdata;
      if (custom) onPick(Number(custom[3]));
    });
  }
}
