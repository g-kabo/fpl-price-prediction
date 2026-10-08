// Clubs: how the model would reprice each club's squad next season.
//
// Reads data/board.json (every current player, priced as Price Watch prices
// him) and groups it by club; data/forecasts.json adds each club's trend.
// Every change is the forecast against today's price, Price Watch's default.
//
// Three calls the data forces (see the engineering notes):
//   - Players who have played count by default. The ones who haven't are each
//     forecast down about £0.13m, so a raw total mostly measures squad size.
//   - A full squad can't fit on a pitch, so players who've played go on it
//     and the rest on a bench under it.
//   - Clubs the model pools into one shared "other club" setting are named
//     as such, because the club part of their forecasts is an average.

import { loadJson, loadModel, showError } from "./data.js";
import { dayMonth, esc, fixed, seasonLabel } from "./format.js";
import { drawClubBars, drawClubTrend, drawPriceHistory } from "./charts.js";
import { initNavSearch, playerUrl } from "./nav.js";
import { DEFAULT_SORT, listHtml, nextSort, sortRows } from "./tlist.js";
import { FORMER_NAMES, recordedOn, seasonRows, snapshotDay } from "./records.js";
import { direction, money } from "./theme.js";
import * as ui from "./ui.js";

const $ = (id) => document.getElementById(id);

/** Pitch rows, goalkeepers at the top as Price Watch's XI has them. */
const POSITIONS = ["GK", "DEF", "MID", "FWD"];

const MEASURES = {
  total: { label: "Squad total", note: "the sum of every counted player's predicted change against today's price" },
  average: { label: "Per player", note: "the average predicted change per counted player, so big and small squads compare fairly" },
  owned: { label: "Managers' money", note: "each player's predicted change weighted by the share of managers who own him: what the forecast means for the average manager's squad" },
};

const state = { count: "played", sort: "total", team: null, listSort: { ...DEFAULT_SORT }, listPos: null };

let model;
let board;
let forecasts;
let pastSeasons = [];
let TARGET;
let clubs = [];

// ---------------------------------------------------------------- data

const counted = (p) => state.count === "all" || p.minutes_now > 0;

/** A group of players under one of the three measures. */
function measureOf(players, measure) {
  const total = players.reduce((t, p) => t + p.delta, 0);
  if (measure === "average") return players.length ? total / players.length : 0;
  if (measure === "owned") return players.reduce((t, p) => t + (Number(p.selected_by_percent || 0) / 100) * p.delta, 0);
  return total;
}

/** Points per £m of today's price. */
const valueOf = (p) => (p.price_now > 0 ? (p.points_now || 0) / p.price_now : 0);

/** One club's squad and its totals under the current "which players count". */
function summarise(team) {
  const squad = board.players.filter((p) => p.team_name === team)
    .map((p) => ({ ...p, delta: p.pred - p.price_now }));
  const players = squad.filter(counted);
  const n = players.length;
  const sum = (f) => players.reduce((total, p) => total + f(p), 0);
  const total = sum((p) => p.delta);
  const byPosition = Object.fromEntries(POSITIONS.map((pos) => {
    const group = players.filter((p) => p.element_type === pos);
    return [pos, { players: group, n: group.length, total: measureOf(group, "total") }];
  }));
  // Best value counts only players who've played: points per £m means
  // nothing for a player with no minutes.
  const best = squad.filter((p) => p.minutes_now > 0).sort((a, b) => valueOf(b) - valueOf(a))[0];
  const ranked = [...players].sort((a, b) => b.delta - a.delta);
  return {
    team, squad, players, n, total,
    average: n ? total / n : 0,
    owned: measureOf(players, "owned"),
    best,
    now: sum((p) => p.price_now),
    predicted: sum((p) => p.pred),
    rising: players.filter((p) => direction(p.delta) === "rise").length,
    falling: players.filter((p) => direction(p.delta) === "fall").length,
    riser: ranked[0],
    faller: ranked[ranked.length - 1],
    byPosition,
    pooled: ui.isPooled(model, team),
  };
}

function summariseAll() {
  const teams = [...new Set(board.players.map((p) => p.team_name).filter(Boolean))].sort();
  clubs = teams.map(summarise);
}

/** Each club's average gap between forecast and price, every recorded
 *  morning, over today's counted squad; today from the board itself. */
