"""Expanded reporting on the most recently predicted season.

``run_pipeline.py`` produces the predictions and ``backtest.py`` scores them;
this adds the breakdowns that make the score interpretable — by position, by
price point, by the two circumstances that break the model (a player changing
position or club) — plus three mutually-checking views of variable impact.

Everything lands in ``output/report_<season>.json``, which is what the
published report page is built from. Re-run it after each pipeline run.

    python report.py                 # uses the season settings in config.py
    python report.py --season 2026
"""

from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np
import pandas as pd

import clean
import config
import fpl_data
import model as model_mod

#: Price bands used for every price-point breakdown, in GBPm. Chosen to put a
#: usable number of players in each: FPL prices far more densely at the bottom
#: of the range than the top.
PRICE_BANDS = [0, 4.5, 5.5, 7.0, 9.0, 20]
PRICE_LABELS = ["<= 4.5", "4.6 - 5.5", "5.6 - 7.0", "7.1 - 9.0", "> 9.0"]

MINUTE_BANDS = [-1, 0, 500, 1500, 2500, 10000]
MINUTE_LABELS = ["0", "1 - 500", "501 - 1500", "1501 - 2500", "> 2500"]

#: Groups smaller than this report nothing but noise, so cross-tab cells
#: below it are dropped rather than shown.
MIN_CELL = 3
MIN_TEAM = 8


def _rmse(s: pd.Series) -> float:
    return float(np.sqrt((s.astype(float) ** 2).mean()))


def _summarise(g: pd.DataFrame) -> dict:
    """The same block of statistics wherever a group is summarised."""
    return {
        "n": int(len(g)),
        "rmse": _rmse(g["error"]),
        "mae": float(g["abs_error"].mean()),
        "bias": float(g["error"].mean()),
        "within_0_25m": float((g["abs_error"] <= 0.25).mean()),
        "coverage": float(g["in_interval"].mean()),
        "naive_rmse": _rmse(g["naive_error"]),
        "mean_interval_width": float(g["interval_width"].mean()),
    }


def prepare(backtest: pd.DataFrame) -> pd.DataFrame:
    """Attach the derived columns every breakdown below depends on."""
    b = backtest.copy()
    b["in_interval"] = (b["actual_start_cost"] >= b["pred_lower"]) & (
        b["actual_start_cost"] <= b["pred_upper"]
    )
    b["interval_width"] = b["pred_upper"] - b["pred_lower"]
    # The benchmark any price model has to beat: assume next season's price is
    # the same as this season's.
    b["naive_error"] = b["start_cost"] - b["actual_start_cost"]
    b["moved_club"] = b["team"] != b["current_team"]
    b["repositioned"] = b["element_type"] != b["current_position"]
    b["price_band"] = pd.cut(b["start_cost"], PRICE_BANDS, labels=PRICE_LABELS)
    b["minutes_band"] = pd.cut(b["minutes"], MINUTE_BANDS, labels=MINUTE_LABELS)
    b["actual_change"] = b["actual_start_cost"] - b["start_cost"]
    b["predicted_change"] = b["pred"] - b["start_cost"]
    return b


def breakdowns(b: pd.DataFrame) -> dict:
    def by(col: str) -> dict:
        return {str(k): _summarise(g) for k, g in b.groupby(col, observed=True)}

    cross: dict = {}
    for (pos, band), g in b.groupby(["element_type", "price_band"], observed=True):
        if len(g) >= MIN_CELL:
            cross.setdefault(str(pos), {})[str(band)] = _summarise(g)

    return {
        "overall": _summarise(b),
        "by_position": by("element_type"),
        "by_price_band": by("price_band"),
        "by_minutes_band": by("minutes_band"),
        "by_position_and_price": cross,
        "by_repositioned": by("repositioned"),
        "by_moved_club": by("moved_club"),
        "by_team": {
            str(k): _summarise(g)
            for k, g in b.groupby("current_team", observed=True)
            if len(g) >= MIN_TEAM
        },
    }


def interval_calibration(b: pd.DataFrame) -> list[dict]:
    """Quoted interval width against the width the errors actually imply.

    An honest 95% interval spans about 3.92 residual standard deviations.
    Comparing that with what the model quotes shows whether the intervals are
    the right *shape*, not merely the right size on average.
    """
    rows = []
    for band, g in b.groupby("price_band", observed=True):
        quoted = float(g["interval_width"].mean())
        implied = 3.92 * float(g["error"].std())
        rows.append({
            "band": str(band),
            "n": int(len(g)),
            "quoted_width": quoted,
            "implied_width": implied,
            "ratio": implied / quoted if quoted else float("nan"),
            "coverage": float(g["in_interval"].mean()),
        })
    return rows


