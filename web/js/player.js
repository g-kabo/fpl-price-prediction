// The player page: one canonical page per player, current or departed.
//
// player.html?code=<code> reads the player from the address, as Price
// Watch's ?player= does, because a static GitHub Pages site can't route a
// path without a file per player. It joins everything on `code`, never on
// name: FPL renames players (Salah became M.Salah).
//
// A current player gets what his Price Watch card has -- next season's
// forecast, why, and the forecast trend -- built from the same board.json
// record, so the two agree to the penny. Every player gets his price in each
// season since 2017-18, with the start price the model would have called
// from the season before. Those calls are worked out here from seasons.json,
// the way What if works them out, so opening a season there shows the same
// number. Calls from seasons the model learned from are drawn faint: only a
// season it never saw is a fair test.
//
// Without a code, the page is a way in: a search box and a few players.

import { loadJson, loadModel, showError } from "./data.js";
import { esc, fixed, fmt, seasonLabel } from "./format.js";
import { drawForecastTrend, drawTrackRecord } from "./charts.js";
import { attachSearch, initNavSearch, playerUrl } from "./nav.js";
import { boardValues, seasonRows, seasonValues, trendDays, withRatios } from "./records.js";
import { money } from "./theme.js";
import * as ui from "./ui.js";

const $ = (id) => document.getElementById(id);

/** Players offered on the page without a code. */
const POPULAR = 12;
const DEPARTED = 6;

let model;
let spec;
let board;
let forecasts;
let rows = [];
let CURRENT;
let TARGET;
let FIRST;
let TRAIN_THROUGH;

// ---------------------------------------------------------------- the calls

/** Where a call made from `season` stands as a test of the model. */
function callKind(season) {
  if (season >= CURRENT) return "forecast";
  if (season <= TRAIN_THROUGH) return "learned";
  return "test";
}

function callNote(season, kind) {
  if (kind === "forecast") return `Forecast from ${seasonLabel(season)} form so far, projected to 38 gameweeks`;
  if (kind === "learned") return `Made from ${seasonLabel(season)}, which the model learned from: not a test`;
  return `Made from ${seasonLabel(season)}, which the model never saw: a fair test`;
}

/** The model's call for the season after `row`, as What if makes it. */
function callFrom(row) {
  return model.predict(withRatios(spec.form, seasonValues(spec.form, row)));
}

/** One chart group per season he played, plus the season after his last:
 *  the forecast for a current player, an unanswered call for one who left. */
function trackGroups(seasons, record, interval) {
  const bySeason = new Map(seasons.map((r) => [r.season, r]));
  const groups = seasons.map((r) => {
    const current = r.season === CURRENT && record;
    const group = {
      season: r.season,
      start: current ? record.start_cost : r.start_cost,
      end: current ? record.price_now : r.final_cost,
      endLabel: current ? "Today's price" : "End price",
    };
    const before = bySeason.get(r.season - 1);
    if (before && before.season < CURRENT) {
      group.call = callFrom(before).pred;
      group.callKind = callKind(before.season);
      group.callNote = callNote(before.season, group.callKind);
    }
    return group;
  });

  const last = seasons[seasons.length - 1];
  if (record) {
    groups.push({ season: TARGET, call: interval.pred, callKind: "forecast",
      callNote: callNote(CURRENT, "forecast") });
  } else if (last) {
    const kind = callKind(last.season);
    groups.push({ season: last.season + 1, call: callFrom(last).pred, callKind: kind,
      callNote: `${callNote(last.season, kind)}. He left, so FPL never priced him` });
  }
  return groups;
}

// ---------------------------------------------------------------- sections

