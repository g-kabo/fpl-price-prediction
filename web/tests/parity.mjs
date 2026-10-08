// Checks the JavaScript model against Python's answers.
//
//     python export_static.py --parity
//     node web/tests/parity.mjs
//
// Python wrote the expected numbers to web/tests/parity.json; this recomputes
// every one in the browser's code path and fails on any disagreement.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { makeModel } from "../js/model.js";
import { fixed, pyRound, sig4 } from "../js/format.js";

const here = dirname(fileURLToPath(import.meta.url));
const read = (path) => JSON.parse(readFileSync(join(here, path), "utf8"));

const model = makeModel(read("../data/model.json"));
const { cases, board } = read("parity.json");

let failures = 0;
let worst = 0;
function check(label, got, want, tolerance = 1e-9) {
  const gap = Math.abs(got - want);
  worst = Math.max(worst, gap);
  if (!(gap <= tolerance)) {
    failures++;
    if (failures <= 15) console.error(`FAIL ${label}: got ${got}, want ${want} (gap ${gap})`);
  }
}

cases.forEach((c, i) => {
  const got = model.predict(c.values);
  check(`case ${i} pred`, got.pred, c.pred);
  check(`case ${i} lower`, got.lower, c.lower);
  check(`case ${i} upper`, got.upper, c.upper);

  const parts = model.contributions(c.values);
  check(`case ${i} total`, parts.total, c.total);
  check(`case ${i} intercept`, parts.intercept, c.intercept);
  check(`case ${i} rest`, parts.rest, c.rest);
  check(`case ${i} nRest`, parts.nRest, c.n_rest);
  if (parts.shown.length !== c.shown.length) {
    failures++;
    console.error(`FAIL case ${i}: ${parts.shown.length} terms shown, want ${c.shown.length}`);
  } else {
    parts.shown.forEach((t, j) => {
      if (t.column !== c.shown[j][0]) {
        failures++;
        console.error(`FAIL case ${i} term ${j}: ${t.column}, want ${c.shown[j][0]}`);
      }
      check(`case ${i} term ${t.column}`, t.contribution, c.shown[j][1]);
    });
  }
});

// Price Watch's own list: Python rounds its prediction to 3 places.
for (const p of board) {
  check(`board ${p.code}`, model.predict(p.values).pred, p.pred, 0.0005 + 1e-9);
}

// Python's rounding, where JavaScript's differs: exact ties go to even.
const rounding = [[2.25, 1, "2.2"], [2.35, 1, "2.4"], [0.125, 2, "0.12"], [2.675, 2, "2.67"],
  [0.5, 0, "0"], [1.5, 0, "2"], [2.5, 0, "2"], [-2.25, 1, "-2.2"], [5.55, 1, "5.5"], [7, 1, "7.0"]];
for (const [x, d, want] of rounding) {
  if (fixed(x, d) !== want) {
    failures++;
    console.error(`FAIL fixed(${x}, ${d}) = ${fixed(x, d)}, want ${want}`);
  }
}
if (pyRound(45 / 20, 1) !== 2.2) { failures++; console.error("FAIL pyRound(2.25, 1)"); }
for (const [x, want] of [[0.12345, "0.1235"], [1234.5, "1235"], [-0.0004567, "0.0004567"], [0, "0"], [12.5, "12.5"]]) {
  if (sig4(x) !== want) { failures++; console.error(`FAIL sig4(${x}) = ${sig4(x)}, want ${want}`); }
}

console.log(`${cases.length} cases and ${board.length} Price Watch players checked; `
  + `largest gap ${worst.toExponential(2)}.`);
if (failures) {
  console.error(`${failures} failure(s).`);
  process.exit(1);
}
console.log("JavaScript model matches Python.");
