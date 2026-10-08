// Price Watch: who the model thinks FPL should reprice next season.
//
// Reads data/board.json -- every current player, already projected to 38
// gameweeks and priced by the daily build -- and does the rest in the
// browser: filters, sort, search, the XI, the map and the player card.
// data/forecasts.json -- each earlier morning's forecast, from the daily
// history -- adds the forecast movers and the card's forecast trend.
//
// The filters scope the transfer list *and* the market map together, and
// narrow what is displayed, never what is computed: the projection always
// ran on the whole league, because its league-average denominator is a
// league-wide quantity.

import { loadJson, loadModel, showError } from "./data.js";
import { dayMonth, esc, fixed, fmt, fold, seasonLabel } from "./format.js";
import { DEFAULT_X, X_FIELDS, drawForecastTrend, drawPriceHistory, drawPriceScatter } from "./charts.js";
import { clubUrl, initNavSearch } from "./nav.js";
import { DEFAULT_SORT, listHtml, nextSort, sortRows } from "./tlist.js";
import { boardValues, recordedOn, snapshotDay, trendDays } from "./records.js";
import { direction, money } from "./theme.js";
import * as ui from "./ui.js";

/** Shape of the XI on the pitch, goalkeeper first, the way FPL draws a team. */
const FORMATION = [["GK", 1], ["DEF", 4], ["MID", 4], ["FWD", 2]];
const PAGE_SIZE = 20;

/** How often an open page checks for a new daily snapshot. */
const POLL_MS = 60 * 60 * 1000;

const REFERENCE_WORDS = { price_now: "today's price", start_cost: "his August price" };

/** Forecast movers' comparison windows, in days back; null is the first
 *  recorded day. A window reaching back before the record starts falls back
 *  to that first day, and the note names the day used. */
const MOVER_WINDOWS = { day: 1, week: 7, all: null };

/** Players shown on each side of the forecast movers. */
const MOVERS_EACH = 5;

/** Smallest forecast change worth listing: anything less rounds to £0.00m. */
const MOVER_FLOOR = 0.005;

const $ = (id) => document.getElementById(id);

const state = {
  xi: "rise",
  window: "week",
  xref: DEFAULT_X,
  search: "",
  pos: [],
  clubs: [],
  sort: { ...DEFAULT_SORT },
  pages: 1,
  selected: null,
};

let model;
let board;
let history;
let forecasts;
let SEASON;
let TARGET;
let players = [];
let positions = [];
let card;
let deeplink = new URLSearchParams(location.search).get("player");

// ---------------------------------------------------------------- data

/** The players with the reference price and the predicted move beside them. */
function withDelta() {
  const xref = state.xref in X_FIELDS ? state.xref : DEFAULT_X;
  return players.map((p) => {
    const ref = p[xref];
    return { ...p, ref, delta: Number.isFinite(ref) ? p.pred - ref : NaN };
  });
}

function filtered(rows) {
  let out = rows;
  if (state.search) {
    const needle = fold(state.search).replace(/ss/g, "s");
    out = out.filter((p) => fold(p.web_name).replace(/ss/g, "s").includes(needle));
  }
  if (state.pos.length) out = out.filter((p) => state.pos.includes(p.element_type));
  if (state.clubs.length) out = out.filter((p) => state.clubs.includes(p.team_name));
  return out;
}

// ---------------------------------------------------------------- status

/** How fresh the data is, and how the season was projected. */
function renderStatus() {
  const ageHours = board.fetched_at ? (Date.now() - Date.parse(board.fetched_at)) / 36e5 : Infinity;
  let source;
  if (!board.is_live) {
    source = '<span class="chip chip-warn" title="No daily FPL snapshot could be read '
      + `(${esc(board.error)}), so this is the GitHub mirror's copy, which can be weeks old.">`
      + '<i class="bi bi-cloud-slash"></i>Offline: cached snapshot</span>';
  } else if (ageHours > board.stale_after_hours) {
    source = '<span class="chip chip-warn" title="The daily snapshot has not updated for over a day, '
      + 'so recent price changes are missing."><i class="bi bi-exclamation-triangle"></i>'
      + `Prices as of ${esc(board.as_of_label)}</span>`;
  } else {
    source = '<span class="chip chip-live" title="Read from the official FPL API once a day, after '
      + 'the overnight price changes."><i class="bi bi-broadcast"></i>'
      + `Prices as of ${esc(board.as_of_label)}</span>`;
  }
  const gameweek = board.gameweek_label;
  $("board-status").innerHTML = source
    + `<span class="chip">${esc(gameweek.charAt(0).toUpperCase() + gameweek.slice(1))}</span>`
    + '<span class="chip" title="Each player\'s totals so far are multiplied up to 38 gameweeks, '
    + 'using his own club\'s fixtures played.">Form scaled to a full season</span>';
}

