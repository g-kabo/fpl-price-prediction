// What if: take a season, change it, and see the price move.
//
// Picking a season and a player fills every field from his real season;
// "Start from an average player" seeds them at the training medians instead.
// Medians rather than zeros: an all-zero form describes a free player who
// never played, which is outside the fitted range.
//
// The seasons are every completed one since 2017-18, plus the season in
// progress as Price Watch projects it to 38 gameweeks, so a Price Watch
// player can be opened here and tweaked (?season=<year>&player=<code>).
//
// For a completed season the price being predicted has already been set by
// FPL, and the page says what FPL actually did. Only the scoring season is a
// fair test: the model was trained on every season before it.

import { loadJson, loadModel, showError } from "./data.js";
import { asFloat, esc, fixed, fmt, pyRound, seasonLabel } from "./format.js";
import { initNavSearch } from "./nav.js";
import { seasonRows, seasonValues, withRatios as ratios } from "./records.js";
import * as ui from "./ui.js";

const $ = (id) => document.getElementById(id);

let model;
let spec;
let form;
let CURRENT;
let SCORE_SEASON;
let TRAIN_THROUGH;
let SEASONS = [];
let byseason = new Map(); // season -> [player row, ...]

const state = { season: null, code: null, values: {} };

// ---------------------------------------------------------------- data

function loadSeasons(data) {
  byseason = new Map();
  for (const row of seasonRows(data)) {
    if (!byseason.has(row.season)) byseason.set(row.season, []);
    byseason.get(row.season).push(row);
  }
  // Newest first: the projected season, then every completed one.
  SEASONS = [...byseason.keys()].sort((a, b) => b - a);
  if (!SEASONS.includes(CURRENT)) SEASONS.unshift(CURRENT);
}

const players = (season) => byseason.get(season) || [];

/** One player's season, or undefined if he did not play in it. */
function row(season, code) {
  if (code === null || code === undefined) return undefined;
  return players(season).find((p) => p.code === code);
}

function ordered(season) {
  // A stable sort, biggest points total first.
  return [...players(season)].sort((a, b) => b.total_points - a.total_points);
}

const defaultCode = (season) => ordered(season)[0].code;

function medians() {
  return { ...spec.medians, [form.position_field]: "MID", [form.team_field]: spec.other_team };
}

function valuesFor(season, code) {
  const player = row(season, code);
  return player ? seasonValues(form, player) : medians();
}

// ---------------------------------------------------------------- ratios

const withRatios = (values) => ratios(form, values);

/** Hold every projected value inside the fitted range, in place. Also how
 *  Price Watch prices the season in progress. Returns the fields it moved. */
function clamp(values) {
  const moved = [];
  for (const name of form.numeric_names) {
    const bounds = spec.ranges[name];
    if (!bounds) continue;
    const original = values[name];
    values[name] = Math.min(Math.max(original, bounds.min), bounds.max);
    if (Math.abs(original - values[name]) > 1e-8 + 1e-5 * Math.abs(values[name])) moved.push(name);
  }
  return moved;
}

// ---------------------------------------------------------------- the form

const fieldSpec = () => Object.fromEntries(form.fields.map(([name, label, step, integer]) => [name, { label, step, integer }]));
const inputId = (name) => `lab-f-${name}`;

function chip(name, def) {
  const bounds = spec.ranges[name];
  let hint = form.help[name] || "";
  if (bounds) hint = `${hint} Seen ${fmt(bounds.min)} to ${fmt(bounds.max)}.`.trim();
  const nudge = fmt(form.steps[name] ?? def.step);
  return `<div class="stat-chip"><label class="chip-label" for="${inputId(name)}">${esc(def.label)}</label>`
    + '<div class="chip-row">'
    + `<button type="button" class="stepper" data-step="${name}" data-dir="-1" title="Down ${nudge}" aria-label="Decrease ${esc(def.label)}"><i class="bi bi-dash-lg"></i></button>`
    + `<input id="${inputId(name)}" data-field="${name}" class="chip-input" type="number" step="${def.step}" inputmode="decimal">`
    + `<button type="button" class="stepper" data-step="${name}" data-dir="1" title="Up ${nudge}" aria-label="Increase ${esc(def.label)}"><i class="bi bi-plus-lg"></i></button>`
    + `</div><div class="chip-hint">${esc(hint)}</div></div>`;
}

