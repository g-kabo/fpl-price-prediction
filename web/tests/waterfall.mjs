// Checks the waterfall steps: price terms combined and adding up exactly.
//
//     node web/tests/waterfall.mjs

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { makeModel } from "../js/model.js";

const here = dirname(fileURLToPath(import.meta.url));
const read = (path) => JSON.parse(readFileSync(join(here, path), "utf8"));
const model = makeModel(read("../data/model.json"));
const board = read("../data/board.json");

let failures = 0;
const check = (label, ok, detail = "") => { if (!ok) { failures++; console.error(`FAIL ${label} ${detail}`); } };
const inputs = (p) => ({ ...Object.fromEntries(model.spec.form.numeric_names.map((n) => [n, p[n]])),
  element_type: p.element_type, team_name: p.team_name });

for (const p of board.players.slice(0, 200)) {
  const now = inputs(p);
  const parts = model.contributions(now);
  const steps = model.steps(parts);
  const labels = steps.map((s) => s[0]);
  check(`${p.web_name} one price bar`, labels.filter((l) => l === "Overall price contribution").length === 1);
  check(`${p.web_name} no separate price terms`, !labels.some((l) => /price/i.test(l) && l !== "Overall price contribution" && l !== "Predicted price"), labels.join("|"));
  const sum = steps.filter((s) => s[2] === "relative").reduce((t, s) => t + s[1], steps[0][1]);
  check(`${p.web_name} waterfall adds up`, Math.abs(sum - parts.total) < 1e-9, `${sum} vs ${parts.total}`);

}

if (failures) { console.error(`${failures} failure(s)`); process.exit(1); }
console.log("waterfall steps OK");
