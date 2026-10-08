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
import { dayMonth, esc, seasonLabel } from "./format.js";
import { drawClubBars, drawClubTrend } from "./charts.js";
import { initNavSearch, playerUrl } from "./nav.js";
import { recordedOn, snapshotDay } from "./records.js";
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

const state = { count: "played", sort: "total", team: null };

let model;
let board;
let forecasts;
let TARGET;
let clubs = [];

// ---------------------------------------------------------------- data

const counted = (p) => state.count === "all" || p.minutes_now > 0;

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
    return [pos, { n: group.length, total: group.reduce((t, p) => t + p.delta, 0) }];
  }));
  const ranked = [...players].sort((a, b) => b.delta - a.delta);
  return {
    team, squad, players, n, total,
    average: n ? total / n : 0,
    owned: sum((p) => (Number(p.selected_by_percent || 0) / 100) * p.delta),
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
    .map((c) => ({ team: c.team, value: c[state.sort], pooled: c.pooled, n: c.n }));
  const who = state.count === "played" ? "players who have played this season" : "every player in the squad";
  const pooled = clubs.filter((c) => c.pooled).length;
  $("club-bars-note").textContent = `${measure.label}: ${measure.note}, counting ${who}. `
    + `Against today's prices, forecast for ${seasonLabel(TARGET)}. The ${pooled} clubs marked "pooled" share `
    + "one club setting in the model. Click a club to see its squad.";
  $("club-bars").querySelector(".loading")?.remove();
  drawClubBars($("club-bars"), sorted, state.team, measure.label, pick);
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
  note.innerHTML = `${esc(club.team)}'s average forecast change per player is ${money(last.value, true, 2)} `
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
  renderTrend(club, series);
}

function renderAll() {
  summariseAll();
  series = trendSeries();
  renderBars();
  renderClub();
}

/** Pick a club from the chart or the select, and keep it in the address. */
function pick(team, scroll = true) {
  if (!clubs.some((c) => c.team === team)) return;
  state.team = team;
  const url = new URL(location.href);
  url.searchParams.set("team", team);
  history.replaceState(null, "", url);
  renderBars();
  renderClub();
  if (scroll) $("club-detail").scrollIntoView({ behavior: "smooth", block: "start" });
}

function wire() {
  document.querySelectorAll('input[name="club-count"]').forEach((input) =>
    input.addEventListener("change", () => { state.count = input.value; renderAll(); }));
  document.querySelectorAll('input[name="club-sort"]').forEach((input) =>
    input.addEventListener("change", () => { state.sort = input.value; renderBars(); }));
  $("club-select").addEventListener("change", (event) => pick(event.target.value, false));
}

async function main() {
  initNavSearch();
  try {
    [model, board, forecasts] = await Promise.all([loadModel(), loadJson("board"), loadJson("forecasts")]);
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
