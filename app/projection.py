"""Turning a part-played season into a full-season row the model can read.

The model was fitted on completed seasons, so a player three gameweeks in
has to be turned into "what will this look like over 38?" This page answers
with the player's own current-season form only: each total is multiplied by
``38 / games_played``. No blend with last season -- the projection is what
this season says, and nothing else.

Two guards:

1. **Divide by the right number of games.** Mid-gameweek there is no single
   answer to "how many games have been played". On a Saturday evening in
   gameweek 5, twelve clubs have played five and eight have played four;
   scaling everyone by 38/4 hands the twelve a 25% bonus they did not earn,
   and scaling by 38/5 docks the eight for fixtures they have not had yet.
   So each player is divided by *his own club's* fixtures played, carried
   in a :class:`fpl_data.SeasonProgress`.

2. **Clamp to the fitted range.** Early on, scaling a hot start by 38/3 can
   produce a season no player has ever had, and OLS does not degrade
   gracefully outside the range it was fitted on. Projected values are held
   inside the training min/max, and the page says how many players that
   touched.

Ratios (``points_per_game``, ``value_season``) are never scaled -- they are
recomputed from the projected totals, since a per-game rate is already
season-length independent and multiplying one by 38 is meaningless. Points
per game is divided by projected *appearances*, recovered from FPL's own
figure and projected like any other total, not by minutes / 90: a substitute
playing twenty minutes a week has far more appearances than 90s, and
dividing by 90s would credit him with several times his real points per
game. Points and appearances scale together, so the projected rate is
exactly the one FPL publishes today.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

import schema

TOTAL_GAMEWEEKS = 38

#: Counting stats that accumulate over a season and so scale with games
#: played. Everything else in the form is a price, a share or a ratio.
COUNTING_FIELDS = ["minutes", "total_points", "goals_scored", "assists"]

#: Counting stats that accrue on the league's calendar rather than on one
#: club's fixture list, and so scale by the league-average games played.
#: Empty since transfers in/out left the model; kept so a future
#: league-calendar stat has somewhere to go.
LEAGUE_FIELDS: list[str] = []

#: Known facts about *this* season, not forecasts -- projecting them would
#: be inventing information we already have. Ownership is a share, not a
#: running total, so it needs no scaling either: today's figure stands.
FIXED_FIELDS = ["start_cost", "final_cost", "selected_by_percent"]

#: Recomputed from the projected totals rather than scaled.
RATIO_FIELDS = ["points_per_game", "value_season"]


def with_appearances(frame: pd.DataFrame) -> pd.DataFrame:
    """``frame`` plus each player's appearances, recovered from FPL's ppg."""
    frame = frame.copy()
    frame[schema.APPEARANCES_FIELD] = [
        schema.infer_appearances(points, ppg, minutes)
        for points, ppg, minutes in zip(
            frame["total_points"], frame["points_per_game"], frame["minutes"])
    ]
    return frame


def project_row(
    player: pd.Series,
    games_played: float,
    ranges: dict,
    league_games: float | None = None,
) -> tuple[dict, list[str]]:
    """Project one part-season player to a full season.

    ``games_played`` is this player's *club's* fixtures played, fractional
    while a match is in progress. ``league_games`` is the twenty-club
    average, used for the fields in :data:`LEAGUE_FIELDS`; it defaults to
    ``games_played``, which is the right answer whenever every club is level.

    Returns the projected field values and the names of any field that had
    to be clamped, so the page can mark them rather than quietly altering
    what the user sees.
    """
    games = max(0.0, float(games_played))
    league = games if league_games is None else max(0.0, float(league_games))

    # A club that has not kicked off has no rate to extrapolate: its
    # players' totals are all zero, and stay zero.
    scale = TOTAL_GAMEWEEKS / games if games else 0.0
    league_scale = TOTAL_GAMEWEEKS / league if league else 0.0

    values: dict[str, float] = {}

    for field in schema.NUMERIC_NAMES:
        current = float(player.get(field, 0.0) or 0.0)

        if field in FIXED_FIELDS:
            values[field] = current
            continue
        if field in RATIO_FIELDS:
            continue  # recomputed below, once the totals are known

        values[field] = current * (league_scale if field in LEAGUE_FIELDS else scale)

    # Appearances are projected like the other totals, then held between
    # the games already played and one per gameweek.
    appearances_now = player.get(schema.APPEARANCES_FIELD)
    if appearances_now is None or pd.isna(appearances_now):
        appearances_now = schema.infer_appearances(
            player.get("total_points"), player.get("points_per_game"), player.get("minutes"))
    appearances_now = float(appearances_now)
    appearances = min(float(schema.MAX_APPEARANCES), max(appearances_now * scale, appearances_now))

    # Ratios follow from the projected totals, rounded as FPL publishes them.
    values["points_per_game"] = (round(values["total_points"] / appearances, 1)
                                 if appearances > 0 else 0.0)
    final_cost = float(player.get("final_cost") or player.get("start_cost") or 1.0)
    values["value_season"] = round(values["total_points"] / max(final_cost, 0.1), 1)

    clamped = _clamp(values, ranges)

    for name, _, _, integer in schema.NUMERIC_FIELDS:
        values[name] = int(round(values[name])) if integer else round(values[name], 2)

    values[schema.POSITION_FIELD] = player.get(schema.POSITION_FIELD)
    values[schema.TEAM_FIELD] = player.get(schema.TEAM_FIELD)

    return values, clamped


def _clamp(values: dict, ranges: dict) -> list[str]:
    """Hold every projected value inside the fitted range, in place."""
    clamped = []
    for field in schema.NUMERIC_NAMES:
        bounds = ranges.get(field)
        if not bounds:
            continue
        low, high = bounds["min"], bounds["max"]
        original = values[field]
        values[field] = float(np.clip(original, low, high))
        if not np.isclose(original, values[field]):
            clamped.append(field)
    return clamped


def resolve_games(current: pd.DataFrame, games_played) -> np.ndarray:
    """One games-played figure per row of ``current``.

    Accepts a single number -- every club level, or the user overriding the
    live figure by hand -- or one value per player, which is what
    :meth:`fpl_data.SeasonProgress.for_players` returns.
    """
    if isinstance(games_played, (pd.Series, np.ndarray, Sequence)) and not isinstance(
        games_played, (str, bytes)
    ):
        games = np.asarray(games_played, dtype=float)
        if len(games) != len(current):
            raise ValueError(
                f"games_played has {len(games)} entries for {len(current)} players"
            )
        return games

    return np.full(len(current), float(games_played), dtype=float)


def project_frame(
    current: pd.DataFrame,
    games_played,
    ranges: dict,
    league_games: float | None = None,
) -> pd.DataFrame:
    """Project every current player, for the page's table.

    ``games_played`` is either one number for the whole league or one per
    player; see :func:`resolve_games`. The projected frame carries the
    figure each player was actually divided by, so the page can show it
    rather than leave the reader to assume everyone shared a denominator.
    """
    current = with_appearances(current)

    games = resolve_games(current, games_played)
    league = float(np.mean(games)) if league_games is None else float(league_games)

    rows, clamp_counts = [], []
    for position, (_, player) in enumerate(current.iterrows()):
        values, clamped = project_row(
            player, games[position], ranges, league
        )
        values["code"] = player["code"]
        values["web_name"] = player["web_name"]
        values["games_played"] = round(float(games[position]), 2)
        rows.append(values)
        clamp_counts.append(len(clamped))

    projected = pd.DataFrame(rows)
    projected["n_clamped"] = clamp_counts
    return projected
