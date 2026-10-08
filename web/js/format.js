// Number and text helpers. Python's rounding is half-to-even on the exact
// binary value, JavaScript's toFixed rounds an exact tie up; FPL's ratios
// (45 points in 20 games is exactly 2.25) hit that, so rounding goes through
// here to land on the same answer as the Python the model was built with.

/** x to d decimals as Python's format() would print it. */
export function fixed(x, d = 1) {
  const negative = x < 0;
  const abs = Math.abs(x);
  const digits = abs.toFixed(Math.min(100, d + 30)); // the exact expansion
  const dot = digits.indexOf(".");
  const tail = digits.slice(dot + 1 + d);
  let out;
  if (/^50*$/.test(tail)) {
    // An exact tie: keep the digit when it is even, otherwise round up.
    const kept = digits.slice(0, d === 0 ? dot : dot + 1 + d);
    const last = Number(kept.slice(-1));
    out = last % 2 === 0 ? kept : abs.toFixed(d);
  } else {
    out = abs.toFixed(d);
  }
  return negative ? `-${out}` : out;
}

/** Python's round(x, d). */
export function pyRound(x, d = 0) {
  return Number(fixed(x, d));
}

/** A form value as a number: blank or junk is 0, as the form has always read it. */
export function asFloat(value) {
  if (value === null || value === undefined || value === "") return 0;
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

/** Compact figures for hints and cells: 1.2M, 12k, 5, 5.25. */
export function fmt(value) {
  value = Number(value);
  if (Math.abs(value) >= 1_000_000) return `${fixed(value / 1_000_000, 1)}M`;
  if (Math.abs(value) >= 10_000) return `${fixed(value / 1_000, 0)}k`;
  if (Number.isInteger(value)) return String(value);
  return fixed(value, 2);
}

/** Four significant figures, positional, trailing zeros trimmed. */
export function sig4(value) {
  const x = Math.abs(value);
  if (x === 0) return "0";
  const exponent = Math.floor(Math.log10(x));
  const decimals = Math.max(0, 3 - exponent);
  const text = Number(x.toPrecision(4)).toFixed(decimals);
  return text.includes(".") ? text.replace(/0+$/, "").replace(/\.$/, "") : text;
}

/** Signed fixed, like Python's {:+.4f}. */
export function signed(value, places) {
  const text = fixed(Math.abs(value), places);
  return value < 0 ? `-${text}` : `+${text}`;
}

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Escape text for HTML. Names come from an API, so nothing goes in raw. */
export function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

/** Case- and accent-insensitive: "joao" finds João, "gross" finds Groß. */
export function fold(text) {
  return String(text ?? "")
    .replace(/ß/g, "ss")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^\x00-\x7f]/g, "")
    .toLowerCase();
}

/** 2025 -> "2025-26". */
export function seasonLabel(season) {
  return `${season}-${String((season + 1) % 100).padStart(2, "0")}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-08" -> "8 Oct". Spelled out here because en-GB has "Sept". */
export function dayMonth(iso) {
  const [, month, day] = iso.split("-").map(Number);
  return `${day} ${MONTHS[month - 1]}`;
}