function buildForm() {
  const defs = fieldSpec();
  const groups = form.groups.map(([title, names]) =>
    `<fieldset class="group"><legend class="group-title">${esc(title)}</legend>`
    + `<div class="group-fields">${names.map((n) => chip(n, defs[n])).join("")}</div></fieldset>`);

  const positions = spec.positions.map((p) =>
    `<div class="form-check form-check-inline"><input class="form-check-input" type="radio" name="lab-pos" `
    + `id="lab-pos-${p}" value="${p}"><label class="form-check-label" for="lab-pos-${p}">${p}</label></div>`).join("");
  const teams = [`<option value="${esc(spec.other_team)}">Any other club</option>`,
    ...spec.teams_retained.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`)].join("");

  groups.push('<fieldset class="group"><legend class="group-title">Role</legend>'
    + '<div class="group-fields role-fields">'
    + `<div class="field"><div class="field-label">Position</div><div class="pos-picker" role="radiogroup" aria-label="Position">${positions}</div></div>`
    + `<div class="field field-wide"><label class="field-label" for="lab-team">Club</label><select id="lab-team" class="select">${teams}</select>`
    + '<div class="field-hint">Clubs with too little history in the data share one setting.</div></div>'
    + "</div></fieldset>");
  $("lab-groups").innerHTML = groups.join("");
}

/** Put a set of values into the inputs. */
function fillForm(values) {
  for (const name of form.form_names) {
    const el = $(inputId(name));
    const v = values[name];
    el.value = v === null || v === undefined ? "" : String(v);
  }
  const position = values[form.position_field] || "MID";
  document.querySelectorAll('input[name="lab-pos"]').forEach((r) => { r.checked = r.value === position; });
  $("lab-team").value = values[form.team_field] || spec.other_team;
}

/** Read the inputs back. A blank box is null, as the form has always held it. */
function readForm() {
  const values = {};
  for (const name of form.form_names) {
    const raw = $(inputId(name)).value;
    values[name] = raw === "" ? null : Number(raw);
  }
  values[form.position_field] = document.querySelector('input[name="lab-pos"]:checked')?.value || "MID";
  values[form.team_field] = $("lab-team").value;
  return values;
}

// ---------------------------------------------------------------- the pickers

const labelOf = (p) => `${p.web_name} · ${p.team_name}, ${p.element_type}`;
let labels = new Map(); // label -> code

function renderSeasonOptions() {
  $("lab-season").innerHTML = SEASONS.map((s) =>
    `<option value="${s}">${seasonLabel(s)}${s === CURRENT ? " · projected" : ""}</option>`).join("");
  $("lab-season").value = String(state.season);
}

function renderPlayerOptions() {
  labels = new Map();
  const seen = new Set();
  const options = ordered(state.season).map((p) => {
    let label = labelOf(p);
    if (seen.has(label)) label = `${label} #${p.code}`; // two of the same name and club
    seen.add(label);
    labels.set(label, p.code);
    return `<option value="${esc(label)}"></option>`;
  });
  $("lab-players").innerHTML = options.join("");
  showPlayerLabel();
}

function showPlayerLabel() {
  const player = row(state.season, state.code);
  const input = $("lab-player");
  input.value = player ? [...labels].find(([, code]) => code === player.code)?.[0] ?? "" : "";
}

// ---------------------------------------------------------------- the answer

function edited() {
  const unedited = valuesFor(state.season, state.code);
  return form.form_names.some((name) => asFloat(state.values[name]) !== asFloat(unedited[name]))
    || [form.position_field, form.team_field].some((f) => state.values[f] !== unedited[f]);
}

function heldNote(held, values) {
  if (!held.length) return "";
  const names = Object.fromEntries(form.numeric_fields.map(([name, label]) => [name, label]));
  const items = held.map((name) => `<li>${esc(names[name] || name)} held at ${fmt(values[name])}.</li>`);
  return '<div class="flag"><div class="flag-title"><i class="bi bi-info-circle-fill"></i> '
    + `Held inside what the model has seen</div><ul>${items.join("")}</ul>`
    + '<p class="fine">Projected figures beyond the training range are held at its edge, as '
    + "Price Watch does, rather than extrapolated.</p></div>";
}

