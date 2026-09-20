"""Score the exported predictions against the prices FPL actually set.

    python backtest.py

The R version never had this. It always predicted a season that had not
started, so the only error estimate available was the held-out split —
which measures performance on *past* transitions, under the price
structure of those years. Now that 2026-27 is under way, its starting
prices are known and the predictions can be checked against them directly.

Read the output with one caveat in mind: only players who appeared in the
scoring season *and* the predicted season can be scored. Newly promoted
squads and new signings from abroad have no prior FPL season, so the model
never produced a number for them and they are absent here.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

import clean
import config
import fpl_data
import model
import plots


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--predict-season", type=int, default=config.PREDICT_SEASON,
                   help="season being scored (default: %(default)s)")
    p.add_argument("--refresh", action="store_true", help="re-download instead of using data/ cache")
    p.add_argument("--tag", default="", help="suffix of the predictions file to score")
    p.add_argument("--no-plots", action="store_true")
    return p.parse_args()


def _summarise(df: pd.DataFrame) -> dict:
    error = df["pred"] - df["actual_start_cost"]
    covered = (df["actual_start_cost"] >= df["pred_lower"]) & (df["actual_start_cost"] <= df["pred_upper"])
    return {
        "n": int(len(df)),
        "rmse": model.rmse(df["actual_start_cost"], df["pred"]),
        "mae": model.mae(df["actual_start_cost"], df["pred"]),
        "bias": float(error.mean()),
        "within_0_1m": float((error.abs() <= 0.1).mean()),
        "within_0_25m": float((error.abs() <= 0.25).mean()),
        "interval_coverage": float(covered.mean()),
    }


def main() -> None:
    args = parse_args()
    tag = f"_{args.tag}" if args.tag else ""
    pred_path = config.OUTPUT_DIR / f"pred_price_{args.predict_season}{tag}.csv"
    if not pred_path.exists():
        raise SystemExit(f"{pred_path.name} not found — run run_pipeline.py first")

    predictions = pd.read_csv(pred_path, encoding="utf-8")

    # Actual starting prices, recovered the same way clean_season() does:
    # the live snapshot's price minus its season-to-date change.
    master_teams = fpl_data.load_master_teams([args.predict_season], args.refresh)
    actual = clean.clean_season(
        fpl_data.load_players_raw(args.predict_season, args.refresh),
        args.predict_season,
        master_teams,
    )

    scored = predictions.merge(
        actual[["code", "web_name", "team_name", "element_type", "start_cost"]].rename(
            columns={
                "web_name": "current_web_name",
                "team_name": "current_team",
                "element_type": "current_position",
                "start_cost": "actual_start_cost",
            }
        ),
        on="code",
        how="inner",
    )
    scored["error"] = scored["pred"] - scored["actual_start_cost"]
    scored["abs_error"] = scored["error"].abs()

    season = config.season_label(args.predict_season)
    print(f"Backtest for {season}")
    print(f"  {len(predictions)} predictions, {len(actual)} players in {season}, "
          f"{len(scored)} matched (returning players)")
    print(f"  {len(actual) - len(scored)} players in {season} had no prediction "
          f"(promoted clubs, new signings, debutants)")

    overall = _summarise(scored)
    print(f"\n  RMSE {overall['rmse']:.4f}   MAE {overall['mae']:.4f}   "
          f"bias {overall['bias']:+.4f}")
    print(f"  within £0.1m: {overall['within_0_1m']:.1%}   "
          f"within £0.25m: {overall['within_0_25m']:.1%}")
    print(f"  95% interval coverage: {overall['interval_coverage']:.1%}")

    by_position = {
        str(pos): _summarise(group)
        for pos, group in scored.groupby("current_position", observed=True)
    }
    print("\n  By position:")
    print(pd.DataFrame(by_position).T[["n", "rmse", "mae", "bias", "interval_coverage"]]
          .round(4).to_string())

    print("\n  Largest over-predictions (model too generous):")
    print(scored.nlargest(10, "error")[
        ["current_web_name", "current_team", "current_position",
         "start_cost", "pred", "actual_start_cost", "error"]
    ].to_string(index=False))

    print("\n  Largest under-predictions (model too stingy):")
    print(scored.nsmallest(10, "error")[
        ["current_web_name", "current_team", "current_position",
         "start_cost", "pred", "actual_start_cost", "error"]
    ].to_string(index=False))

    # A naive "price stays the same" baseline is the bar worth clearing:
    # most players' prices do not move much between seasons, so a model
    # that cannot beat carrying last season's start price forward is not
    # earning its keep.
    naive = model.rmse(scored["actual_start_cost"], scored["start_cost"])
    print(f"\n  Baseline (carry {config.season_label(args.predict_season - 1)} "
          f"starting price forward): RMSE {naive:.4f}")
    print(f"  Model improvement: {(1 - overall['rmse'] / naive):.1%}")

    scored_path = config.OUTPUT_DIR / f"backtest_{args.predict_season}{tag}.csv"
    scored.sort_values("abs_error", ascending=False).to_csv(scored_path, index=False, encoding="utf-8")

    results = {
        "predict_season": season,
        "matched_players": len(scored),
        "unmatched_players": len(actual) - len(scored),
        "overall": overall,
        "by_position": by_position,
        "naive_carry_forward_rmse": naive,
        "improvement_over_naive": float(1 - overall["rmse"] / naive),
    }
    results_path = config.OUTPUT_DIR / f"backtest_metrics_{args.predict_season}{tag}.json"
    results_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    if not args.no_plots:
        path = plots.backtest_scatter(scored, args.predict_season)
        print(f"\n  Plot: {path.name}")
    print(f"  Wrote {scored_path.name}, {results_path.name}")


if __name__ == "__main__":
    main()
