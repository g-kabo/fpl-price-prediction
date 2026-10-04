# FPL Price Prediction

**Predicts every Fantasy Premier League player's starting price for next season
from how their current season is going.**

A transparent, backtested linear model rather than a black-box number. Each
prediction comes with a 95% prediction interval and breaks down exactly into
per-term contributions, so you can see *why* a player is priced the way he is.

**Live app:** <https://fpl-price-prediction.onrender.com>
(free hosting; the first visit after a quiet spell takes 30–60 seconds to wake it)

![Python](https://img.shields.io/badge/python-3.14-blue)
![Dash](https://img.shields.io/badge/app-Dash-informational)
![statsmodels](https://img.shields.io/badge/model-OLS%20(statsmodels)-lightgrey)

---

## Highlights

- **38% more accurate than assuming prices stay the same.** Backtested against
  the prices FPL actually set for 2026-27: RMSE £0.35m vs £0.57m for carrying
  each price forward.
- **Updated daily.** A GitHub Action snapshots the official FPL API every
  morning, after the overnight price changes, and the site redeploys from it.
- **Explainable.** The model is linear, so every prediction is shown as a
  waterfall from the intercept to the final price.
- **A record of every day's predictions.** Each snapshot also saves what the
  model predicted that day to `data/history/`, so forecasts can be tracked
  across the season.

## The app

| Page | What it does |
|---|---|
| **Price Watch** (`/`) | Every player's current 2026-27 form, projected to a full 38-game season, priced for 2027-28. Includes a scatter of today's price vs predicted, filterable by club. |
| **What if** (`/lab`) | Load any player's season since 2017-18, or this season as Price Watch projects it (or a typical player), edit the numbers, and see how next season's predicted price moves. |
| **How it works** (`/how-it-works`) | The fitted model written out as one equation, with every weight. |

Every player view shows the predicted price, its 95% interval, a plain-English
reading, a price history chart and the "why this price" breakdown.

## Results

Trained on 2017-18 → 2024-25 (3,812 player-seasons), scored on 2025-26 and
checked against the **actual** 2026-27 starting prices of 468 returning players:

| Metric | Value |
|---|---|
| RMSE | £0.353m |
| MAE | £0.262m |
| Within £0.25m of the real price | 59% |
| 95% interval coverage | 90.8% |
| Carry-forward baseline RMSE | £0.571m |
| **Improvement over baseline** | **38.2%** |

On a held-out 25% split, R² is 0.94.

**Known limitations**

- **Forwards are the weak spot.** Forward RMSE is £0.48m, compared with
  £0.32–0.34m for other positions, and the model tends to over-price them.
- **Intervals are slightly narrow.** 90.8% coverage against a nominal 95%. The
  real uncertainty grows with price, and a single OLS error term cannot capture
  that.
- **New players can't be priced.** Promoted-club players, new signings and
  debutants have no previous Premier League season to predict from.

## The model

Ordinary least squares, fitted with `statsmodels`:

```
next_start_price ~ start_cost + final_cost + start_cost² + final_cost²
                 + total_points + minutes + goals_scored + assists
                 + points_per_game + value_season + selected_by_percent
                 + no_mins + position + team
```

- **The squared price terms let the price curve bend.** A £4m player keeps about
  half his price into next season, while a £15m player keeps about 85%, because
  FPL keeps stars expensive.
- **Features were chosen by a rolling-origin temporal backtest.** Each season is
  predicted using only earlier seasons. This matters because some raw FPL
  figures, such as transfer counts, mean something different each year as the
  game grows.
- **Clubs in under 3% of training rows** are pooled into an `other` level, so
  newly promoted clubs never break the model.

Mid-season, Price Watch scales each player's totals by 38 ÷ *his club's*
fixtures played, counting a match in progress as a fraction. The projection is
clamped to the range the model was trained on.

The full reasoning, including the feature-selection ladder, accuracy by price
band and the design decisions behind each chart, is in
[docs/engineering-notes.md](docs/engineering-notes.md).

## Getting started

Requires Python 3.14.

```bash
git clone https://github.com/g-kabo/fpl-price-prediction.git
cd fpl-price-prediction
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

**Run the app**

```bash
python train_and_save.py        # fit and cache the model (~20s)
python snapshot.py              # save today's prices from the FPL API
python app/app.py               # open http://127.0.0.1:8051
```

**Run the static site** (the GitHub Pages version in `web/`)

```bash
python export_static.py --parity   # write web/data/*.json and the parity fixtures
node web/tests/parity.mjs          # the JavaScript model matches Python
python -m http.server 8052 -d web  # open http://localhost:8052
```

**Run the batch pipeline and backtest**

```bash
python run_pipeline.py          # predict every player, write output/
python backtest.py              # score against the prices FPL actually set
python feature_experiments.py   # re-run the feature-selection comparison
pytest                          # the app and pipeline agree on every player
```

Season data is downloaded on the first run and cached under `data/`, so later
runs work offline. Pass `--refresh` to download it again.

## Project structure

| Path | Purpose |
|---|---|
| `fpl_data.py` | Download and cache season data, and read the live snapshot |
| `clean.py` | Select columns, recover start prices, attach next season's price as the target |
| `features.py` | Squared price terms, team pooling, dummy encoding |
| `model.py` | `PriceModel`: OLS fit, cross-validation, prediction intervals |
| `feature_experiments.py` | Temporal backtest of alternative feature sets |
| `price_analysis.py` | Accuracy by price band, tier and position |
| `run_pipeline.py` / `backtest.py` | Batch predictions and scoring against actual prices |
| `train_and_save.py` | Fit once and cache the model to `models/` for the app |
| `snapshot.py` / `record_predictions.py` | Daily API snapshot and prediction history |
| `app/` | The Dash web app |
| `web/` / `export_static.py` | The static site (plain HTML and JavaScript) and the export that feeds it |
| `explore/` | Builds the full model report (`output/model_report.html`) |
| `tests/` | App vs pipeline parity tests |

## Deployment

- **[Render](https://render.com)** hosts the app from `render.yaml`. Each deploy
  installs the requirements, refits the model and serves it with gunicorn.
- **[GitHub Pages](https://pages.github.com)** serves the static site in `web/`,
  which has no server to wake up. `.github/workflows/pages.yml` refits the model,
  exports it and the day's projection to JSON, checks the JavaScript model against
  Python, and publishes. Settings > Pages > Source must be "GitHub Actions".
- **GitHub Actions** (`.github/workflows/snapshot.yml`) runs at 03:00 UTC daily.
  It snapshots the FPL API, records that day's predictions, commits both, then
  rebuilds the Pages site. That commit also triggers a Render redeploy. If a run
  fails, the site keeps showing the last good snapshot, marked with its date.

## Rolling forward a season

When a season ends, update the three values at the top of `config.py`:

```python
TRAIN_THROUGH  = 2025   # newest training transition: 2025-26 -> 2026-27
SCORE_SEASON   = 2026   # 2026-27 end-of-season stats feed the model
PREDICT_SEASON = 2027   # predict 2027-28 starting prices
```

Nothing else needs editing. New seasons' team lists are filled in automatically,
and newly promoted clubs pool into `other`.

## Background

This started as an R Markdown analysis (tidymodels, 2025) and was ported to
Python so it could be run, tested and served. Porting it surfaced two bugs in
the original's training data. One mislabelled a whole season's targets, and the
other paired a player with seasons years apart. Fixing both cut cross-validated
RMSE from 0.347 to 0.314. See
[Differences from the R](docs/engineering-notes.md#differences-from-the-r).

## Data

Historical seasons come from
[vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League),
which archives the official FPL API season by season. Live prices come from the
official [Fantasy Premier League](https://fantasy.premierleague.com) API. This is
an independent project and is not affiliated with the Premier League.
