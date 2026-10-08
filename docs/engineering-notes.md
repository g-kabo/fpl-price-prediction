# Engineering notes

The reasoning behind the design decisions: what was tried, what went wrong the
first time, and what not to undo. The [README](../README.md) covers what the
project is and how to run it.

- [The app](#the-app)
  - [What if: derived ratios](#what-if-derived-ratios)
  - [Model caching](#model-caching)
  - [Projecting a part-played season](#projecting-a-part-played-season)
  - [What *n* is, mid-gameweek](#what-n-is-mid-gameweek)
  - [Price history chart](#price-history-chart)
  - [The repricing scatter](#the-repricing-scatter)
  - [Why this price (waterfall)](#why-this-price-waterfall)
  - [Live data source](#live-data-source)
- [Daily history](#daily-history)
- [Differences from the R](#differences-from-the-r)
- [Feature selection](#feature-selection)
- [Where on the price scale it works](#where-on-the-price-scale-it-works)
- [Pipeline outputs](#pipeline-outputs)

---

## The app

### What if: derived ratios

The What if form has no boxes for points per game or points per £m. The model
reads both, but they are FPL's own arithmetic on other figures, so the form asks
for games played instead and works them out: points ÷ games, and points ÷ end
price, each rounded to one decimal as FPL does (`schema.with_ratios`). Typed in
directly, they could contradict the rest of the form: doubling a player's points
would leave his points per game unchanged.

A real season's games played is recovered from FPL's published points per game
(`schema.infer_appearances`), which reproduces it exactly for 840 of the 841
players in 2025-26, so an unedited season still predicts exactly what
`run_pipeline.py` does. Dropping points per £m from the model instead would cost
little (temporal RMSE +£0.0011m, worse in 4 of 6 folds), but dropping both ratios
is worse in every fold.

### What if: any season, including the projected one

What if loads every completed season since 2017-18, plus the season in progress
as Price Watch projects it. Price Watch's player card links to the projected
season (`/lab?season=<year>&player=<code>`).

- **Completed seasons come from `models/seasons.csv`**, which `train_and_save.py`
  writes with `next_cost`, the start price FPL set the following season. "What FPL
  actually did" used to read `output/backtest_<season>.csv`, which is gitignored,
  so the line never appeared on the hosted app. For 2025-26 the two sources agree
  on all 468 returning players.
- **Only the scoring season is a fair test.** Seasons up to `TRAIN_THROUGH` were
  training data, so a close call there proves little, and the page says so
  beside the comparison.
- **The projected season is priced as Price Watch prices it.** Price Watch holds
  every projected input inside the training range (`projection.clamp`). What if
  derives the ratios from the totals, and unclamped, a projected 327 points on a
  £4.6m price gives a points per £m of 69 against a training maximum of 38.7. That
  was worth up to £0.72m. So for the projected season only, What if clamps too, and
  lists what it held. Completed seasons keep the warn-don't-clamp behaviour.
- **Games played is carried over fractionally** (e.g. 7.6) from the projection, so
  points per game comes out as Price Watch's. What remains is rounding: Price
  Watch works its ratios out from unrounded totals, and the form holds whole
  points. On 1 Oct 2026, 90% of players matched to the penny and none was more
  than £0.02m apart; the page says which applies.
- **Side finding: the most expensive players' end price is clamped.** Haaland's
  £15.6m is above the training maximum of £14.9m, so Price Watch prices him as a
  £14.9m player, while his points per £m uses the real £15.6m. It's a consequence
  of clamping to the training range, not of What if, and it affects only players
  priced above anyone in training.

### Model caching

`train_and_save.py` fits once and caches to `models/`, because loading ten
seasons takes ~17s against a 0.1s fit. The app refits automatically if that
cache is older than the code or data it was built from. A stale pickle still
loads and still predicts, just wrongly, so this is checked rather than assumed.
`tests/test_app_parity.py` asserts the app and `run_pipeline.py` price all 841
players identically.

### Projecting a part-played season

Price Watch has to turn *n* gameweeks into 38. It uses current-season form only:
each player's totals are multiplied by 38/*n*, with no blend toward last season.
Early on that can overshoot. After three games, 38/3 can give a 354-point season
against a training maximum of 344, and OLS does not extrapolate gracefully, so
projected values are clamped to the fitted range. Clubs that have not kicked off
yet project to zero.

`start_cost`, `final_cost` and `selected_by_percent` are never projected. They
are facts about the current season, not forecasts, and ownership is a share
rather than a running total. `points_per_game` and `value_season` are ratios,
recomputed from the projected totals rather than scaled. Points per game is
divided by projected appearances (recovered from FPL's published figure and
projected like the other totals), not by minutes ÷ 90, which would credit a
substitute with several times his real rate. Points and appearances scale
together, so the projected rate is the one FPL shows today.

### What *n* is, mid-gameweek

There is no single answer while a gameweek is in progress, and assuming there
was is what this page used to get wrong. On a Saturday evening in gameweek 5,
twelve clubs have played five matches and eight have played four. Dividing every
player by the same number hands one group a quarter more season than they played:

| | scaled by | Saka's projected points | predicted price |
|---|---|---|---|
| one figure for the league | 38/4 | 216 | £9.88 |
| his club's own fixtures | 38/5 | 196 | £9.64 |

So *n* is per club, not per league: each player is divided by his own team's
fixtures played, read from the `fixtures` endpoint. Across the 667 players priced
that evening it moves 57 of them by more than £0.05, all in the over-projected
direction, and halves the number clamped to the fitted range from 34 to 17.

Two details that are easy to get wrong:

- **Counting finished gameweeks undercounts.** An event only flips `finished`
  once its bonus points are confirmed, hours after the last whistle and often the
  next morning. `events.finished` said 4 while every club had 4 or 5 matches in
  the bag. Fixtures that have **started** are what count.
- **A match in progress is a fraction of a fixture.** Each started fixture is
  worth its own `minutes / 90`, so a game at half time counts as half. A finished
  match counts as one whatever minutes it recorded, since an abandoned game still
  happened.

A player's denominator is his *club's* fixtures, never his own appearances: a
defender benched four games running has still had four gameweeks of opportunity,
and counting only his appearances would project those zero minutes as though the
season had not started.

The table shows each player's denominator in a `GWs` column, and the banner names
the split ("257 of 667 players are at clubs that have not played it yet").

### Price history chart

Selecting a player draws a small clustered column chart on the player card:
start and finishing price for every season he has one, then the forecast.

Clustered rather than stacked: a start and a finishing price are two readings of
the same thing, not two parts of it, and stacking them would draw a £12m player
as £24m of bar. Same hue at two lightnesses for the two ends of a season, a
different hue for the forecast, because observed and predicted are different
kinds of number (worst all-pairs separation 24.6 OKLab ΔE under a simulated
deuteranope). The forecast being its own series leaves a gap where a finishing
price would go, which is the point: that season has not been played.

The history comes from `models/price_history.csv`, written by `train_and_save.py`
because the seasons are already loaded and cleaned at that moment. Reading them
again in the app would cost the ~17s that script exists to avoid. The season *in
progress* is the exception: its cached row is dropped and rebuilt from the live
record the page is already holding, since the mirror had one player finishing
2026-27 on £15.5m while the API already said £15.6m.

Min/max season price bars were considered and dropped: the raw season files hold
one snapshot per player, so an intra-season extreme cannot be recovered from them.

### The repricing scatter

Above the table: today's price against the predicted one, a mark per player, with
`y = x` dashed in as the line of no change. Above it the model wants a higher
price than the player carries now, below it a lower one, and distance from the
line is the size of the call. Both axes take the same range so the diagonal runs
corner to corner and "above the line" means one thing everywhere.

They are deliberately *not* locked to the same pixel scale. Plotly's
`scaleanchor` would hold the plot square inside a card three times as wide as it
is tall, stranding every mark in a column down the middle. Matching ranges is
what makes the reference line honest; matching pixel scales only makes it 45°.

**Which current price** is a radio on the chart itself, since it changes what the
chart asks rather than how it answers:

| x-axis | the question |
|---|---|
| `Price today` (`final_cost`, the API's `now_cost`) | is the model repricing this player from where he is *now*? What a manager holding him wants |
| `Start price (August)` (`start_cost`) | where does he end up across the two seasons? Like-for-like, since the y-axis is itself a start price |

The two differ for 284 of the 667 players, by up to £0.40. The table shows both,
under `Start price` and `Price now`.

**The club filter** scopes the chart *and* the table. Filtering one and not the
other is how a page ends up showing three marks above a six-hundred-row table. It
narrows what is displayed, never what is computed: the projection runs on the
whole league first. A test asserts no player's prediction moves when the filter
changes. The banner describes the projection run, not the selection, so it is
left alone too.

**Position colours** are the R's Set1, defined once in `config.POSITION_COLOURS`
and read by both `plots.py` (matplotlib) and `app/charts.py` (Plotly):

| | GK | DEF | MID | FWD |
|---|---|---|---|---|
| colour | `#984EA3` | `#4DAF4A` | `#377EB8` | `#E41A1C` |
| symbol | diamond | square | triangle | circle |

**Position is encoded twice, and the second channel is not decoration.** Set1's
MID blue and GK purple sit 3.5 apart in OKLab ΔE under a simulated deuteranope,
against a floor of 6. Where the two overlap in the £4–5.5m huddle, colour alone
leaves a deuteranope unable to tell them apart, so identity rides on marker shape
as well. (Set1's green is 2.78:1 against white, under the 3:1 contrast floor; the
labelled legend and the table are the relief.)

**Marker size is fixed at 20px** (`charts.MARK_SIZE`). It was briefly scaled to
the number of points on screen, which is wrong twice over: a mark that resizes
when a filter changes reads as an encoding when it means nothing, and the small
end of the range disappears on a wide monitor. The £4–6.5m band is dense at full
league; that is what the club filter is for.

Two smaller things that were wrong the first time:

- **Draw order.** Iterating positions in `config.POSITIONS` order draws GK first,
  so the other 594 marks paint over the 73 goalkeepers. Traces are added biggest
  group first, with `legendrank` holding the legend in GK-DEF-MID-FWD order.
- **The "no change" label.** Anchored at the line's end, the text box's edge sits
  exactly on the line and strikes it through. It takes a `yshift` to sit clear.

### Why this price (waterfall)

Every player view ends with a waterfall beside the per-term table. The model is
linear, so the prediction is exactly `const + Σ βx`: the bars bridge from the
intercept, through each term, to the predicted price, and close on it rather than
near it. A waterfall rather than a bar chart because the quantity is a
*decomposition*.

Increases are green (`--rise`), decreases red (`--fall`), matching the result card
and table. The intercept and total are neutral grey: they are not movements. The
green/red pair is 6.5 OKLab ΔE apart under a simulated deuteranope, legal only
because the waterfall also carries direction by position and a signed label.

A dashed horizontal line marks the price the player already carries, so the
chart answers "does this clear what he costs?" as well as "how is it built". It
sits *behind* the bars; drawn on top, it runs through the value labels. Which
price it is depends on the page:

| page | line | why |
|---|---|---|
| `/lab` (What if) | start price | a typed season has no "today" |
| `/` (Price Watch) | follows the scatter's x-axis radio | the two charts share a page; measuring one against today's price and the other against August's would be a quiet disagreement |

Terms contributing less than £0.0005 are pooled into an "N smaller" bar. At the
breakdown's precision they would print as `+0.000`. Pooled, not dropped:
`form.contributions` is the single source for both chart and table, and a test
asserts the bars still bridge exactly to the model's own number for 60 sampled
players.

### Live data source

Price Watch reads a daily snapshot of the official API (`snapshot.py`, via
`fpl_data.load_live_season`), not the GitHub mirror the pipeline uses, because
the mirror's current-season file can be weeks behind. Prices change once a day,
so a daily read loses nothing, and the web server never has to reach the API
itself. With no snapshot it falls back to the cached CSV and says so, and a
snapshot more than 36 hours old is flagged in the status strip. If only the
fixture list is unreachable, `fpl_data.infer_progress` recovers games played per
club from each squad's busiest player's minutes, which reproduces the
fixture-derived counts exactly.

`snapshot.load()` ignores a snapshot whose season isn't `config.PREDICT_SEASON`,
so bump config before a new season's first snapshot.

---

## The static site

`web/` is the app again as plain HTML and JavaScript, so GitHub Pages can serve
it with no server and no cold start (Render's free tier sleeps after 15 minutes).

- **Python still does the fitting and the projection.** `export_static.py` writes
  `model.json` (weights, covariance, residual variance, ranges, form definitions),
  `board.json` (every player, projected and priced), `seasons.json` and
  `history.json`. They are built in CI and gitignored, not committed.
- **The browser re-does the one line of arithmetic** (`web/js/model.js`), because
  What if needs it on every keystroke. The prediction interval is the OLS
  new-observation one: `pred ± t * sqrt(scale + x'Cx)`, with `C` the covariance
  of the weights. `web/tests/parity.mjs` checks 400-odd cases, including a
  never-played player, an unseen club and values past the training range, against
  Python to 1e-9, and CI refuses to publish if they differ.
- **Python's `round` is half-to-even, JavaScript's is not.** FPL's ratios hit exact
  ties (45 points in 20 games is 2.25), so all rounding goes through `fixed()` in
  `web/js/format.js`, which breaks exact ties to even as Python does.
- **Plotly's waterfall trace is not in the light bundle.** The "Why this price"
  chart is drawn as floating bars (`base`) instead, to keep the page small.
- **Search fold fix.** The Dash version dropped "ß" before replacing it, so "gross"
  never found Groß; the port replaces it first.
- **Dropped:** the "same answer as the batch pipeline" line on What if. It needed
  `output/`, which is not committed, so it never showed on a hosted copy anyway.
- **GitHub Pages needs a public repo on the free plan.**

---

## Daily history

After each snapshot, the GitHub Action runs `record_predictions.py`, which writes
one file per day to `data/history/<season>/<date>.csv`: one row per player with
that day's FPL figures (prices, points, ownership, transfers, availability and
news, expected stats, FPL's price-change pressure), Price Watch's full-season
projection, and the predicted start price for next season with its 95% interval
(`pred_next_start`, `pred_next_lower`, `pred_next_upper`). It is what Price Watch
showed that day, kept after `data/live/` is overwritten.

One file per day rather than one per season, because a whole season in one file
would approach GitHub's 100 MB file limit.

```python
import record_predictions
history = record_predictions.load_history()   # every day, stacked
history.pivot(index="date", columns="web_name", values="price")
```

`python record_predictions.py --backfill` also records every earlier snapshot in
git history. It needs the full history, so run it locally, not in the Action.

### Forecast trend and forecast movers

The app reads the history back through `app/forecast_history.py`, which loads
only the seven columns it draws and reloads when a day's file is added. Two
features use it:

- **Forecast trend** (player card): the forecast each morning, with its 95% band,
  against the price that day as a step line (FPL prices jump overnight, they don't
  drift). Both are £m, so one axis.
- **Forecast movers** (Price Watch, under the XI): the biggest changes in forecast
  since yesterday, the past week or the first recorded day. League-wide, like the
  XI; the filters belong to the list and the map.

Decisions worth keeping:

- **Today always comes from the live frame, never from today's history file.**
  The history is only used for earlier days. So the trend ends on the number the
  card shows above it, and a machine that never ran `record_predictions.py`
  (local dev) still works.
- **Changes are shown to £0.01m, not on the £0.1m move threshold.** Between
  gameweeks a forecast only shifts with price changes, by hundredths (the first
  three recorded days, all after GW5, moved by at most £0.04m). On the
  `delta_chip` threshold every mover would read "Holds", so movers use
  `ui.change_chip`.
- **A window reaching back before the record starts falls back to the first
  day**, and the note names the day actually used rather than claiming "a week".
- The history is what the page showed *with the model of that day*. A refit
  mid-season shows up as a step in every forecast trend. That's accurate, not
  a bug, but it will look like a gameweek effect.

On the static site (`web/`), `export_static.py` writes the history as
`forecasts.json`: every recorded morning *before* the snapshot's date, so the
rule above (today from the live frame) holds there too, with today taken from
`board.json` and the card's own interval. The file keeps **change points only**
per player (`[day, price, pred, lower, upper]` when anything moved, `[day]` from
a day he was missing). One row per player per day was ~16 KB a day, heading for
~5 MB by May; between gameweeks most forecasts hold for days, so change points
were 28 KB for the first nine days. `recordedOn()` in `web/js/board.js` carries
the last point forward. On a phone the movers drop the earlier forecast and keep
the new one and the change chip, which imply it.

---

## Differences from the R

The model began as a translation of the `# Creating a GLobal ID List for FPL`
section (lines 998–1602) of the author's `Price Prediction.Rmd`, last run in July
2025 against 2024-25. Three things in the R were corrected rather than
reproduced. Together they take CV RMSE from 0.3465 to 0.3138 on the R's own
training window.

**1. Line 1170 passed the wrong season's data.**

```r
clean_df(raw_FPL2023, 2024)   # should be raw_FPL2024
```

This looks harmless because `filter(season < 2024)` two lines later discards
those rows. But `lead(start_cost)` runs *before* that filter, so every 2023 row
took its target from the mislabelled duplicate: the target for the whole 2023
cohort was **each player's own 2023 starting price**. That inflated the share of
training rows where the target equals the current start price from 54.1% to
63.1%, teaching the model to lean on the identity mapping.

**2. `lead()` paired non-consecutive seasons.** A player who left the Premier
League and returned had their row matched to a target two, three, even seven
years later. 450 of 3,728 rows (12%) were such pairs, and they are much noisier
than genuine year-on-year transitions (mean absolute price move £0.35m against
£0.31m). Pairing is now required to be consecutive.

**3. ELO ratings are not ported.** The R builds `fpl_season_elo` across ~70 lines
but every `elo` reference in the recipe is commented out, and the R's own notes
show it made the model *worse* (0.3637 with ELO against 0.3620 without). Dropping
it removes an Excel workbook, the `season_end` table and `team_masterlist.rds`
from the critical path.

The `cumul_weighted_*` features are still computed (`clean.py`) but, as in the R,
left out of the model.

### Reproducing the R's published RMSE

The R reported a test RMSE of **0.362043**. An exact match is not obtainable, as R
and scikit-learn draw different splits from the same seed, so the check is
whether that figure falls inside the spread this code produces. Rebuilding the
R's frame bug-for-bug over 40 random splits:

| Configuration | n | CV RMSE | Holdout median | Holdout range |
|---|---|---|---|---|
| R exactly (mislabelled season + loose `lead()`) | 3,904 | 0.3465 | 0.3419 | 0.3033 – 0.3836 |
| Season bug fixed | 3,633 | 0.3378 | 0.3390 | 0.3005 – 0.3756 |
| \+ consecutive seasons (this pipeline) | 3,278 | 0.3138 | 0.3152 | 0.2922 – 0.3423 |

0.362043 sits inside the first row's range, so the translation is faithful; it
sits outside the third, so the corrections are doing real work.

To re-run that configuration (`--r-compat` also switches back to the R's feature
set, `features.R_NUMERIC`):

```bat
python run_pipeline.py --train-through 2023 --score-season 2023 ^
    --predict-season 2024 --r-compat --tag r_compat
```

The R named its output files after the *input* season (`pred_price_2024.csv`
holds predictions made **from** 2024-25 data). This project names them after the
season being **predicted**.

---

## Feature selection

The R's formula was replaced in September 2026 after `feature_experiments.py`
scored the alternatives. Random CV mixes seasons, so it cannot see a feature
whose meaning drifts over time; the deciding test is a **rolling-origin temporal
backtest**: fit on every season before *s*, predict the *s → s+1* transition, for
2020-21 through 2025-26.

| Change | Temporal RMSE |
|---|---|
| R formula | 0.3288 |
| `transfers_in`/`transfers_out` → `selected_by_percent` | 0.3154 |
| drop the five per-minute rates | 0.3138 |
| add `start_cost²` and `final_cost²` | 0.3057 |
| drop `bps` and `clean_sheets` | **0.3054** |

- **Transfers drift.** FPL's manager count roughly doubled between 2017-18 and
  2025-26, so a raw transfer count means something different every season.
  Ownership is a share and does not. Season-share and log transfers were tried
  and did less well.
- **Rates, `bps` and `clean_sheets` were redundant** with `total_points` and
  `minutes`; removing each cost nothing out of sample.
- **The squares let the price slope bend.** A cheap player carries about half his
  price into next season (prices sit against a £4.0–4.5m floor), a premium about
  85% (FPL keeps stars expensive). A straight line mis-prices both ends. Natural
  splines and per-price-tier adjustments were tested and did no better.
- **`final_cost` in place of `cost_change_start`** changes nothing numerically;
  alongside `start_cost` the two carry the same information. It reads more
  naturally.
- **Tried and rejected:** gameweek-derived start/min/max/final ownership, in-season
  min/max price, previous-season lags, the `cumul_weighted_*` history, ICT index,
  bonus, ELO / team strength.

The table is `feature_experiments.py`'s `LADDER`, written to
`output/feature_experiments.csv`.

The R's original formula, still available as `features.R_NUMERIC`:

```
next_cost ~ start_cost + cost_change_start + element_type + total_points
          + minutes + transfers_in + transfers_out + goals_scored + assists
          + bps + clean_sheets + team_name + points_per_game + value_season
          + goals_per_min + assists_per_min + bps_per_min + points_per_mins
          + cleansheets_per_min + no_mins
```

---

## Where on the price scale it works

`price_analysis.py` (also run by `run_pipeline.py`) uses the same rolling-origin
folds as the feature selection: one out-of-sample prediction per row, 2020-21 to
2025-26 (2,974 player-seasons). Everything lands in `output/price_analysis.json`.

- **The price curve.** How much of £1 of this season's price survives into next
  season's: `b_start + b_final + 2 (b_start_sq + b_final_sq) p`. It rises from
  £0.53 at £4m to £0.85 at £15m; without the squares it is a flat £0.58.
- **Moves by band.** 71% of £4.0–4.5m players hold their price; from £6m up most
  fall, typically by £0.5m, and £10m+ players fall no further on average than
  £8–9.5m ones (−£0.39m against −£0.40m).
- **Errors by band.** The squares lower RMSE in all six price bands, most at £7m+.
  Without them the model over-prices £7.0–7.5m players by £0.19m and
  *under*-prices £10m+ players by £0.16m. Either way RMSE more than doubles from
  the floor (£0.24m) to £10m+ (£0.63m).
- **Tiers by position**, cut by `config.PRICE_TIERS` (Budget / Low-Mid / High-Mid /
  Premium, the author's own tiering from the R) on `start_cost`. Budget tiers are
  well covered in every position; expensive outfield tiers are not: 95% intervals
  hold only 71% of High-Mid forwards and 75% of Premium midfielders. Premium GK,
  MID and FWD tiers have under 30 rows each.
- **Grouped drivers.** Each input group refitted away in turn. Dropping all four
  price terms raises RMSE by only £0.10m, because `value_season` is points ÷ price
  and lets the model rebuild price; drop it too and RMSE is £0.524m, level with
  carrying the price forward (£0.530m). Position is a distant second (+£0.015m);
  `total_points` adds nothing once the rest are in. This replaces permutation
  importance, because the four price terms partly cancel, so shuffling one alone
  exaggerates it.

`statsmodels` is used rather than `scikit-learn` because the R's output includes
prediction intervals and a coefficient table with p-values; neither exists in
scikit-learn. `PriceModel` owns the fitted team-lumping and column order alongside
the regression, which is what a tidymodels `workflow()` does and what keeps the
design matrix aligned when the league's composition changes.

---

## Pipeline outputs

Everything lands in `output/` (not committed):

| File | Contents |
|---|---|
| `pred_price_2026.csv` | Per-player predicted 2026-27 starting price with 95% interval. Same shape as the R's `pred_price_2024.csv`, minus the leading dots on column names. |
| `backtest_2026.csv` | Those predictions joined to actual 2026-27 prices, sorted by absolute error. |
| `metrics.json`, `backtest_metrics_2026.json` | Every headline figure in the README. |
| `coefficients.csv` | Coefficients with p-values and 95% CIs, the equivalent of R's `tidy(conf.int = TRUE)`. |
| `variable_importance.csv` | Permutation drop-out loss per variable, the equivalent of `DALEX::model_parts(B = 50)`. |
| `feature_experiments.csv`, `feature_experiments_folds.csv` | Every feature-set variant's random-CV and temporal RMSE. `ladder_step` marks the rows of the [feature selection](#feature-selection) table. |
| `price_analysis.json` | See [Where on the price scale it works](#where-on-the-price-scale-it-works). |
| `model_report.html` | Full model report, built by `explore/model_report.py`. |
| `plots/*.png` | The four ggplot figures from the R, plus the backtest scatter. |
