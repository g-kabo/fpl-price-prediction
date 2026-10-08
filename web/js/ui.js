// Rendering shared by every page: shirts, pills, price tags, the answer.
//
// Each function returns an HTML string. Anything that came from the data
// (names, clubs) goes through esc(); everything else is built here.

import { dayMonth, esc, fmt, pyRound } from "./format.js";
import { direction, money, shirtUri } from "./theme.js";
import { drawContributionBars } from "./charts.js";

// ---------------------------------------------------------------- atoms

export function shirt(team, size = "md") {
  return `<img src="${shirtUri(team)}" alt="${esc(team || "Unknown club")} shirt" `
    + `class="shirt shirt-${size}">`;
}

export function positionPill(position) {
  const p = position || "?";
  return `<span class="pos-pill pos-${esc(p.toLowerCase())}">${esc(p)}</span>`;
}

const ICONS = { rise: "bi-caret-up-fill", fall: "bi-caret-down-fill", hold: "bi-dash" };

/** The predicted move as a filled chip: +£0.6m, −£0.4m, or holds. */
export function deltaChip(delta, size = "md") {
  const way = direction(delta);
  const text = way === "hold" ? "Holds" : money(delta, true);
  return `<span class="delta delta-${way} delta-${size}"><i class="bi ${ICONS[way]}"></i>${text}</span>`;
}

/** A change in a forecast, to the penny of a £m: +£0.04m.
 *
 *  Not deltaChip, whose £0.1m threshold is about whether a price is moving
 *  at all. Day to day a forecast shifts by hundredths, and a forecast movers
 *  list of "Holds" would say nothing. */
export function changeChip(change, size = "sm") {
  const way = pyRound(change, 2) === 0 ? "hold" : change > 0 ? "rise" : "fall";
  return `<span class="delta delta-${way} delta-${size}"><i class="bi ${ICONS[way]}"></i>`
    + `${money(change, true, 2)}</span>`;
}

export function empty(message, icon = "bi-search") {
  return `<div class="empty"><i class="bi ${icon}"></i><p>${esc(message)}</p></div>`;
}

// ---------------------------------------------------------------- the answer

// Range bar geometry, in px: one line of labels, the track's height, and the
// gap between the track and the first line of labels under it.
const ROW = 22;
const TRACK = 14;
const BELOW_GAP = 6;

// Labels closer than this (in % of the bar) would overlap, so the later one
// moves to another line.
const CROWDED = 30.0;

/** A line for each label, in order: the nearest line it fits on. */
function rowsFor(positions) {
  const placed = [];
  return positions.map((x) => {
    let row = placed.findIndex((line) => line.every((other) => Math.abs(x - other) >= CROWDED));
    if (row === -1) {
      row = placed.length;
      placed.push([]);
    }
    placed[row].push(x);
    return row;
  });
}

/** The likely range drawn, with the prediction and the prices around it.
 *
 * Above the track: the prediction and, optionally, the reference price.
 * Below it: the range's two ends and, optionally, `actual`, the price FPL
 * really set -- an outcome rather than an input, so it gets its own mark (a
 * diamond) and its own side. The span is padded so a price just outside the
 * range still lands on the bar, and labels take the nearest line they fit on,
 * so a crowded bar grows taller instead of overprinting. */
