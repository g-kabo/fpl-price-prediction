# FPL Price Prediction (Python)

Predicts each Fantasy Premier League player's **starting price for the next
season** from their current-season performance.

This is a translation of the `# Creating a GLobal ID List for FPL` section
(lines 998–1602) of `../Price Prediction.Rmd`, which was last run in July 2025
against the 2024-25 season. It has been brought forward to train through
2025-26 and predict 2026-27.

## Running it

The pipeline uses the sibling dashboard's virtual environment:

```
"..\FPL Python Dashboard\.venv\Scripts\python.exe" run_pipeline.py
"..\FPL Python Dashboard\.venv\Scripts\python.exe" backtest.py
```

Run these from the repository root. The venv path is relative to it, so the
sibling `FPL Python Dashboard` folder has to sit alongside this one.

`scikit-learn` and `statsmodels` were added to that venv; everything else it
already had. For a standalone environment, `requirements.txt` is the full list.

Season data is cached under `data/` on first run, so subsequent runs work
offline. Pass `--refresh` to re-pull.

The season CSVs come from [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League),
which mirrors the official FPL API per season. The copies committed under
`data/` are snapshots of that source.

## The interactive app

`run_pipeline.py` answers "what will every player cost?" in one batch. The app
answers "what would *this* player cost if…?" — the same model, one player at a
time, with the inputs editable.

```
"..\FPL Python Dashboard\.venv\Scripts\python.exe" train_and_save.py
"..\FPL Python Dashboard\.venv\Scripts\python.exe" snapshot.py
"..\FPL Python Dashboard\.venv\Scripts\python.exe" app\app.py
```

