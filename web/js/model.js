// The fitted price model, in the browser.
//
// A port of PriceModel.predict_with_interval and form.contributions. The
// model is linear -- price = const + Σ βx -- and the interval is the usual
// OLS prediction interval for a new observation, so nothing here needs more
// than the weights, their covariance and the residual variance, all shipped
// in model.json. web/tests/parity.mjs checks it against Python.

import { asFloat } from "./format.js";

const PRICE_COLUMNS = new Set(["start_cost", "final_cost", "start_cost_sq", "final_cost_sq"]);
const PRICE_LABEL = "Overall price contribution";

/** Build the model from model.json. */
export function makeModel(spec) {
  const { columns, params, cov, scale, tcrit, other_team: other } = spec;
  const retained = new Set(spec.teams_retained);
  const numericNames = spec.form.numeric_names;
  const positionField = spec.form.position_field;
  const teamField = spec.form.team_field;
  const order = ["const", ...columns];
  const beta = order.map((name) => params[name]);

  /** The design row for one player, constant first. Mirrors
   *  features.build_design_matrix, including the squares and "never played". */
  function design(values) {
    const v = {};
    for (const name of numericNames) v[name] = asFloat(values[name]);
    const position = values[positionField] || "MID";
    const team = values[teamField] || other;
    const lumped = retained.has(team) ? team : other;
    const teamColumn = `team_name_${lumped.replace(/ /g, "_").replace(/'/g, "")}`;

    const x = columns.map((column) => {
      if (column === "start_cost_sq") return v.start_cost ** 2;
      if (column === "final_cost_sq") return v.final_cost ** 2;
      if (column === "no_mins") return v.minutes > 0 ? 0 : 1;
      if (column.startsWith("element_type_")) return position === column.slice(13) ? 1 : 0;
      if (column.startsWith("team_name_")) return column === teamColumn ? 1 : 0;
      return v[column];
    });
    return [1, ...x];
  }

  /** {pred, lower, upper}: the 95% interval is for a new observation. */
  function predict(values) {
    const x = design(values);
    let pred = 0;
    let variance = scale;
    for (let i = 0; i < x.length; i++) {
      pred += beta[i] * x[i];
      let row = 0;
      for (let j = 0; j < x.length; j++) row += cov[i][j] * x[j];
      variance += x[i] * row;
    }
    const half = tcrit * Math.sqrt(variance);
    return { pred, lower: pred - half, upper: pred + half };
  }

  /** Every term of one price as {column, value, beta, contribution}, and the
   *  intercept. Terms with no effect are left out. */
  function termList(values) {
    const x = design(values);
    const terms = [];
    columns.forEach((column, i) => {
      const value = x[i + 1];
      const b = beta[i + 1];
      const contribution = b * value;
      if (Math.abs(contribution) < 1e-9) return;
      terms.push({ column, value, beta: b, contribution });
    });
    return { intercept: beta[0], terms };
  }

  /** One price decomposed into its terms; see form.contributions. */
  function contributions(values, topN = 12) {
    const { intercept, terms } = termList(values);
    terms.sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));

    const material = terms.filter((t) => Math.abs(t.contribution) >= spec.material_contribution);
    const shown = material.slice(0, topN);
    const drawn = new Set(shown.map((t) => t.column));
    const pooled = terms.filter((t) => !drawn.has(t.column));
    const pooledPrice = pooled.filter((t) => PRICE_COLUMNS.has(t.column));
    return {
      intercept,
      shown,
      rest: pooled.reduce((sum, t) => sum + t.contribution, 0),
      nRest: pooled.length,
      // All four price terms together, wherever they fell; the waterfall
      // draws them as one bar (see steps).
      price: terms.filter((t) => PRICE_COLUMNS.has(t.column)).reduce((sum, t) => sum + t.contribution, 0),
      pricePooled: { amount: pooledPrice.reduce((sum, t) => sum + t.contribution, 0), count: pooledPrice.length },
      total: intercept + terms.reduce((sum, t) => sum + t.contribution, 0),
    };
  }

  /** Contributions as ordered waterfall steps: [label, amount, measure].
   *  The start and end price, and their squares, are one "Overall price
   *  contribution" here: the chart is about how much his price matters, not
   *  which of its four terms carries it. Tables and the narration keep the
   *  terms apart. */
  function steps(parts) {
    const rows = parts.shown.filter((t) => !PRICE_COLUMNS.has(t.column))
      .map((t) => [spec.term_labels[t.column] || t.column, t.contribution, "relative"]);
    rows.push([PRICE_LABEL, parts.price, "relative"]);
    rows.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
    const out = [["Model baseline", parts.intercept, "absolute"], ...rows];
    const nRest = parts.nRest - parts.pricePooled.count;
    if (nRest) out.push([`${nRest} smaller terms`, parts.rest - parts.pricePooled.amount, "relative"]);
    out.push(["Predicted price", parts.total, "total"]);
    return out;
  }

  /** How much each term moved between two sets of inputs, price terms
   *  combined as in `steps`: [[label, amount], ...], biggest first. Linear,
   *  so the amounts add up to the change in the prediction exactly. */
  function changeTerms(thenValues, nowValues) {
    const before = termList(thenValues);
    const after = termList(nowValues);
    const delta = new Map();
    for (const t of before.terms) delta.set(t.column, -t.contribution);
    for (const t of after.terms) delta.set(t.column, (delta.get(t.column) || 0) + t.contribution);

    let price = 0;
    const rows = [];
    for (const [column, amount] of delta) {
      if (PRICE_COLUMNS.has(column)) price += amount;
      else rows.push([spec.term_labels[column] || column, amount]);
    }
    rows.push([PRICE_LABEL, price]);
    const total = (side) => side.intercept + side.terms.reduce((sum, t) => sum + t.contribution, 0);
    const terms = rows.filter((r) => Math.abs(r[1]) >= 0.0005).sort((x, y) => Math.abs(y[1]) - Math.abs(x[1]));
    return { terms, before: total(before), after: total(after) };
  }

  return { spec, design, predict, contributions, steps, changeTerms, termLabel: (c) => spec.term_labels[c] || c.replace(/_/g, " ") };
}