function trendSeries() {
  const today = snapshotDay(board);
  const series = {};
  for (const club of clubs) {
    const days = [];
    forecasts.dates.forEach((date, day) => {
      if (today && date >= today) return;
      let total = 0;
      let n = 0;
      for (const p of club.players) {
        const values = recordedOn(forecasts.players[String(p.code)], day);
        if (!values) continue;
        total += values[1] - values[0];
        n += 1;
      }
      if (n) days.push({ date, value: total / n });
    });
    if (board.is_live && club.n) days.push({ date: today, value: club.average });
    series[club.team] = days;
  }
  return series;
}

// ---------------------------------------------------------------- every club

function renderBars() {
  const measure = MEASURES[state.sort];
  const sorted = [...clubs].sort((a, b) => b[state.sort] - a[state.sort])
    .map((c) => ({ team: c.team, value: c[state.sort], n: c.n }));
  const who = state.count === "played" ? "players who have played this season" : "every player in the squad";
  $("club-bars-note").textContent = `${measure.label}: ${measure.note}, counting ${who}. `
    + `Against today's prices, forecast for ${seasonLabel(TARGET)}. Click a club to see its squad.`;
  $("club-bars").querySelector(".loading")?.remove();
  drawClubBars($("club-bars"), sorted, state.team, measure.label, pick);
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
  const picked = team === state.team && (pos === state.listPos || (pos === "ALL" && state.listPos === null));
  const label = group.length ? money(value, true, places) : "–";
  // Phones get the figure without "£" and "m": the legend carries the unit.
  const short = group.length ? label.replace("£", "").replace(/m$/, "") : "–";
  const who = `${group.length} player${group.length === 1 ? "" : "s"}`;
  return `<button type="button" class="grid-cell${picked ? " is-picked" : ""}" data-team="${esc(team)}" `
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

// ---------------------------------------------------------------- one club

function figure(label, value, extra = "") {
  return `<div class="club-stat"><span class="club-stat-value">${value}</span>`
    + `<span class="club-stat-label">${esc(label)}</span>${extra}</div>`;
}

function playerLink(p) {
  return p ? `<a href="${playerUrl(p.code)}">${esc(p.web_name)}</a> ${ui.deltaChip(p.delta, "sm")}` : "–";
}

function renderSummary(club) {
  const target = seasonLabel(TARGET);
  const who = state.count === "played" ? "who've played" : "in the squad";
  $("club-title").innerHTML = `${ui.shirt(club.team, "lg")}<div><h2 class="block-title">${esc(club.team)}</h2>`
    + `<p class="block-note">${club.n} players ${who}, today against ${target}.</p></div>`;

  const positions = POSITIONS.map((pos) => {
    const group = club.byPosition[pos];
    return `<div class="club-pos">${ui.positionPill(pos)}<span class="club-pos-n">${group.n}</span>`
      + `${group.n ? ui.deltaChip(group.total, "sm") : '<span class="club-pos-none">none</span>'}</div>`;
  }).join("");

  $("club-summary").innerHTML = '<div class="panel club-summary">'
    + '<div class="club-stats">'
    + figure("Squad change", ui.deltaChip(club.total, "lg"))
    + figure("Value today", money(club.now))
    + figure(`Predicted ${target}`, money(club.predicted))
    + figure("Per player", money(club.average, true, 2))
    + figure("Managers' money", money(club.owned, true, 2), '<span class="club-stat-hint">per average manager</span>')
    + figure("Rising · falling", `${club.rising} · ${club.falling}`, `<span class="club-stat-hint">of ${club.n}</span>`)
    + "</div>"
    + '<div class="club-lines">'
    + `<div class="club-line"><span class="club-line-label">Biggest riser</span>${playerLink(club.riser)}</div>`
    + `<div class="club-line"><span class="club-line-label">Biggest faller</span>${playerLink(club.faller)}</div>`
    + (club.best ? '<div class="club-line"><span class="club-line-label">Best value</span>'
      + `<a href="${playerUrl(club.best.code)}">${esc(club.best.web_name)}</a>`
      + `<span class="club-line-fig">${fixed(valueOf(club.best), 1)} points per £m</span></div>` : "")
    + `<div class="club-line club-line-pos"><span class="club-line-label">By position</span>${positions}</div>`
    + "</div>"
    + ui.pooledNote(model, club.team)
    + "</div>";
}

function spot(p) {
  return `<a class="spot" href="${playerUrl(p.code)}">${ui.shirt(p.team_name, "pitch")}`
    + `<span class="spot-name">${esc(p.web_name)}</span>`
    + `<span class="spot-tag spot-${direction(p.delta)}"><span class="spot-now">${money(p.price_now)}</span>`
    + `<i class="bi bi-arrow-right"></i><span class="spot-pred">${money(p.pred)}</span></span></a>`;
}

/** Players who've played on the pitch, by position, dearest predicted price
 *  on the left; everyone else on the bench under it. */
function renderSquad(club) {
  const onPitch = club.squad.filter((p) => p.minutes_now > 0);
  const bench = club.squad.filter((p) => !(p.minutes_now > 0));
  const rows = POSITIONS.map((pos) => {
    const group = onPitch.filter((p) => p.element_type === pos).sort((a, b) => b.pred - a.pred);
    return group.length ? `<div class="pitch-row">${group.map(spot).join("")}</div>` : "";
  });
  $("club-pitch").innerHTML = '<div class="pitch-lines"></div><div class="pitch-six"></div>'
    + `<div class="pitch-halfway"></div>${rows.join("")}`;

  if (!bench.length) {
    $("club-bench").innerHTML = "";
    return;
  }
  bench.sort((a, b) => POSITIONS.indexOf(a.element_type) - POSITIONS.indexOf(b.element_type) || b.pred - a.pred);
  const tiles = bench.map((p) => `<a class="player-tile" href="${playerUrl(p.code)}">${ui.shirt(p.team_name, "sm")}`
    + `<span class="tl-who"><span class="tl-name">${esc(p.web_name)}</span>`
    + `<span class="tl-sub">${ui.positionPill(p.element_type)}<span class="tl-club">${money(p.price_now)} today</span></span></span>`
    + `<span class="tile-side">${money(p.pred)}${ui.deltaChip(p.delta, "sm")}</span></a>`).join("");
  const counting = state.count === "all" ? "They count in the totals above." : "They are left out of the totals above unless you pick the whole squad.";
  $("club-bench").innerHTML = `<details class="details club-bench"><summary>The bench: ${bench.length} `
    + `player${bench.length === 1 ? "" : "s"} yet to play this season</summary>`
    + `<p class="fine">${counting} With no minutes, each is forecast from his price alone, which is why `
    + `most are forecast down.</p><div class="tile-grid">${tiles}</div></details>`;
}

/** The squad as Price Watch's transfer list, under the same "which players
 *  count" as the totals, each row linking to the player page. */
function renderList(club) {
  const players = club.players.filter((p) => !state.listPos || p.element_type === state.listPos);
  const rows = sortRows(players.map((p) => ({ ...p, ref: p.price_now })), state.listSort);
  const labels = { player: "Player", points: "Pts", minutes: "Mins", selected: "Sel.", value: "Pts/£m",
    ref: "Today", pred: seasonLabel(TARGET), move: "Move" };
  const who = state.count === "played" ? "who've played this season" : "in the squad";
  const only = state.listPos
    ? ` <button type="button" class="link-button" id="club-list-all">Show every position</button>`
    : "";
  $("club-list-note").innerHTML = `${rows.length} ${state.listPos ? `${state.listPos} ` : ""}players ${who}. `
    + "Pts/£m is points so far per £m of today's price. Click a column to sort, or a player to open his page."
    + only;
  $("club-list").innerHTML = rows.length
    ? listHtml(rows, state.listSort, labels, (p) => playerUrl(p.code), { value: true })
    : ui.empty("No players to list.");
}

/** "Spurs'", "Hull City's". */
const possessive = (name) => (name.endsWith("s") ? `${name}'` : `${name}'s`);

/** The club's squad value at the start and end of every season it played,
 *  from seasons.json, with next season's forecast. Always the whole squad,
 *  whatever the toggle says: counting only players who've played would set
 *  a season five gameweeks old against complete ones. */
function renderHistory(club) {
  const names = [club.team, ...(FORMER_NAMES[club.team] || [])];
  const bySeason = new Map();
  for (const r of pastSeasons) {
    if (!names.includes(r.team_name)) continue;
    const s = bySeason.get(r.season) || { start: 0, end: 0 };
    s.start += Number(r.start_cost || 0);
    s.end += Number(r.final_cost || 0);
    bySeason.set(r.season, s);
  }
  const current = TARGET - 1;
  const seasons = [...bySeason.entries()].sort(([a], [b]) => a - b).map(([season, s]) => [season, s.start, s.end]);
  const total = (field) => club.squad.reduce((t, p) => t + Number(p[field] || 0), 0);
  seasons.push([current, total("start_cost"), total("price_now")]);
  const first = seasons[0][0];
  const gaps = current - first + 1 > seasons.length;
  $("club-history-note").textContent = `The total price of ${possessive(club.team)} whole squad at the start `
    + `and end of each Premier League season since ${seasonLabel(first)}, and the model's ${seasonLabel(TARGET)} `
    + "forecast for today's squad. Every player at the club that season counts, whether he played or not, so "
    + "totals move with squad size as well as prices."
    + `${gaps ? " Missing seasons were outside the Premier League." : ""} The ${seasonLabel(current)} end figure is today's.`;
  drawPriceHistory($("club-history-chart"), seasons, TARGET, total("pred"));
}

function renderTrend(club, series) {
  const days = series[club.team] || [];
  const note = $("club-trend-note");
  if (days.length < 2) {
    note.textContent = "Forecasts are recorded every morning; the trend appears from the second day.";
    $("club-trend-chart").innerHTML = "";
    return;
  }
  const first = days[0];
  const last = days[days.length - 1];
  const moved = last.value - first.value;
  note.innerHTML = `${esc(possessive(club.team))} average forecast change per player is ${money(last.value, true, 2)} `
    + `today, ${Math.abs(moved) < 0.005 ? "unchanged" : `${moved > 0 ? "up" : "down"} <strong>${money(Math.abs(moved), false, 2)}</strong>`} `
    + `since the morning of ${dayMonth(first.date)}.`;
  drawClubTrend($("club-trend-chart"), series, club.team, TARGET);
}

// ---------------------------------------------------------------- wiring

let series = {};

function renderClub() {
  const club = clubs.find((c) => c.team === state.team);
  if (!club) return;
  $("club-select").value = club.team;
  renderSummary(club);
  renderSquad(club);
  renderList(club);
  renderHistory(club);
  renderTrend(club, series);
}

function renderAll() {
  summariseAll();
  series = trendSeries();
  renderBars();
  renderGrid();
  renderClub();
}

/** Pick a club from the chart or the select, and keep it in the address. */
function pick(team, scroll = true, pos = null) {
  if (!clubs.some((c) => c.team === team)) return;
  state.team = team;
  state.listPos = pos;
  const url = new URL(location.href);
  url.searchParams.set("team", team);
  history.replaceState(null, "", url);
  renderBars();
  renderGrid();
  renderClub();
  if (scroll) (pos ? $("club-list-block") : $("club-detail")).scrollIntoView({ behavior: "smooth", block: "start" });
}

function wire() {
  document.querySelectorAll('input[name="club-count"]').forEach((input) =>
    input.addEventListener("change", () => { state.count = input.value; renderAll(); }));
  document.querySelectorAll('input[name="club-sort"]').forEach((input) =>
    input.addEventListener("change", () => { state.sort = input.value; renderBars(); renderGrid(); }));
  $("club-grid").addEventListener("click", (event) => {
    const cell = event.target.closest("[data-team]");
    if (!cell) return;
    const pos = cell.dataset.pos && cell.dataset.pos !== "ALL" ? cell.dataset.pos : null;
    pick(cell.dataset.team, true, pos);
  });
  $("club-select").addEventListener("change", (event) => pick(event.target.value, false));
  $("club-list-note").addEventListener("click", (event) => {
    if (event.target.id !== "club-list-all") return;
    state.listPos = null;
    renderGrid();
    renderList(clubs.find((c) => c.team === state.team));
  });
  $("club-list").addEventListener("click", (event) => {
    const header = event.target.closest("[data-sort]");
    if (!header) return;
    state.listSort = nextSort(state.listSort, header.dataset.sort);
    renderList(clubs.find((c) => c.team === state.team));
  });
}

async function main() {
  initNavSearch();
  try {
    let seasonsData;
    [model, board, forecasts, seasonsData] = await Promise.all([
      loadModel(), loadJson("board"), loadJson("forecasts"), loadJson("seasons")]);
    // Completed seasons only: the season in progress comes from the board.
    pastSeasons = seasonRows(seasonsData).filter((r) => r.season < model.spec.meta.predict_season);
  } catch (error) {
    showError($("club-bars"), error);
    return;
  }
  TARGET = model.spec.meta.predict_season + 1;
  $("club-season").textContent = seasonLabel(TARGET);
  $("club-lede").textContent = `How the model would reprice each club's squad for ${seasonLabel(TARGET)}, `
    + `from current ${seasonLabel(TARGET - 1)} form projected to a full season.`;

  summariseAll();
  $("club-select").innerHTML = clubs.map((c) => `<option value="${esc(c.team)}">${esc(c.team)}</option>`).join("");

  // ?team=<club> opens that club; otherwise the club at the top of the chart.
  const asked = new URLSearchParams(location.search).get("team");
  state.team = clubs.some((c) => c.team === asked) ? asked
    : [...clubs].sort((a, b) => b.total - a.total)[0]?.team;
  wire();
  renderAll();
  if (asked && state.team === asked) $("club-detail").scrollIntoView({ block: "start" });
}

main();