// ---------------------------------------------------------------- the XI

function spot(p) {
  return `<button type="button" class="spot" data-code="${p.code}">${ui.shirt(p.team_name, "pitch")}`
    + `<span class="spot-name">${esc(p.web_name)}</span>`
    + `<span class="spot-tag spot-${direction(p.delta)}"><span class="spot-now">${money(p.ref)}</span>`
    + `<i class="bi bi-arrow-right"></i><span class="spot-pred">${money(p.pred)}</span></span></button>`;
}

/** The biggest predicted movers per position, in formation. Drawn from
 *  players who have played this season, league-wide: the filters below
 *  scope the list and the map, not the XI. */
function renderPitch() {
  const rows = withDelta();
  const pool = rows.filter((p) => p.minutes_now > 0 && Number.isFinite(p.delta));
  const lines = [];
  for (const [position, count] of FORMATION) {
    const group = pool.filter((p) => p.element_type === position);
    group.sort((a, b) => (state.xi === "rise" ? b.delta - a.delta : a.delta - b.delta));
    lines.push(`<div class="pitch-row">${group.slice(0, count).map(spot).join("")}</div>`);
  }
  const against = REFERENCE_WORDS[state.xref];
  $("board-xi-note").textContent = `Biggest predicted ${state.xi === "rise" ? "rises" : "falls"} `
    + `against ${against}, by position, from players who have featured this season. Each tag reads `
    + `${state.xref === "price_now" ? "today" : "August"} → ${seasonLabel(TARGET)}.`;
  $("board-pitch").innerHTML = '<div class="pitch-lines"></div><div class="pitch-six"></div>'
    + `<div class="pitch-halfway"></div>${lines.join("")}`;
}

// ---------------------------------------------------------------- forecast movers

/** Today's date as the snapshot has it, "2026-10-08". */
const today = () => snapshotDay(board);

/** Index into forecasts.dates of the day to measure a change from: the
 *  latest day at least `days` before today, or the first day when there is
 *  none that far back (or `days` is null). -1 when nothing was recorded. */
function baselineDay(days) {
  const dates = forecasts.dates;
  if (!dates.length) return -1;
  if (days !== null) {
    const cutoff = new Date(`${today()}T00:00:00Z`);
    cutoff.setUTCDate(cutoff.getUTCDate() - days);
    const limit = cutoff.toISOString().slice(0, 10);
    for (let i = dates.length - 1; i >= 0; i--) if (dates[i] <= limit) return i;
  }
  return 0;
}

function mover(p) {
  return `<button type="button" class="mv-row" data-code="${p.code}">`
    + `<span class="tl-player">${ui.shirt(p.team_name, "sm")}<span class="tl-who">`
    + `<span class="tl-name">${esc(p.web_name)}</span><span class="tl-sub">${ui.positionPill(p.element_type)}`
    + `<span class="tl-club">${esc(p.team_name)}</span></span></span></span>`
    + `<span class="num mv-path"><span class="mv-then">${money(p.then, false, 2)}<i class="bi bi-arrow-right"></i></span>`
    + `<strong>${money(p.pred, false, 2)}</strong></span>`
    + `<span class="num">${ui.changeChip(p.change)}</span></button>`;
}

function moversSide(title, icon, rows, none) {
  const body = rows.length ? rows.map(mover).join("") : `<p class="mv-none">${esc(none)}</p>`;
  return `<div class="mv-side"><div class="mv-head"><i class="bi ${icon}"></i>${title}</div>${body}</div>`;
}

