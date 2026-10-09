// Linked edits for What if: figures that move together move together.
//
// Editing goals alone describes a player who scored without earning the
// points for it; editing minutes alone describes the same output from more
// playing time, which the model reads as a less efficient player. The model
// is fine (a linear model prices any consistent season correctly); the form
// was the problem. So:
//
//   goals or assists  ->  total points move by what those returns earn
//   minutes or games  ->  goals, assists and points scale at his per-90 rates
//                         (games also scale minutes)
//
// Points use the FPL rules for a goal by position, with no bonus added: the
// data runs a little above them (about 6.2 per midfielder goal against 5).

import { asFloat, fixed, pyRound } from "./format.js";

export const GOAL_POINTS = { GK: 6, DEF: 6, MID: 5, FWD: 4 };
export const ASSIST_POINTS = 3;
export const MIN_MINUTES_FOR_RATES = 270; // fewer than this is too small a sample to compare
const MAX_MINUTES = 3420;

const LINKED = ["minutes", "appearances", "total_points", "goals_scored", "assists"];
const RATE_FIELDS = ["goals_scored", "assists", "total_points"];

const goalPoints = (position) => GOAL_POINTS[position] ?? GOAL_POINTS.MID;

/** The linked figures as plain numbers. */
const snapshot = (values) => Object.fromEntries(LINKED.map((f) => [f, asFloat(values[f])]));

function clampField(field, value) {
  if (field === "total_points") return Math.max(pyRound(value, 0), -1);
  if (field === "minutes") return Math.min(Math.max(pyRound(value, 0), 0), MAX_MINUTES);
  return Math.max(pyRound(value, 0), 0);
}

const plural = (n, one, many) => `${Math.abs(n)} ${Math.abs(n) === 1 ? one : many}`;
const signed = (n) => `${n > 0 ? "+" : "−"}${Math.abs(n)}`;

/**
 * Apply one edit's knock-ons.
 *
 * `prev` is the form as last shown, `next` is the form just read (one figure
 * changed). `link` carries the baseline for scaling between calls
 * ({anchor, field}): repeated edits of the same field scale from the figures
 * before the first of them, so typing 1, 12, 123 does not compound rounding.
 * Returns the values to show, the link to carry forward and any knock-on
 * notes (the form shows them, so the extra movement is never silent).
 */
export function applyLinks(prev, next, link) {
  const keep = (values, anchor = snapshot(values), field = null) =>
    ({ values, link: { anchor, field }, notes: [] });

  // A blank box is mid-typing: leave everything, including the baseline, alone.
  if (LINKED.some((f) => next[f] === null || next[f] === undefined)) {
    return { values: next, link, notes: [] };
  }
  const changed = LINKED.filter((f) => asFloat(next[f]) !== asFloat(prev[f]));
  if (changed.length !== 1) return keep(next);

  const field = changed[0];
  const values = { ...next };

  if (field === "goals_scored" || field === "assists") {
    const delta = asFloat(next[field]) - asFloat(prev[field]);
    const each = field === "assists" ? ASSIST_POINTS : goalPoints(next.element_type);
    const earned = delta * each;
    values.total_points = clampField("total_points", asFloat(prev.total_points) + earned);
    const moved = values.total_points - asFloat(prev.total_points);
    const what = field === "assists"
      ? plural(delta, "assist", "assists") : plural(delta, "goal", "goals");
    const notes = moved === 0 ? [] : [`${signed(moved)} pts from ${what.replace(/ (\w+)$/, ` ${delta > 0 ? "extra" : "fewer"} $1`)}`];
    return { values, link: { anchor: snapshot(values), field: null }, notes };
  }

  if (field === "minutes" || field === "appearances") {
    const base = link.field === field ? link.anchor : snapshot(prev);
    if (!(base[field] > 0)) return keep(next);
    const ratio = asFloat(next[field]) / base[field];
    for (const f of RATE_FIELDS) values[f] = clampField(f, base[f] * ratio);
    if (field === "appearances") values.minutes = clampField("minutes", base.minutes * ratio);
    const unit = field === "minutes" ? "minutes" : "games";
    const scaled = field === "minutes" ? "goals, assists and points" : "minutes, goals, assists and points";
    return {
      values,
      link: { anchor: base, field },
      notes: ratio === 1 ? [] : [`${scaled[0].toUpperCase()}${scaled.slice(1)} scaled to match ${unit} (×${fixed(ratio, 2)})`],
    };
  }

  return keep(next); // total points: nothing follows from it
}

// ---------------------------------------------------------------- impossible combinations

/** The highest goals, assists and points per 90 minutes in `rows` (player
 *  seasons with the form's fields), among those with enough minutes to mean it. */
export function rateCaps(rows) {
  const caps = Object.fromEntries(RATE_FIELDS.map((f) => [f, 0]));
  for (const row of rows) {
    if (!(row.minutes >= MIN_MINUTES_FOR_RATES)) continue;
    for (const f of RATE_FIELDS) caps[f] = Math.max(caps[f], (row[f] * 90) / row.minutes);
  }
  return caps;
}

const RATE_LABELS = { goals_scored: "Goals", assists: "Assists", total_points: "Points" };

/** Plain-language reasons the form describes a season nobody could have had. */
export function impossible(values, caps) {
  const minutes = asFloat(values.minutes);
  const games = asFloat(values.appearances);
  const goals = asFloat(values.goals_scored);
  const assists = asFloat(values.assists);
  const points = asFloat(values.total_points);
  const found = [];

  if (minutes >= MIN_MINUTES_FOR_RATES) {
    for (const f of RATE_FIELDS) {
      const rate = (asFloat(values[f]) * 90) / minutes;
      if (rate > caps[f] + 1e-9) {
        found.push(`${RATE_LABELS[f]} come to ${fixed(rate, 2)} per 90 minutes; the highest in the data is ${fixed(caps[f], 2)}.`);
      }
    }
  }
  const earned = goals * goalPoints(values.element_type) + assists * ASSIST_POINTS;
  if (points < earned) {
    found.push(`${points} total points is fewer than his goals and assists alone earn (${earned}).`);
  }
  if (minutes > games * 90) {
    found.push(`${minutes} minutes in ${games} ${games === 1 ? "game" : "games"} is more than 90 a game.`);
  }
  return found;
}
