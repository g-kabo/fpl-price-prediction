// One club: its summary, squad on a pitch, squad list, value history and
// forecast trend, and every player's forecast over time.
//
// Opened from the Every club page (clubs.html) or from a club name anywhere
// on the site: club.html?team=<club>, with ?pos=<position> to open the squad
// list cut to one position and ?count=all for the whole squad. The data both
// pages read, and the calls it forces, are in clubdata.js.

import { loadJson, loadModel, showError } from "./data.js";
import { dayMonth, esc, fixed, seasonLabel } from "./format.js";
import { drawClubTrend, drawPlayerForecasts, drawPriceHistory } from "./charts.js";
import { initNavSearch, playerUrl } from "./nav.js";
import { DEFAULT_SORT, listHtml, nextSort, sortRows } from "./tlist.js";
import { FORMER_NAMES, recordedOn, seasonRows, snapshotDay } from "./records.js";
import { POSITIONS, clubs, minuteShare, ownedShare, readCount, setData, shared, summariseAll, trendSeries, valueOf, writeCount }
  from "./clubdata.js";
import { direction, money } from "./theme.js";
import * as ui from "./ui.js";

const $ = (id) => document.getElementById(id);

/** Squad value by season: every player at the club, or weighted as two of
 *  the measures above weight a change. */
const HISTORY_WEIGHTS = {
  squad: "every player at the club that season, whether he played or not, so totals move with squad size as well as prices",
  minutes: "each player's price weighted by his share of the club's minutes that season (38 games of 90 minutes for a finished one): the value of the side that actually played, about eleven players' worth",
  owned: "each player's price weighted by the share of managers who owned him at the end of that season (today, for this one): how much of the average manager's squad the club's players made up",
};

const state = { team: null, listSort: { ...DEFAULT_SORT }, listPos: null, history: "squad", forecastView: "position" };

let model;
let board;
let forecasts;
let pastSeasons = [];
let TARGET;
let series = {};

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
  const who = shared.count === "played" ? "who've played" : "in the squad";
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
    + figure("Playing time", money(club.minutes, true, 2), '<span class="club-stat-hint">the side that plays</span>')
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
  const counting = shared.count === "all" ? "They count in the totals above." : "They are left out of the totals above unless you pick the whole squad.";
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
  const who = shared.count === "played" ? "who've played this season" : "in the squad";
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

/** A finished season's weight for one player, under the history toggle. */
function pastWeight(r) {
  if (state.history === "minutes") return Math.min(Number(r.minutes || 0) / (38 * 90), 1);
  if (state.history === "owned") return Number(r.selected_by_percent || 0) / 100;
  return 1;
}

/** This season's weight for one player, under the history toggle. */
function currentWeight(p) {
  if (state.history === "minutes") return minuteShare(p);
  if (state.history === "owned") return ownedShare(p);
  return 1;
}

/** The club's squad value at the start and end of every season it played,
 *  from seasons.json, with next season's forecast. Never filtered by the
 *  "players who've played" toggle: that count would set a season five
 *  gameweeks old against complete ones. Its own toggle weights the prices
 *  instead, as playing time or ownership weight a change. */