/** Whose forecast has moved most since an earlier recorded morning. Today's
 *  side is the board the rest of the page shows; the earlier side is the
 *  forecast recorded that morning. League-wide, like the XI: the filters
 *  belong to the list and the map. */
function renderMovers() {
  const note = $("board-movers-note");
  const out = $("board-movers");
  note.textContent = "";
  if (!board.is_live) {
    out.innerHTML = ui.empty("Forecast movers need the daily FPL snapshot, which could not be read.",
      "bi-cloud-slash");
    return;
  }
  const day = baselineDay(MOVER_WINDOWS[state.window] ?? null);
  if (day < 0) {
    out.innerHTML = ui.empty("Forecasts are recorded every morning. Movers appear from the second day.",
      "bi-calendar-plus");
    return;
  }

  const rows = [];
  for (const p of players) {
    const then = recordedOn(forecasts.players[String(p.code)], day);
    if (then && Number.isFinite(p.pred)) rows.push({ ...p, then: then[1], change: p.pred - then[1] });
  }
  const ups = rows.filter((r) => r.change >= MOVER_FLOOR).sort((a, b) => b.change - a.change).slice(0, MOVERS_EACH);
  const downs = rows.filter((r) => r.change <= -MOVER_FLOOR).sort((a, b) => a.change - b.change).slice(0, MOVERS_EACH);

  const since = dayMonth(forecasts.dates[day]);
  note.textContent = `Whose ${seasonLabel(TARGET)} forecast has moved most since the morning of ${since}. `
    + "Forecasts move most after a gameweek, as points and minutes come in, and a little with each "
    + "price change.";
  if (!ups.length && !downs.length) {
    out.innerHTML = ui.empty(`No forecast has moved by £0.01m or more since ${since}. Expect movement `
      + "after the next gameweek.", "bi-pause-circle");
    return;
  }
  out.innerHTML = moversSide("Forecast up", "bi-graph-up-arrow", ups, `No forecast up since ${since}.`)
    + moversSide("Forecast down", "bi-graph-down-arrow", downs, `No forecast down since ${since}.`);
}

// ---------------------------------------------------------------- the list

function renderList() {
  const all = sortRows(filtered(withDelta()), state.sort);

  const limit = PAGE_SIZE * state.pages;
  const shown = all.slice(0, limit);
  if (!shown.length) {
    $("board-list").innerHTML = ui.empty("No players match these filters.");
    $("board-count").textContent = "No players match.";
    $("board-more-wrap").hidden = true;
    return;
  }

  const nowLabel = state.xref !== "start_cost" ? "Today" : "August";
  const labels = { player: "Player", points: "Pts", minutes: "Mins", selected: "Sel.", ref: nowLabel,
    pred: seasonLabel(TARGET), move: "Move" };
  $("board-list").innerHTML = listHtml(shown, state.sort, labels);
  $("board-count").textContent = `Showing ${shown.length} of ${all.length} players`;
  $("board-more-wrap").hidden = shown.length >= all.length;
}

// ---------------------------------------------------------------- the map

function renderMap() {
  const shown = filtered(withDelta());
  const against = REFERENCE_WORDS[state.xref];
  $("board-map-note").textContent = `Every player in the list, ${against} against the `
    + `${seasonLabel(TARGET)} prediction. Above the dashed line the model wants him dearer, below it `
    + "cheaper; the further from the line, the bigger the call. Click a mark to open the player.";
  drawPriceScatter($("board-map"), shown, TARGET, state.xref, positions, openCard);
}

// ---------------------------------------------------------------- the card

/** This player's completed seasons, plus the one in progress. The in-progress
 *  row is rebuilt from the record the page is holding, which came from the
 *  API this morning, rather than from the history mirror, which lags. */
function playerSeasons(record) {
  const past = history[String(record.code)] || [];
  return [...past, [SEASON, record.start_cost, record.price_now]];
}

