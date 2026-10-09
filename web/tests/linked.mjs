// Checks What if's linked edits against the Cherki 2025-26 case in the backlog.
//
//     node web/tests/linked.mjs

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { makeModel } from "../js/model.js";
import { applyLinks, impossible, rateCaps } from "../js/linked.js";
import { withRatios } from "../js/records.js";
import { seasonRows, seasonValues } from "../js/records.js";

const here = dirname(fileURLToPath(import.meta.url));
const read = (path) => JSON.parse(readFileSync(join(here, path), "utf8"));
const model = makeModel(read("../data/model.json"));
const seasons = read("../data/seasons.json");
const { form } = model.spec;

let failures = 0;
const check = (label, ok, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL ${label} ${detail}`); }
};

const rows = seasonRows(seasons);
const cherki = rows.find((r) => r.web_name === "Cherki" && r.season === model.spec.meta.score_season);
if (!cherki) { console.error("no Cherki row"); process.exit(1); }
const base = seasonValues(form, cherki);
const price = (v) => model.predict(withRatios(form, v)).pred;
const start = price(base);
const gap = (v) => price(v) - start;

// +3 goals: points follow (midfielder goal = 5).
let next = { ...base, goals_scored: base.goals_scored + 3 };
let r = applyLinks(base, next, { anchor: null, field: null });
check("goals add points", r.values.total_points === base.total_points + 15, r.values.total_points);
check("goals note", r.notes[0] === "+15 pts from 3 extra goals", r.notes[0]);
console.log(`+3 goals linked: ${gap(r.values).toFixed(2)} (goals alone ${gap(next).toFixed(2)})`);

// One assist fewer takes 3 points off.
next = { ...base, assists: base.assists - 1 };
r = applyLinks(base, next, { anchor: null, field: null });
check("assist removes points", r.values.total_points === base.total_points - 3);

// A full season of minutes scales returns with it.
next = { ...base, minutes: 3420 };
r = applyLinks(base, next, { anchor: null, field: null });
check("minutes scale returns", r.values.total_points > base.total_points && r.values.goals_scored >= base.goals_scored);
console.log(`3420 minutes linked: ${gap(r.values).toFixed(2)} (minutes alone ${gap(next).toFixed(2)})`);

// Typing toward the same minutes in steps lands on the same answer (no compounding).
let step = base;
let link = { anchor: null, field: null };
for (const m of [3, 34, 342, 3420]) {
  const out = applyLinks(step, { ...step, minutes: m }, link);
  step = out.values; link = out.link;
}
check("stepwise minutes match one jump", step.total_points === r.values.total_points && step.goals_scored === r.values.goals_scored,
  `${step.total_points} vs ${r.values.total_points}`);

// A blank box leaves everything alone.
r = applyLinks(base, { ...base, minutes: null }, { anchor: null, field: null });
check("blank is untouched", r.notes.length === 0 && r.values.minutes === null);

// Impossible combinations.
const caps = rateCaps(rows.filter((x) => x.season !== model.spec.meta.predict_season));
check("real season is possible", impossible(base, caps).length === 0, impossible(base, caps).join("|"));
check("low points flagged", impossible({ ...base, total_points: 3 }, caps).length >= 1);
check("rate flagged", impossible({ ...base, goals_scored: 40, total_points: 400 }, caps).some((m) => m.startsWith("Goals")));
check("minutes per game flagged", impossible({ ...base, appearances: 5 }, caps).some((m) => m.includes("more than 90")));

if (failures) { console.error(`${failures} failure(s)`); process.exit(1); }
console.log("linked edits OK");