`snapshot.py` saves today's table from the official FPL API to `data/live/`,
which is what Price Watch reads. Online, a GitHub Action does this daily (see
[Hosting](#hosting)); locally, rerun it whenever you want fresher prices, and an
open page picks the new file up within the hour, or on reload.

### Daily history

The same Action then runs `record_predictions.py`, which writes one file per
day to `data/history/<season>/<date>.csv`: one row per player with that day's
FPL figures (prices, points, ownership, transfers, availability and news,
expected stats, FPL's price-change pressure), Price Watch's full-season
projection, and the predicted start price for next season with its 95%
interval (`pred_next_start`, `pred_next_lower`, `pred_next_upper`). That is
what Price Watch showed that day, kept after `data/live/` is overwritten.

```python
import record_predictions
history = record_predictions.load_history()   # every day, stacked
history.pivot(index="date", columns="web_name", values="price")
```

`python record_predictions.py --backfill` also records every earlier snapshot
in git history. It needs the full history, so run it locally, not in the Action.

Then open <http://127.0.0.1:8051> (8051, so it can run alongside the dashboard
on 8050). Three pages:

| Page | Inputs | Predicts |
|---|---|---|
| `/` Price Watch | **current** 2026-27 form from the daily FPL API snapshot, projected to 38 gameweeks | 2027-28 start price |
| `/lab` What if | any completed 2025-26 season, or the training medians, then editable | 2026-27 start price |
| `/how-it-works` | none: the fitted model written out as one equation | |

The old `/projected`, `/player` and `/manual` routes redirect to the new ones.
`/?player=<code>` opens that player's card directly.

Every player view shows the 95% prediction interval, a plain-English reading
of the price, and a per-term breakdown. That last one is exact rather than
approximate: the model is linear, so the contributions sum to the point
estimate. The visual system is documented in `DESIGN.md`.

The What if form has no boxes for points per game or points per £m. The model
reads both, but they are FPL's own arithmetic on other figures, so the What if form asks for games
played instead and works them out: points ÷ games, and points ÷ end price, each
rounded to one decimal as FPL does (`schema.with_ratios`). Typed in directly,
they could contradict the rest of the form; doubling a player's points would
leave his points per game unchanged. A real season's games played is recovered
from FPL's published points per game (`schema.infer_appearances`), which
reproduces it exactly for 840 of the 841 players in 2025-26, so an unedited
season still predicts exactly what `run_pipeline.py` does. Dropping points per
£m from the model instead would cost little (temporal RMSE +£0.0011m, worse in 4
of 6 folds), but dropping both ratios is worse in every fold.

`train_and_save.py` fits once and caches to `models/`, because loading ten
seasons takes ~17s against a 0.1s fit. The app refits automatically if that
cache is older than the code or data it was built from — a stale pickle still
loads and still predicts, just wrongly, so this is checked rather than assumed.
`tests/test_app_parity.py` asserts the app and `run_pipeline.py` price all 841
players identically.

### Projecting a part-played season

Price Watch has to turn *n* gameweeks into 38. It uses current-season form
only: each player's totals are multiplied by 38/*n*, with no blend toward last
season. Early on that can overshoot. After three games, 38/3 can give a
354-point season against a training maximum of 344, and OLS does not
extrapolate gracefully. So projected values are clamped to the fitted range. Clubs that have not kicked
off yet project to zero.

`start_cost`, `final_cost` and `selected_by_percent` are never projected — they
are facts about the current season, not forecasts, and ownership is a share
rather than a running total. `points_per_game` and `value_season` are
ratios, recomputed from the projected totals rather than scaled. Points per
game is divided by projected appearances, recovered from FPL's published figure
and projected like the other totals, not by minutes ÷ 90, which would credit a
substitute with several times his real rate. Points and appearances scale
together, so the projected rate is the one FPL shows today.

#### What *n* is, mid-gameweek

There is no single answer while a gameweek is in progress, and assuming there
was is what this page used to get wrong. On a Saturday evening in gameweek 5,
twelve clubs have played five matches and eight have played four. Dividing
every player by the same number hands one group a quarter more season than they
played:

| | scaled by | Saka's projected points | predicted price |
|---|---|---|---|
| one figure for the league | 38/4 | 216 | £9.88 |
| his club's own fixtures | 38/5 | 196 | £9.64 |

So *n* is per club, not per league: each player is divided by his own team's
fixtures played, read from the `fixtures` endpoint. Across the 667 players
priced on that evening it moves 57 of them by more than £0.05, all in the
over-projected direction, and halves the number clamped to the fitted range
from 34 to 17.

Two details that are easy to get wrong:

- **Counting finished gameweeks undercounts.** An event only flips `finished`
  once its bonus points are confirmed, hours after the last whistle and often
  the next morning. `events.finished` said 4 while every club had 4 or 5
  matches in the bag. Fixtures that have **started** are what count.
- **A match in progress is a fraction of a fixture.** Each started fixture is
  worth its own `minutes / 90`, so a game at half time counts as half. A
  finished match counts as one whatever minutes it recorded, since an abandoned
  game still happened.

A player's denominator is his *club's* fixtures, never his own appearances: a
defender benched four games running has still had four gameweeks of
opportunity, and counting only his appearances would project those zero minutes
as though the season had not started.

The table shows each player's denominator in a `GWs` column, and the banner
names the split ("257 of 667 players are at clubs that have not played it yet").

#### Price history

Selecting a player also draws a small clustered column chart on the
player card: start and finishing price for every season he has one, then the forecast.

Clustered rather than stacked — a start and a finishing price are two readings
of the same thing, not two parts of it, and stacking them would draw a £12m
player as £24m of bar. Same hue at two lightnesses for the two ends of a season,
a different hue for the forecast, because observed and predicted are different
kinds of number (worst all-pairs separation 24.6 OKLab ΔE under a simulated
deuteranope). The forecast being its own series costs it the start slot and
leaves a gap where a finishing price would go, which is the point: that season
has not been played.

The history comes from `models/price_history.csv`, written by
`train_and_save.py` because the seasons are already loaded and cleaned at that
moment — reading them again in the app would cost the ~17s that script exists to
avoid. The season *in progress* is the exception: its cached row is dropped and
rebuilt from the live record the page is already holding, since the mirror had
this player finishing 2026-27 on £15.5m while the API already said £15.6m.

#### The repricing scatter

Above the table, today's price against the predicted one, a mark per player,
with `y = x` dashed in as the line of no change: above it the model wants a
higher price than the player carries now, below it a lower one, and distance
from the line is the size of the call. Both axes take the same range so the
diagonal runs corner to corner and "above the line" means one thing everywhere.

They are deliberately *not* locked to the same pixel scale. Plotly's
`scaleanchor` would hold the plot square inside a card three times as wide as it
is tall, stranding every mark in a column down the middle. Matching ranges is
what makes the reference line honest; matching pixel scales only makes it 45°.

**Which current price** is a radio on the chart itself, since it changes what
the chart asks rather than how it answers:

| x-axis | the question |
|---|---|
| `Price today` (`final_cost`, the API's `now_cost`) | is the model repricing this player from where he is *now*? — what a manager holding him wants |
| `Start price (August)` (`start_cost`) | where does he end up across the two seasons? — like-for-like, since the y-axis is itself a start price |

The two differ for 284 of the 667 players, by up to £0.40. The table shows both,
under `Start price` and `Price now`; its price column used to be labelled "Price
now" while holding `start_cost`, which is the collision that surfaced when the
scatter needed a genuinely current price.

**The club filter** sits in the controls row and scopes the chart *and* the
table. Filtering one and not the other is how a page ends up showing three marks
above a six-hundred-row table and inviting the reader to reconcile them. It
narrows what is displayed, never what is computed — the projection runs on the
whole league first, because the league-average denominator is a league-wide
quantity.
Filtering to Arsenal and projecting Arsenal alone would quietly give Arsenal a
different denominator; a test asserts no player's prediction moves when the
filter changes. The banner above is left alone for the same reason: it describes
the projection run, not the selection.

Colours are the R's Set1, the same four this project has always used for
positions, now defined once in `config.POSITION_COLOURS` and read by both
`plots.py` (matplotlib PNGs) and `app/charts.py` (Plotly):

| | GK | DEF | MID | FWD |
|---|---|---|---|---|
| colour | `#984EA3` | `#4DAF4A` | `#377EB8` | `#E41A1C` |
| symbol | diamond | square | triangle | circle |

**Position is encoded twice, and the second channel is not decoration.** Run
through the colorblind checks, Set1's MID blue and GK purple sit 3.5 apart in
OKLab ΔE under a simulated deuteranope — against a floor of 6 and a target of 8.
On a scatter where the two overlap in the same £4–5.5 huddle, colour alone leaves
a deuteranope unable to tell a midfielder from a goalkeeper. The palette is the
R's and stays the R's, so identity rides on marker shape as well as hue, in the
legend and on every mark. (Set1's green also lands at 2.78:1 against white,
under the 3:1 contrast floor; the labelled legend and the table below it are the
documented relief.)

**Marker size is fixed at 20px** (`charts.MARK_SIZE`) for every view, filtered
or not. It was briefly scaled to the number of points on screen, which is wrong
twice over: a mark that resizes when a filter changes reads as an encoding —
bigger dot, bigger *something* — when it means nothing of the kind, and the
small end of any such range disappears on the wide monitor this page is
actually read on. The cost is that the £4–6.5m band is dense at full league;
that is what the club filter is for.

Two smaller things that were wrong the first time and are worth not repeating:

- **Draw order.** Iterating positions in `config.POSITIONS` order draws GK
  first, which means all 594 other marks paint over the 73 goalkeepers and the
  series effectively vanishes. Traces are added biggest group first so the
  smallest lands on top, with `legendrank` holding the legend in GK-DEF-MID-FWD
  order regardless.
- **The "no change" label.** Anchoring it at the line's end puts the text box's
  edge exactly on the line, which strikes it through. It takes a `yshift` to sit
  clear.

The page reads a daily snapshot of the official API (`snapshot.py`, via
`fpl_data.load_live_season`), not the GitHub mirror the pipeline uses, because
the mirror's current-season file can be weeks behind. Prices change once a day,
so a daily read loses nothing, and it means the web server never has to reach
the API itself. With no snapshot it falls back to the cached CSV and says so, and
a snapshot more than 36 hours old is flagged in the status strip. If only the
fixture list is unreachable when the snapshot is taken, `fpl_data.infer_progress` recovers
games played per club from each squad's busiest player's minutes, which on the
data above reproduces the fixture-derived counts exactly.

### Why this price

All three pages end with the same breakdown, now a waterfall beside the numbers
rather than numbers alone. The model is linear, so the prediction is exactly
`const + Σ βx`: the bars bridge from the intercept, through each term, to the
predicted price, and they close on it rather than near it. A waterfall rather
than a bar chart because the quantity is a *decomposition* — the bridge is the
point, and independent magnitudes would not add up to anything.

Increases are green (`--rise`), decreases red (`--fall`), the same two the
result card and the table already use. Anchors — the intercept and the total —
are neutral grey: they are not movements, and colouring them as though they
were would imply a direction they do not have.

That green/red pair is 6.5 OKLab ΔE apart under a simulated deuteranope, above
the floor of 6 but under the target of 8, which makes it legal only where
something other than hue carries the same information. A waterfall does that by
construction: the bar rises or falls from the connector, and every bar is
labelled with its signed value.

A dashed horizontal line marks the price the player already carries, so the
chart answers "does this clear what he costs?" as well as "how is it built".
Where the running total crosses the line is the term that pays for the current
price; everything after it is the model's markup, and the gap between the line
and the final bar is the predicted change. It sits *behind* the bars — a
reference price usually lands close to the predicted one, and drawn on top the
dash runs straight through the value label on every bar in that neighbourhood.

Which price that is belongs to the page:

| page | line | why |
|---|---|---|
| `/manual` | start price | a typed season has no "today" |
| `/` | start price | `final_cost` is on the prefilled row but is not a form field, so editing the start price would leave it pointing at whatever the originally-picked player finished on |
| `/projected` | follows the scatter's x-axis radio | the two charts are on the same page; letting one measure against today's price while the other measures against August's is the sort of quiet disagreement this page has been bitten by before |

Terms contributing less than £0.0005 are pooled into the "N smaller" bar rather
than given one each — at the breakdown's own precision they print as `+0.000`,
which reads as "this does nothing" and takes a bar and a table row to say it.
Pooled, not dropped: `form.contributions` is the single source both the chart
and the table read, and a test asserts the bars still bridge exactly to the
model's own number for 60 sampled players.

The table keeps every column and moves to a narrower five-twelfths beside the
chart. On `/projected` the whole breakdown moved to its own full-width row —
nesting a fifteen-bar waterfall inside seven twelfths of seven twelfths left the
bars too narrow to label.

## Hosting

The app is set up to run on [Render](https://render.com)'s free tier, deployed
from GitHub:

- **`render.yaml`** defines the web service. In the Render dashboard choose
  New > Blueprint and pick this repository. Each deploy installs
  `requirements.txt`, refits the model with `train_and_save.py --force`
  (about 20 seconds, and it sidesteps any mismatch between library versions and a
  committed model file), then serves the app with gunicorn.
- **`.github/workflows/snapshot.yml`** runs `snapshot.py` at 03:00 UTC every day,
  after FPL's overnight price changes, and commits `data/live/`. Render redeploys
  on that commit. A failed run turns red in the Actions tab and GitHub emails
  you; the site keeps showing the previous snapshot, with its date. The Actions
  tab's "Run workflow" button takes a snapshot on demand.
- **`.python-version`** pins Python for both.

On the free tier the app sleeps after 15 minutes without visitors, and the first
visit after that takes 30 to 60 seconds to wake it.

## What it does

| Step | File |
|---|---|
| Pull `players_raw.csv` per season from the `vaastav/Fantasy-Premier-League` repo, plus a slim per-gameweek ownership/price file (experiments only) | `fpl_data.py` |
| Select 22 columns, recover `start_cost` from `now_cost - cost_change_start`, map positions, join team names, drop managers | `clean.py` |
| Attach next season's starting price as the target, matched on the permanent player `code` | `clean.py` |
| Squared price terms, 3%-frequency team lumping, dummy encoding | `features.py` |
| Score alternative feature sets on a rolling-origin temporal backtest | `feature_experiments.py` |
| OLS fit with 10-fold CV, 95% prediction intervals, permutation importance | `model.py` |
| Price curve, moves and errors by price band, tiers by position, grouped drivers | `price_analysis.py` |
| Orchestration and CSV/JSON/PNG export | `run_pipeline.py` |
| Score the predictions against the prices FPL actually set | `backtest.py` |
| Fit once and cache the model for serving | `train_and_save.py` |
| Interactive single-player front end | `app/` |

## Results

Training on 2017-18 → 2024-25 (3,812 player-seasons), scoring 2025-26,
predicting 2026-27:

| | RMSE | MAE | R² |
|---|---|---|---|
| Held-out test split (25%) | 0.2876 | 0.2186 | 0.9410 |
| 10-fold cross-validation | 0.2999 (SE 0.0063) | | 0.9392 |

**Backtest against actual 2026-27 starting prices** — 468 returning players
(148 of the 616 players in 2026-27 are promoted-club players, new signings or
debutants, and so have no prediction):

| | Value |
|---|---|
| RMSE | 0.3528 |
| MAE | 0.2618 |
| Bias | −0.0563 (slightly under-predicts overall) |
| Within £0.25m | 59.0% |
| 95% interval coverage | 90.8% |
| Carry-forward baseline RMSE | 0.5708 |
| **Improvement over baseline** | **38.2%** |

The R's feature set scored 0.3871 on the same backtest; see
[Feature selection](#feature-selection) for what changed.

Two things worth knowing before trusting a number out of this:

- **Forwards are the weak spot.** FWD backtest RMSE is 0.4795 against 0.32–0.34
  for every other position, with a +0.167 bias and 79% interval coverage — the
  model still over-prices them, if less than it did. FPL priced Ekitiké and
  Gyökeres at £7.5m when the model said £8.6–8.7m. Striker pricing appears to
  depend on something the model cannot see.
- **The intervals are a little narrow.** 90.8% actual coverage against a nominal
  95% means the real uncertainty is modestly wider than quoted — and it grows
  with price, which a single OLS error term cannot represent.

## Differences from the R

Three things in the R were corrected rather than reproduced. Together they take
CV RMSE from 0.3465 to 0.3138 on the R's own training window.

**1. Line 1170 passed the wrong season's data.**

```r
clean_df(raw_FPL2023, 2024)   # should be raw_FPL2024
```

This looks harmless because `filter(season < 2024)` two lines later discards
those rows. But `lead(start_cost)` runs *before* that filter, so every 2023 row
took its target from the mislabelled duplicate — meaning the target for the
whole 2023 cohort was **each player's own 2023 starting price**. That inflated
the share of training rows where the target equals the current start price from
54.1% to 63.1%, teaching the model to lean on the identity mapping.

**2. `lead()` paired non-consecutive seasons.** A player who left the Premier
League and returned had their row matched to a target two, three, even seven
years later. 450 of 3,728 rows (12%) were such pairs, and they are much noisier
than genuine year-on-year transitions — mean absolute price move of £0.35m
against £0.31m. Pairing is now required to be consecutive.

**3. ELO ratings are not ported.** The R builds `fpl_season_elo` across ~70
lines but every `elo` reference in the recipe is commented out, and the RMSE
notes under line 1267 show it made the model *worse* (0.3637 with ELO against
0.3620 without). Dropping it removes the Excel workbook, the `season_end`
table and the `team_masterlist.rds` dependency from the critical path.

The `cumul_weighted_*` features are still computed (`clean.py`) but, as in the
R, left out of the model formula.

### Reproducing the R's published RMSE

The R reported a test RMSE of **0.362043**. An exact match is not obtainable —
R and scikit-learn draw different splits from the same seed — so the check is
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
set, `features.R_NUMERIC`, since today's default is not the R's):

```
"..\FPL Python Dashboard\.venv\Scripts\python.exe" run_pipeline.py ^
    --train-through 2023 --score-season 2023 --predict-season 2024 ^
    --r-compat --tag r_compat
```

## Output

Everything lands in `output/`:

| File | Contents |
|---|---|
| `pred_price_2026.csv` | Per-player predicted 2026-27 starting price with 95% interval. Same shape as the R's `pred_price_2024.csv`, minus the leading dots on column names (and with `price_start_change` spelled correctly). |
| `backtest_2026.csv` | Those predictions joined to actual 2026-27 prices, sorted by absolute error. |
| `metrics.json`, `backtest_metrics_2026.json` | Every figure quoted above. |
| `coefficients.csv` | Coefficient table with p-values and 95% confidence intervals — R's `tidy(conf.int = TRUE)`. |
| `variable_importance.csv` | Permutation drop-out loss per variable — R's `DALEX::model_parts(B = 50)`. Ranked `final_cost_sq`, `start_cost`, `start_cost_sq`, `goals_scored`, `value_season`, `final_cost`. |
| `feature_experiments.csv`, `feature_experiments_folds.csv` | Written by `feature_experiments.py`: every feature-set variant's random-CV and temporal RMSE, overall and per season. `ladder_step` marks the five rows of the table under [Feature selection](#feature-selection). |
| `price_analysis.json` | Written by `price_analysis.py` (and by `run_pipeline.py`): see [Where on the price scale it works](#where-on-the-price-scale-it-works). |
| `plots/*.png` | The four ggplot figures from the R, plus the backtest scatter. |

Note the R named its output files after the *input* season (`pred_price_2024.csv`
holds predictions made **from** 2024-25 data, i.e. 2025-26 prices). This project
names them after the season being **predicted**.

## Rolling forward a season

At the end of 2026-27, bump the three values at the top of `config.py`:

```python
TRAIN_THROUGH  = 2025   # newest training transition becomes 2025-26 -> 2026-27
SCORE_SEASON   = 2026   # 2026-27 end-of-season stats feed the model
PREDICT_SEASON = 2027   # predict 2027-28 starting prices
```

Nothing else needs editing. Team mappings for new seasons are pulled
automatically — upstream's `master_team_list.csv` stops at 2023-24, and
`fpl_data.load_master_teams()` fills the gap from each season's own
`teams.csv`. Newly promoted clubs are unseen at training time and pool into
the `other` team level rather than erroring.

## Model specification

```
next_cost ~ start_cost + final_cost + start_cost² + final_cost²
          + total_points + minutes + goals_scored + assists
          + points_per_game + value_season + selected_by_percent
          + no_mins + element_type + team_name
```

Teams appearing in under 3% of training rows are pooled into `other`, which is
also the dummy-encoding reference level; `GK` is the reference position. On the
current training window that leaves 18 named teams and 33 predictors, adjusted
R² 0.9423.

### Feature selection

The R's formula (below) was replaced in September 2026 after
`feature_experiments.py` scored the alternatives. Random CV mixes seasons, so it
cannot see a feature whose meaning drifts over time; the deciding test is a
**rolling-origin temporal backtest** — fit on every season before *s*, predict
the *s → s+1* transition, for 2020-21 through 2025-26.

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
- **The squares let the price slope bend.** A cheap player carries about half
  his price into next season (prices sit against a £4.0–4.5m floor), a premium
  about 85% (FPL keeps stars expensive). A straight line splits the difference
  and mis-prices both ends. Natural splines and per-price-tier adjustments were
  tested and did no better.
- **`final_cost` in place of `cost_change_start`** changes nothing numerically —
  alongside `start_cost` the two carry the same information — it just reads more
  naturally.
- **Tried and rejected:** gameweek-derived start/min/max/final ownership (no
  better than the end-of-season figure), in-season min/max price, previous-season
  lags, the `cumul_weighted_*` history, ICT index, bonus.

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

### Where on the price scale it works

`price_analysis.py` (also run by `run_pipeline.py`) asks the default model
where it does well and where it does not, using the same rolling-origin folds
as the feature selection: one out-of-sample prediction per row, 2020-21 to
2025-26 (2,974 player-seasons). Everything lands in
`output/price_analysis.json`.

- **The price curve.** How much of £1 of this season's price survives into
  next season's, holding the season fixed:
  `b_start + b_final + 2 (b_start_sq + b_final_sq) p`. It rises from £0.53 at
  £4m to £0.85 at £15m; without the squares it is a flat £0.58.
- **Moves by band.** 71% of £4.0–4.5m players hold their price; from £6m up
  most fall, typically by £0.5m, and £10m+ players fall no further on average
  than £8–9.5m ones (−£0.39m against −£0.40m).
- **Errors by band, with and without the squares.** The squares lower RMSE
  in all six price bands, most at £7m+. Without them the model over-prices
  £7.0–7.5m players by £0.19m and *under*-prices £10m+ players by £0.16m.
  Either way RMSE more than doubles from the floor (£0.24m) to £10m+ (£0.63m).
- **Tiers by position**, cut by `config.PRICE_TIERS` (Budget / Low-Mid /
  High-Mid / Premium, from the author's R tiering) on `start_cost`. Budget
  tiers are well covered in every position; expensive outfield tiers are not:
  95% intervals hold only 71% of High-Mid forwards and 75% of Premium
  midfielders. Premium GK, MID and FWD tiers have under 30 rows each.
- **Grouped drivers.** Each input group refitted away in turn. Dropping all
  four price terms raises RMSE by only £0.10m, because `value_season` is
  points ÷ price and lets the model rebuild price; drop it too and RMSE is
  £0.524m, level with carrying the price forward (£0.530m). Position is a
  distant second (+£0.015m); `total_points` adds nothing once the rest are in.
  This replaces permutation importance on the page: the four price terms
  partly cancel, so shuffling one alone exaggerates it.

`statsmodels` is used rather than `scikit-learn` because the R's output includes
prediction intervals and a coefficient table with p-values; neither exists in
scikit-learn. `PriceModel` owns the fitted team-lumping and column order
alongside the regression, which is what a tidymodels `workflow()` does and what
keeps the design matrix aligned when the league's composition changes.