function projectedReality(player, predicted) {
  const lines = [`<p class="fine">FPL sets his ${seasonLabel(CURRENT + 1)} price in August ${CURRENT + 1}. `
    + "Until then, this is the forecast Price Watch shows from his form so far.</p>"];
  // Price Watch works points per game and per £m out from the unrounded
  // projected totals; the form holds whole points, so a few players land a
  // penny or two apart. Said rather than hidden.
  const gap = Math.abs(player.pred - predicted);
  if (gap < 0.005) {
    lines.push('<p class="fine verified"><i class="bi bi-check2-circle"></i> Same answer as Price Watch, to the penny.</p>');
  } else if (gap < 0.05) {
    lines.push(`<p class="fine">Within £${fixed(gap, 2)}m of Price Watch, which works its ratios out `
      + "from the projected totals before rounding them to whole numbers.</p>");
  }
  return `<div>${lines.join("")}</div>`;
}

/** What FPL actually did, for an unedited season. */
function reality(values, predicted) {
  const player = row(state.season, state.code);
  if (!player) return "";
  if (edited()) {
    return '<p class="fine">Edited: this is no longer his real season, so there is no real '
      + "price to compare against.</p>";
  }
  if (state.season === CURRENT) return projectedReality(player, predicted);

  const lines = [];
  const actual = player.next_cost;
  if (actual !== null && actual !== undefined) {
    const miss = predicted - actual;
    const close = Math.abs(miss) < 0.05;
    lines.push('<div class="reality"><span class="reality-label">What FPL actually did</span>'
      + `<span class="reality-text">Priced him at £${fixed(actual, 1)}m in August ${state.season + 1}, `
      + `<strong>${close ? "on the money" : `£${fixed(Math.abs(miss), 2)}m ${miss > 0 ? "below" : "above"}`}</strong>`
      + `${close ? "." : " the model's call."}</span></div>`);
    if (state.season <= TRAIN_THROUGH) {
      lines.push('<p class="fine">The model learned from this season, so a close call here is not a test '
        + `of it. ${seasonLabel(SCORE_SEASON)} is the season it never saw.</p>`);
    } else if (state.season === SCORE_SEASON) {
      lines.push('<p class="fine">The model never saw this season, so this is a fair test.</p>');
    }
  } else {
    lines.push(`<p class="fine">He did not return for ${seasonLabel(state.season + 1)}, so FPL never priced him.</p>`);
  }
  return `<div>${lines.join("")}</div>`;
}

function update() {
  // The form holds games played; the model wants FPL's two ratios.
  const values = withRatios(state.values);
  const season = state.season;
  // The end price as typed, before any clamping below: the bar shows his
  // real price, not the edge of the training range.
  const endPrice = asFloat(values.final_cost);
  let held = [];
  if (season === CURRENT) {
    // Priced as Price Watch prices it: every input held inside the training
    // range. Otherwise a projected 344 points over a £4.6m price derives a
    // points-per-£m no player has ever had.
    for (const name of form.numeric_names) values[name] = asFloat(values[name]);
    held = clamp(values);
  }
  const interval = model.predict(values);
  const predicted = interval.pred;
  const start = asFloat(values.start_cost);

  const player = row(season, state.code);
  let who;
  if (player) {
    const meta = season === CURRENT
      ? `${seasonLabel(season)} so far, projected from ${fmt(player.games_played)} gameweeks to 38`
      : `${seasonLabel(season)} season`;
    who = ui.playerHeader(player.web_name, player.team_name, player.element_type,
      `<div class="player-meta">${esc(meta)} · <a href="player.html?code=${player.code}">Player page</a></div>`);
  } else {
    who = ui.playerHeader("An average player", null, values[form.position_field],
      `<div class="player-meta">Every figure starts at the median of the `
      + `${spec.meta.training_rows.toLocaleString("en-GB")} seasons the model learned from.</div>`);
  }

  const tag = ui.answerTag(model, interval, start, `Predicted ${seasonLabel(season + 1)} price`);

  // Start and end price (today's, for a season still running) as cards rather
  // than ticks on the bar; for an unedited completed season, the price FPL
  // went on to set too, which also stays on the bar.
  let actual = null;
  if (player && season !== CURRENT && !edited()) {
    actual = player.next_cost === null || player.next_cost === undefined ? null : Number(player.next_cost);
  }
  const cards = [["Start price", start, "start"],
    [season === CURRENT ? "Today's price" : "End price", endPrice, "end"]];
  if (actual !== null) cards.push([`FPL set, ${seasonLabel(season + 1)}`, actual, "actual"]);

  const body = ui.answerBody(interval, start, "his start price", "Start", {
    extra: reality(values, predicted), actual, referenceOnBar: false, cards: ui.priceCards(cards),
  });
  const why = ui.whyThisPrice(model, values, ["Start price", start]);
  const flags = season === CURRENT ? heldNote(held, values) : ui.outOfRange(model, values, asFloat);

  $("lab-head").innerHTML = who + tag;
  $("lab-tag").innerHTML = "";
  $("lab-answer").innerHTML = body;
  $("lab-flags").innerHTML = flags;
  $("lab-why").innerHTML = why.html;
  why.mount($("lab-why"));
}

