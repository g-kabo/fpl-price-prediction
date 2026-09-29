"""Score alternative feature sets against the default model.

    python feature_experiments.py [--refresh] [--tag NAME]

Each variant is a ``PriceModel(numeric=..., use_team=...)`` and is scored two
ways:

* **Random 10-fold CV** over the default training window -- the protocol
  ``run_pipeline.py`` reports, kept so the numbers line up with the README.
* **Rolling-origin temporal CV** -- for each season ``s`` from
  ``FIRST_TEST_SEASON`` to the newest completed one, fit on every transition
  that starts before ``s`` and predict the ``s -> s+1`` transition. This is
  the question the model is actually asked (next season, never seen), and
  unlike random CV it cannot borrow a season's price structure from rows of
  that same season. It is the column to trust: a feature whose meaning drifts
  over time, like raw transfer counts in a game whose player base has nearly
  doubled, can look fine under random CV and still hurt here.

The final fold (2025 -> 2026) is the same transition ``backtest.py`` scores,
so its RMSE is directly comparable with ``backtest_metrics_2026.json``.

Writes ``output/feature_experiments{_tag}.csv`` (one row per variant) and
``output/feature_experiments_folds{_tag}.csv`` (one row per variant x fold).
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold

import clean
import config
import features
import fpl_data
import model

#: First season used as a temporal test fold. Training on 2017-2019 alone
#: (three transitions, ~1,100 rows) is the smallest window worth trusting.
FIRST_TEST_SEASON = 2020

#: Previous-season features. A player's price is sticky and FPL's pricing
#: team clearly looks past one season, so the season *before* the scoring
#: one carries information the snapshot does not.
LAG_FEATURES = [
    "prev_total_points", "prev_minutes", "prev_cost_change", "prev_start_cost",
    "has_prev_season",
]
CUMUL_FEATURES = [
    "cumul_weighted_points", "cumul_weighted_mins", "cumul_weighted_points_per_min",
]

#: Round one's variants are all defined relative to the R's formula.
D = features.R_NUMERIC


def without(*drop: str) -> list[str]:
    return [c for c in D if c not in drop]


TRANSFERS = ("transfers_in", "transfers_out")
RATES = tuple(features.RATE_FEATURES)

#: The base this round builds on: raw transfer counts and the per-minute
#: rates both removed. Round one found transfers drift with the size of the
#: game, and dropping the rates on top cost nothing (temporal RMSE 0.3154 ->
#: 0.3138, better in 5 of 6 folds).
LEAN = without(*TRANSFERS, *RATES)

START, FINAL, MIN, MAX = (f"{k}_selected_by_percent" for k in ("start", "final", "min", "max"))
OWNERSHIP = [START, FINAL, MIN, MAX]

#: The route from the R's formula to today's default, one change per step --
#: the README's Feature selection table, and the ladder the app's "Inside
#: the model" page draws. Each step keeps every change above it.
LADDER: dict[str, dict] = {
    "R formula": {"numeric": D},
    "transfers -> selected_by_percent": {"numeric": without(*TRANSFERS) + ["selected_by_percent"]},
    "drop the per-minute rates": {"numeric": LEAN + ["selected_by_percent"]},
    "add start_cost^2 and final_cost^2": {
        "numeric": LEAN + ["selected_by_percent", "start_cost_sq", "final_cost_sq"]},
    "drop bps and clean_sheets": {},
}

#: name -> PriceModel keyword arguments. The ladder comes first, so the
#: baseline every delta is measured from is the R formula.
VARIANTS: dict[str, dict] = {
    **LADDER,
    "default without the squared prices": {
        "numeric": [c for c in features.DEFAULT_NUMERIC if not c.endswith("_sq")]},
    "lean (no transfers, no rates)": {"numeric": LEAN},

    # --- one ownership number -----------------------------------------------
    "lean + selected_by_percent (snapshot)": {"numeric": LEAN + ["selected_by_percent"]},
    "lean + final_selected (gameweek)": {"numeric": LEAN + [FINAL]},
    "lean + start_selected": {"numeric": LEAN + [START]},
    "lean + max_selected": {"numeric": LEAN + [MAX]},

    # --- the ownership path -------------------------------------------------
    "lean + start + final": {"numeric": LEAN + [START, FINAL]},
    "lean + final + max": {"numeric": LEAN + [FINAL, MAX]},
    "lean + min + max": {"numeric": LEAN + [MIN, MAX]},
    "lean + start + final + max": {"numeric": LEAN + [START, FINAL, MAX]},
    "lean + all four ownership": {"numeric": LEAN + OWNERSHIP},

    # --- keeping the rates, to confirm dropping them still holds ------------
    "lean + rates + all four ownership": {"numeric": LEAN + list(RATES) + OWNERSHIP},
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--refresh", action="store_true", help="re-download instead of using data/ cache")
    p.add_argument("--tag", default="", help="suffix for output filenames")
    p.add_argument("--leave-one-out", action="store_true",
                   help="also refit without each lean variable under temporal CV")
    return p.parse_args()


def add_lag_features(stacked: pd.DataFrame) -> pd.DataFrame:
    """Attach the previous *consecutive* season's stats to every row.

    A player's first season, or their first back after a gap, has no
    previous season: the lags are zeroed and ``has_prev_season`` says so,
    the same treatment ``no_mins`` gives zero-minute players.
    """
    df = stacked.sort_values(["code", "season"]).reset_index(drop=True)
    g = df.groupby("code", sort=False)
    consecutive = g["season"].shift(1) == df["season"] - 1
    for new, col in (("prev_total_points", "total_points"), ("prev_minutes", "minutes"),
                     ("prev_cost_change", "cost_change_start"), ("prev_start_cost", "start_cost")):
        df[new] = g[col].shift(1).where(consecutive, 0.0)
    df["has_prev_season"] = consecutive.astype(float)
    for col in CUMUL_FEATURES:
        df[col] = df[col].fillna(0.0)
    return df


def load_frame(refresh: bool) -> pd.DataFrame:
    """Every consecutive-season transition from 2017-18 to the newest one."""
    newest = config.PREDICT_SEASON  # its start prices are the newest targets
    seasons = list(range(config.FIRST_SEASON, newest + 1))
    master_teams = fpl_data.load_master_teams(seasons, refresh)
    # Gameweek ownership is only needed for seasons that are predictors, and
    # the newest season's file is incomplete until it ends.
    gameweeks = fpl_data.load_all_gameweeks(seasons[:-1], refresh)
    cleaned = clean.clean_all(fpl_data.load_all_seasons(seasons, refresh), master_teams, gameweeks)
    frame = clean.build_training_frame(cleaned, train_through=newest - 1)
    # Lags need every season's rows, including ones with no next season.
    stacked = pd.concat(cleaned.values(), ignore_index=True)
    stacked = clean._add_cumulative_features(stacked.sort_values(["code", "season"]).reset_index(drop=True))
    lagged = add_lag_features(stacked)[["code", "season"] + LAG_FEATURES + CUMUL_FEATURES]
    frame = frame.drop(columns=CUMUL_FEATURES).merge(lagged, on=["code", "season"], how="left")
    return frame


def _score(truth: pd.Series, pred: pd.Series) -> tuple[float, float, int]:
    keep = truth.notna() & pred.notna()
    return model.rmse(truth[keep], pred[keep]), model.mae(truth[keep], pred[keep]), int(keep.sum())


def temporal_cv(frame: pd.DataFrame, kwargs: dict) -> list[dict]:
    rows = []
    for season in range(FIRST_TEST_SEASON, int(frame["season"].max()) + 1):
        train, test = frame[frame["season"] < season], frame[frame["season"] == season]
        pred = model.PriceModel(**kwargs).fit(train).predict(test)
        rmse, mae, n = _score(test[model.TARGET], pred)
        naive, _, _ = _score(test[model.TARGET], test["start_cost"])
        rows.append({"test_season": config.season_label(season), "rmse": rmse, "mae": mae,
                     "naive_rmse": naive, "n": n})
    return rows


def random_cv(frame: pd.DataFrame, kwargs: dict) -> float:
    """``model.cross_validate`` with a configurable model, same folds."""
    df = frame[frame["season"] <= config.TRAIN_THROUGH]
    kfold = KFold(n_splits=config.CV_FOLDS, shuffle=True, random_state=config.SEED)
    scores = []
    for tr, te in kfold.split(df):
        pred = model.PriceModel(**kwargs).fit(df.iloc[tr]).predict(df.iloc[te])
        scores.append(_score(df.iloc[te][model.TARGET], pred)[0])
    return float(np.mean(scores))


def run(frame: pd.DataFrame, variants: dict[str, dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary, folds = [], []
    for name, kwargs in variants.items():
        fold_rows = temporal_cv(frame, kwargs)
        fold_df = pd.DataFrame(fold_rows)
        folds += [{"variant": name, **r} for r in fold_rows]
        n_predictors = len(model.PriceModel(**kwargs).fit(frame).columns)
        summary.append({
            "variant": name,
            "n_predictors": n_predictors,
            "random_cv_rmse": random_cv(frame, kwargs),
            "temporal_rmse": float(fold_df["rmse"].mean()),
            "temporal_mae": float(fold_df["mae"].mean()),
            "rmse_2026": float(fold_df["rmse"].iloc[-1]),
        })
        print(f"  {name:<55} temporal {summary[-1]['temporal_rmse']:.4f}")

    out = pd.DataFrame(summary)
    ladder = list(LADDER)
    out["ladder_step"] = [ladder.index(v) if v in ladder else pd.NA for v in out["variant"]]
    out["ladder_step"] = out["ladder_step"].astype("Int64")
    base = out.iloc[0]
    for col in ("random_cv_rmse", "temporal_rmse", "rmse_2026"):
        out[f"{col}_delta"] = out[col] - base[col]
    # How many temporal folds the variant beats the baseline in -- a change
    # that wins on average but in only two of six seasons is noise.
    fold_df = pd.DataFrame(folds)
    base_folds = fold_df[fold_df["variant"] == base["variant"]].set_index("test_season")["rmse"]
    out["folds_won"] = [
        int((fold_df[fold_df["variant"] == v].set_index("test_season")["rmse"] < base_folds).sum())
        for v in out["variant"]
    ]
    return out, fold_df


def main() -> None:
    args = parse_args()
    tag = f"_{args.tag}" if args.tag else ""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    frame = load_frame(args.refresh)
    print(f"{len(frame)} transitions, {config.season_label(frame['season'].min())} to "
          f"{config.season_label(frame['season'].max())}")
    print(f"Temporal folds: {config.season_label(FIRST_TEST_SEASON)} .. "
          f"{config.season_label(frame['season'].max())}\n")

    variants = dict(VARIANTS)
    if args.leave_one_out:
        best = LEAN + OWNERSHIP
        for var in best:
            variants.setdefault(f"loo: lean + ownership minus {var}",
                                {"numeric": [c for c in best if c != var]})

    summary, folds = run(frame, variants)
    n_folds = folds["test_season"].nunique()

    pd.set_option("display.width", 200)
    print(f"\nSorted by temporal RMSE (lower is better; deltas vs baseline; folds won of {n_folds}):")
    cols = ["variant", "n_predictors", "random_cv_rmse", "random_cv_rmse_delta",
            "temporal_rmse", "temporal_rmse_delta", "rmse_2026", "rmse_2026_delta", "folds_won"]
    print(summary.sort_values("temporal_rmse")[cols].round(4).to_string(index=False))

    naive = folds[folds["variant"] == summary.iloc[0]["variant"]][["test_season", "naive_rmse", "rmse"]]
    print("\nBaseline vs carry-forward, per temporal fold:")
    print(naive.rename(columns={"rmse": "baseline_rmse"}).round(4).to_string(index=False))

    summary.to_csv(config.OUTPUT_DIR / f"feature_experiments{tag}.csv", index=False, encoding="utf-8")
    folds.to_csv(config.OUTPUT_DIR / f"feature_experiments_folds{tag}.csv", index=False, encoding="utf-8")
    print(f"\nWrote feature_experiments{tag}.csv, feature_experiments_folds{tag}.csv")


if __name__ == "__main__":
    main()
