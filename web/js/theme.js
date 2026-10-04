// The visual vocabulary for what CSS cannot reach: chart colours and the
// club shirts, which are drawn SVG. The hex values mirror the custom
// properties at the top of css/style.css; change one, change both.
//
// The world is FPL's own transfer market: aubergine chrome, a striped pitch,
// shirts in club colours, a price tag under every shirt. Green and pink-red
// are reserved for price direction and nothing else, which is why the
// position colours avoid both.

import { fixed } from "./format.js";

export const AUBERGINE = "#2b0033";
export const INK = "#1b0a21";
export const INK_SOFT = "#5b4a63";
export const LINE = "#e6e0ea";
export const SURFACE = "#ffffff";
export const CYAN = "#05e2ff";
export const RISE = "#007a3f";
export const FALL = "#d6004f";

export const FONT = "Barlow, system-ui, sans-serif";
export const FONT_FIGURES = "'Barlow Condensed', Barlow, system-ui, sans-serif";

/** One threshold for "moved": FPL prices move in tenths. */
export const MOVE_THRESHOLD = 0.1;

export const POSITION_COLOURS = { GK: "#f5b400", DEF: "#00b8d4", MID: "#7c4dff", FWD: "#ff6d00" };
export const POSITION_SYMBOLS = { GK: "diamond", DEF: "square", MID: "triangle-up", FWD: "circle" };

const BODY = "M18 22 L18 58 L46 58 L46 22 L46 9 L38 4 Q32 10 26 4 L18 9 Z";
const LEFT_SLEEVE = "M18 9 L5 17 L11 28 L18 23 Z";
const RIGHT_SLEEVE = "M46 9 L59 17 L53 28 L46 23 Z";
const OUTLINE = "M26 4 Q32 10 38 4 L46 9 L59 17 L53 28 L46 23 L46 58 L18 58 "
  + "L18 23 L11 28 L5 17 L18 9 Z";

let kits = {};
let neutral = ["#d9d2de", "#d9d2de", "#5b4a63", null];
const shirts = new Map();

/** Kit colours come from model.json, so Python's table stays the one copy. */
export function setKits(table, neutralKit) {
  kits = table;
  neutral = neutralKit;
  shirts.clear();
}

/** A club's home shirt as an SVG data URI, for an <img>. */
export function shirtUri(team) {
  const key = team || "";
  if (shirts.has(key)) return shirts.get(key);
  const [body, sleeves, trim, stripe] = kits[key] || neutral;
  const stripes = stripe
    ? `<g clip-path="url(#b)">${[21, 29, 37]
        .map((x) => `<rect x="${x}" y="0" width="4" height="64" fill="${stripe}"/>`)
        .join("")}</g>`
    : "";
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    + `<defs><clipPath id="b"><path d="${BODY}"/></clipPath></defs>`
    + `<path d="${BODY}" fill="${body}"/>${stripes}`
    + `<path d="${LEFT_SLEEVE}" fill="${sleeves}"/><path d="${RIGHT_SLEEVE}" fill="${sleeves}"/>`
    + `<path d="M26 4 Q32 10 38 4" fill="none" stroke="${trim}" stroke-width="3"/>`
    + `<path d="${OUTLINE}" fill="none" stroke="rgba(27,10,33,0.35)" stroke-width="1.2" `
    + 'stroke-linejoin="round"/></svg>';
  const uri = `data:image/svg+xml;base64,${btoa(svg)}`;
  shirts.set(key, uri);
  return uri;
}

/** "rise", "fall" or "hold", on the one shared threshold. */
export function direction(delta) {
  if (delta >= MOVE_THRESHOLD) return "rise";
  if (delta <= -MOVE_THRESHOLD) return "fall";
  return "hold";
}

/** £7.5m, or +£0.6m / −£0.4m with a true minus sign. */
export function money(value, signed = false, places = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  const text = `£${fixed(Math.abs(value), places)}m`;
  if (!signed) return value >= 0 ? text : `−${text}`;
  if (Number(fixed(Math.abs(value), places)) === 0) return `±${text}`;
  return value > 0 ? `+${text}` : `−${text}`;
}