export function rangeBar(lower, upper, pred, reference, referenceLabel, actual = null) {
  const points = [lower, upper, pred, ...[reference, actual].filter((v) => v !== null && v !== undefined)];
  let low = Math.min(...points);
  let high = Math.max(...points);
  const pad = Math.max((high - low) * 0.12, 0.1);
  low -= pad;
  high += pad;
  const pct = (value) => ((value - low) / (high - low)) * 100;

  const above = [{ text: `Predicted <strong>${money(pred)}</strong>`, value: pred, extra: "rl-pred", tick: null }];
  if (reference !== null && reference !== undefined) {
    above.push({ text: `${referenceLabel} ${money(reference)}`, value: reference, extra: "rl-ref", tick: "range-ref" });
  }
  const aboveRows = rowsFor(above.map((a) => pct(a.value)));
  const nAbove = Math.max(...aboveRows) + 1;
  const trackTop = 30 + (nAbove - 1) * ROW;

  const below = pct(upper) - pct(lower) < 18
    ? [{ text: `${money(lower)} – ${money(upper)}`, value: (lower + upper) / 2, extra: "", tick: null }]
    : [{ text: money(lower), value: lower, extra: "", tick: null },
       { text: money(upper), value: upper, extra: "", tick: null }];
  if (actual !== null && actual !== undefined) {
    below.push({ text: `FPL set <strong>${money(actual)}</strong>`, value: actual, extra: "rl-actual", tick: "range-actual-tick" });
  }
  const belowRows = rowsFor(below.map((b) => pct(b.value)));
  const nBelow = Math.max(...belowRows) + 1;

  const label = (item, top, belowTrack = false) => {
    const x = pct(item.value);
    const anchor = x < 10 ? "start" : x > 90 ? "end" : "mid";
    const kind = belowTrack ? "rl-below" : "rl-above";
    const cls = `rl ${kind} rl-${anchor} ${item.extra}`.trim();
    return `<span class="${cls}" style="left:${x.toFixed(1)}%;top:${top}px">${item.text}</span>`;
  };

  const labels = [];
  const marks = [
    `<div class="range-band" style="left:${pct(lower).toFixed(1)}%;width:${(pct(upper) - pct(lower)).toFixed(1)}%"></div>`,
    `<div class="range-pred" style="left:${pct(pred).toFixed(1)}%"></div>`,
  ];
  above.forEach((item, i) => {
    const row = aboveRows[i];
    labels.push(label(item, trackTop - 30 - row * ROW));
    if (item.tick) {
      const rise = row === 0 ? 14 : 6;
      marks.push(`<div class="${item.tick}" style="left:${pct(item.value).toFixed(1)}%;top:-${rise}px"></div>`);
    }
  });
  const firstBelow = trackTop + TRACK + BELOW_GAP;
  below.forEach((item, i) => {
    const row = belowRows[i];
    labels.push(label(item, firstBelow + row * ROW, true));
    if (item.tick) {
      marks.push(`<div class="${item.tick}" style="left:${pct(item.value).toFixed(1)}%;bottom:-${row === 0 ? 6 : 2}px"></div>`);
      marks.push(`<div class="range-actual" style="left:${pct(item.value).toFixed(1)}%"></div>`);
    }
  });

  let legend = '<span class="range-swatch"></span>95% likely range';
  if (actual !== null && actual !== undefined) {
    legend += '<span class="range-actual-key"></span>FPL\'s actual price';
  }
  return `<div class="range"><div class="range-scale" style="height:${firstBelow + nBelow * ROW}px">`
    + `${labels.join("")}<div class="range-track" style="top:${trackTop}px">${marks.join("")}</div></div>`
    + `<div class="range-legend">${legend}</div></div>`;
}

/** One plain sentence: which way, how far, and how sure. `against` reads
 *  mid-sentence: "today's price". */
export function verdict(delta, lower, upper, reference, against) {
  const way = direction(delta);
  let text;
  if (way === "rise") text = `The model would price him ${money(Math.abs(delta))} above ${against}.`;
  else if (way === "fall") text = `The model would price him ${money(Math.abs(delta))} below ${against}.`;
  else text = `The model would keep him at about ${against}.`;
  if (reference !== null && reference !== undefined && way !== "hold" && lower <= reference && reference <= upper) {
    text += ` Its likely range still includes ${against}, so treat the call as soft.`;
  }
  return text;
}

/** Next season's price as a price tag, with the move beside it. FPL prices
 *  move in tenths, so a headline of £6.43m is precision the game lacks. */
