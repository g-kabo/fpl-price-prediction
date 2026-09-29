"""Where on the price scale the model works, and where it doesn't.

    python price_analysis.py [--refresh] [--tag NAME]

Also run by ``run_pipeline.py``. Four questions, all asked of the default
model, answered in ``output/price_analysis{_tag}.json``:

* **The price curve.** How much of this season's price carries into next
  season's, at each price level -- the slope of the fitted model with
  respect to price, holding performance fixed. With the squared terms the
  slope bends; without them it is one number for every player.
* **Moves by band.** How far FPL actually moved prices between seasons, per
  £1m band. Descriptive: every transition, no model.
* **Errors by band, with and without the squares.** Out-of-sample error per
  band for the default model and for the same model minus
  ``start_cost_sq``/``final_cost_sq``.
* **Tiers by position.** The same errors cut by ``config.PRICE_TIERS``.
* **Drivers.** How much worse the model does out of sample when each group
  of inputs is refitted away. Permutation importance (``run_pipeline.py``)
  cannot answer this for the price terms: the four of them are collinear and
  partly cancel, so shuffling one alone breaks the others and exaggerates it.
  Dropping them as a group, and refitting, measures what price is worth.

Errors come from the rolling-origin temporal backtest ``feature_experiments.py``
trusts: for each season ``s`` from ``FIRST_TEST_SEASON``, fit on every
transition before ``s`` and predict ``s -> s+1``. Pooling those folds gives
one out-of-sample prediction per row across six seasons, which is enough to
score a £10m+ band that a single season's backtest would leave a handful of
players in.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

import clean
import config
import features
import fpl_data
import model
from feature_experiments import FIRST_TEST_SEASON

#: League-wide price bands, by ``start_cost``: (label, lower, upper).
#: The £8.0-9.5m and £10m+ bands are wider because the rows thin out.
PRICE_BANDS = [
    ("£4.0–4.5m", 4.0, 5.0),
    ("£5.0–5.5m", 5.0, 6.0),
    ("£6.0–6.5m", 6.0, 7.0),
    ("£7.0–7.5m", 7.0, 8.0),
    ("£8.0–9.5m", 8.0, 10.0),
    ("£10.0m+", 10.0, np.inf),
]

LINEAR_NUMERIC = [c for c in features.DEFAULT_NUMERIC if not c.endswith("_sq")]

#: Input groups refitted away one at a time for the drivers ranking:
#: key -> PriceModel keyword arguments. ``no_mins`` is always in the design
#: matrix and is not scored.
PRICE_TERMS = ("start_cost", "final_cost", "start_cost_sq", "final_cost_sq")


def _without(*drop: str) -> dict:
    return {"numeric": [c for c in features.DEFAULT_NUMERIC if c not in drop]}


DRIVER_GROUPS = {
    "price": _without(*PRICE_TERMS),
    **{c: _without(c) for c in features.DEFAULT_NUMERIC if c not in PRICE_TERMS},
    "position": {"use_position": False},
    "club": {"use_team": False},
}

#: The two models every error below is reported for.
VARIANTS = {"squares": {}, "linear": {"numeric": LINEAR_NUMERIC}}


def _price(df: pd.DataFrame) -> pd.Series:
    """``start_cost`` on FPL's 0.1 grid: it is recovered by subtraction and
    carries float noise (3.9999...) that would drop a £4.0m player out of
    the £4.0m band."""
    return df["start_cost"].round(1)


def price_band(df: pd.DataFrame) -> pd.Series:
    price = _price(df)
    out = pd.Series(pd.NA, index=df.index, dtype="object")
    for label, lower, upper in PRICE_BANDS:
        out[(price >= lower) & (price < upper)] = label
    return out


def price_tier(df: pd.DataFrame) -> pd.Series:
    price = _price(df)
    out = pd.Series(pd.NA, index=df.index, dtype="object")
    for position, bounds in config.PRICE_TIERS.items():
        at = df["element_type"] == position
        # Number of lower bounds the price clears = index into TIER_NAMES.
        level = sum((price >= b).astype(int) for b in bounds)
        out[at] = [config.TIER_NAMES[i] for i in level[at]]
    return out


def tier_ranges() -> dict[str, list[str]]:
    """``{"MID": ["under £5.0m", "£5.0–7.4m", ...]}``, for labelling."""
    out = {}
    for position, bounds in config.PRICE_TIERS.items():
        labels = [f"under £{bounds[0]:.1f}m"]
        labels += [f"£{lo:.1f}–{hi - 0.1:.1f}m" for lo, hi in zip(bounds, bounds[1:])]
        labels.append(f"£{bounds[-1]:.1f}m+")
        out[position] = labels
    return out


# --- the model's own slope --------------------------------------------------


def slope_curve(squares: model.PriceModel, linear: model.PriceModel,
                grid: np.ndarray) -> dict:
    """d(predicted next price) / d(this season's price), per price level.

    The price is moved as a whole -- start and end price together, so a
    player whose price did not move in-season -- which is the reading "how
    much of his price carries over". With the squares that derivative is

        b_start + b_final + 2 (b_start_sq + b_final_sq) p

    and without them it is the constant ``b_start + b_final``.
    """
    b = squares.result.params
    intercept = b["start_cost"] + b["final_cost"]
    bend = 2 * (b["start_cost_sq"] + b["final_cost_sq"])
    lin = linear.result.params
    return {
        "grid": [round(float(p), 2) for p in grid],
        "squares": [float(intercept + bend * p) for p in grid],
        "linear": float(lin["start_cost"] + lin["final_cost"]),
        "intercept": float(intercept),
        "bend": float(bend),
    }


# --- out-of-sample predictions ----------------------------------------------


def temporal_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    """One out-of-sample prediction per row, per variant, pooled over folds.

    Columns ``pred_<variant>``, plus ``lower_squares``/``upper_squares`` for
    the default model's 95% interval.
    """
    folds = []
    for season in range(FIRST_TEST_SEASON, int(frame["season"].max()) + 1):
        train, test = frame[frame["season"] < season], frame[frame["season"] == season]
        test = test.copy()
        for name, kwargs in VARIANTS.items():
            fitted = model.PriceModel(**kwargs).fit(train)
            if name == "squares":
                interval = fitted.predict_with_interval(test)
                test["pred_squares"] = interval["pred"]
                test["lower_squares"] = interval["pred_lower"]
                test["upper_squares"] = interval["pred_upper"]
            else:
                test[f"pred_{name}"] = fitted.predict(test)
        folds.append(test)
    pooled = pd.concat(folds)
    return pooled[pooled[model.TARGET].notna() & pooled["pred_squares"].notna()
                  & pooled["pred_linear"].notna()]


def temporal_rmse(frame: pd.DataFrame, kwargs: dict) -> float:
    """Pooled out-of-sample RMSE over the same folds as the predictions."""
    truth, preds = [], []
    for season in range(FIRST_TEST_SEASON, int(frame["season"].max()) + 1):
        train, test = frame[frame["season"] < season], frame[frame["season"] == season]
        preds.append(model.PriceModel(**kwargs).fit(train).predict(test))
        truth.append(test[model.TARGET])
    truth, pred = pd.concat(truth), pd.concat(preds)
    keep = truth.notna() & pred.notna()
    return model.rmse(truth[keep], pred[keep])


def drivers(frame: pd.DataFrame, baseline: float) -> list[dict]:
    rows = [{"group": name, "rmse": (r := temporal_rmse(frame, kwargs)),
             "rmse_increase": r - baseline}
            for name, kwargs in DRIVER_GROUPS.items()]
    return sorted(rows, key=lambda row: row["rmse_increase"], reverse=True)


def _errors(group: pd.DataFrame) -> dict:
    truth = group[model.TARGET]
    out = {"n": int(len(group))}
    for name in VARIANTS:
        pred = group[f"pred_{name}"]
        out[f"rmse_{name}"] = model.rmse(truth, pred)
        out[f"mae_{name}"] = model.mae(truth, pred)
        out[f"bias_{name}"] = float((pred - truth).mean())
    out["coverage"] = float(((truth >= group["lower_squares"])
                             & (truth <= group["upper_squares"])).mean())
    out["naive_rmse"] = model.rmse(truth, group["start_cost"])
    out["mean_move"] = float((truth - group["start_cost"]).mean())
    return out


def _moves(group: pd.DataFrame) -> dict:
    move = group[model.TARGET] - group["start_cost"]
    return {
        "n": int(len(group)),
        "mean_move": float(move.mean()),
        "median_move": float(move.median()),
        "share_up": float((move >= 0.1 - 1e-9).mean()),
        "share_hold": float((move.abs() < 0.1 - 1e-9).mean()),
        "share_down": float((move <= -0.1 + 1e-9).mean()),
        "mean_start": float(group["start_cost"].mean()),
        "mean_next": float(group[model.TARGET].mean()),
    }


def analyse(frame: pd.DataFrame, train_through: int = config.TRAIN_THROUGH) -> dict:
    """Everything in the JSON, from every consecutive transition in ``frame``.

    The slope is read off models fitted through ``train_through`` -- the
    same window as the model the app serves, so the curve and the equation
    on the page describe one fit. Errors use every season, fold by fold.
    """
    frame = frame.assign(band=price_band(frame), tier=price_tier(frame))

    train = frame[frame["season"] <= train_through]
    squares = model.PriceModel().fit(train)
    linear = model.PriceModel(numeric=LINEAR_NUMERIC).fit(train)
    top = float(_price(train).max())
    curve = slope_curve(squares, linear, np.arange(4.0, top + 0.01, 0.5))

    pooled = temporal_predictions(frame)
    labels = [label for label, _, _ in PRICE_BANDS]

    bands = []
    for label, lower, upper in PRICE_BANDS:
        everyone, tested = frame[frame["band"] == label], pooled[pooled["band"] == label]
        bands.append({"band": label, "lower": lower,
                      "upper": None if np.isinf(upper) else upper,
                      "moves": _moves(everyone), "errors": _errors(tested)})

    tiers = {}
    for position in config.POSITIONS:
        rows = []
        for tier, price_range in zip(config.TIER_NAMES, tier_ranges()[position]):
            group = pooled[(pooled["element_type"] == position) & (pooled["tier"] == tier)]
            if len(group):
                rows.append({"tier": tier, "range": price_range, **_errors(group)})
        tiers[position] = rows

    seasons = sorted(pooled["season"].unique())
    overall = _errors(pooled)
    return {
        "train_through": train_through,
        "transitions": int(len(frame)),
        "moves_seasons": [config.season_label(int(frame["season"].min())),
                          config.season_label(int(frame["season"].max()))],
        "test_seasons": [config.season_label(int(s)) for s in seasons],
        "slope": curve,
        "band_order": labels,
        "bands": bands,
        "overall": overall,
        "drivers": drivers(frame, overall["rmse_squares"]),
        # value_season is points / price, so with total_points beside it the
        # model half-rebuilds price when the price terms go. Dropping both
        # shows what price is really worth.
        "without_price_or_value_rmse": temporal_rmse(
            frame, _without(*PRICE_TERMS, "value_season")),
        "tier_names": config.TIER_NAMES,
        "tier_bounds": {k: list(v) for k, v in config.PRICE_TIERS.items()},
        "tiers": tiers,
    }


def all_transitions(cleaned: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Every consecutive transition whose target is already known.

    The newest loaded season is the one whose start prices are the newest
    targets, so transitions run up to the season before it.
    """
    return clean.build_training_frame(cleaned, train_through=max(cleaned) - 1)


def write(result: dict, tag: str = "") -> None:
    path = config.OUTPUT_DIR / f"price_analysis{tag}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {path.name}")


