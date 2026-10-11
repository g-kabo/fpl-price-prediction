// Every club: how the model would reprice each club's squad next season.
//
// The bars and the club-by-position grid. Picking a club (a bar, a grid row
// or a cell) opens its own page, club.html, with the squad on a pitch; the
// data both pages read, and the calls it forces, are in clubdata.js.

import { loadJson, loadModel, showError } from "./data.js";
import { dayMonth, esc, fixed, seasonLabel } from "./format.js";
import { drawClubBars, drawClubScatter } from "./charts.js";
import { initNavSearch } from "./nav.js";
import { POSITIONS, baselineDay, clubs, forecastMove, measureOf, readCount, setData, shared, summariseAll, writeCount }
  from "./clubdata.js";
import { snapshotDay } from "./records.js";
import { money } from "./theme.js";
import * as ui from "./ui.js";

const $ = (id) => document.getElementById(id);

const MEASURES = {
  total: { label: "Squad total", note: "the sum of every counted player's predicted change against today's price" },
  average: { label: "Per player", note: "the average predicted change per counted player, so big and small squads compare fairly" },
  owned: { label: "Managers' money", note: "each player's predicted change weighted by the share of managers who own him: what the forecast means for the average manager's squad" },
  minutes: { label: "Playing time", note: "each player's predicted change weighted by his share of the club's minutes so far, so the shares add up to about eleven: the change in the side that actually plays" },
};

const state = { sort: "total", moveSort: { key: "all", dir: -1 }, tableSort: { key: "change", dir: -1 } };

let board;

let TARGET;

/** Open a club's own page, keeping "which players count", and optionally
 *  its squad list cut to one position. */
function openClub(team, pos = null) {
  const url = new URL("club.html", location.href);
  url.searchParams.set("team", team);
  if (pos) url.searchParams.set("pos", pos);
  if (shared.count === "all") url.searchParams.set("count", "all");
  location.href = url.toString();
}

// ---------------------------------------------------------------- every club

function renderBars() {
  const measure = MEASURES[state.sort];
  const sorted = [...clubs].sort((a, b) => b[state.sort] - a[state.sort])
    .map((c) => ({ team: c.team, value: c[state.sort], n: c.n }));
  const who = shared.count === "played" ? "players who have played this season" : "every player in the squad";
  $("club-bars-note").textContent = `${measure.label}: ${measure.note}, counting ${who}. `
    + `Against today's prices, forecast for ${seasonLabel(TARGET)}. Click a club to open its page.`;
  $("club-bars").querySelector(".loading")?.remove();
  drawClubBars($("club-bars"), sorted, null, measure.label, openClub);
}

// ---------------------------------------------------------------- club by position

/** Fill for a cell: the rise or fall colour, darker the bigger the move,
 *  with the label turning white once the fill is dark enough. */
function cellColours(value, cap) {
  const strength = cap > 0 ? Math.min(Math.abs(value) / cap, 1) : 0;
  const rgb = value >= 0 ? "0, 122, 63" : "214, 0, 79";
  return {
    background: `rgba(${rgb}, ${(0.08 + strength * 0.82).toFixed(3)})`,
    color: strength > 0.5 ? "#ffffff" : value >= 0 ? "var(--rise-on)" : "#7a002d",
  };
}

function cellHtml(team, pos, group, value, cap, places) {
  const { background, color } = cellColours(value, cap);
  const label = group.length ? money(value, true, places) : "–";
  // Phones get the figure without "£" and "m": the legend carries the unit.
  const short = group.length ? label.replace("£", "").replace(/m$/, "") : "–";
  const who = `${group.length} player${group.length === 1 ? "" : "s"}`;
  return `<button type="button" class="grid-cell" data-team="${esc(team)}" `
    + `data-pos="${pos}" style="background:${background};color:${color}" `
    + `aria-label="${esc(team)} ${pos === "ALL" ? "whole squad" : pos}: ${label}, ${who}">`
    + `<span class="grid-value"><span class="grid-long">${label}</span><span class="grid-short">${short}</span></span>`
    + `<span class="grid-n">${who}</span></button>`;
}

/** Every club by position, under the chart's measure and in its order. A
 *  cell opens that club with its squad list cut to that position. */