function renderHistory(club) {
  const names = [club.team, ...(FORMER_NAMES[club.team] || [])];
  const bySeason = new Map();
  for (const r of pastSeasons) {
    if (!names.includes(r.team_name)) continue;
    const w = pastWeight(r);
    const s = bySeason.get(r.season) || { start: 0, end: 0 };
    s.start += w * Number(r.start_cost || 0);
    s.end += w * Number(r.final_cost || 0);
    bySeason.set(r.season, s);
  }
  const current = TARGET - 1;
  const seasons = [...bySeason.entries()].sort(([a], [b]) => a - b).map(([season, s]) => [season, s.start, s.end]);
  const total = (field) => club.squad.reduce((t, p) => t + currentWeight(p) * Number(p[field] || 0), 0);
  seasons.push([current, total("start_cost"), total("price_now")]);
  const first = seasons[0][0];
  const gaps = current - first + 1 > seasons.length;
  const what = { squad: "whole squad", minutes: "side, weighted by playing time,", owned: "players, weighted by ownership," }[state.history];
  $("club-history-note").textContent = `The price of ${possessive(club.team)} ${what} at the start and end of `
    + `each Premier League season since ${seasonLabel(first)}, and the model's ${seasonLabel(TARGET)} forecast for `
    + `today's squad. It counts ${HISTORY_WEIGHTS[state.history]}.`
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

// ---------------------------------------------------------------- every player's forecast

const POSITION_NAMES = { GK: "Goalkeepers", DEF: "Defenders", MID: "Midfielders", FWD: "Forwards" };

/** Each counted player's forecast every recorded morning, today from the
 *  board itself, so a line ends on the number the rest of the page shows. */
function playerSeries(club) {
  const today = snapshotDay(board);
  return club.players.map((p) => {
    const days = [];
    forecasts.dates.forEach((date, day) => {
      if (today && date >= today) return;
      const values = recordedOn(forecasts.players[String(p.code)], day);
      if (values) days.push({ date, value: values[1] });
    });
    if (board.is_live && Number.isFinite(p.pred)) days.push({ date: today, value: p.pred });
    return { code: p.code, name: p.web_name, position: p.element_type, days };
  }).filter((p) => p.days.length);
}

function renderForecasts(club) {
  const players = playerSeries(club);
  const out = $("club-forecasts");
  const note = $("club-forecasts-note");
  if (!players.length || Math.max(...players.map((p) => p.days.length)) < 2) {
    note.textContent = "Forecasts are recorded every morning; the lines appear from the second day.";
    out.innerHTML = "";
    return;
  }
  note.textContent = `Every ${shared.count === "played" ? "player who has played" : "player"} at ${club.team}: `
    + `his ${seasonLabel(TARGET)} forecast as it stood each morning, with today's on the right. `
    + "Hover a line for the player. A line is flat until his team plays, then steps as his points and minutes come in.";

  if (state.forecastView === "together") {
    out.innerHTML = '<div class="pf-chart" id="pf-all"></div>';
    drawPlayerForecasts($("pf-all"), players, { legend: true });
    return;
  }
  const facets = POSITIONS.map((pos) => {
    const group = players.filter((p) => p.position === pos);
    return group.length ? { pos, group } : null;
  }).filter(Boolean);
  out.innerHTML = '<div class="pf-grid">' + facets.map(({ pos, group }) =>
    `<div class="pf-facet"><div class="pf-head">${ui.positionPill(pos)}<span>${POSITION_NAMES[pos]}</span>`
    + `<span class="pf-n">${group.length}</span></div><div class="pf-chart" id="pf-${pos}"></div></div>`).join("") + "</div>";
  for (const { pos, group } of facets) drawPlayerForecasts($(`pf-${pos}`), group, { legend: false });
}

// ---------------------------------------------------------------- wiring

function renderClub() {
  const club = clubs.find((c) => c.team === state.team);
  renderSummary(club);
  renderSquad(club);
  renderList(club);
  renderHistory(club);
  renderTrend(club, series);
  renderForecasts(club);
}

function renderAll() {
  summariseAll();
  series = trendSeries();
  renderClub();
}

/** Switch to another club, keeping the address in step. */
function pick(team) {
  if (!clubs.some((c) => c.team === team)) return;
  state.team = team;
  state.listPos = null;
  const url = new URL(location.href);
  url.searchParams.set("team", team);
  url.searchParams.delete("pos");
  history.replaceState(null, "", url);
  $("club-select").value = team;
  renderClub();
}

function wire() {
  document.querySelectorAll('input[name="club-count"]').forEach((input) =>
    input.addEventListener("change", () => { shared.count = input.value; writeCount(); renderAll(); }));
  document.querySelectorAll('input[name="club-history"]').forEach((input) =>
    input.addEventListener("change", () => {
      state.history = input.value;
      renderHistory(clubs.find((c) => c.team === state.team));
    }));
  document.querySelectorAll('input[name="club-forecast-view"]').forEach((input) =>
    input.addEventListener("change", () => {
      state.forecastView = input.value;
      renderForecasts(clubs.find((c) => c.team === state.team));
    }));
  $("club-select").addEventListener("change", (event) => pick(event.target.value));
  $("club-list-note").addEventListener("click", (event) => {
    if (event.target.id !== "club-list-all") return;
    state.listPos = null;
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
  const params = new URLSearchParams(location.search);
  try {
    let seasonsData;
    [model, board, forecasts, seasonsData] = await Promise.all([
      loadModel(), loadJson("board"), loadJson("forecasts"), loadJson("seasons")]);
    // Completed seasons only: the season in progress comes from the board.
    pastSeasons = seasonRows(seasonsData).filter((r) => r.season < model.spec.meta.predict_season);
  } catch (error) {
    showError($("club-summary"), error);
    return;
  }
  setData(model, board, forecasts);
  TARGET = model.spec.meta.predict_season + 1;
  $("club-season").textContent = seasonLabel(TARGET);
  readCount();
  summariseAll();

  // No club (or one that is not in the league this season): the list of them.
  const asked = params.get("team");
  if (!clubs.some((c) => c.team === asked)) {
    location.replace("clubs.html");
    return;
  }
  state.team = asked;
  const pos = params.get("pos");
  state.listPos = POSITIONS.includes(pos) ? pos : null;
  document.title = `${asked} · Clubs · FPL Price Prediction`;
  $("club-select").innerHTML = clubs.map((c) => `<option value="${esc(c.team)}">${esc(c.team)}</option>`).join("");
  $("club-select").value = asked;
  wire();
  renderAll();
  if (state.listPos) $("club-list-block").scrollIntoView({ block: "start" });
}

main();