function cardHtml(record) {
  const values = boardValues(model.spec, record);
  const interval = model.predict(values);

  const xref = state.xref in X_FIELDS ? state.xref : DEFAULT_X;
  const reference = Number(record[xref]);
  const short = xref === "price_now" ? "Today" : "August";

  const games = Number(record.games_played || 0);
  const note = `<p class="fine">Projected from ${fmt(games)} gameweeks to a full 38: `
    + `${fmt(record.total_points)} points and ${fmt(record.minutes)} minutes.</p>`;
  const link = '<div class="card-links">'
    + `<a class="btn-ghost" href="player.html?code=${record.code}"><i class="bi bi-person-badge"></i>Player page</a>`
    + `<a class="btn-ghost" href="lab.html?season=${SEASON}&amp;player=${record.code}">`
    + '<i class="bi bi-sliders"></i>Tweak this season in What if</a></div>';

  const header = ui.playerHeader(record.web_name, record.team_name, record.element_type,
    ui.statStrip([
      ["Points", String(Math.trunc(record.points_now || 0))],
      ["Minutes", Math.trunc(record.minutes_now || 0).toLocaleString("en-GB")],
      ["Selected", `${fixed(Number(record.selected_by_percent || 0), 1)}%`],
      ["Gameweeks", fmt(games)],
    ]), clubUrl(record.team_name));
  const answer = ui.answer(model, interval, reference, REFERENCE_WORDS[xref], short,
    `Predicted ${seasonLabel(TARGET)} price`, `<div>${note}${ui.pooledNote(model, record.team_name)}${link}</div>`);
  const why = ui.whyThisPrice(model, values, [short, reference]);
  const days = trendDays(forecasts, board, record, interval);
  const trend = ui.forecastTrend(days);
  const past = ui.priceHistory(`The ${seasonLabel(SEASON)} season is still running, so its end price is today's.`);

  return {
    html: header + answer + why.html + trend + past,
    mount(root) {
      why.mount(root);
      const trendEl = root.querySelector(".trend-chart");
      if (trendEl) drawForecastTrend(trendEl, days, TARGET);
      drawPriceHistory(root.querySelector(".history-chart"), playerSeasons(record), TARGET, interval.pred);
    },
  };
}

let openCode = null;

/** Open (or refresh) the player card. */
function openCard(code) {
  const record = players.find((p) => p.code === Number(code));
  const body = $("board-card-body");
  openCode = record ? record.code : null;
  if (!record) {
    body.innerHTML = ui.empty("That player is no longer in the live data.");
  } else {
    const built = cardHtml(record);
    body.innerHTML = built.html;
    const draw = () => built.mount(body);
    if ($("board-card").classList.contains("show")) draw();
    else $("board-card").addEventListener("shown.bs.offcanvas", draw, { once: true });
  }
  card.show();
}

/** A new reference price redraws a card that is already open; it never pops
 *  one open by itself. */
function refreshCard() {
  if (openCode === null || !$("board-card").classList.contains("show")) return;
  const record = players.find((p) => p.code === openCode);
  if (!record) return;
  const built = cardHtml(record);
  $("board-card-body").innerHTML = built.html;
  built.mount($("board-card-body"));
}

// ---------------------------------------------------------------- wiring

function renderAll() {
  renderStatus();
  renderPitch();
  renderMovers();
  renderList();
  renderMap();
  refreshCard();
}

function renderFilters() {
  $("board-pos").innerHTML = positions.map((p, i) =>
    `<div class="form-check form-check-inline"><input class="form-check-input" type="checkbox" `
    + `id="pos-${p}" value="${p}"><label class="form-check-label" for="pos-${p}">${p}</label></div>`).join("");

  const clubs = [...new Set(players.map((p) => p.team_name).filter(Boolean))].sort();
  state.clubs = state.clubs.filter((c) => clubs.includes(c));
  $("board-clubs-panel").innerHTML = '<button type="button" class="multi-clear" id="board-clubs-clear">Clear</button>'
    + clubs.map((c, i) => `<label><input type="checkbox" value="${esc(c)}"${state.clubs.includes(c) ? " checked" : ""}> ${esc(c)}</label>`).join("");
  clubsLabel();
}

function clubsLabel() {
  const n = state.clubs.length;
  $("board-clubs-label").textContent = n === 0 ? "All clubs" : n <= 2 ? state.clubs.join(", ") : `${n} clubs`;
}

