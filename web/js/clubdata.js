// What the two Clubs pages share: every club's squad and its totals, under
// the "which players count" setting both pages offer.
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

import { recordedOn, snapshotDay } from "./records.js";
import { direction } from "./theme.js";
import * as ui from "./ui.js";

/** Pitch rows, goalkeepers at the top as Price Watch's XI has them. */
export const POSITIONS = ["GK", "DEF", "MID", "FWD"];

/** Which players count, shared by both pages: "played" or "all". */
export const shared = { count: "played" };

let ctx = {};

/** Every club, summarised; rebuilt by `summariseAll`. */
export let clubs = [];

/** Hand over the loaded data, once. */
export function setData(model, board, forecasts) {
  ctx = { model, board, forecasts };
}

/** The "which players count" choice from the address (`?count=all`), if any. */
export function readCount() {
  const asked = new URLSearchParams(location.search).get("count");
  if (asked === "all" || asked === "played") shared.count = asked;
  document.querySelectorAll('input[name="club-count"]').forEach((input) => { input.checked = input.value === shared.count; });
}

/** Keep the choice in the address, so a link or a reload holds it. */
export function writeCount() {
  const url = new URL(location.href);
  if (shared.count === "all") url.searchParams.set("count", "all");
  else url.searchParams.delete("count");
  history.replaceState(null, "", url);
}

export const counted = (p) => shared.count === "all" || p.minutes_now > 0;

/** A player's share of his club's minutes so far: his minutes over its
 *  games played (board.json's games_played is the club's) times 90, capped
 *  at 1. A club's shares add up to about eleven. */
export const minuteShare = (p) => (p.games_played > 0 ? Math.min((p.minutes_now || 0) / (p.games_played * 90), 1) : 0);

/** The share of managers who own a player. */
export const ownedShare = (p) => Number(p.selected_by_percent || 0) / 100;

/** A group of players under one of the four measures. */
export function measureOf(players, measure) {
  const total = players.reduce((t, p) => t + p.delta, 0);
  if (measure === "average") return players.length ? total / players.length : 0;
  if (measure === "owned") return players.reduce((t, p) => t + ownedShare(p) * p.delta, 0);
  if (measure === "minutes") return players.reduce((t, p) => t + minuteShare(p) * p.delta, 0);
  return total;
}

/** Points per £m of today's price. */
export const valueOf = (p) => (p.price_now > 0 ? (p.points_now || 0) / p.price_now : 0);

/** One club's squad and its totals under the current "which players count". */
function summarise(team) {
  const { board, model } = ctx;
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
    minutes: measureOf(players, "minutes"),
    best,
    started: sum((p) => p.start_cost),
    // Players per average manager's squad: the club's share of every pick.
    picked: sum(ownedShare),
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

export function summariseAll() {
  const { board } = ctx;
  const teams = [...new Set(board.players.map((p) => p.team_name).filter(Boolean))].sort();
  clubs = teams.map(summarise);
}

/** Each club's average gap between forecast and price, every recorded
 *  morning, over today's counted squad; today from the board itself. */
export function trendSeries() {
  const { board, forecasts } = ctx;
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

// ---------------------------------------------------------------- change since an earlier morning

/** The recorded morning to measure from: the latest one at least `days`
 *  before today, or the first when history is shorter (`short`), or the first
 *  when `days` is null. Null when nothing was recorded. */
export function baselineDay(days) {
  const { board, forecasts } = ctx;
  const dates = forecasts.dates;
  if (!dates.length) return null;
  if (days !== null) {
    const cutoff = new Date(`${snapshotDay(board)}T00:00:00Z`);
    cutoff.setUTCDate(cutoff.getUTCDate() - days);
    const limit = cutoff.toISOString().slice(0, 10);
    for (let i = dates.length - 1; i >= 0; i--) if (dates[i] <= limit) return { index: i, date: dates[i], short: false };
    return { index: 0, date: dates[0], short: true };
  }
  return { index: 0, date: dates[0], short: false };
}

/** How far a club's forecast has moved since `day` (from `baselineDay`): the
 *  sum, over the players counted now who were tracked then, of today's
 *  forecast minus that morning's. Null with nothing to compare. */
export function forecastMove(club, day) {
  const { forecasts } = ctx;
  if (!day) return null;
  let total = 0;
  let n = 0;
  for (const p of club.players) {
    const then = recordedOn(forecasts.players[String(p.code)], day.index);
    if (!then || !Number.isFinite(p.pred)) continue;
    total += p.pred - then[1];
    n += 1;
  }
  return n ? total : null;
}
