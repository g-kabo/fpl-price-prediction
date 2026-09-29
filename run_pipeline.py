"""End-to-end pipeline: fetch -> clean -> train -> evaluate -> predict -> export.

    python run_pipeline.py

Reproduce the R's published configuration and RMSE:

    python run_pipeline.py --train-through 2023 --score-season 2023 \
        --predict-season 2024 --r-compat --tag r_compat

Everything lands in ``output/``: the per-player predictions CSV, a
``metrics_*.json`` with every number quoted in the README, the price-curve
and tier analysis (``price_analysis.json``), and the figures.
"""

from __future__ import annotations

import argparse
import json

import pandas as pd

import clean
import config
import features
import fpl_data
import model
import plots
import price_analysis

#: Columns of the exported predictions, matching the R's pred_price_*.csv
#: shape (R used a leading dot on .pred; pandas-friendly names here).
OUTPUT_COLS = [
    "code", "id", "first_name", "second_name", "web_name", "element_type",
    "team", "minutes", "total_points", "final_cost", "start_cost",
    "pred", "pred_lower", "pred_upper", "price_start_change",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--train-through", type=int, default=config.TRAIN_THROUGH,
                   help="last season used for training (default: %(default)s)")
    p.add_argument("--score-season", type=int, default=config.SCORE_SEASON,
                   help="season whose end-of-season stats feed the model (default: %(default)s)")
    p.add_argument("--predict-season", type=int, default=config.PREDICT_SEASON,
                   help="season whose starting prices are predicted (default: %(default)s)")
    p.add_argument("--refresh", action="store_true", help="re-download instead of using data/ cache")
    p.add_argument("--r-compat", action="store_true",
                   help="reproduce the R: its lead() target, which pairs non-consecutive "
                        "seasons, and its original feature set")
    p.add_argument("--tag", default="", help="suffix for output filenames")
    p.add_argument("--importance-repeats", type=int, default=50,
                   help="permutation repeats, DALEX B (default: %(default)s); 0 to skip")
    p.add_argument("--no-plots", action="store_true")
    p.add_argument("--no-analysis", action="store_true",
                   help="skip price_analysis.py's price-curve and tier analysis")
    return p.parse_args()


def _suffix(tag: str) -> str:
    return f"_{tag}" if tag else ""


