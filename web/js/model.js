// The fitted price model, in the browser.
//
// A port of PriceModel.predict_with_interval and form.contributions. The
// model is linear -- price = const + Σ βx -- and the interval is the usual
// OLS prediction interval for a new observation, so nothing here needs more
// than the weights, their covariance and the residual variance, all shipped
// in model.json. web/tests/parity.mjs checks it against Python.

import { asFloat } from "./format.js";

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

  /** One price decomposed into its terms; see form.contributions. */
  function contributions(values, topN = 12) {
    const x = design(values);
    const intercept = beta[0];
    const terms = [];
    columns.forEach((column, i) => {
      const value = x[i + 1];
      const b = beta[i + 1];
      const contribution = b * value;
      if (Math.abs(contribution) < 1e-9) return;
      terms.push({ column, value, beta: b, contribution });
    });
    terms.sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));

    const material = terms.filter((t) => Math.abs(t.contribution) >= spec.material_contribution);
    const shown = material.slice(0, topN);
    const drawn = new Set(shown.map((t) => t.column));
    const pooled = terms.filter((t) => !drawn.has(t.column));
    return {
      intercept,
      shown,
      rest: pooled.reduce((sum, t) => sum + t.contribution, 0),
      nRest: pooled.length,
      total: intercept + terms.reduce((sum, t) => sum + t.contribution, 0),
    };
  }

  /** Contributions as ordered waterfall steps: [label, amount, measure]. */
  function steps(parts) {
    const out = [["Model baseline", parts.intercept, "absolute"]];
    for (const t of parts.shown) out.push([spec.term_labels[t.column] || t.column, t.contribution, "relative"]);
    if (parts.nRest) out.push([`${parts.nRest} smaller terms`, parts.rest, "relative"]);
    out.push(["Predicted price", parts.total, "total"]);
    return out;
  }

  return { spec, design, predict, contributions, steps, termLabel: (c) => spec.term_labels[c] || c.replace(/_/g, " ") };
}