function wire() {
  card = new bootstrap.Offcanvas($("board-card"));

  $("board-settings-toggle").addEventListener("click", (event) => {
    const panel = $("board-settings");
    panel.hidden = !panel.hidden;
    event.currentTarget.classList.toggle("is-open", !panel.hidden);
    event.currentTarget.setAttribute("aria-expanded", String(!panel.hidden));
  });

  document.querySelectorAll('input[name="board-xref"]').forEach((input) =>
    input.addEventListener("change", () => { state.xref = input.value; state.pages = 1; renderAll(); }));
  document.querySelectorAll('input[name="board-xi"]').forEach((input) =>
    input.addEventListener("change", () => { state.xi = input.value; renderPitch(); }));
  document.querySelectorAll('input[name="board-window"]').forEach((input) =>
    input.addEventListener("change", () => { state.window = input.value; renderMovers(); }));
  $("board-movers").addEventListener("click", (event) => {
    const row = event.target.closest("[data-code]");
    if (row) openCard(row.dataset.code);
  });

  let timer;
  $("board-search").addEventListener("input", (event) => {
    clearTimeout(timer);
    timer = setTimeout(() => { state.search = event.target.value.trim(); state.pages = 1; renderList(); renderMap(); }, 200);
  });
  $("board-pos").addEventListener("change", () => {
    state.pos = [...document.querySelectorAll("#board-pos input:checked")].map((i) => i.value);
    state.pages = 1; renderList(); renderMap();
  });
  $("board-clubs-panel").addEventListener("change", () => {
    state.clubs = [...document.querySelectorAll("#board-clubs-panel input:checked")].map((i) => i.value);
    state.pages = 1; clubsLabel(); renderList(); renderMap();
  });
  $("board-clubs-panel").addEventListener("click", (event) => {
    if (event.target.id !== "board-clubs-clear") return;
    document.querySelectorAll("#board-clubs-panel input").forEach((i) => { i.checked = false; });
    state.clubs = []; state.pages = 1; clubsLabel(); renderList(); renderMap();
  });
  document.addEventListener("click", (event) => {
    const details = $("board-clubs");
    if (details.open && !details.contains(event.target)) details.open = false;
  });

  $("board-more").addEventListener("click", () => { state.pages += 1; renderList(); });
  $("board-list").addEventListener("click", (event) => {
    const header = event.target.closest("[data-sort]");
    if (header) {
      state.sort = nextSort(state.sort, header.dataset.sort);
      state.pages = 1;
      renderList();
      return;
    }
    const row = event.target.closest("[data-code]");
    if (row) openCard(row.dataset.code);
  });
  $("board-pitch").addEventListener("click", (event) => {
    const spotEl = event.target.closest("[data-code]");
    if (spotEl) openCard(spotEl.dataset.code);
  });
}

/** Pick up a new daily snapshot in a tab left open overnight. */
function poll() {
  setInterval(async () => {
    try {
      const fresh = await loadJson("board", true);
      if (fresh.fetched_at === board.fetched_at) return;
      forecasts = await loadJson("forecasts", true);
      board = fresh;
      players = board.players;
      renderFilters();
      renderAll();
    } catch (error) {
      console.warn("Could not refresh the snapshot", error);
    }
  }, POLL_MS);
}

async function main() {
  initNavSearch();
  try {
    [model, board, history, forecasts] = await Promise.all([
      loadModel(), loadJson("board"), loadJson("history"), loadJson("forecasts")]);
  } catch (error) {
    showError($("board-pitch"), error);
    return;
  }
  SEASON = model.spec.meta.predict_season;
  TARGET = SEASON + 1;
  positions = model.spec.positions;
  players = board.players;

  $("board-season").textContent = seasonLabel(TARGET);
  $("board-lede").textContent = `Who the model thinks FPL should reprice for ${seasonLabel(TARGET)}, `
    + `from current ${seasonLabel(SEASON)} form projected to a full 38-gameweek season.`;

  // Bootstrap and Plotly are deferred scripts; modules run after them.
  wire();
  renderFilters();
  renderAll();
  poll();

  // ?player=<code> opens that player's card once the data lands.
  const code = Number(deeplink);
  if (deeplink && Number.isInteger(code)) openCard(code);
  deeplink = null;
}

main();