def summarise(result: dict) -> None:
    curve = result["slope"]
    first, last = curve["squares"][0], curve["squares"][-1]
    print(f"Price carried over: {first:.2f} at £{curve['grid'][0]:.1f}m -> "
          f"{last:.2f} at £{curve['grid'][-1]:.1f}m (without the squares: {curve['linear']:.2f})")
    print("Refitted without each input group (out-of-sample RMSE increase):")
    for row in result["drivers"]:
        print(f"  {row['group']:<20} {row['rmse_increase']:+.4f}")
    print(f"Out-of-sample errors, {result['test_seasons'][0]} to {result['test_seasons'][-1]}:")
    for band in result["bands"]:
        e = band["errors"]
        print(f"  {band['band']:<10} n={e['n']:>4}  move {band['moves']['mean_move']:+.2f}  "
              f"RMSE {e['rmse_squares']:.3f} (linear {e['rmse_linear']:.3f})  "
              f"bias {e['bias_squares']:+.3f} (linear {e['bias_linear']:+.3f})")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--refresh", action="store_true", help="re-download instead of using data/ cache")
    p.add_argument("--tag", default="", help="suffix for the output filename")
    args = p.parse_args()

    seasons = list(range(config.FIRST_SEASON, config.PREDICT_SEASON + 1))
    master_teams = fpl_data.load_master_teams(seasons, args.refresh)
    cleaned = clean.clean_all(fpl_data.load_all_seasons(seasons, args.refresh), master_teams)

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result = analyse(all_transitions(cleaned))
    summarise(result)
    write(result, f"_{args.tag}" if args.tag else "")


if __name__ == "__main__":
    main()