def main() -> None:
    args = parse_args()
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = _suffix(args.tag)

    seasons = config.required_seasons(args.train_through, args.score_season, args.predict_season)
    print(f"Seasons required: {', '.join(config.season_label(s) for s in seasons)}")

    master_teams = fpl_data.load_master_teams(seasons, args.refresh)
    cleaned = clean.clean_all(fpl_data.load_all_seasons(seasons, args.refresh), master_teams)

    missing_team = {s: int(d["team_name"].isna().sum()) for s, d in cleaned.items()}
    if any(missing_team.values()):
        print(f"  WARNING unmapped team ids: {missing_team}")

    train_df = clean.build_training_frame(
        cleaned, args.train_through, consecutive_only=not args.r_compat
    )
    print(f"Training rows: {len(train_df)} across "
          f"{config.season_label(train_df['season'].min())}-{config.season_label(train_df['season'].max())}"
          f"{'  [R-compatible target]' if args.r_compat else ''}")

    # The R's published RMSE came from the R's formula, not today's default.
    model_kwargs = {"numeric": features.R_NUMERIC} if args.r_compat else {}

    # --- evaluation on held-out data ---------------------------------------

    train_split, test_split = model.split_train_test(train_df)
    holdout = model.PriceModel(**model_kwargs).fit(train_split)
    test_pred = holdout.predict(test_split)
    holdout_metrics = {
        "rmse": model.rmse(test_split[model.TARGET], test_pred),
        "mae": model.mae(test_split[model.TARGET], test_pred),
        "rsq": model.r_squared(test_split[model.TARGET], test_pred),
        "n_train": len(train_split),
        "n_test": len(test_split),
    }
    print(f"Holdout  RMSE {holdout_metrics['rmse']:.4f}  MAE {holdout_metrics['mae']:.4f}  "
          f"R2 {holdout_metrics['rsq']:.4f}")

    cv_metrics = model.cross_validate(train_df, **model_kwargs)
    print(f"{cv_metrics['folds']}-fold CV  RMSE {cv_metrics['rmse_mean']:.4f} "
          f"(SE {cv_metrics['rmse_std_err']:.4f})  R2 {cv_metrics['rsq_mean']:.4f}")

    # --- final fit on every training row -----------------------------------

    final = model.PriceModel(**model_kwargs).fit(train_df)
    print(f"Final fit: {len(final.columns)} predictors, "
          f"{len(final.lumper.keep_)} named teams + '{config.OTHER_TEAM}', "
          f"adj R2 {final.result.rsquared_adj:.4f}")
    if final.n_dropped:
        print(f"  {final.n_dropped} incomplete rows dropped from the fit")

    coefs = final.coefficients()
    coefs.to_csv(config.OUTPUT_DIR / f"coefficients{tag}.csv", index=False, encoding="utf-8")

    # --- predict the next season -------------------------------------------

    score_df = cleaned[args.score_season].copy()
    intervals = final.predict_with_interval(score_df)
    predictions = pd.concat([score_df, intervals], axis=1)
    predictions["team"] = predictions["team_name"]
    predictions["price_start_change"] = predictions["pred"] - predictions["start_cost"]
    for col in ("pred", "pred_lower", "pred_upper", "price_start_change"):
        predictions[col] = predictions[col].round(2)

    unseen = sorted(set(score_df["team_name"].dropna()) - set(final.lumper.keep_))
    if unseen:
        print(f"  teams pooled into '{config.OTHER_TEAM}' when scoring: {', '.join(unseen)}")

    predictions = predictions[OUTPUT_COLS].sort_values(
        ["team", "element_type", "pred"], ascending=[True, True, False]
    )
    pred_path = config.OUTPUT_DIR / f"pred_price_{args.predict_season}{tag}.csv"
    predictions.to_csv(pred_path, index=False, encoding="utf-8")
    print(f"Wrote {len(predictions)} predictions -> {pred_path.name}")

    # --- variable importance ------------------------------------------------

    importance = None
    if args.importance_repeats:
        print(f"Permutation importance ({args.importance_repeats} repeats)...")
        importance = final.permutation_importance(train_df, n_repeats=args.importance_repeats)
        importance.to_csv(config.OUTPUT_DIR / f"variable_importance{tag}.csv", index=False, encoding="utf-8")
        print(importance.head(6).to_string(index=False))

    # --- price curve, bands and tiers ----------------------------------------

    # Describes the default model, so it is skipped when --r-compat swaps in
    # the R's formula.
    if not (args.no_analysis or args.r_compat):
        print("Price-curve and tier analysis (temporal folds)...")
        analysis = price_analysis.analyse(price_analysis.all_transitions(cleaned),
                                          args.train_through)
        price_analysis.summarise(analysis)
        price_analysis.write(analysis, tag)

    # --- figures ------------------------------------------------------------

    if not args.no_plots:
        test_frame = test_split.assign(pred=test_pred)
        written = [
            plots.predicted_vs_actual_by_season(test_frame),
            plots.previous_vs_predicted_by_position(predictions, args.predict_season),
            plots.team_prediction_intervals(predictions, args.predict_season),
            plots.coefficients(coefs),
        ]
        print("Plots: " + ", ".join(p.name for p in written))

    # --- metrics ------------------------------------------------------------

    metrics = {
        "config": {
            "train_through": args.train_through,
            "score_season": args.score_season,
            "predict_season": args.predict_season,
            "r_compat_target": args.r_compat,
            "team_lump_threshold": config.TEAM_LUMP_THRESHOLD,
            "seed": config.SEED,
        },
        "training_rows": len(train_df),
        "rows_per_season": train_df.groupby("season").size().to_dict(),
        "holdout": holdout_metrics,
        "cross_validation": cv_metrics,
        "final_fit": {
            "n_predictors": len(final.columns),
            "teams_retained": final.lumper.keep_,
            "rsquared": float(final.result.rsquared),
            "rsquared_adj": float(final.result.rsquared_adj),
            "sigma": float(final.result.mse_resid ** 0.5),
            "rows_dropped": final.n_dropped,
        },
        "predictions": {
            "n": len(predictions),
            "mean": float(predictions["pred"].mean()),
            "min": float(predictions["pred"].min()),
            "max": float(predictions["pred"].max()),
            "mean_interval_width": float((predictions["pred_upper"] - predictions["pred_lower"]).mean()),
        },
    }
    if importance is not None:
        metrics["variable_importance"] = importance.set_index("variable")["dropout_loss"].round(5).to_dict()

    metrics_path = config.OUTPUT_DIR / f"metrics{tag}.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {metrics_path.name}")


if __name__ == "__main__":
    main()
