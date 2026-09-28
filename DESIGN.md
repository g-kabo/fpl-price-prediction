---
name: FPL Price Prediction
description: Who the model thinks FPL will reprice next season, shown in the game's own transfer-market grammar.
colors:
  aubergine: "#2b0033"
  aubergine-2: "#3b0a47"
  aubergine-3: "#57206a"
  on-dark: "#ffffff"
  on-dark-soft: "#dccbe3"
  cyan: "#05e2ff"
  ink: "#1b0a21"
  ink-soft: "#5b4a63"
  line: "#e6e0ea"
  line-strong: "#cbbfd2"
  paper: "#f6f4f8"
  surface: "#ffffff"
  tint: "#f1ebf4"
  rise: "#007a3f"
  rise-fill: "#00ff85"
  rise-on: "#00341b"
  fall: "#d6004f"
  fall-fill: "#e0004d"
  fall-on-dark: "#ff5c93"
  gk: "#f5b400"
  def: "#00b8d4"
  mid: "#7c4dff"
  fwd: "#ff6d00"
  pitch-a: "#16904a"
  pitch-b: "#138643"
  pitch-line: "rgba(255, 255, 255, 0.5)"
typography:
  display:
    fontFamily: "Barlow Condensed, Barlow, system-ui, sans-serif"
    fontSize: "clamp(2.4rem, 4.4vw, 3.5rem)"
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: "-0.01em"
  price:
    fontFamily: "Barlow Condensed, Barlow, system-ui, sans-serif"
    fontSize: "3.6rem"
    fontWeight: 800
    lineHeight: 0.95
    fontFeature: "tnum"
  headline:
    fontFamily: "Barlow Condensed, Barlow, system-ui, sans-serif"
    fontSize: "2rem"
    fontWeight: 800
    lineHeight: 1
  title:
    fontFamily: "Barlow Condensed, Barlow, system-ui, sans-serif"
    fontSize: "1.35rem"
    fontWeight: 700
  figure:
    fontFamily: "Barlow Condensed, Barlow, system-ui, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 600
    fontFeature: "tnum"
  body:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "0.88rem"
    fontWeight: 600
  fine:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "0.85rem"
    fontWeight: 400
rounded:
  pill-sm: "4px"
  plate: "5px"
  control: "8px"
  card: "10px"
  field: "14px"
  full: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  2xl: "40px"
components:
  button-ghost:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.aubergine}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-ghost-hover:
    backgroundColor: "{colors.tint}"
  button-on-dark:
    textColor: "{colors.on-dark}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  nav-tab:
    textColor: "{colors.on-dark-soft}"
    typography: "{typography.label}"
    padding: "0 14px"
  nav-tab-active:
    textColor: "{colors.on-dark}"
  segmented-option-selected:
    backgroundColor: "{colors.aubergine}"
    textColor: "{colors.on-dark}"
    rounded: "{rounded.full}"
    padding: "7px 18px"
  delta-rise:
    backgroundColor: "{colors.rise-fill}"
    textColor: "{colors.rise-on}"
    rounded: "{rounded.full}"
  delta-fall:
    backgroundColor: "{colors.fall-fill}"
    textColor: "{colors.on-dark}"
    rounded: "{rounded.full}"
  delta-hold:
    backgroundColor: "{colors.tint}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.full}"
  position-pill-mid:
    backgroundColor: "{colors.mid}"
    textColor: "{colors.on-dark}"
    rounded: "{rounded.pill-sm}"
    padding: "1px 7px"
  position-pill-gk:
    backgroundColor: "{colors.gk}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill-sm}"
    padding: "1px 7px"
  price-tag:
    backgroundColor: "{colors.aubergine}"
    textColor: "{colors.on-dark}"
    typography: "{typography.price}"
    padding: "14px 26px 14px 44px"
  name-plate:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.plate}"
    padding: "3px 6px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "20px 24px"
  list-head:
    backgroundColor: "{colors.aubergine}"
    textColor: "{colors.on-dark-soft}"
    typography: "{typography.label}"
    height: "40px"
  list-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    height: "60px"
  list-row-hover:
    backgroundColor: "{colors.tint}"
  search-field:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.control}"
    height: "42px"
    padding: "0 12px"
  stat-chip:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.card}"
    padding: "10px 12px"
  stepper:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.aubergine}"
    rounded: "{rounded.full}"
    size: "32px"
  stepper-hover:
    backgroundColor: "{colors.aubergine}"
    textColor: "{colors.on-dark}"