export function answerTag(model, interval, reference, targetLabel) {
  const grid = model.spec.price_grid;
  const onGrid = pyRound(interval.pred / grid, 0) * grid;
  const delta = reference !== null && reference !== undefined ? interval.pred - reference : 0;
  const hasReference = reference !== null && reference !== undefined;
  return `<div class="answer-head"><div class="tag"><div class="answer-label">${esc(targetLabel)}</div>`
    + `<div class="answer-price">${money(onGrid)}</div></div>${hasReference ? deltaChip(delta, "lg") : ""}</div>`;
}

/** The likely range, drawn, and the verdict in one sentence. `actual` adds
 *  the price FPL really set to the bar; `referenceOnBar: false` keeps the
 *  reference for the verdict but off the bar, for a page that shows it in
 *  `cards` instead. */
export function answerBody(interval, reference, against, marker,
  { extra = "", actual = null, referenceOnBar = true, cards = "" } = {}) {
  const { pred, lower, upper } = interval;
  const hasReference = reference !== null && reference !== undefined;
  const delta = hasReference ? pred - reference : 0;
  return `<div class="answer-body">${rangeBar(lower, upper, pred, referenceOnBar ? reference : null, marker, actual)}`
    + `${cards}<p class="answer-verdict">${verdict(delta, lower, upper, reference, against)}</p>${extra}</div>`;
}

/** The prices a prediction is read against, as a row of small cards. Kind
 *  "actual" carries the range bar's diamond. */
export function priceCards(items) {
  const cards = items.map(([label, price, kind]) => {
    const key = kind === "actual" ? '<span class="range-actual-key"></span>' : "";
    return `<div class="price-card price-card-${kind}"><span class="price-card-label">${key}${esc(label)}</span>`
      + `<span class="price-card-value">${money(price)}</span></div>`;
  });
  return `<div class="price-cards">${cards.join("")}</div>`;
}

/** The headline: next season's price, the move, the range, the verdict. */
export function answer(model, interval, reference, against, marker, targetLabel, extra = "") {
  return `<div class="answer">${answerTag(model, interval, reference, targetLabel)}`
    + `${answerBody(interval, reference, against, marker, { extra })}</div>`;
}

/** FPL's player-popup strip: a row of small labelled figures. */
export function statStrip(items) {
  return `<div class="strip">${items.map(([label, value]) =>
    `<div class="strip-item"><span class="strip-value">${esc(value)}</span>`
    + `<span class="strip-label">${esc(label)}</span></div>`).join("")}</div>`;
}

// ---------------------------------------------------------------- why this price

/** The breakdown as a sentence, before anyone has to read a chart. */
function narrate(model, parts) {
  const anchor = parts.shown.find((t) => t.column === "start_cost");
  const movers = parts.shown.filter((t) => t.column !== "start_cost");
  const ups = movers.filter((t) => t.contribution > 0).slice(0, 2);
  const downs = movers.filter((t) => t.contribution < 0).slice(0, 2);
  const named = (terms) => terms
    .map((t) => `${esc(model.termLabel(t.column).toLowerCase())} (${money(t.contribution, true, 2)})`)
    .join(", ");

  let sentence = `Of ${money(parts.total, false, 2)}, `;
  if (anchor) {
    sentence += `<strong>${money(anchor.contribution, false, 2)}</strong>`
      + " comes straight from what he cost this season: prices are sticky. ";
  }
  if (ups.length) sentence += `Pushing it up: ${named(ups)}. `;
  if (downs.length) sentence += `Pulling it down: ${named(downs)}.`;
  return sentence;
}

/** Narrated breakdown, the bars behind it. Returns the HTML and a `mount`
 *  that draws the chart once the HTML is in the page. */
export function whyThisPrice(model, values, reference) {
  const parts = model.contributions(values);
  const steps = model.steps(parts);
  const html = '<div class="why"><h3 class="section-title">Why this price</h3>'
    + `<p class="why-lede">${narrate(model, parts)}</p><div class="why-chart"></div>`
    + '<p class="fine">Each bar is one ingredient of the price, and they add up exactly: '
    + "the model is linear, so nothing is approximated.</p></div>";
  const mount = (root) => drawContributionBars(root.querySelector(".why-chart"), steps, reference);
  return { html, mount };
}