function hero(seasons, record) {
  const latest = record || seasons[seasons.length - 1];
  const count = seasons.length;
  const span = `In FPL for ${count} of the ${CURRENT - FIRST + 1} seasons since ${seasonLabel(FIRST)}`;
  const status = record
    ? `<span class="chip chip-live"><i class="bi bi-broadcast"></i>Current player</span>`
    : `<span class="chip"><i class="bi bi-box-arrow-right"></i>Last in FPL ${seasonLabel(latest.season)}</span>`;

  let strip;
  if (record) {
    strip = ui.statStrip([
      ["Today", money(record.price_now)],
      ["Points", String(Math.trunc(record.points_now || 0))],
      ["Minutes", Math.trunc(record.minutes_now || 0).toLocaleString("en-GB")],
      ["Selected", `${fixed(Number(record.selected_by_percent || 0), 1)}%`],
      ["Gameweeks", fmt(Number(record.games_played || 0))],
    ]);
  } else {
    const points = seasons.reduce((sum, r) => sum + Number(r.total_points || 0), 0);
    strip = ui.statStrip([
      ["Last price", money(latest.final_cost)],
      ["Career points", Math.trunc(points).toLocaleString("en-GB")],
      ["Seasons", String(count)],
    ]);
  }

  const whatIf = `lab.html?season=${record ? CURRENT : latest.season}&amp;player=${latest.code}`;
  return '<div class="wrap player-hero-inner">'
    + `<div class="player-id">${ui.shirt(latest.team_name, "xl")}<div>`
    + `<h1 class="player-title">${esc(latest.web_name)}</h1>`
    + `<div class="player-sub">${ui.positionPill(latest.element_type)}<span class="player-club">${esc(latest.team_name || "")}</span></div>`
    + `<div class="player-meta">${esc(span)}.</div>${strip}</div></div>`
    + `<div class="hero-side"><div class="chips">${status}</div><div class="hero-actions">`
    + '<button type="button" class="btn-on-dark" id="player-copy"><i class="bi bi-link-45deg"></i><span>Copy link</span></button>'
    + `<a class="btn-on-dark" href="${whatIf}"><i class="bi bi-sliders"></i>Open in What if</a>`
    + "</div></div></div>";
}

/** Next season for a current player: the Price Watch card's answer. */
function forecastSection(record, interval) {
  const games = Number(record.games_played || 0);
  const note = `<p class="fine">Projected from ${fmt(games)} gameweeks to a full 38: `
    + `${fmt(record.total_points)} points and ${fmt(record.minutes)} minutes. Read against today's `
    + `price, as Price Watch does by default.</p>`;
  return '<section class="panel player-panel">'
    + ui.answer(model, interval, record.price_now, "today's price", "Today",
      `Predicted ${seasonLabel(TARGET)} price`, note + ui.pooledNote(model, record.team_name))
    + "</section>";
}

/** What the model would have priced a departed player at, had he stayed. */
function leftSection(last) {
  const values = withRatios(spec.form, seasonValues(spec.form, last));
  const interval = model.predict(values);
  const next = seasonLabel(last.season + 1);
  const extra = `<p class="fine">He did not return for ${next}, so FPL never priced him. `
    + (last.season <= TRAIN_THROUGH
      ? "The model learned from his last season, so treat this as a description rather than a test.</p>"
      : "</p>");
  return '<section class="panel player-panel">'
    + ui.answer(model, interval, last.final_cost, "his end price", "End",
      `Model's ${next} price, had he stayed`, extra)
    + "</section>";
}

function trendSection(days) {
  return `<section class="panel player-panel">${ui.forecastTrend(days)}</section>`;
}

function whySection(why) {
  return `<section class="panel player-panel player-wide">${why.html}</section>`;
}

function trackSection(record) {
  const now = record
    ? ` The ${seasonLabel(CURRENT)} season is still running, so its end price is today's.`
    : "";
  return '<section class="panel player-panel player-wide"><div class="history">'
    + '<h3 class="section-title">Price history and the model\'s calls</h3>'
    + '<p class="why-lede">Each season, the start price FPL set beside the one the model would have called '
    + "from the season before, and where the price ended.</p>"
    + '<div class="track-chart"></div>'
    + `<p class="fine">Each call sits under the season it is for. Faint ones, for ${seasonLabel(TRAIN_THROUGH + 1)} `
    + `and earlier, were made from seasons the model learned from, so a close one is not a test of it. `
    + `Calls for ${seasonLabel(TRAIN_THROUGH + 2)} on were made from seasons it never saw.${now}</p></div></section>`;
}

