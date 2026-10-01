"""Fit the price model once and save it for the app to load.

    python train_and_save.py [--force]

``run_pipeline.py`` refits on every run, which is right for a batch job but
not for a web app: loading and cleaning ten seasons takes ~17s against a
0.1s fit, so the expensive half is the data, not the regression. This
script pays that cost once and writes three artifacts to ``models/``:

    price_model.joblib   the fitted PriceModel (lumper + columns + OLS)
    score_2025.csv       the cleaned scoring season, for the prefill list
    price_history.csv    every player's start/final price, every season
    meta.json            training ranges, team levels and source mtimes

The fitting steps mirror ``run_pipeline.py`` exactly so the app and the
batch pipeline cannot produce different numbers for the same player;
``tests/test_app_parity.py`` asserts that they don't.
"""

from __future__ import annotations

import argparse
import json

import joblib
import pandas as pd

import clean
import config
import features
import fpl_data
import model

MODEL_DIR = config.PROJECT_DIR / "models"
MODEL_PATH = MODEL_DIR / "price_model.joblib"
#: CSV rather than parquet: the frame is under a thousand rows, and the
#: venv has no pyarrow -- not worth the dependency for this.
SCORES_PATH = MODEL_DIR / f"score_{config.SCORE_SEASON}.csv"
#: Four columns per player-season, written here because the seasons are
#: already loaded and cleaned at this point. Reading them again in the app
#: would cost the ~17s this script exists to avoid.
PRICES_PATH = MODEL_DIR / "price_history.csv"
#: Every completed season What if can load, with the start price FPL then
#: set for the next one. Saved here rather than read from ``output/``,
#: which is not committed, so the hosted app has the real prices too.
SEASONS_PATH = MODEL_DIR / "seasons.csv"
META_PATH = MODEL_DIR / "meta.json"

#: Changing any of these changes what the model predicts, so the saved
#: artifact is stale if one of them is newer than it.
SOURCE_FILES = ["config.py", "clean.py", "features.py", "model.py"]


def source_mtimes() -> dict[str, float]:
    """Modification times of everything the fitted artifact depends on.

    The data files are included because re-downloading a season with
    ``--refresh`` changes the training set without touching any code.
    """
    stamps = {
        name: (config.PROJECT_DIR / name).stat().st_mtime
        for name in SOURCE_FILES
        if (config.PROJECT_DIR / name).exists()
    }
    for path in sorted(config.DATA_DIR.glob("*.csv")):
        stamps[f"data/{path.name}"] = path.stat().st_mtime
    return stamps


def is_stale() -> bool:
    """True if the artifacts are missing or older than their inputs."""
    if not (MODEL_PATH.exists() and SCORES_PATH.exists()
            and PRICES_PATH.exists() and SEASONS_PATH.exists()
            and META_PATH.exists()):
        return True
    try:
        saved = json.loads(META_PATH.read_text(encoding="utf-8"))["source_mtimes"]
    except (json.JSONDecodeError, KeyError, OSError):
        return True

    current = source_mtimes()
    if set(current) != set(saved):
        return True
    return any(current[name] > saved[name] for name in current)


def _training_ranges(train_df: pd.DataFrame, fitted: model.PriceModel) -> dict:
    """Observed min/median/max per input, as seen by the fitted model.

    Read off the *design matrix* rather than the raw frame so the derived
    rate columns are covered too, and so the numbers are exactly the range
    the OLS was fitted over. The app uses these three ways: to seed the
    manual form with medians, to warn when an entered value sits outside
    the fitted range, and to clamp projections before they reach the model.
    """
    X = features.build_design_matrix(train_df, fitted.lumper, fitted.columns)
    described = X.describe().transpose()
    return {
        column: {
            "min": float(described.loc[column, "min"]),
            "median": float(X[column].median()),
            "max": float(described.loc[column, "max"]),
        }
        for column in X.columns
    }


def completed_seasons(cleaned: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Every completed season, each row with the price FPL set next.

    ``next_cost`` is the player's start price in the *following* season,
    blank when he did not return. Seasons up to ``SCORE_SEASON``: anything
    later is still being played.
    """
    seasons = pd.concat([df for season, df in cleaned.items()
                         if season <= config.SCORE_SEASON], ignore_index=True)
    starts = pd.concat([df[["code", "season", "start_cost"]] for df in cleaned.values()],
                       ignore_index=True)
    starts = starts.assign(season=starts["season"] - 1).rename(
        columns={"start_cost": "next_cost"})
    seasons = seasons.merge(starts, on=["code", "season"], how="left")
    return seasons.sort_values(["season", "code"]).reset_index(drop=True)


def price_history(cleaned: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Every player's start and finishing price, one row per season.

    ``code`` rather than ``id`` because it is the identifier that survives
    across seasons -- ``id`` is reassigned each year, so joining on it would
    silently splice together the histories of unrelated players.
    """
    frames = [
        df[["code", "season", "start_cost", "final_cost"]]
        for df in cleaned.values()
    ]
    history = pd.concat(frames, ignore_index=True)
    return history.sort_values(["code", "season"]).reset_index(drop=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="rebuild even when the artifacts look current")
    parser.add_argument("--refresh", action="store_true",
                        help="re-download the season data instead of using data/")
    args = parser.parse_args(argv)

    if not (args.force or args.refresh) and not is_stale():
        print(f"Artifacts are current -> {MODEL_DIR.name}/  (--force to rebuild)")
        return

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    seasons = config.required_seasons()
    print(f"Loading {len(seasons)} seasons...")
    master_teams = fpl_data.load_master_teams(seasons, args.refresh)
    cleaned = clean.clean_all(fpl_data.load_all_seasons(seasons, args.refresh), master_teams)

    train_df = clean.build_training_frame(cleaned, config.TRAIN_THROUGH)
    fitted = model.PriceModel().fit(train_df)
    print(f"Fitted on {len(train_df)} rows, {len(fitted.columns)} predictors, "
          f"adj R2 {fitted.result.rsquared_adj:.4f}")

    # remove_data() would shrink the pickle, but get_prediction() needs the
    # retained design matrix -- without it predict_with_interval() loses the
    # obs_ci_* bounds that are the whole point of showing an interval.
    joblib.dump(fitted, MODEL_PATH)

    score_df = cleaned[config.SCORE_SEASON]
    score_df.to_csv(SCORES_PATH, index=False, encoding="utf-8")

    price_history(cleaned).to_csv(PRICES_PATH, index=False, encoding="utf-8")
    completed_seasons(cleaned).to_csv(SEASONS_PATH, index=False, encoding="utf-8")

    meta = {
        "score_season": config.SCORE_SEASON,
        "predict_season": config.PREDICT_SEASON,
        "train_through": config.TRAIN_THROUGH,
        "training_rows": len(train_df),
        "n_predictors": len(fitted.columns),
        "columns": fitted.columns,
        "teams_retained": fitted.lumper.keep_,
        "rsquared_adj": float(fitted.result.rsquared_adj),
        "sigma": float(fitted.result.mse_resid ** 0.5),
        "ranges": _training_ranges(train_df, fitted),
        "source_mtimes": source_mtimes(),
    }
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    for path in (MODEL_PATH, SCORES_PATH, PRICES_PATH, SEASONS_PATH, META_PATH):
        print(f"  wrote {path.relative_to(config.PROJECT_DIR)} "
              f"({path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
