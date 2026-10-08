// Loading the JSON the export wrote, and the chrome every page shares.

import { esc, fixed } from "./format.js";
import { makeModel } from "./model.js";
import { setKits } from "./theme.js";

/** Fetch one of data/*.json. `fresh` skips the cache, for the hourly refresh. */
export async function loadJson(name, fresh = false) {
  const response = await fetch(`data/${name}.json${fresh ? `?t=${Date.now()}` : ""}`,
    fresh ? { cache: "no-store" } : undefined);
  if (!response.ok) throw new Error(`${name}.json: ${response.status}`);
  return response.json();
}

/** The model, with kits registered and the footer filled in. */
export async function loadModel() {
  const spec = await loadJson("model");
  setKits(spec.kits, spec.neutral_kit);
  const model = makeModel(spec);
  fillFooter(spec.meta);
  return model;
}

function fillFooter(meta) {
  const el = document.getElementById("footer-model");
  if (!el) return;
  el.textContent = `Linear model · ${meta.n_predictors} predictors · trained on `
    + `${meta.training_rows.toLocaleString("en-GB")} player-seasons · explains `
    + `${fixed(meta.rsquared_adj * 100, 1)}% of the variation in price (adjusted R²).`;
}

/** Say so on the page when something fails to load, rather than leave it blank. */
export function showError(target, error) {
  console.error(error);
  target.innerHTML = `<div class="load-error"><p>Could not load the data (${esc(error.message)}). `
    + "Try reloading the page.</p></div>";
}