function seasonsTable(seasons, record) {
  const lines = [...seasons].reverse().map((r) => {
    const current = r.season === CURRENT && record;
    const points = current ? record.points_now : r.total_points;
    const minutes = current ? record.minutes_now : r.minutes;
    const end = current ? record.price_now : r.final_cost;
    return `<tr><td class="st-season">${seasonLabel(r.season)}${current ? '<span class="st-now">so far</span>' : ""}</td>`
      + `<td><span class="st-club">${ui.shirt(r.team_name, "xs")}${esc(r.team_name || "")}</span></td>`
      + `<td>${ui.positionPill(r.element_type)}</td>`
      + `<td class="num">${Math.trunc(points || 0)}</td>`
      + `<td class="num st-mins">${Math.trunc(minutes || 0).toLocaleString("en-GB")}</td>`
      + `<td class="num">${money(r.start_cost)}</td>`
      + `<td class="num">${money(end)}${current ? '<span class="st-now">today</span>' : ""}</td></tr>`;
  });
  return '<section class="panel player-panel player-wide"><h3 class="section-title">Season by season</h3>'
    + '<div class="table-scroll"><table class="terms seasons-table"><thead><tr>'
    + '<th>Season</th><th>Club</th><th>Pos</th><th class="num">Points</th><th class="num st-mins">Minutes</th>'
    + '<th class="num">Start</th><th class="num">End</th></tr></thead>'
    + `<tbody>${lines.join("")}</tbody></table></div></section>`;
}

// ---------------------------------------------------------------- the page

function renderPlayer(code) {
  const seasons = rows.filter((r) => r.code === code && r.season < CURRENT).sort((a, b) => a.season - b.season);
  const record = board.players.find((p) => p.code === code) || null;
  if (record) {
    // The season in progress, from the record the page shows, not from the
    // history mirror, which lags.
    const live = rows.find((r) => r.code === code && r.season === CURRENT);
    seasons.push({ ...(live || {}), season: CURRENT, code, web_name: record.web_name,
      team_name: record.team_name, element_type: record.element_type,
      start_cost: record.start_cost, final_cost: record.price_now });
  }
  if (!seasons.length) {
    renderLanding(`No player in the data has the code ${code}. Search by name instead.`);
    return;
  }

  const latest = record || seasons[seasons.length - 1];
  document.title = `${latest.web_name} · FPL Price Prediction`;
  $("player-hero").innerHTML = hero(seasons, record);
  wireCopy(code);

  let interval = null;
  let why = null;
  let days = [];
  const parts = [];
  if (record) {
    const values = boardValues(spec, record);
    interval = model.predict(values);
    days = trendDays(forecasts, board, record, interval);
    why = ui.whyThisPrice(model, values, ["Today", record.price_now]);
    parts.push(forecastSection(record, interval), trendSection(days), whySection(why));
  } else {
    parts.push(leftSection(seasons[seasons.length - 1]));
  }
  parts.push(trackSection(record), seasonsTable(seasons, record));

  const root = $("player-root");
  root.className = `wrap player-body${record ? "" : " player-departed"}`;
  root.innerHTML = parts.join("");
  if (why) why.mount(root);
  const trendEl = root.querySelector(".trend-chart");
  if (trendEl) drawForecastTrend(trendEl, days, TARGET);
  drawTrackRecord(root.querySelector(".track-chart"), trackGroups(seasons, record, interval));
}

function wireCopy(code) {
  const button = $("player-copy");
  const label = button.querySelector("span");
  const url = `${location.origin}${location.pathname}?code=${code}`;
  let timer;
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(url);
      label.textContent = "Link copied";
    } catch {
      label.textContent = "Copy the address bar";
    }
    clearTimeout(timer);
    timer = setTimeout(() => { label.textContent = "Copy link"; }, 2400);
  });
}