def shrinkage(b: pd.DataFrame) -> dict:
    """How much of the price movement FPL made the model was willing to call."""
    return {
        "sd_actual_change": float(b["actual_change"].std()),
        "sd_predicted_change": float(b["predicted_change"].std()),
        "mean_abs_actual_change": float(b["actual_change"].abs().mean()),
        "mean_abs_predicted_change": float(b["predicted_change"].abs().mean()),
        "correlation": float(
            np.corrcoef(b["predicted_change"], b["actual_change"])[0, 1]
        ),
        "shrinkage": 1
        - float(b["predicted_change"].std() / b["actual_change"].std()),
    }


def variable_impact(train: pd.DataFrame) -> dict:
    """Three views of which predictors matter, recomputed each run.

    They are reported together because they disagree in an informative way:
    permutation importance credits collinear predictors individually, while a
    leave-one-out refit shows the model does not actually miss any one of them.
    """
    tr, te = model_mod.split_train_test(train)
    split_fit = model_mod.PriceModel().fit(tr)
    full_fit = model_mod.PriceModel().fit(train)

    baseline = model_mod.rmse(
        te[model_mod.TARGET].astype(float).to_numpy(),
        split_fit.predict(te).to_numpy(),
    )

    return {
        "standardized_effects": full_fit.standardized_effects(train).to_dict("records"),
        "permutation_importance": full_fit.permutation_importance(
            train, n_repeats=50
        ).to_dict("records"),
        "leave_one_out": split_fit.leave_one_out(tr, te).to_dict("records"),
        "loo_baseline_rmse": baseline,
    }


NOTABLE_COLS = [
    "web_name", "current_team", "element_type", "current_position",
    "minutes", "total_points", "start_cost", "pred", "pred_lower",
    "pred_upper", "actual_start_cost", "error", "abs_error",
    "moved_club", "repositioned", "in_interval",
]


def notable(b: pd.DataFrame, n: int = 15) -> dict:
    def out(d: pd.DataFrame) -> list[dict]:
        return d[NOTABLE_COLS].to_dict("records")

    # A player whose price did not move is trivially easy to call, so the
    # "best calls" list is restricted to players FPL actually repriced.
    repriced = b[b["start_cost"] != b["actual_start_cost"]]

    return {
        "over_predicted": out(b.nsmallest(n, "error")),
        "under_predicted": out(b.nlargest(n, "error")),
        "repositioned": out(b[b["repositioned"]].sort_values("abs_error", ascending=False)),
        "outside_interval_worst": out(b[~b["in_interval"]].nlargest(n, "abs_error")),
        "best_calls": out(repriced.nsmallest(n, "abs_error")),
    }


SCATTER_COLS = [
    "web_name", "element_type", "current_position", "current_team",
    "start_cost", "pred", "actual_start_cost", "error",
    "minutes", "total_points", "moved_club", "repositioned", "in_interval",
]

#: How many players each group on the report page shows. ``repositioned`` is
#: exempt — it is a complete list, not a top-n.
GROUP_SIZE = 15


def _flags(row: pd.Series) -> str:
    """The badges the report page shows beside a player, as plain text."""
    out = []
    if row["repositioned"]:
        out.append(f"{row['element_type']}->{row['current_position']}")
    if row["moved_club"]:
        out.append("moved club")
    if not row["in_interval"]:
        out.append("outside interval")
    return "; ".join(out)


def notable_table(
    b: pd.DataFrame, score_season: int, n: int = GROUP_SIZE
) -> pd.DataFrame:
    """Every scored player in the shape the report page's table uses.

    The page shows five overlapping slices of this frame; rather than emit a
    file per slice, each row carries the groups it belongs to in ``Groups``,
    so filtering on that column reproduces any tab exactly.

    The previous-price column is named after the season it came from
    (``2025-26``), so the header stays truthful as the seasons roll forward.
    """
    # A player whose price did not move is trivially easy to call, so the
    # "best calls" group is restricted to players FPL actually repriced.
    repriced = b[b["start_cost"] != b["actual_start_cost"]]
    members = {
        "over": b.nsmallest(n, "error").index,
        "under": b.nlargest(n, "error").index,
        "repositioned": b.index[b["repositioned"]],
        "missed interval": b[~b["in_interval"]].nlargest(n, "abs_error").index,
        "best call": repriced.nsmallest(n, "abs_error").index,
    }

    out = pd.DataFrame({
        "Player": b["current_web_name"],
        "Club": b["current_team"],
        "Pos": b["current_position"],
        "Mins": b["minutes"].astype(int),
        "Pts": b["total_points"].astype(int),
        config.season_label(score_season): b["start_cost"].round(2),
        "Predicted": b["pred"].round(2),
        "Actual": b["actual_start_cost"].round(2),
        "Miss": b["error"].round(2),
        "Flags": b.apply(_flags, axis=1),
    })
    out["Groups"] = [
        "; ".join(g for g, idx in members.items() if i in idx) for i in b.index
    ]
    return out.sort_values("Miss", key=lambda s: s.abs(), ascending=False)