/** A quiet flag per field outside what the model has ever seen. */
export function outOfRange(model, values, asFloat) {
  const ranges = model.spec.ranges;
  const flags = [];
  for (const [name, label] of model.spec.form.numeric_fields) {
    const bounds = ranges[name];
    const value = asFloat(values[name]);
    if (bounds && (value < bounds.min || value > bounds.max)) {
      flags.push(`<li>${esc(label)}: ${fmt(value)} is outside anything in the training data `
        + `(${fmt(bounds.min)} to ${fmt(bounds.max)}).</li>`);
    }
  }
  if (!flags.length) return "";
  return '<div class="flag"><div class="flag-title"><i class="bi bi-exclamation-triangle-fill"></i> '
    + `Beyond what the model has seen</div><ul>${flags.join("")}</ul>`
    + '<p class="fine">A linear model keeps answering past its data, but the answer is a guess.</p></div>';
}

/** True for a club the model folds into its shared "other club" setting. */
export function isPooled(model, team) {
  return Boolean(team) && !model.spec.teams_retained.includes(team);
}

/** A note for a forecast that leans on the shared club setting, or "". The
 *  forecast is fine; the club part of it is an average, not that club's own. */
export function pooledNote(model, team) {
  if (!isPooled(model, team)) return "";
  return `<p class="fine pooled-note"><i class="bi bi-people"></i> The model has too little history for `
    + `${esc(team)} to give it a club setting of its own, so it shares one with the other clubs `
    + "in that position. The club part of this price is their average, not "
    + `${esc(team)}'s own.</p>`;
}

export function priceHistory(note) {
  return '<div class="history"><h3 class="section-title">Price history</h3>'
    + `<div class="history-chart"></div><p class="fine">${esc(note)}</p></div>`;
}

/** The player's forecast as it stood each morning, and how far it has come.
 *  `days` is one {date, gw, price, pred, lower, upper} per day, today last.
 *  The chart goes in `.trend-chart`; null `days` means just the note. */
export function forecastTrend(days) {
  const title = '<h3 class="section-title">Forecast trend</h3>';
  if (days.length < 2) {
    return `<div class="trend">${title}<p class="fine">The forecast is recorded every morning; `
      + "its trend appears from the second day.</p></div>";
  }
  const first = days[0];
  const last = days[days.length - 1];
  const moved = last.pred - first.pred;
  const priceMoved = last.price - first.price;
  let lede;
  if (pyRound(moved, 2) === 0) {
    lede = `The forecast has held at ${money(last.pred, false, 2)} since ${dayMonth(first.date)}.`;
  } else {
    lede = `The forecast is ${moved > 0 ? "up" : "down"} <strong>${money(Math.abs(moved), false, 2)}</strong>`
      + ` since ${dayMonth(first.date)}, from ${money(first.pred, false, 2)} to ${money(last.pred, false, 2)}.`;
  }
  if (pyRound(priceMoved, 1) !== 0) {
    lede += ` His price has ${priceMoved > 0 ? "risen" : "fallen"} ${money(Math.abs(priceMoved))}`
      + " over the same days.";
  }
  return `<div class="trend">${title}<p class="why-lede">${lede}</p><div class="trend-chart"></div>`
    + '<p class="fine">Each point is what Price Watch predicted that morning. Forecasts move most '
    + "after a gameweek, as points and minutes come in, and a little with each price change.</p></div>";
}

/** Shirt, name plate, club and position: the top of a player card. */
export function playerHeader(name, team, position, meta = "") {
  return `<div class="player-header">${shirt(team, "lg")}<div><h2 class="player-name">${esc(name)}</h2>`
    + `<div class="player-sub">${positionPill(position)}<span class="player-club">${esc(team || "")}</span></div>`
    + `${meta}</div></div>`;
}
