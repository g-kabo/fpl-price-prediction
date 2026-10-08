// How it works: the served model, written out.
//
// Every weight is read from model.json, which the daily build exports from
// the fitted model itself, so the equation on this page is the one pricing
// players.

import { loadModel, showError } from "./data.js";
import { esc, fixed, seasonLabel, sig4, signed } from "./format.js";
import { initNavSearch } from "./nav.js";
import { money } from "./theme.js";

const SUB = "₀₁₂₃₄₅₆₇₈₉";
const subscript = (n) => String(n).replace(/\d/g, (d) => SUB[Number(d)]);

/** Numeric terms in the equation, by the name a reader sees in the formula. */
const VAR_NAMES = {
  start_cost: "start", final_cost: "end", start_cost_sq: "start²", final_cost_sq: "end²",
  total_points: "points", minutes: "minutes", goals_scored: "goals", assists: "assists",
  points_per_game: "ppg", value_season: "value", selected_by_percent: "selected",
  no_mins: "never_played",
};
const varName = (c) => VAR_NAMES[c] || c;
const variable = (c) => `<var>${esc(varName(c))}</var>`;
const term = (html) => `<span class="eq-term">${html}</span>`;
const prose = (text, cls = "prose") => `<p class="${cls}">${text}</p>`;

function equations(params, numeric) {
  const lhs = '<span class="eq-lhs"><var>next start price</var> =</span>';
  const symbolic = [term("β₀")];
  const filled = [term(sig4(params.const))];
  numeric.forEach((column, i) => {
    symbolic.push(term(` + β${subscript(i + 1)} · ${variable(column)}`));
    filled.push(term(` ${params[column] < 0 ? "−" : "+"} ${sig4(params[column])} · ${variable(column)}`));
  });
  symbolic.push(term(" + β<sub>position</sub> + β<sub>club</sub>"));
  filled.push(term(" + <var>position adjustment</var> + <var>club adjustment</var>"));
  return '<h3 class="step-title">In symbols</h3>'
    + prose("One weight (β) per input, plus a position and a club adjustment.", "fine")
    + `<div class="equation">${lhs}${symbolic.join("")}</div>`
    + '<h3 class="step-title">With its fitted weights</h3>'
    + prose("Rounded to four significant figures; the site computes with the full ones.", "fine")
    + `<div class="equation">${lhs}${filled.join("")}</div>`;
}

function adjustments(spec, params) {
  const positions = [["GK", 0], ...spec.columns.filter((c) => c.startsWith("element_type_"))
    .map((c) => [c.split("_").pop(), params[c]])];
  const clubs = spec.columns.filter((c) => c.startsWith("team_name_"))
    .map((c) => [c.slice("team_name_".length).replace(/_/g, " "), params[c]])
    .sort((a, b) => b[1] - a[1]);
  clubs.push(["Every other club", 0]);

  const chip = (label, value, reference) => '<div class="adj">'
    + `<span class="adj-label">${esc(label)}</span><span class="adj-value">`
    + `${reference ? "0 (reference)" : money(value, true, 3)}</span></div>`;
  return '<div class="adj-row">'
    + '<div><h3 class="step-title">Position adjustment</h3><div class="adj-grid">'
    + positions.map(([p, v]) => chip(p, v, p === "GK")).join("") + "</div></div>"
    + '<div><h3 class="step-title">Club adjustment</h3><div class="adj-grid adj-clubs">'
    + clubs.map(([c, v]) => chip(c, v, c === "Every other club")).join("") + "</div></div></div>";
}

/** How to read the fitted weights, in a manager's units. */
function reading(params, numeric) {
  const bend = params.start_cost_sq + params.final_cost_sq;
  const linear = params.start_cost + params.final_cost;
  const negative = numeric.filter((c) => params[c] < 0).map(varName);
  const items = [
    `Each goal adds ${money(params.goals_scored, true, 3)} and each assist ${money(params.assists, true, 3)} `
    + `to next season's price; each 1% of ownership adds ${money(params.selected_by_percent, true, 3)}.`,
    `Minutes carry ${money(params.minutes * 90, true, 4)} per 90 played: with points, goals and ppg `
    + "held fixed, more minutes means those returns came less efficiently.",
    `start² and end² together add ${signed(bend, 4)} × price². That is the bend: a £1 price difference `
    + `carries about £${fixed(linear + 2 * bend * 4, 2)} at £4m and £${fixed(linear + 2 * bend * 12, 2)} `
    + "at £12m, because FPL props cheap players against a floor and keeps its stars expensive.",
  ];
  if (negative.length) {
    items.push(`Negative weights (${negative.join(", ")}) look odd alone because the inputs overlap `
      + "heavily; their combined effect is what the model means. The breakdown on every player card "
      + "shows those combined effects for one player.");
  }
  return '<div class="prose note"><strong>Read the weights in FPL units, and read the four price '
    + `terms together.</strong><ul>${items.map((i) => `<li>${i}</li>`).join("")}</ul></div>`;
}

async function main() {
  initNavSearch();
  const root = document.getElementById("how-root");
  let model;
  try {
    model = await loadModel();
  } catch (error) {
    showError(root, error);
    return;
  }
  const { spec } = model;
  const params = spec.params;
  const numeric = spec.columns.filter((c) => !c.startsWith("element_type_") && !c.startsWith("team_name_"));

  document.getElementById("how-lede").textContent = `The model is fitted on `
    + `${spec.meta.training_rows.toLocaleString("en-GB")} player-seasons `
    + `(${seasonLabel(spec.first_season)} to ${seasonLabel(spec.meta.train_through)}). `
    + "Every price in the app is this one line of arithmetic.";

  const legend = numeric.map((c) => `<tr><td>${variable(c)}</td><td class="muted mono">${esc(c)}</td>`
    + `<td>${esc(model.termLabel(c))}</td></tr>`).join("");

  root.innerHTML = '<section class="block how-block"><h2 class="block-title">The model, written out</h2>'
    + equations(params, numeric)
    + prose("Prices in £m, minutes in minutes, selected in percent; never_played is 1 for a player "
      + "with no minutes, else 0.", "fine")
    + adjustments(spec, params)
    + prose("What each adjustment adds to the price, against goalkeepers and against every other club. "
      + `Clubs under ${Math.round(spec.team_lump_threshold * 100)}% of training rows, and promoted clubs `
      + "the model has never seen, share the reference level.", "fine")
    + '<details class="details"><summary>What each name in the equation means</summary>'
    + '<table class="terms"><thead><tr><th>In the equation</th><th>Column</th><th>Meaning</th></tr></thead>'
    + `<tbody>${legend}</tbody></table></details>`
    + reading(params, numeric)
    + "</section>";
}

main();