---

# Design System: FPL Price Prediction

## Overview

**Creative North Star: "The Transfer Market"**

The app lives inside the game its users already open every night. It borrows Fantasy Premier League's own grammar instead of a dashboard's: deep aubergine chrome, a striped pitch with an XI of club shirts, a name plate and price tag under every shirt, position pills, a transfer list, and a player card that slides in from the right. A stranger to the model should recognise the furniture before reading a word, and trust the answer because it is presented the way prices are always presented to them.

The page is a light, dense working surface (paper ground, white list and panel surfaces) framed top and bottom by aubergine chrome. Figures carry the weight: Barlow Condensed, heavy, uppercase for headings and tabular for every price. Colour is spent sparingly and with meaning. Cyan marks the chrome (brand, active tab, selection, the predicted point on the range bar); green and pink-red mark a price moving and nothing else; four saturated position colours sort players. Motion is short and ease-out: shirts lift on hover, the player card slides in and its sections rise in sequence, and all of it is removed under reduced-motion.

The build rejects the admin-dashboard stack of a form, then a card, then a chart. Even the What-if editor is a player sheet: the answer pinned as a price tag on the left, the season's figures as editable stat chips on the right.

**Key Characteristics:**
- Aubergine chrome frames a light paper working surface; no dark mode.
- Figures in heavy Barlow Condensed with tabular numerals; UI text in Barlow.
- Club-coloured SVG shirts drawn from kit facts, never crests or photos.
- Direction colour is reserved: green rises, pink-red falls, a neutral tint holds.
- Every predicted price is shown as a tag: today's price, then next season's.
- Desktop-first; phone layout and screen-reader semantics are not yet designed.

## Colors

A near-black aubergine family carries all chrome, a single cool cyan lights it, and the only warm-to-hot signals on the page are the four position colours and the two directions of price.

### Primary
- **Transfer-Market Aubergine** (aubergine): header, hero band, footer, transfer-list head, price tags, player-card header, selected segmented options, chart totals and hover labels. It is the brand; nothing else occupies this much of the screen.
- **Raised Aubergine** (aubergine-2): the settings drawer that opens below the hero, one step lighter than the chrome it drops out of.
- **Plum Link** (aubergine-3): links, focus-within borders on fields, the tag on a darker sheet head, the scrollbar thumb family.

### Secondary
- **Floodlight Cyan** (cyan): chrome accent only. Brand mark, active nav underline, the season in the hero title, selected option in on-dark segmented controls, the ring on the range bar's predicted point, footer links, text selection. Never used to encode data.

### Tertiary
- **Rise Green** (rise): rising values as text on light surfaces (term table, waterfall bars); clears 4.5:1 on white.
- **Rise Volt** (rise-fill): the rise chip's fill, and the rising predicted price on a dark name plate; carries dark rise-on text (rise-on) when filled.
- **Fall Pink-Red** (fall): falling values as text and bars on light surfaces.
- **Fall Fill** (fall-fill): the fall chip's fill, always with white text.
- **Fall on Dark** (fall-on-dark): a falling predicted price on a dark name plate.
- **Position colours** (gk amber, def cyan-teal, mid violet, fwd orange): position pills, the checked state of position filters, and scatter marks. Each position also has a marker shape (diamond, square, triangle, circle) so colour is never the only cue. MID carries white text; the other three carry ink.

### Neutral
- **Aubergine Ink** (ink): body text and figures on light surfaces.
- **Muted Ink** (ink-soft): secondary text, hints, list stats, placeholders, the hold chip's text.
- **Soft Rule** (line) and **Firm Rule** (line-strong): row dividers and card borders; control borders and table header rules.
- **Paper** (paper): the page ground and the stat-chip fill.
- **Surface** (surface): lists, panels, sheets, chart backgrounds.
- **Lilac Tint** (tint): row hover, segmented track, hold chip, range track.
- **On-dark** (on-dark) and **On-dark Soft** (on-dark-soft): primary and secondary text on aubergine.
- **Pitch Stripes** (pitch-a, pitch-b) with **Chalk** (pitch-line): the pitch's 64px mown bands and its half-pitch markings.

### Named Rules
**The Direction-Only Rule.** In the interface, green and pink-red mean a price is moving and nothing else: not success, not error, not a brand accent. The pitch turf and club kits are the world's own materials and are exempt; position colours and chart series avoid both hues.

