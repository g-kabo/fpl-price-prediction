// The transfer list: one row per player, sortable by any column. Shared by
// Price Watch, whose rows open the player card, and the Clubs page, whose
// rows link to the player page.
//
// Each row needs `ref` (the price the move is read against) and `delta`
// (pred - ref) beside the board.json fields.

import { esc, fixed, fold } from "./format.js";
import { money } from "./theme.js";
import * as ui from "./ui.js";

/** The columns: [key, player field, numeric?]. A numeric one starts
 *  biggest-first, the player name A to Z, and a second click on the same
 *  header reverses it. */
export const COLUMNS = [
  ["player", "name_key", false],
  ["points", "points_now", true],
  ["minutes", "minutes_now", true],
  ["selected", "selected_now", true],
  ["ref", "ref", true],
  ["pred", "pred", true],
  ["move", "delta", true],
];
/** Points per £m of today's price, offered after "Sel." where a page wants it. */
const VALUE_COLUMN = ["value", "value_now", true];
/** The forecast record, offered after the player where a page wants it. It
 *  starts at the highest kind, a second click starts at the lowest, and a
 *  player with no record comes last either way. */
const TAG_COLUMN = ["tag", "tag_rank", true];

const COLUMN = Object.fromEntries([...COLUMNS, VALUE_COLUMN, TAG_COLUMN].map(([key, field, numeric]) => [key, [field, numeric]]));

function columnsFor(value, tags) {
  const columns = value ? [...COLUMNS.slice(0, 4), VALUE_COLUMN, ...COLUMNS.slice(4)] : COLUMNS;
  return tags ? [columns[0], TAG_COLUMN, ...columns.slice(1)] : columns;
}

export const DEFAULT_SORT = { col: "move", desc: true };

const missing = (v) => v === null || v === undefined || Number.isNaN(v);

function compare(sort) {
  const [field] = COLUMN[sort.col] || COLUMN.move;
  return (a, b) => {
    const x = a[field];
    const y = b[field];
    if (missing(x) !== missing(y)) return missing(x) ? 1 : -1; // missing last, either way
    let order = 0;
    if (!missing(x)) order = typeof x === "string" ? (x < y ? -1 : x > y ? 1 : 0) : x - y;
    if (sort.desc) order = -order;
    if (order !== 0) return order;
    // Ties fall back to the predicted move, so equal points or minutes still
    // come out in a meaningful order rather than whatever order they arrived.
    const dx = a.delta;
    const dy = b.delta;
    if (missing(dx) !== missing(dy)) return missing(dx) ? 1 : -1;
    return missing(dx) ? 0 : dy - dx;
  };
}

/** The rows sorted by `sort`, as a new array. */
export function sortRows(rows, sort) {
  return rows.map((p) => ({
    ...p,
    name_key: fold(p.web_name),
    value_now: p.price_now > 0 ? (p.points_now || 0) / p.price_now : null,
    tag_rank: p.record ? ui.RECORD_KINDS.length - ui.RECORD_KINDS.indexOf(ui.recordKind(p.record)) : null,
  })).sort(compare(sort));
}

/** The sort after a click on header `key`: the same header again reverses
 *  the order, a new one starts at its natural end. */
export function nextSort(sort, key) {
  return key === sort.col ? { col: key, desc: !sort.desc } : { col: key, desc: COLUMN[key][1] };
}

function sortHeader(sort, key, label) {
  const active = sort.col === key;
  const icon = active ? (sort.desc ? "bi-caret-down-fill" : "bi-caret-up-fill") : "bi-chevron-expand";
  return `<button type="button" class="sort-col${key !== "player" && key !== "tag" ? " num" : ""}${active ? " is-active" : ""}" `
    + `data-sort="${key}" title="Sort by ${esc(label)}">${esc(label)}<i class="bi ${icon}"></i></button>`;
}

function row(p, href, value, records, tags) {
  const open = href ? `<a class="tl-row" href="${href(p)}">` : `<button type="button" class="tl-row" data-code="${p.code}">`;
  const pill = records || tags ? ui.recordPill(p.record) : "";
  return open
    + `<span class="tl-player">${ui.shirt(p.team_name, "sm")}<span class="tl-who">`
    + `<span class="tl-name">${esc(p.web_name)}</span><span class="tl-sub${pill ? " tl-sub-record" : ""}"><span class="tl-id">${ui.positionPill(p.element_type)}`
    + `<span class="tl-club">${esc(p.team_name)}</span></span>${pill}</span></span></span>`
    + (tags ? `<span class="tl-tag">${pill}</span>` : "")
    + `<span class="num tl-stat">${Math.trunc(p.points_now || 0)}</span>`
    + `<span class="num tl-stat">${Math.trunc(p.minutes_now || 0).toLocaleString("en-GB")}</span>`
    + `<span class="num tl-stat">${fixed(Number(p.selected_now || 0), 1)}%</span>`
    + (value ? `<span class="num tl-stat">${p.value_now === null ? "–" : fixed(p.value_now, 1)}</span>` : "")
    + `<span class="num tl-now">${money(p.ref)}</span><span class="num tl-pred">${money(p.pred)}</span>`
    + `<span class="num">${ui.deltaChip(p.delta, "sm")}</span>${href ? "</a>" : "</button>"}`;
}

/** The header and rows, already sorted. `labels` names each column key;
 *  `href(p)` makes rows links rather than buttons carrying data-code;
 *  `value` adds points per £m (and the list needs the `tlist-value` class);
 *  `records` adds each player's forecast record, if any, under his name;
 *  `tags` gives it a sortable column (and the list needs the `tlist-tags`
 *  class), falling back to under his name where there is no room. */
export function listHtml(rows, sort, labels, href = null, { value = false, records = false, tags = false } = {}) {
  const head = `<div class="tlist-head">${columnsFor(value, tags).map(([key]) => sortHeader(sort, key, labels[key])).join("")}</div>`;
  return head + rows.map((p) => row(p, href, value, records, tags)).join("");
}