function renderGrid() {
  const places = state.sort === "total" ? 1 : 2;
  const rows = [...clubs].sort((a, b) => b[state.sort] - a[state.sort]).map((club) => ({
    club,
    cells: POSITIONS.map((pos) => {
      const group = club.byPosition[pos].players;
      return { pos, group, value: measureOf(group, state.sort) };
    }),
  }));
  const cap = Math.max(...rows.flatMap((r) => r.cells.map((c) => Math.abs(c.value))), 0.01) * 0.85;
  const capAll = Math.max(...clubs.map((c) => Math.abs(c[state.sort])), 0.01) * 0.85;

  const head = '<div class="grid-row grid-head"><div>Club</div>'
    + POSITIONS.map((pos) => `<div>${ui.positionPill(pos)}</div>`).join("") + "<div>All</div></div>";
  $("club-grid").innerHTML = head + rows.map(({ club, cells }) => '<div class="grid-row">'
    + `<button type="button" class="grid-club" data-team="${esc(club.team)}">${ui.shirt(club.team, "xs")}`
    + `<span>${esc(club.team)}</span></button>`
    + cells.map((c) => cellHtml(club.team, c.pos, c.group, c.value, cap, places)).join("")
    + `<div class="grid-all">${cellHtml(club.team, "ALL", club.players, club[state.sort], capAll, places)}</div>`
    + "</div>").join("");
  const low = cellColours(-1, 1).background;
  const mid = cellColours(0, 1).background;
  const high = cellColours(1, 1).background;
  $("club-grid-legend").innerHTML = `<span>${money(-cap, true, places)}</span>`
    + `<span class="grid-ramp" style="background:linear-gradient(90deg, ${low}, ${mid}, ${high})"></span>`
    + `<span>${money(cap, true, places)}</span><span>£m. Darker is a bigger move. Click a cell for its players.</span>`;
}

// ---------------------------------------------------------------- the tables

/** A sortable column header: click to sort by it, again to reverse. */
function header(label, key, sort, { num = true, sub = "" } = {}) {
  const on = sort.key === key;
  const arrow = on ? (sort.dir < 0 ? "bi-caret-down-fill" : "bi-caret-up-fill") : "bi-chevron-expand";
  return `<th class="${num ? "num " : ""}sortable${on ? " is-sorted" : ""}" aria-sort="${on ? (sort.dir < 0 ? "descending" : "ascending") : "none"}">`
    + `<button type="button" class="th-sort" data-key="${key}">${esc(label)}<i class="bi ${arrow}"></i></button>`
    + `${sub ? `<span class="th-sub">${esc(sub)}</span>` : ""}</th>`;
}

const clubCell = (club) => `<td><a class="st-club" href="club.html?team=${encodeURIComponent(club.team)}${shared.count === "all" ? "&count=all" : ""}">`
  + `${ui.shirt(club.team, "xs")}<span>${esc(club.team)}</span></a></td>`;

/** Rows in the order a sort asks for; a club with nothing to compare goes last. */
const byKey = (sort) => (a, b) => {
  const [x, y] = [a[sort.key], b[sort.key]];
  if (x === null || x === undefined) return 1;
  if (y === null || y === undefined) return -1;
  return typeof x === "string" ? sort.dir * x.localeCompare(y) : sort.dir * (x - y);
};

/** A change in £m, to the penny and coloured by direction: the chips round
 *  anything under £0.1m to "holds", which would hide most of a week's moves. */
const changeCell = (value) => (value === null
  ? '<td class="num"><span class="muted">–</span></td>'
  : `<td class="num"><span class="move move-${Math.abs(value) < 0.005 ? "hold" : value > 0 ? "rise" : "fall"}">${money(value, true, 2)}</span></td>`);

/** How far each club's forecast has moved: over the past month, the past
 *  week and since tracking began. */
function renderMoves() {
  const live = board.is_live && snapshotDay(board);
  const windows = live ? [["month", "Past month", 30], ["week", "Past week", 7], ["all", "Since tracking began", null]]
    .map(([key, label, days]) => ({ key, label, day: baselineDay(days) })) : [];
  const note = $("club-moves-note");
  if (!windows.length || windows.some((w) => !w.day)) {
    note.textContent = "Forecasts are recorded every morning; movers appear from the second day.";
    $("club-moves").innerHTML = "";
    return;
  }
  const rows = clubs.map((club) => ({
    club, team: club.team,
    ...Object.fromEntries(windows.map((w) => [w.key, forecastMove(club, w.day)])),
  }));
  rows.sort(byKey(state.moveSort));
  const first = windows.find((w) => w.key === "all").day.date;
  const shorter = windows.filter((w) => w.day.short);
  note.textContent = `The change in each club's ${seasonLabel(TARGET)} forecast: how far the combined forecast of its `
    + `${shared.count === "played" ? "players who have played" : "squad"} has moved since an earlier morning. `
    + `Tracking began ${dayMonth(first)}.`
    + (shorter.length ? ` There is not yet a ${shorter.map((w) => w.key).join(" or ")} of history, so that column measures from ${dayMonth(first)}.` : "");
  const head = "<thead><tr>" + header("Club", "team", state.moveSort, { num: false })
    + windows.map((w) => header(w.label, w.key, state.moveSort, { sub: `since ${dayMonth(w.day.date)}` })).join("")
    + "</tr></thead>";
  const body = rows.map((r) => `<tr>${clubCell(r.club)}${windows.map((w) => changeCell(r[w.key])).join("")}</tr>`).join("");
  $("club-moves").innerHTML = `<table class="terms club-table" data-table="moves">${head}<tbody>${body}</tbody></table>`;
}

/** One row per club for the club table and the scatter beside it. A player
 *  is up or down by whether his forecast is above or below his start price;
 *  the two totals add up to the change. */