**The One Threshold Rule.** A price has moved when the predicted change is at least £0.1m either way; anything smaller holds. Every chip, tag, verdict and colour uses that one threshold.

**The Cyan-Is-Chrome Rule.** Cyan decorates the frame and marks the current selection. It never encodes a value.

## Typography

**Display Font:** Barlow Condensed (with Barlow, system-ui)
**Body Font:** Barlow (with system-ui)

**Character:** A sports-broadcast pairing: condensed, heavy, uppercase figures and headings over a plain, friendly grotesque for everything read in sentences.

### Hierarchy
- **Display** (800, clamp(2.4rem, 4.4vw, 3.5rem), 0.95, uppercase): the one page title in the hero band; the season inside it goes cyan.
- **Price** (800, 3.6rem, 0.95, tabular): the predicted price inside the answer tag. The largest figure on any card.
- **Headline** (800, 2rem, 1, uppercase): section titles on the page (The Model's XI, Transfer List). The player name uses the same voice at 2.4rem.
- **Title** (700, 1.35rem, uppercase): titles inside cards and sheets (Why this price, Price history); stat-group titles step down to 1.15rem.
- **Figure** (600 to 800, 1.15rem, tabular): prices in list rows and name plates; the predicted price is always heavier than today's.
- **Body** (400, 1rem, 1.5): all running text; long prose capped at 60 to 72ch.
- **Label** (600, 0.88rem): list headers, chips, field labels.
- **Fine** (400, 0.85rem, ink-soft): chart footnotes and method notes under a figure.

### Named Rules
**The Tabular Price Rule.** Every price and stat is set in Barlow Condensed with tabular numerals, written £7.5m, and signed with a true minus (−£0.4m) or ± when it rounds to zero.

**The Condensed Voice Rule.** Headings are Barlow Condensed and uppercase; sentences are Barlow in sentence case. Do not set running text in the condensed face.

## Layout

A single centred column (max 1320px, 24px gutters) under a sticky 64px aubergine header. Pages stack full-width blocks: a hero band in the chrome colour, then light blocks separated by 40px top padding, closing on an aubergine footer. Rhythm is built from 4, 8, 12, 16, 24 and 40px steps; controls sit 8 to 12px apart, blocks 40px.

Price Watch leads with a full-width pitch (1-4-4-2, shirts 128px apart in evenly spaced rows), then the transfer list as a fixed-column grid (player column flexible, stat columns 56 to 124px), then the market map. What if is one sheet: a 5:7 grid, the answer pinned sticky on the left and the stat editor on the right, divided by a rule. How it works is prose at 70ch with a three-column steps row.

The only responsive rule designed is for narrower desktops (at 1100px the filters and settings drop to two columns, the sheet stacks, and shirts narrow to 104px). Phone layout was out of scope for this round and is undesigned.

## Elevation & Depth

Mostly flat with one soft ambient shadow. Lists, panels, the pitch and the sheet sit on the paper ground with a hairline border and a low, aubergine-tinted shadow. Real lift is reserved for things that move toward the user: a hovered shirt gains a stronger drop shadow, and the player card casts a wide shadow over a dimmed aubergine backdrop.

### Shadow Vocabulary
- **Ambient** (`box-shadow: 0 1px 2px rgba(43, 0, 51, 0.06), 0 6px 18px rgba(43, 0, 51, 0.07)`): every resting container.
- **Shirt at rest / lifted** (`filter: drop-shadow(0 4px 6px rgba(0,0,0,0.25))`, hover `drop-shadow(0 8px 10px rgba(0,0,0,0.35))`): shirts on the pitch.
- **Player card** (`box-shadow: -20px 0 60px rgba(43, 0, 51, 0.25)`): the sliding card only.
- **Focus** (`box-shadow: 0 0 0 3px rgba(124, 77, 255, 0.45)`): the focus ring everywhere, violet so it never reads as a direction.

### Named Rules
**The Lift Means Reach Rule.** Shadows deepen only for things the user is about to open. Resting surfaces all share the one ambient shadow.

## Shapes

Gently rounded and rectangular: 8px on controls, 10px on cards and stat chips, 14px on the large fields (pitch, sheet). Pills (999px) are reserved for chips that state something: hero status chips, delta chips, segmented controls, the range track. Position pills are nearly square (4px). Two shapes are borrowed straight from the game: the name plate, square-cornered where it meets the price strip below it (5px outer corners only), and the price tag, rounded more on its free end (6px 14px 14px 6px) with a punched hole on the left.

## Components

### Buttons
Quiet and outlined; the app has no filled call-to-action.
- **Shape:** control radius (8px), 8px 14px, 600 weight, optional leading icon.
- **Ghost (on light):** surface fill, aubergine text, firm-rule border; hover fills lilac tint and darkens the border to plum.
- **On-dark (in chrome):** transparent, white text, a 28% white border; hover lifts to a 10% white fill.
- **Stepper:** 32px circle, surface fill, aubergine glyph; hover inverts to aubergine; press scales to 0.92.

### Chips
- **Status chips (hero):** 999px pill, 9% white fill on aubergine, 0.88rem. A warning variant inverts to white with aubergine text.
- **Delta chip:** the predicted move in three sizes (sm, md, lg), caret icon plus signed money. Rise is volt with dark green text, fall is pink-red with white, hold is lilac tint reading "Holds".
- **Position pill:** 38px minimum, condensed 700, filled in the position colour.

### Cards / Containers
- **Corner Style:** 10px (panels, list), 14px (pitch, sheet).
- **Background:** surface on the paper ground.
- **Shadow Strategy:** ambient only (see Elevation & Depth).
- **Border:** 1px soft rule on panels and the list; the sheet relies on its shadow.
- **Internal Padding:** 20px 24px for panels, 28px 32px for sheet sections.

### Inputs / Fields
- **Style:** 42px tall, firm-rule border, 8px radius, surface fill; numeric entries set in condensed 600 at 1.2rem.
- **Focus:** border shifts to plum and the violet focus ring appears.
- **Stat chip:** a paper tile with a label, a large condensed aubergine figure on an underline, a stepper each side and a hint beneath; the tile tints on focus-within. Browser spin buttons are removed.

### Navigation
Tabs in the aubergine header: on-dark-soft text, 600 weight; hover goes white; the active tab is white with a 3px cyan underline. The brand is a cyan rounded-square mark with the name in condensed type.

### Segmented Control
A 999px track with pill options. On light: lilac track, aubergine selected. In chrome: translucent white track, cyan selected. On the pitch: a dark translucent track, white selected.

### The Pitch and the Shirt Spot
The signature. A 14px-radius field of 64px mown stripes with chalk markings for a half pitch (goal, boxes, halfway line, centre circle). Each spot is a 60px club shirt, a white name plate, and an aubergine price strip reading today's price then next season's, the predicted figure heavy and coloured by direction. Spots lift 4px on hover and open the player card.

### The Answer
A price tag in aubergine holding the predicted price, the delta chip beside it, then the range bar: a lilac track, a lilac-violet band for the 95% likely range, an aubergine point ringed in cyan for the prediction, and a thin ink rule labelled with the reference price. One plain verdict sentence follows.

### The Player Card
A 600px panel sliding in from the right (0.5s ease-out) over a dimmed aubergine backdrop. The header band holds a large shirt, the name, the position pill and a stat strip; sections below rise in sequence with small staggered delays.

### Transfer List
An aubergine header row over 60px surface rows split by soft rules; each row is a button (shirt, name, position pill and club; stats; today's price; the predicted price in heavy aubergine; the delta chip). Rows tint on hover and show an inset focus ring.

## Do's and Don'ts

### Do:
- **Do** show every predicted price as a pair, today's then next season's, with the predicted figure heavier.
- **Do** classify every move with the one £0.1m threshold before choosing a colour or a word.
- **Do** give every position both its colour and its marker shape in charts.
- **Do** draw club shirts from kit colours, with a neutral kit for clubs outside the table.
- **Do** set prices and stats in Barlow Condensed with tabular numerals, using a true minus sign.
- **Do** keep chart styling on the light surface: aubergine hover labels, soft-rule gridlines, Barlow type.
- **Do** honour reduced-motion by removing all animation and transition.

### Don't:
- **Don't** use green or pink-red in the interface for anything but price direction; the pitch and club kits are the only exceptions.
- **Don't** use cyan to encode data.
- **Don't** fall back to the stacked form, then card, then chart arrangement; present players on the pitch, in the list, or on a sheet.
- **Don't** use club crests or photographed shirts.
- **Don't** add a dark mode by inverting the light palette; one would need its own steps.
- **Don't** treat phone layout or screen-reader behaviour as designed; both are open work.
