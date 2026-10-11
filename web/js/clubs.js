// Every club: how the model would reprice each club's squad next season.
//
// The bars and the club-by-position grid. Picking a club (a bar, a grid row
// or a cell) opens its own page, club.html, with the squad on a pitch; the
// data both pages read, and the calls it forces, are in clubdata.js.

import { loadJson, loadModel, showError } from "./data.js";
import { esc, seasonLabel } from "./format.js";
import { drawClubBars } from "./charts.js";
import { initNavSearch } from "./nav.js";
import { POSITIONS, clubs, measureOf, readCount, setData, shared, summariseAll, writeCount } from "./clubdata.js";
import { money } from "./theme.js";
import * as ui from "./ui.js";

const $ = (id) => document.getElementById(id);

const MEASURES = {
  total: { label: "Squad total", note: "the sum of every counted player's predicted change against today's price" },
  average: { label: "Per player", note: "the average predicted change per counted player, so big and small squads compare fairly" },
  owned: { label: "Managers' money", note: "each player's predicted change weighted by the share of managers who own him: what the forecast means for the average manager's squad" },
  minutes: { label: "Playing time", note: "each player's predicted change weighted by his share of the club's minutes so far, so the shares add up to about eleven: the change in the side that actually plays" },
};

const state = { sort: "total" };

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

// ---------------------------------------------------------------- wiring

function renderAll() {
  summariseAll();
  renderBars();
  renderGrid();
}

function wire() {
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
  let board;
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
