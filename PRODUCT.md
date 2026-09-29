# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

A public audience of Fantasy Premier League players. They know FPL well
(prices, gameweeks, transfers, positions) but should not be assumed to know the
model, OLS, prediction intervals or per-minute rates. They arrive as strangers,
without the author on hand to explain anything.

The app is also a portfolio piece: a second audience is anyone evaluating the
author's analytical and engineering craft, for whom the rigour behind the
number is part of what is on show.

## Product Purpose

Predicts a Fantasy Premier League player's starting price for next season from
their season's performance. The batch pipeline (`run_pipeline.py`) answers
"what will every player cost?"; the app answers "what would *this* player cost
if…?" with the same model, one player at a time and with the inputs editable.

Success: a visitor gets a credible price answer quickly, can see why the model
gave it, and comes away impressed by the work behind it.

## Positioning

A transparent, backtested model rather than a black-box number. It is linear,
so every prediction decomposes exactly into per-term contributions, and each
comes with a 95% prediction interval. Live current-season form is projected to
38 gameweeks from current-season form alone, scaled by each club's own
fixtures played and clamped to the range the model was fitted on.

## Operating Context

- Dash + dash-bootstrap-components app in `app/`, served on port 8051 so it
  can run beside the sibling FPL dashboard on 8050.
- Three pages:
  - `/` (Player): prefill from any completed 2025-26 season, then edit.
  - `/manual`: a hypothetical season typed from scratch, seeded at training medians.
  - `/projected`: live 2026-27 form from the FPL API, projected to 38 gameweeks, predicting 2027-28.
- `/projected` includes a repricing scatter, a club filter, a price-history
  chart and a player table.
- Hosting for the public is intended but not yet set up; the deploy target is
  undecided.

## Capabilities and Constraints

- Every prediction shows the point estimate, the 95% interval, the derived
  features and an exact per-term breakdown. Presentation: **answer first,
  detail on demand.** The predicted price and its direction lead; model
  internals stay available one step away, never removed.
- Rates are shown per 90 minutes with the per-minute figure the model actually
  reads kept underneath, so the breakdown can be reconciled.
- The club filter narrows what is displayed, never what is computed.
- `start_cost` and `cost_change_start` are facts, never projected.
- Season min/max price is not available from the current data; do not design
  for it.
- Terminology: "Start price" = `start_cost` (August); "Price now" /
  "Price today" = `final_cost` / the API's `now_cost`; "GWs" = the per-club
  fixtures-played denominator.

## Evidence on Hand

- Season data from vaastav/Fantasy-Premier-League, snapshots under `data/`.
- Backtest against the prices FPL actually set (`backtest.py`); test parity
  across all 841 players between the app and the pipeline
  (`tests/test_app_parity.py`).
- Model metadata (predictor count, training rows, adj R²) comes from
  `models/`; quote those values, never invented ones.
- No user testimonials, usage figures or accuracy claims beyond the backtest
  exist. Do not fabricate any.

## Product Principles

1. **Answer first, evidence on demand.** Lead with the price and the verdict;
   keep the full reasoning one step away.
2. **Never less honest than the model.** Intervals, clamping and projection
   caveats stay visible wherever they change how much to trust a number.
3. **Speak FPL, not statistics.** Use a manager's units (£m, per 90,
   gameweeks) up front, with the model's units available for reconciliation.
4. **The rigour is the showpiece.** The transparency is what sets this apart,
   so present it as a strength, not as fine print.