function tableRows() {
  return clubs.map((club) => {
    const deltas = club.players.map((p) => p.pred - p.start_cost);
    const ups = deltas.filter((d) => d > 0);
    const downs = deltas.filter((d) => d < 0);
    const sum = (list) => list.reduce((t, d) => t + d, 0);
    return {
      club, team: club.team, picked: club.picked, started: club.started, predicted: club.predicted,
      change: club.predicted - club.started,
      up: ups.length, down: downs.length, upTotal: sum(ups), downTotal: sum(downs),
    };
  });
}

/** Start price against predicted price for every club's squad. */
function renderScatter() {
  const rows = tableRows();
  $("club-scatter-note").textContent = `Each mark is a club: its squad's combined start-of-season price against its `
    + `combined ${seasonLabel(TARGET)} forecast. Above the dashed line the model wants the squad dearer, below it cheaper. `
    + "Click a club to open it.";
  drawClubScatter($("club-scatter"), rows, TARGET, openClub);
}

/** Every club's squad in one table: how many picks it has, what it cost in
 *  August, what the model predicts for next season, and the difference. */
function renderTable() {
  const rows = tableRows();
  rows.sort(byKey(state.tableSort));
  const who = shared.count === "played" ? "players who have played this season" : "every player in the squad";
  $("club-table-note").textContent = `Counting ${who}. Selected picks is how many of an average manager's fifteen `
    + "players come from the club. Prices are the squad's combined start-of-season price and its combined "
    + `${seasonLabel(TARGET)} forecast, so the change is like for like; the bars further down compare with today's prices. `
    + "Players up and down count those forecast above or below their start price, and the two totals add up to the change.";
  const head = "<thead><tr>" + header("Club", "team", state.tableSort, { num: false })
    + header("Selected picks", "picked", state.tableSort)
    + header("Start price", "started", state.tableSort, { sub: seasonLabel(TARGET - 1) })
    + header("Predicted price", "predicted", state.tableSort, { sub: seasonLabel(TARGET) })
    + header("Change", "change", state.tableSort)
    + header("Players up", "up", state.tableSort) + header("Players down", "down", state.tableSort)
    + header("Total up", "upTotal", state.tableSort) + header("Total down", "downTotal", state.tableSort)
    + "</tr></thead>";
  const body = rows.map((r) => `<tr>${clubCell(r.club)}<td class="num">${fixed(r.picked, 1)}</td>`
    + `<td class="num">${money(r.started)}</td><td class="num">${money(r.predicted)}</td>${changeCell(r.change)}`
    + `<td class="num">${r.up}</td><td class="num">${r.down}</td>${changeCell(r.upTotal)}${changeCell(r.downTotal)}</tr>`).join("");
  $("club-table").innerHTML = `<table class="terms club-table" data-table="table">${head}<tbody>${body}</tbody></table>`;
}

// ---------------------------------------------------------------- wiring

function renderAll() {
  summariseAll();
  renderMoves();
  renderTable();
  renderScatter();
  renderBars();
  renderGrid();
}

/** Click a column to sort by it, again to reverse; text starts A-Z, figures biggest first. */
function sortBy(sort, key) {
  if (sort.key === key) sort.dir = -sort.dir;
  else { sort.key = key; sort.dir = key === "team" ? 1 : -1; }
}

function wire() {
  $("club-moves").addEventListener("click", (event) => {
    const button = event.target.closest(".th-sort");
    if (button) { sortBy(state.moveSort, button.dataset.key); renderMoves(); }
  });
  $("club-table").addEventListener("click", (event) => {
    const button = event.target.closest(".th-sort");
    if (button) { sortBy(state.tableSort, button.dataset.key); renderTable(); }
  });
  document.querySelectorAll('input[name="club-count"]').forEach((input) =>
    input.addEventListener("change", () => { shared.count = input.value; writeCount(); renderAll(); }));
  document.querySelectorAll('input[name="club-sort"]').forEach((input) =>
    input.addEventListener("change", () => { state.sort = input.value; renderBars(); renderGrid(); }));
  $("club-grid").addEventListener("click", (event) => {
    const cell = event.target.closest("[data-team]");
    if (!cell) return;
    openClub(cell.dataset.team, cell.dataset.pos && cell.dataset.pos !== "ALL" ? cell.dataset.pos : null);
  });
}

async function main() {
  initNavSearch();
  let model;
  let forecasts;
  try {
    [model, board, forecasts] = await Promise.all([loadModel(), loadJson("board"), loadJson("forecasts")]);
  } catch (error) {
    showError($("club-bars"), error);
    return;
  }
  setData(model, board, forecasts);
  TARGET = model.spec.meta.predict_season + 1;
  $("club-season").textContent = seasonLabel(TARGET);
  $("club-lede").textContent = `How the model would reprice each club's squad for ${seasonLabel(TARGET)}, `
    + `from current ${seasonLabel(TARGET - 1)} form projected to a full season.`;
  readCount();
  wire();
  renderAll();
}

main();
