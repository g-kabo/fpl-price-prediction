"""Cleaning the raw season snapshots into a modelling frame.

Translation of ``clean_df()`` and the ``full_clean_df`` pipeline at lines
1126-1198 of ``Price Prediction.Rmd``.

Two deliberate departures from the R, both noted in the project README:

1. The R's ``clean_df(raw_FPL2023, 2024)`` on line 1170 passed the wrong
   season's data. It was masked by the ``filter(season < 2024)`` two lines
   later, so the published RMSE is unaffected, but it is not reproduced.
2. ``lead(start_cost)`` in R pairs a player's row with their next *present*
   season, which for someone who left the Premier League and returned means
   a target two or more years away. Here the pairing is required to be
   consecutive.
"""

from __future__ import annotations

import pandas as pd

import config

#: The 22 columns ``clean_df()`` selects, in R's order.
RAW_COLS = [
    "code", "id", "first_name", "second_name", "element_type", "team",
    "team_code", "total_points", "minutes", "goals_scored", "assists",
    "bonus", "now_cost", "bps", "cost_change_start", "points_per_game",
    "selected_by_percent", "transfers_in", "transfers_out", "value_season",
    "web_name", "clean_sheets",
]

#: Columns the upstream CSVs sometimes deliver as strings.
NUMERIC_COLS = [
    "total_points", "minutes", "goals_scored", "assists", "bonus", "now_cost",
    "bps", "cost_change_start", "points_per_game", "selected_by_percent",
    "transfers_in", "transfers_out", "value_season", "clean_sheets",
]

#: element_type 1-4 are playing positions; 5 (manager) is dropped, matching
#: the R's ``.default = "MAN"`` followed by ``filter(element_type != "MAN")``.
POSITION_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def clean_season(raw: pd.DataFrame, season: int, master_teams: pd.DataFrame) -> pd.DataFrame:
    """Clean one season's ``players_raw.csv`` snapshot.

    Prices arrive in tenths of a million. ``now_cost`` is the price at the
    time of the snapshot (end of season for completed seasons), so the
    starting price is recovered by subtracting the season-to-date change.
    """
    df = raw[RAW_COLS].copy()

    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["final_cost"] = df["now_cost"] / 10
    df["cost_change_start"] = df["cost_change_start"] / 10
    df["start_cost"] = df["final_cost"] - df["cost_change_start"]
    df = df.drop(columns=["now_cost"])

    df["element_type"] = df["element_type"].map(POSITION_MAP)
    df = df[df["element_type"].notna()].copy()
    df["element_type"] = pd.Categorical(
        df["element_type"], categories=config.POSITIONS, ordered=False
    )

    df["season"] = season
    df = df.merge(
        master_teams[["season", "team", "team_name"]],
        on=["season", "team"],
        how="left",
    )

    return df.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)


def clean_all(
    raw_by_season: dict[int, pd.DataFrame], master_teams: pd.DataFrame
) -> dict[int, pd.DataFrame]:
    return {
        season: clean_season(raw, season, master_teams)
        for season, raw in raw_by_season.items()
    }


def _add_cumulative_features(df: pd.DataFrame) -> pd.DataFrame:
    """Season-weighted running averages of a player's history to date.

    R lines 1174-1177. These are computed but deliberately *not* in the
    model formula — the R had them commented out of the recipe, and they
    are kept here for the same reason: available if wanted, not used yet.

    The R divides ``total_points / minutes`` unguarded, which yields Inf
    for any zero-minute season and poisons the running sum from that point
    on. Here zero-minute seasons contribute 0 instead.
    """
    grouped = df.groupby("code", sort=False)
    weight = grouped["season"].cumsum()

    points_per_min = (df["total_points"] / df["minutes"]).where(df["minutes"] > 0, 0.0)

    for name, series in (
        ("cumul_weighted_points", df["season"] * df["total_points"]),
        ("cumul_weighted_mins", df["season"] * df["minutes"]),
        ("cumul_weighted_points_per_min", df["season"] * points_per_min),
    ):
        running = series.groupby(df["code"], sort=False).cumsum() / weight
        df[name] = running.groupby(df["code"], sort=False).shift(1)

    return df


def build_training_frame(
    cleaned_by_season: dict[int, pd.DataFrame],
    train_through: int,
    consecutive_only: bool = True,
) -> pd.DataFrame:
    """Stack the cleaned seasons and attach next season's start price.

    The target ``next_cost`` is the same player's starting price in the
    immediately following season, matched on ``code`` — FPL's permanent
    per-player identifier, which unlike ``id`` survives across seasons.

    ``consecutive_only=False`` restores the R's raw ``lead()`` behaviour,
    which pairs a row with the player's next *present* season however many
    years later that is. It exists so the R's published RMSE can be
    reproduced on demand; leave it True for real runs.
    """
    df = (
        pd.concat(cleaned_by_season.values(), ignore_index=True)
        .sort_values(["code", "season"])
        .reset_index(drop=True)
    )

    df = _add_cumulative_features(df)

    grouped = df.groupby("code", sort=False)
    df["next_season"] = grouped["season"].shift(-1)
    df["next_cost"] = grouped["start_cost"].shift(-1)

    keep = df["next_cost"].notna()
    if consecutive_only:
        keep &= df["next_season"] == df["season"] + 1
    df = df[keep]
    df = df[df["season"] <= train_through]

    return df.reset_index(drop=True)
