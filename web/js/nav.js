// Player search in every page's header: type a name, land on his page.
//
// Reads data/players.json -- everyone since the first season, current or
// departed -- and only when the box is first used, so a page that never
// searches never loads it. The box is added by script rather than written
// into each page, so the four headers can't drift apart.

import { loadJson } from "./data.js";
import { esc, fold, seasonLabel } from "./format.js";
import { positionPill, shirt } from "./ui.js";

/** Results shown at once. */
const LIMIT = 8;

let index = null;
let loading = null;

/** players.json as objects, loaded once per page. */
function loadIndex() {
  if (index) return Promise.resolve(index);
  loading ??= loadJson("players").then((data) => {
    const rows = data.rows.map((raw) => Object.fromEntries(data.fields.map((f, i) => [f, raw[i]])));
    const current = Math.max(...rows.map((r) => r.last_season));
    index = rows.map((r) => ({
      ...r,
      current: r.last_season === current,
      keys: [r.web_name, ...r.other_names].map((n) => fold(n).replace(/ss/g, "s")),
    }));
    return index;
  });
  return loading;
}

/** 0 for a name that starts with the text, 1 for a word in it that does,
 *  2 for anywhere else, null for no match. */
function matchRank(keys, needle) {
  let best = null;
  for (const key of keys) {
    let rank = null;
    if (key.startsWith(needle)) rank = 0;
    else if (key.split(/[^a-z0-9]+/).some((word) => word.startsWith(needle))) rank = 1;
    else if (key.includes(needle)) rank = 2;
    if (rank !== null && (best === null || rank < best)) best = rank;
  }
  return best;
}

/** The best matches: closest name first, then current players, then the
 *  most recently seen. */
export function searchPlayers(players, text, limit = LIMIT) {
  const needle = fold(text).replace(/ss/g, "s").trim();
  if (!needle) return [];
  const hits = [];
  for (const p of players) {
    const rank = matchRank(p.keys, needle);
    if (rank !== null) hits.push([rank, p]);
  }
  hits.sort(([ra, a], [rb, b]) => ra - rb
    || Number(b.current) - Number(a.current)
    || b.last_season - a.last_season
    || a.web_name.localeCompare(b.web_name));
  return hits.slice(0, limit).map(([, p]) => p);
}

export const playerUrl = (code) => `player.html?code=${code}`;
export const clubUrl = (team) => `club.html?team=${encodeURIComponent(team)}`;

function option(p, id, active) {
  const when = p.current ? "" : `<span class="sr-when">Last in FPL ${seasonLabel(p.last_season)}</span>`;
  return `<a role="option" id="${id}" class="sr-option${active ? " is-active" : ""}" `
    + `aria-selected="${active}" href="${playerUrl(p.code)}" tabindex="-1">${shirt(p.team_name, "sm")}`
    + `<span class="sr-who"><span class="sr-name">${esc(p.web_name)}</span>`
    + `<span class="sr-sub">${positionPill(p.element_type)}<span>${esc(p.team_name || "")}</span>${when}</span>`
    + "</span></a>";
}

/** Make `input` a player search, with its results in `list`. */
export function attachSearch(input, list) {
  let results = [];
  let active = -1;
  const prefix = `${list.id}-opt`;

  function close() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  function render() {
    if (!input.value.trim()) {
      results = [];
      close();
      return;
    }
    if (!results.length) {
      list.innerHTML = '<p class="sr-none">No player by that name since 2017-18.</p>';
    } else {
      list.innerHTML = results.map((p, i) => option(p, `${prefix}-${i}`, i === active)).join("");
    }
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    if (active >= 0) input.setAttribute("aria-activedescendant", `${prefix}-${active}`);
    else input.removeAttribute("aria-activedescendant");
  }

  async function update() {
    const text = input.value;
    let players;
    try {
      players = await loadIndex();
    } catch (error) {
      console.error(error);
      list.innerHTML = '<p class="sr-none">Could not load the player list.</p>';
      list.hidden = false;
      return;
    }
    if (input.value !== text) return; // a newer keystroke is on its way
    results = searchPlayers(players, text);
    active = results.length ? 0 : -1;
    render();
  }

  input.addEventListener("focus", () => { loadIndex().catch(() => {}); if (input.value.trim()) update(); });
  input.addEventListener("input", update);
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!results.length) return;
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      active = (active + step + results.length) % results.length;
      render();
      list.querySelector(".is-active")?.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter") {
      if (active < 0 || !results[active]) return;
      event.preventDefault();
      location.href = playerUrl(results[active].code);
    } else if (event.key === "Escape") {
      if (!list.hidden) { event.preventDefault(); close(); } else input.blur();
    }
  });
  // Mousedown would blur the box and close the list before the click lands.
  list.addEventListener("mousedown", (event) => event.preventDefault());
  input.addEventListener("blur", close);
}

const MARKUP = '<div class="nav-search" role="search">'
  + '<button type="button" class="nav-search-toggle" aria-label="Find a player" aria-expanded="false" '
  + 'aria-controls="nav-search-box"><i class="bi bi-search"></i></button>'
  + '<div class="nav-search-box" id="nav-search-box"><i class="bi bi-search"></i>'
  + '<input type="search" class="nav-search-input" id="nav-search-input" placeholder="Find any player" '
  + 'aria-label="Find any player since 2017-18" role="combobox" aria-expanded="false" '
  + 'aria-controls="nav-search-list" aria-autocomplete="list" autocomplete="off" spellcheck="false">'
  + '<kbd class="nav-search-key" aria-hidden="true">/</kbd>'
  + '<div class="search-results" id="nav-search-list" role="listbox" aria-label="Players" hidden></div>'
  + "</div></div>";

/** Add the search to the header. On a phone it folds into an icon. */
export function initNavSearch() {
  const header = document.querySelector(".header-inner");
  if (!header || header.querySelector(".nav-search")) return;
  header.insertAdjacentHTML("beforeend", MARKUP);
  const root = header.querySelector(".nav-search");
  const input = root.querySelector(".nav-search-input");
  const toggle = root.querySelector(".nav-search-toggle");
  attachSearch(input, root.querySelector(".search-results"));

  // Keep focus in the box when the icon is pressed again, so the click
  // closes it rather than the blur closing it and the click reopening it.
  toggle.addEventListener("mousedown", (event) => event.preventDefault());
  toggle.addEventListener("click", () => {
    const open = !root.classList.contains("is-open");
    root.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    if (open) input.focus();
  });
  input.addEventListener("blur", () => {
    root.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
  });

  // "/" jumps to the search, as on GitHub and YouTube, unless typing already.
  document.addEventListener("keydown", (event) => {
    if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
    const target = event.target;
    if (target.closest?.("input, textarea, select, [contenteditable]")) return;
    event.preventDefault();
    if (getComputedStyle(toggle).display !== "none") toggle.click();
    else input.focus();
  });
}
