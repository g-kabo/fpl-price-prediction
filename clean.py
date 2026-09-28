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
    # Not used by the default model; candidates in feature_experiments.py.
    # All four are present in every season from 2017-18 on.
    "ict_index", "influence", "creativity", "threat",
]

#: Columns the upstream CSVs sometimes deliver as strings.
NUMERIC_COLS = [
    "total_points", "minutes", "goals_scored", "assists", "bonus", "now_cost",
    "bps", "cost_change_start", "points_per_game", "selected_by_percent",
    "transfers_in", "transfers_out", "value_season", "clean_sheets",
    "ict_index", "influence", "creativity", "threat",
]

#: element_type 1-4 are playing positions; 5 (manager) is dropped, matching
#: the R's ``.default = "MAN"`` followed by ``filter(element_type != "MAN")``.
POSITION_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


#: Ownership over the season, from the gameweek files. See ownership_summary().
OWNERSHIP_COLS = [
    "start_selected_by_percent", "final_selected_by_percent",
    "min_selected_by_percent", "max_selected_by_percent",
]

#: Every FPL squad holds exactly 15 players, so the managers in a gameweek
#: are the sum of every player's owner count over 15.
SQUAD_SIZE = 15


def ownership_summary(gameweeks: pd.DataFrame) -> pd.DataFrame:
    """Start, final, min and max ``selected_by_percent`` per player id.

    The gameweek files record ``selected`` as a raw owner count, which drifts
    with the size of the game just as transfer counts do, so it is turned
    into a percentage here. The denominator is the gameweek's manager count,
    sum(selected) / 15. Its final-gameweek value tracks players_raw's own
    end-of-season ``selected_by_percent`` at r >= 0.999 in every season
    2017-18 to 2025-26, with a median relative gap of ~1% (the snapshot is
    taken a little after the last deadline, so the two are not identical).

    Blank gameweeks leave the players without a fixture out of the file, so
    their sum undercounts (2017-18 GW31 comes to 2.3m managers against ~5.5m
    either side). Manager counts only ever grow during a season -- entries
    join, none leave -- so a running maximum repairs those weeks. Players
    missing from a blank week simply have no observation for it.
    """
    managers = (gameweeks.groupby("gw")["selected"].sum() / SQUAD_SIZE).cummax()
    gw = gameweeks.assign(pct=100 * gameweeks["selected"] / gameweeks["gw"].map(managers))
    gw = gw.sort_values(["element", "gw"])
    g = gw.groupby("element")["pct"]
    return pd.DataFrame({
        "start_selected_by_percent": g.first(),
        "final_selected_by_percent": g.last(),
        "min_selected_by_percent": g.min(),
        "max_selected_by_percent": g.max(),
    }).rename_axis("id").reset_index()


def clean_season(
    raw: pd.DataFrame,
    season: int,
    master_teams: pd.DataFrame,
    gameweeks: pd.DataFrame | None = None,
) -> pd.DataFrame:
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

    df = df.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    df = _add_transfer_shares(df)
    if gameweeks is not None:
        df = _add_ownership(df, gameweeks)
    return df


def _add_ownership(df: pd.DataFrame, gameweeks: pd.DataFrame) -> pd.DataFrame:
    """Merge :func:`ownership_summary` on, by season player id.

    A player in the snapshot but absent from every gameweek (signed after
    the last deadline, say) falls back to the snapshot's own ownership for
    all four -- a flat line, which is what an unobserved season looks like.
    """
    df = df.merge(ownership_summary(gameweeks), on="id", how="left")
    for col in OWNERSHIP_COLS:
        df[col] = df[col].fillna(df["selected_by_percent"])
    return df


def _add_transfer_shares(df: pd.DataFrame) -> pd.DataFrame:
    """Each player's share of the season's transfers, per mille.

    Raw counts drift with the size of the game (FPL roughly doubled its
    manager count between 2017-18 and 2025-26), so a share is the
    season-comparable version. It has to be taken here, over the full
    snapshot: anywhere downstream may only see a slice of the season.
    """
    total_in, total_out = df["transfers_in"].sum(), df["transfers_out"].sum()
    df["transfers_in_share"] = 1000 * df["transfers_in"] / total_in
    df["transfers_out_share"] = 1000 * df["transfers_out"] / total_out
    df["net_transfers_share"] = df["transfers_in_share"] - df["transfers_out_share"]
    return df


def clean_all(
    raw_by_season: dict[int, pd.DataFrame],
    master_teams: pd.DataFrame,
    gameweeks_by_season: dict[int, pd.DataFrame] | None = None,
) -> dict[int, pd.DataFrame]:
    gameweeks_by_season = gameweeks_by_season or {}
    return {
        season: clean_season(raw, season, master_teams, gameweeks_by_season.get(season))
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
