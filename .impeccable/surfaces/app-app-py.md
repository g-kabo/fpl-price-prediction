---
version: 1
slug: "app-app-py"
primary_target: "app/app.py"
related_targets: ["app/pages"]
---

# Surface brief: FPL Price Prediction app (all pages)

Scope: the whole Dash app, a redesign replacing the stock Bootstrap look. Mode: Operate, with a public/portfolio audience to win over.
Audience and task: FPL managers who are strangers to the model. They want to see who the model thinks FPL will reprice next season, open any player for one clear answer, and optionally play what-if.
Constraints: product truth, calculations and callbacks unchanged; `form.predict`, `form.ALL_FIELDS` and `form.row_from_values` stay (parity test). Mobile layout and screen-reader work are out of scope for this round (user decision, 2026-09-28).
IA: `/` Price Watch (live board, the landing page), `/lab` What if (completed season prefill or blank; /player and /manual fold in here), `/how-it-works` (method plus the real backtest).
Unresolved: author/GitHub link and hosting target (not supplied; do not invent).

## Direction contract
THESIS: The app lives inside the game managers open every night: FPL's transfer-market grammar of pitch, shirts, price tags and the transfer list. It refuses the admin-dashboard arrangement of a form, then a card, then a chart.
OWN-WORLD: Deep aubergine chrome (#2b0033 family) with electric-green and cyan accents; white list surfaces; club-coloured SVG shirts; name plates and price-tag chips under each shirt; position pills. Barlow Condensed for figures and headings, Barlow for UI. Green and pink-red are reserved for rise and fall only.
STORY: Visitors see a Risers XI on a striped pitch and understand immediately who the model marks up. They click a shirt and trust the answer through its likely range and a plain "why". Then they explore the list, flip to Fallers, or try what-ifs.
FIRST VIEWPORT: An aubergine header strip with the gameweek, live state and form weighting. Below it, a full-width pitch with an 11-shirt formation (1-4-4-2), Risers/Fallers toggle top-left, each shirt showing today's price → 2027-28 price. The transfer list starts under the fold.
FORM: Transfer Market (my rank 1 of 7, the user's pick over the assigned Sticker Album); seed f4c99ca3. Signature interaction: a shirt or list row opens the player card sliding in from the right, like FPL's player popup.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