// ---------------------------------------------------------------- wiring

/** Load a season/player into the form and redraw. */
function load(season, code, values = null) {
  state.season = season;
  state.code = code;
  state.values = values || valuesFor(season, code);
  fillForm(state.values);
  update();
  showPlayerLabel();
}

function changeSeason(season) {
  // New season, new player list: the same player if he played in it.
  const keep = row(season, state.code) ? state.code : defaultCode(season);
  state.season = season;
  renderPlayerOptions();
  load(season, keep);
}

function step(name, direction) {
  const current = asFloat(readForm()[name]);
  let value = current + direction * (form.steps[name] ?? 1);
  value = Math.max(value, 0);
  if (name === form.appearances_field) value = Math.min(value, form.max_appearances);
  const integer = form.fields.find(([n]) => n === name)[3];
  value = integer ? pyRound(value, 0) : pyRound(value, 2);
  $(inputId(name)).value = String(value);
  edit();
}

function edit() {
  state.values = readForm();
  update();
}

function pickPlayer() {
  const input = $("lab-player");
  const code = labels.get(input.value);
  if (code === undefined) return false;
  if (code !== state.code) load(state.season, code);
  return true;
}

function wire() {
  $("lab-season").addEventListener("change", (event) => changeSeason(Number(event.target.value)));

  const picker = $("lab-player");
  // A datalist filters on what is typed, so clear the box on focus to offer
  // the whole list, and put the name back if nothing was chosen.
  picker.addEventListener("focus", () => { picker.value = ""; });
  picker.addEventListener("input", pickPlayer);
  picker.addEventListener("change", pickPlayer);
  picker.addEventListener("blur", () => { if (!pickPlayer()) showPlayerLabel(); });

  $("lab-blank").addEventListener("click", () => load(state.season, null, medians()));
  $("lab-reset").addEventListener("click", () => {
    load(state.season, state.code, state.code === null ? medians() : valuesFor(state.season, state.code));
  });

  let timer;
  $("lab-groups").addEventListener("input", (event) => {
    if (!event.target.matches("[data-field]")) return;
    clearTimeout(timer);
    timer = setTimeout(edit, 250);
  });
  $("lab-groups").addEventListener("change", edit);
  $("lab-groups").addEventListener("click", (event) => {
    const button = event.target.closest("[data-step]");
    if (button) step(button.dataset.step, Number(button.dataset.dir));
  });
}

async function main() {
  initNavSearch();
  const target = $("lab-root");
  let data;
  try {
    [model, data] = await Promise.all([loadModel(), loadJson("seasons")]);
  } catch (error) {
    showError(target, error);
    return;
  }
  spec = model.spec;
  form = spec.form;
  CURRENT = spec.meta.predict_season;
  SCORE_SEASON = spec.meta.score_season;
  TRAIN_THROUGH = spec.meta.train_through;
  loadSeasons(data);
  buildForm();

  // ?season=<year>&player=<code> opens that season, as Price Watch links.
  const query = new URLSearchParams(location.search);
  let season = Number(query.get("season"));
  if (!SEASONS.includes(season)) season = SCORE_SEASON;
  let code = Number(query.get("player"));
  if (!row(season, code)) code = defaultCode(season);

  state.season = season;
  renderSeasonOptions();
  renderPlayerOptions();
  wire();
  load(season, code);
}

main();
