// Draws what the model tests can't see: every player's tag and list rows, and
// the club charts. A throw in any of these stops a page drawing, so the deploy
// runs this before publishing. No browser, so it can't catch a layout problem.
//
//     python export_static.py --parity
//     node web/tests/render.mjs

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

// The page loads Plotly as a global. This stand-in fails where the real one
// does on a trace property that is present but undefined.
globalThis.Plotly = {
  react(el, traces) {
    for (const trace of traces) {
      for (const [key, value] of Object.entries(trace)) {
        if (value === undefined) throw new Error(`trace "${trace.name}" has ${key}: undefined`);
      }
    }
    el.drawn = traces.length;
  },
};

const { COLUMNS, listHtml, sortRows } = await import("../js/tlist.js");
const ui = await import("../js/ui.js");
const { drawPlayerForecasts, drawClubTrend } = await import("../js/charts.js");

const here = dirname(fileURLToPath(import.meta.url));
const board = JSON.parse(readFileSync(join(here, "../data/board.json"), "utf8"));

let failures = 0;
function attempt(label, draw) {
  try {
    return draw();
  } catch (error) {
    failures++;
    if (failures <= 15) console.error(`FAIL ${label}: ${error.message}`);
    return "";
  }
}
const check = (label, ok, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL ${label} ${detail}`); }
};

const rows = board.players.map((p) => ({ ...p, ref: p.price_now, delta: p.pred - p.price_now }));
const labels = { player: "Player", tag: "Tag", points: "Pts", minutes: "Mins", selected: "Sel.", value: "Pts/£m",
  ref: "Today", pred: "Forecast", move: "Move" };

// Every player's tag, drawn on its own so a failure names him.
for (const p of rows) {
  attempt(`${p.web_name} pill`, () => ui.recordPill(p.record));
  attempt(`${p.web_name} note`, () => ui.recordNote(p.record));
  attempt(`${p.web_name} list row`, () => listHtml([p], { col: "move", desc: true }, labels, null, { tags: true }));
}
const tagged = rows.filter((p) => p.record);
for (const p of tagged) {
  check(`${p.web_name} tag`, ui.RECORD_KINDS.includes(ui.recordKind(p.record)), ui.recordKind(p.record));
  check(`${p.web_name} sentence`, !/undefined|null|NaN/.test(ui.recordNote(p.record)), ui.recordNote(p.record));
}

// Every shape a record can take, whatever today's data happens to hold.
const shapes = [
  { direction: "high", scope: "season", value: 5, since: "2026-10-01", tracked_from: "2026-09-29" },
  { direction: "low", scope: "season", value: 5, since: null, tracked_from: "2026-09-29", new: true },
  { direction: "high", scope: "all", value: 5, since: null, tracked_from: "2026-09-29", past_best: 4,
    past_best_for: 2025, past_from: 2020, few_minutes: 19, new: true },
  { direction: "low", scope: "historic", value: 5, past_best: 6, past_best_for: 2025, past_from: 2020,
    season_best: 5, season_best_on: null },
  { direction: "high", scope: "historic", value: 5, past_best: 4, past_best_for: 2025, past_from: 2020,
    season_best: 6, season_best_on: "2026-10-01", few_minutes: 0 },
];
for (const record of shapes) {
  const name = JSON.stringify(record);
  const note = attempt(`shape ${name}`, () => ui.recordNote(record));
  attempt(`shape ${name}`, () => ui.recordPill(record));
  check(`shape sentence ${name}`, note && !/undefined|null|NaN/.test(note), note);
}

// The list, sorted every way and laid out as each page does.
for (const [key] of [...COLUMNS, ["tag"], ["value"]]) {
  for (const desc of [true, false]) {
    const sorted = attempt(`sort ${key}`, () => sortRows(rows, { col: key, desc }));
    if (!sorted) continue;
    check(`sort ${key} keeps everyone`, sorted.length === rows.length);
    const sort = { col: key, desc };
    attempt(`Price Watch list by ${key}`, () => listHtml(sorted, sort, labels, null, { tags: true }));
    attempt(`Club list by ${key}`, () => listHtml(sorted, sort, labels, (p) => `#${p.code}`, { value: true, records: true }));
  }
}
const list = listHtml(sortRows(rows, { col: "tag", desc: true }), { col: "tag", desc: true }, labels, null, { tags: true });
check("every tag reaches the list", (list.match(/class="tl-tag"><span class="record-pill/g) || []).length === tagged.length);

// Club charts, either side of the 14 days where they stop drawing markers.
const dates = (n) => Array.from({ length: n }, (_, i) => new Date(Date.UTC(2026, 8, 29 + i)).toISOString().slice(0, 10));
for (const n of [1, 14, 15, 40]) {
  const days = dates(n).map((date, i) => ({ date, value: i / 10 }));
  attempt(`club trend, ${n} days`, () => drawClubTrend({}, { Arsenal: days, Spurs: days }, "Arsenal", 2027));
  const players = [{ code: 1, name: "One", position: "MID", days }, { code: 2, name: "Two", position: "DEF", days }];
  attempt(`player forecasts, ${n} days`, () => drawPlayerForecasts({}, players, { legend: true }));
}

// Tag changes over a window.
const forecasts = JSON.parse(readFileSync(join(here, "../data/forecasts.json"), "utf8"));
const { tagChanges, tagOn } = await import("../js/records.js");
const mornings = forecasts.dates.length;
if (forecasts.tags && mornings >= 2) {
  // Since the last recorded morning must say what the export's own "New" marks and
  // lost list say, or the panel and the list's "New since" filter disagree.
  const latest = tagChanges(forecasts, board.players, mornings - 1);
  const marked = board.players.filter((p) => p.record && p.record.new).map((p) => p.code).sort();
  check("tag changes since the last morning match the New marks",
    JSON.stringify(latest.gained.map((p) => p.code).sort()) === JSON.stringify(marked),
    `${latest.gained.length} against ${marked.length}`);
  const lostCodes = (board.tag_changes ? board.tag_changes.lost : []).map((l) => l.code).sort();
  check("tag changes since the last morning match the lost list",
    JSON.stringify(latest.lost.map((p) => p.code).sort()) === JSON.stringify(lostCodes));
  // Every window's baseline day draws, and a longer one never loses the count of tags held today.
  for (let day = 1; day < mornings; day++) {
    const { gained, lost } = tagChanges(forecasts, board.players, day);
    check(`tag changes from day ${day} are players`, [...gained, ...lost].every((p) => p.code && p.web_name));
    check(`lost tags from day ${day} were real kinds`, lost.every((p) => ui.RECORD_KINDS.includes(p.was)));
  }
  check("no tag is held on the first morning", board.players.every((p) => tagOn(forecasts, p.code, 0) === null));
}

console.log(`${rows.length} players and ${tagged.length} tags drawn.`);
if (failures) {
  console.error(`${failures} failure(s).`);
  process.exit(1);
}
console.log("Every player and club chart draws.");
