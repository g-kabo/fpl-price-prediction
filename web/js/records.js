// A player's numbers as more than one page reads them: Price Watch's card,
// What if and the player page. Kept in one place so a player is priced the
// same way wherever he is opened.

import { asFloat, pyRound } from "./format.js";

// ---------------------------------------------------------------- Price Watch's record

/** The model's inputs for one board.json player: his season so far,
 *  already projected to 38 gameweeks and held inside the training range. */
export function boardValues(spec, record) {
  const values = {};
  for (const name of spec.form.numeric_names) values[name] = record[name];
  values.element_type = record.element_type;
  values.team_name = record.team_name;
  return values;
}

/** Today's date as the snapshot has it, "2026-10-08". */
export function snapshotDay(board) {
  return board.fetched_at ? board.fetched_at.slice(0, 10) : null;
}

/** A player's recorded [price, pred, lower, upper] on day `day`, or null.
 *  forecasts.json keeps change points only, so this is the last one at or
 *  before that day; a bare [day] marks him missing from it. */
export function recordedOn(points, day) {
  let found = null;
  for (const point of points || []) {
    if (point[0] > day) break;
    found = point.length > 1 ? point.slice(1) : null;
  }
  return found;
}

/** This player's recorded mornings, with today taken from the board itself,
 *  so the trend always ends on the number shown above it. */
export function trendDays(forecasts, board, record, interval) {
  const today = snapshotDay(board);
  const days = [];
  const points = forecasts.players[String(record.code)];
  if (points && points.length) {
    for (let day = points[0][0]; day < forecasts.dates.length; day++) {
      if (forecasts.dates[day] >= today) break;
      const values = recordedOn(points, day);
      if (!values) continue;
      const [price, pred, lower, upper] = values;
      days.push({ date: forecasts.dates[day], gw: forecasts.gameweeks[day], price, pred, lower, upper });
    }
  }
  if (!board.is_live) return days;
  days.push({ date: today, gw: board.gameweeks_finished, price: record.price_now,
    pred: interval.pred, lower: interval.lower, upper: interval.upper });
  return days;
}

// ---------------------------------------------------------------- club names

/** Earlier names a current club went by in seasons.json. The history mirror
 *  and the live API don't always agree: Ipswich was "Ipswich" in 2024-25 and
 *  is "Ipswich Town" now. Add a line here when a promoted club disagrees. */
export const FORMER_NAMES = { "Ipswich Town": ["Ipswich"] };

/** The current name for a club name from any season, if it is a current
 *  club; null otherwise. `current` is a Set of today's club names. */
export function currentClub(name, current) {
  if (current.has(name)) return name;
  for (const [now, before] of Object.entries(FORMER_NAMES)) {
    if (before.includes(name) && current.has(now)) return now;
  }
  return null;
}

// ---------------------------------------------------------------- seasons.json

/** seasons.json's rows as objects, one per player-season. */
export function seasonRows(data) {
  return data.rows.map((raw) => Object.fromEntries(data.fields.map((f, i) => [f, raw[i]])));
}

/** One player-season as What if's form holds it. */
export function seasonValues(form, row) {
  const values = {};
  for (const name of form.form_names) values[name] = row[name];
  values[form.position_field] = row.element_type;
  values[form.team_field] = row.form_team;
  return values;
}

/** FPL publishes both ratios to one decimal place. */
const fplRound = (value) => pyRound(value, 1);

/** The form's values plus the two ratios, worked out as FPL does: points per
 *  game is points over games played, points per £m over the end price. */
export function withRatios(form, values) {
  const points = asFloat(values.total_points);
  const games = asFloat(values[form.appearances_field]);
  const price = asFloat(values.final_cost);
  return {
    ...values,
    points_per_game: games > 0 ? fplRound(points / games) : 0,
    value_season: price > 0 ? fplRound(points / price) : 0,
  };
}
