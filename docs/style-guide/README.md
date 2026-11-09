# FPL house style

The look of [FPL Price Prediction](https://g-kabo.github.io/fpl-price-prediction/),
written up so other FPL apps can share it. Copy this folder into a new project:

- `fpl-theme.css`: the colour tokens, base styles and core components, ready to load.
- `README.md` (this file): what each piece is for, and the rules that keep apps consistent.

The source of truth is still the Price Prediction site (`web/css/style.css` and
`web/js/theme.js`). If the site's colours change, update this folder too.
`DESIGN.md` in the repo root covers that one site's layouts in more detail.

---

## 1. The idea

**Use the game's own look, not a generic dashboard.** FPL players open the
official app every week. Deep aubergine chrome, position pills, price tags,
a striped pitch and club shirts are things they already recognise, so an app
built from them feels familiar and trustworthy straight away.

- Aubergine frames the page at the top and bottom; the working area in between is light.
- Numbers lead. Prices and stats are set big, heavy and condensed.
- Colour is used sparingly, and always means something.
- Light theme only. A dark mode would need its own colour steps, not an inversion.

### The four rules

1. **Green and pink-red mean direction only.** They show a value going up or
   down: price, points, rank. Never success/error, never decoration. (The pitch
   turf and club kits are exempt; they're part of the game world.)
2. **Cyan is chrome.** It marks the brand, the active tab and the current
   selection. It never stands for a value in a chart.
3. **One threshold for "moved".** FPL prices move in £0.1m steps, so a change
   of at least ±£0.1m is a rise or fall and anything smaller "holds". Every chip,
   colour and word uses that one threshold.
4. **Every position gets a colour and a shape.** Colour is never the only cue.

---

## 2. Colour

### Chrome

| Token | Hex | Use |
|---|---|---|
| `--aubergine` | `#2b0033` | Header, hero band, footer, list header row, price tags, selected options, chart hover labels. The brand colour. |
| `--aubergine-2` | `#3b0a47` | A panel that drops out of the chrome (settings drawer). |
| `--aubergine-3` | `#57206a` | Links, focused field borders, scrollbar. |
| `--on-dark` | `#ffffff` | Main text on aubergine. |
| `--on-dark-soft` | `#dccbe3` | Secondary text on aubergine, inactive tabs. |
| `--cyan` | `#05e2ff` | Brand mark, active-tab underline, accent word in the hero title, selection, footer links. |

### Working surface

| Token | Hex | Use |
|---|---|---|
| `--paper` | `#f6f4f8` | Page background; stat tiles. |
| `--surface` | `#ffffff` | Panels, lists, chart backgrounds. |
| `--tint` | `#f1ebf4` | Row hover, segmented-control track, the "holds" chip. |
| `--ink` | `#1b0a21` | Body text and figures. |
| `--ink-soft` | `#5b4a63` | Secondary text, hints, axis labels, placeholders. |
| `--line` | `#e6e0ea` | Row dividers, panel borders, chart gridlines. |
| `--line-strong` | `#cbbfd2` | Control borders, table header rules. |

### Direction

| Token | Hex | Use |
|---|---|---|
| `--rise` | `#007a3f` | Rising values as text or bars on white (passes 4.5:1). |
| `--rise-fill` | `#00ff85` | Fill of the rise chip, with `--rise-on` text; rising figure on aubergine. |
| `--rise-on` | `#00341b` | Text on `--rise-fill`. |
| `--fall` | `#d6004f` | Falling values as text or bars on white. |
| `--fall-fill` | `#e0004d` | Fill of the fall chip, with white text. |
| `--fall-on-dark` | `#ff5c93` | Falling figure on aubergine. |

### Positions

| Position | Token | Hex | Text on it | Chart marker |
|---|---|---|---|---|
| GK | `--gk` | `#f5b400` | ink | diamond |
| DEF | `--def` | `#00b8d4` | ink | square |
| MID | `--mid` | `#7c4dff` | white | triangle-up |
| FWD | `--fwd` | `#ff6d00` | ink | circle |

These four deliberately avoid green and pink-red so they never read as direction.

### Pitch

`--pitch-a` `#16904a` and `--pitch-b` `#138643` alternate in 64px horizontal
stripes; markings are `--pitch-line` (white at 50%).

### Chart colours

- **Categorical** (series that need telling apart, not ranking), in order:
  `#5a1f6b` `#0091a8` `#ff6d00` `#007a3f` `#d6004f` `#f5b400` `#3b6fd4`,
  with `#a99bb1` for "other". Use at most seven; group the rest as other.
  If the chart also shows direction, drop the green and pink-red from this list.
- **Same measure at two times:** one hue, two lightnesses: `#c3a6cf` (earlier),
  `#5a1f6b` (later).
- **A different kind of number** (a forecast next to actuals): teal `#0091a8`.
- Zero lines `#cbbfd2`; gridlines `--line`.

---

## 3. Type

Two Google fonts, both free:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800&family=Barlow:wght@400;500;600;700&display=swap">
```

- **Barlow Condensed** (`--font-fig`): headings, prices, stats. Headings are uppercase.
- **Barlow** (`--font`): everything read as sentences, in sentence case.
  Never set running text in the condensed face.

| Role | Font | Size | Weight | Notes |
|---|---|---|---|---|
| Display | Condensed | `clamp(2.4rem, 4.4vw, 3.5rem)` | 800 | Page title in the hero; line-height 0.95; uppercase; one accent word in cyan. |
| Price | Condensed | 3.6rem | 800 | The headline figure inside a price tag. Tabular. |
| Headline | Condensed | 2rem | 800 | Section titles on the page; uppercase; aubergine. |
| Title | Condensed | 1.35rem | 700 | Titles inside panels; uppercase; aubergine. |
| Figure | Condensed | 1.15rem | 600–800 | Prices in rows. The predicted/new figure is heavier than the current one. |
| Body | Barlow | 1rem | 400 | Line-height 1.5; cap prose at 60–72ch. |
| Lede | Barlow | 1.1rem | 400 | Intro under the hero title, `--on-dark-soft`. |
| Label | Barlow | 0.88rem | 600 | List headers, chips, field labels. |
| Fine | Barlow | 0.85rem | 400 | Footnotes under charts, `--ink-soft`. |

### Writing numbers

- Money: **£7.5m**. Changes are signed with a true minus: **+£0.6m**, **−£0.4m**
  (U+2212, not a hyphen), and **±£0.0m** when it rounds to zero.
- Missing values: an en dash **–**.
- Seasons: **2026/27**.
- Always tabular numerals (`font-variant-numeric: tabular-nums`) so columns line up.

```js
const MOVE_THRESHOLD = 0.1;

function direction(delta) {
  if (delta >= MOVE_THRESHOLD) return "rise";
  if (delta <= -MOVE_THRESHOLD) return "fall";
  return "hold";
}

function money(value, signed = false, places = 1) {
  if (value == null || Number.isNaN(value)) return "–";
  const abs = Math.abs(value).toFixed(places);
  const text = `£${abs}m`;
  if (!signed) return value >= 0 ? text : `−${text}`;
  if (Number(abs) === 0) return `±${text}`;
  return value > 0 ? `+${text}` : `−${text}`;
}
```

---

## 4. Space, shape, depth, motion

**Spacing steps:** 4, 8, 12, 16, 24, 40px. Controls sit 8–12px apart; page
blocks are 40px apart.

**Corners:**

| Radius | Use |
|---|---|
| 4px | Position pills |
| 8px | Buttons, fields, brand mark |
| 10px (`--radius`) | Panels, lists, stat tiles |
| 14px | Large fields: the pitch, a main sheet |
| 999px | Chips that state something: status, delta, segmented controls |
| 6px 14px 14px 6px | The price tag (rounder on its free end) |

**Shadows:**

- Every resting container: `--shadow` (soft, aubergine-tinted).
- Only things about to open get more lift: a hovered shirt
  (`drop-shadow(0 8px 10px rgba(0,0,0,0.35))`), a side panel
  (`-20px 0 60px rgba(43,0,51,0.25)`) over a dimmed aubergine backdrop.
- Focus ring everywhere: `--focus`, violet so it never reads as a direction.

**Motion:** short and ease-out (`--ease-out`, 0.15s for hovers, about 0.5s
for a panel sliding in). Hovered cards lift a few px; sections in a new panel
rise in with small staggered delays. Remove all of it under
`prefers-reduced-motion` (the theme file does this).

---

## 5. Layout

- One centred column: `max-width: 1320px`, 24px side gutters (16px at ≤720px).
- A sticky 64px aubergine header, then an aubergine hero band with the page
  title, then light blocks, then an aubergine footer.
- Breakpoints used on the site: **1100px** (filters to two columns, side-by-side
  sheets stack), **900px** (two-column grids to one), **720px** (phone: tighter
  gutters, brand name hidden, list columns dropped to the essentials),
  **560px** and **420px** for the narrowest tweaks.
- On a phone, drop secondary columns rather than shrinking text.

### Page skeleton

```html
<div class="app-shell">
  <header class="site-header">
    <div class="wrap header-inner">
      <a class="brand" href="./"><span class="brand-mark"><i class="bi bi-tag-fill"></i></span><span>FPL <strong>App Name</strong></span></a>
      <nav class="nav-tabs-row">
        <a class="nav-tab active" href="./" aria-current="page">First page</a>
        <a class="nav-tab" href="second.html">Second page</a>
      </nav>
    </div>
  </header>
  <main>
    <section class="hero"><div class="wrap">
      <h1>Price <span class="accent">2026/27</span></h1>
      <p class="lede">One sentence on what this page answers.</p>
    </div></section>
    <section class="block"><div class="wrap">
      <div class="block-head"><h2 class="block-title">Section</h2></div>
      <div class="panel">…</div>
    </div></section>
  </main>
  <footer class="site-footer"><div class="wrap"><p>Data: the official FPL API.</p></div></footer>
</div>
```

For each new app, give the brand mark its own
[Bootstrap icon](https://icons.getbootstrap.com/) (Price Prediction uses
`bi-tag-fill`) and keep the "FPL **Name**" wordmark.

---

## 6. Components

All of these are in `fpl-theme.css`.

| Component | Class | Notes |
|---|---|---|
| Header tabs | `.nav-tab`, `.active` | Soft text, white on hover; active is white with a 3px cyan underline. |
| Ghost button | `.btn-ghost` | White, aubergine text, firm border; hover tints. There is no filled call-to-action button. |
| Button on chrome | `.btn-on-dark` | Transparent with a 28% white border. |
| Status chip | `.chip`, `.chip-warn` | Pills in the hero. The warn variant flips to white. |
| Delta chip | `.delta` + `.delta-sm/md/lg` + `.delta-rise/fall/hold` | Caret icon (`bi-caret-up-fill` / `bi-caret-down-fill`) plus the signed amount; hold reads "Holds". |
| Position pill | `.pos-pill` + `.pos-gk/def/mid/fwd` | Nearly square, condensed 700. |
| Price tag | `.tag`, `.tag-price` | Aubergine, punched hole on the left. Show the current price, then the new one. |
| Panel | `.panel`, `.section-title` | White, hairline border, ambient shadow, 20px 24px padding. |
| Field | `.field`, `.field-label` | 42px tall; plum border and violet ring on focus. |
| Segmented control | `.segmented` with `button[aria-pressed]` | Lilac track, aubergine selected. Inside `.hero`, translucent track and cyan selected. |
| List | `.list`, `.list-head`, `.list-row` | Aubergine header row over 60px white rows. Set `grid-template-columns` per list: one flexible name column, fixed stat columns (56–124px). |
| Pitch | `.pitch` | Striped turf for showing an XI. |

### Club shirts

Players are shown with a small SVG shirt in their club's home colours, never
crests or photos (those are trademarked). The kit table is in the Price
Prediction repo's `kits.py` (`body, sleeves, trim, stripe` per club, plus a
grey `NEUTRAL_KIT` for unknown clubs), and `shirtUri()` in `web/js/theme.js`
draws one as a data URI. Copy both; update the kits when clubs are promoted.

---

## 7. Charts

The site uses Plotly; the same settings carry over to any library.

```js
const layout = {
  plot_bgcolor: "#ffffff", paper_bgcolor: "#ffffff",
  font: { family: "Barlow, system-ui, sans-serif", color: "#1b0a21", size: 13 },
  hoverlabel: { bgcolor: "#2b0033", bordercolor: "#2b0033",
                font: { family: "Barlow, system-ui, sans-serif", size: 13, color: "#ffffff" }, align: "left" },
  xaxis: { showgrid: false, tickfont: { size: 12, color: "#5b4a63" } },
  yaxis: { gridcolor: "#e6e0ea", zeroline: false, tickfont: { size: 12, color: "#5b4a63" },
           tickprefix: "£", ticksuffix: "m" },
  showlegend: false,
};
const config = { displayModeBar: false, responsive: true };
```

- Gridlines on the value axis only, in `--line`.
- Hover labels in aubergine with white Barlow text.
- Value labels on bars in Barlow Condensed, `--ink-soft`.
- Dates as `1 Nov` (`tickformat: "%-d %b"`).
- Keep marker size fixed across filters; a mark that changes size reads as an encoding.
- Bars that go up or down use `--rise` / `--fall`. Position scatters use the
  position colours **and** shapes.
- Prefer labelling on hover or on the line end over a legend; when a legend is
  needed, put it horizontally above the plot.

---

## 8. Do and don't

**Do**
- Show a price change as a pair: today's price, then the new one, the new one heavier.
- Classify every change with the £0.1m threshold before picking a colour or word.
- Set every number in Barlow Condensed with tabular numerals and a true minus.
- Present players the way the game does: on a pitch, in a list, or on a player card.
- Honour reduced motion.

**Don't**
- Use green or pink-red for anything but direction.
- Use cyan to encode data.
- Use club crests, player photos or the Premier League's own logos.
- Build pages as a stacked form, then a card, then a chart.
- Invert the palette for dark mode.