function tile(p, sub) {
  return `<a class="player-tile" href="${playerUrl(p.code)}">${ui.shirt(p.team_name, "sm")}`
    + `<span class="tl-who"><span class="tl-name">${esc(p.web_name)}</span>`
    + `<span class="tl-sub">${ui.positionPill(p.element_type)}<span class="tl-club">${esc(p.team_name || "")}</span></span></span>`
    + `<span class="tile-side">${sub}</span></a>`;
}

/** No code, or one nobody has: a search box and somewhere to start. */
function renderLanding(message = "") {
  $("player-hero").innerHTML = '<div class="wrap"><h1>Players</h1>'
    + `<p class="lede">Every player since ${seasonLabel(FIRST)}, still here or long gone: his price each season, `
    + `what the model called it, and for current players the ${seasonLabel(TARGET)} forecast.</p>`
    + '<div class="landing-search search"><i class="bi bi-search"></i>'
    + '<input id="landing-search" class="search-input" type="search" placeholder="Find any player" '
    + 'aria-label="Find any player" role="combobox" aria-expanded="false" aria-controls="landing-results" '
    + 'aria-autocomplete="list" autocomplete="off" spellcheck="false">'
    + '<div class="search-results" id="landing-results" role="listbox" aria-label="Players" hidden></div></div></div>';
  attachSearch($("landing-search"), $("landing-results"));

  const popular = [...board.players]
    .sort((a, b) => Number(b.selected_by_percent || 0) - Number(a.selected_by_percent || 0))
    .slice(0, POPULAR);

  // Departed players worth looking up: the dearest at the end of their last season.
  const lastSeason = new Map();
  for (const r of rows) {
    if (r.season >= CURRENT) continue;
    const seen = lastSeason.get(r.code);
    if (!seen || r.season > seen.season) lastSeason.set(r.code, r);
  }
  const current = new Set(board.players.map((p) => p.code));
  const departed = [...lastSeason.values()].filter((r) => !current.has(r.code))
    .sort((a, b) => b.final_cost - a.final_cost).slice(0, DEPARTED);

  const notice = message
    ? `<div class="player-missing"><i class="bi bi-person-x"></i><p>${esc(message)}</p></div>` : "";
  $("player-root").className = "wrap player-body player-landing";
  $("player-root").innerHTML = notice
    + '<section class="block"><div class="block-head"><div><h2 class="block-title">Most selected</h2>'
    + '<p class="block-note">The players most managers own right now.</p></div></div>'
    + `<div class="tile-grid">${popular.map((p) => tile(p, `${fixed(Number(p.selected_by_percent || 0), 1)}%`)).join("")}</div></section>`
    + '<section class="block"><div class="block-head"><div><h2 class="block-title">Since departed</h2>'
    + '<p class="block-note">The dearest players to have left FPL, by their price on the way out.</p></div></div>'
    + `<div class="tile-grid">${departed.map((r) => tile(r, `${money(r.final_cost)}<span class="tile-when">${seasonLabel(r.season)}</span>`)).join("")}</div></section>`;
}

async function main() {
  initNavSearch();
  const query = new URLSearchParams(location.search);
  const raw = query.get("code") ?? query.get("player");
  let seasonsData;
  try {
    [model, board, seasonsData, forecasts] = await Promise.all([
      loadModel(), loadJson("board"), loadJson("seasons"), loadJson("forecasts")]);
  } catch (error) {
    showError($("player-root"), error);
    return;
  }
  spec = model.spec;
  CURRENT = spec.meta.predict_season;
  TARGET = CURRENT + 1;
  TRAIN_THROUGH = spec.meta.train_through;
  FIRST = spec.first_season;
  rows = seasonRows(seasonsData);

  const code = Number(raw);
  if (raw === null || raw === "") renderLanding();
  else if (!Number.isInteger(code)) renderLanding(`"${raw}" is not a player code. Search by name instead.`);
  else renderPlayer(code);
}

main();