#: Template for the standalone table. The data is spliced in at this marker,
#: so the file opens straight from disk with no server and no side-car files.
TEMPLATE_PATH = config.PROJECT_DIR / "templates" / "price_table.html"
DATA_MARKER = "/*__DATA__*/"


def write_standalone_table(
    table: pd.DataFrame, season: int, score_season: int
) -> pathlib.Path:
    """Render the interactive table as one self-contained HTML file.

    Everything the page needs is inlined, so it works offline from a file://
    URL. The one external reference is the Google Fonts stylesheet, which
    falls back to the system stack when there is no connection.
    """
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if DATA_MARKER not in template:
        raise SystemExit(f"{TEMPLATE_PATH.name} is missing its {DATA_MARKER} marker")

    rows = [
        [
            r["Player"], r["Club"], r["Pos"], int(r["Mins"]), int(r["Pts"]),
            float(r[str(config.season_label(score_season))]),
            float(r["Predicted"]), float(r["Actual"]), float(r["Miss"]),
            [f for f in str(r["Flags"]).split("; ") if f],
            [g for g in str(r["Groups"]).split("; ") if g],
        ]
        for _, r in table.iterrows()
    ]
    data = {
        "season": config.season_label(season),
        "prevSeasonLabel": config.season_label(score_season),
        "source": f"notable_{season}.csv",
        "rows": rows,
    }

    out = config.OUTPUT_DIR / f"price_table_{season}.html"
    out.write_text(
        template.replace(DATA_MARKER, json.dumps(data, separators=(",", ":"))),
        encoding="utf-8",
    )
    return out


def build(season: int, train_through: int, score_season: int) -> dict:
    seasons = config.required_seasons(train_through, score_season, season)
    master = fpl_data.load_master_teams(seasons)
    cleaned = clean.clean_all(fpl_data.load_all_seasons(seasons), master)
    train = clean.build_training_frame(cleaned, train_through)

    path = config.OUTPUT_DIR / f"backtest_{season}.csv"
    if not path.exists():
        raise SystemExit(f"{path.name} not found — run backtest.py first")
    b = prepare(pd.read_csv(path, encoding="utf-8"))

    return {
        "season": config.season_label(season),
        "generated_for": {
            "train_through": train_through,
            "score_season": score_season,
            "predict_season": season,
        },
        "training_rows": int(len(train)),
        "matched_players": int(len(b)),
        "breakdowns": breakdowns(b),
        "interval_calibration": interval_calibration(b),
        "shrinkage": shrinkage(b),
        "variable_impact": variable_impact(train),
        "notable": notable(b),
        "scatter": b[SCATTER_COLS].to_dict("records"),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--season", type=int, default=config.PREDICT_SEASON)
    p.add_argument("--train-through", type=int, default=config.TRAIN_THROUGH)
    p.add_argument("--score-season", type=int, default=config.SCORE_SEASON)
    args = p.parse_args()

    report = build(args.season, args.train_through, args.score_season)
    out = config.OUTPUT_DIR / f"report_{args.season}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    b = prepare(pd.read_csv(
        config.OUTPUT_DIR / f"backtest_{args.season}.csv", encoding="utf-8"
    ))
    table = notable_table(b, args.score_season)
    table_path = config.OUTPUT_DIR / f"notable_{args.season}.csv"
    table.to_csv(table_path, index=False, encoding="utf-8")

    o = report["breakdowns"]["overall"]
    print(f"{report['season']}: {o['n']} players, RMSE {o['rmse']:.4f}, "
          f"coverage {o['coverage']:.1%}")
    print(f"Wrote {out.name}")
    print(f"Wrote {table_path.name} ({len(table)} rows, "
          f"{(table['Groups'] != '').sum()} flagged into groups)")

    html_path = write_standalone_table(table, args.season, args.score_season)
    print(f"Wrote {html_path.name} "
          f"({html_path.stat().st_size / 1024:.0f} KB, opens straight from disk)")


if __name__ == "__main__":
    main()
