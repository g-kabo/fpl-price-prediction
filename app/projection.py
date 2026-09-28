"""Turning a part-played season into a full-season row the model can read.

The model was fitted on completed seasons, so scoring a player on three
gameweeks of data means answering "what will this look like over 38?" The
obvious answer -- multiply by ``38 / games_played`` -- is wrong early
in the season, and not slightly wrong. A player on 28 points after three
games extrapolates to 354, against a training maximum of 344 and a 2025-26
best of 239. OLS does not degrade gracefully outside the range it was fitted
on, so those rows come back with prices that are not merely high but
meaningless.

Three guards, applied in order:

1. **Divide by the right number of games.** Mid-gameweek there is no single
   answer to "how many games have been played". On a Saturday evening in
   gameweek 5, twelve clubs have played five and eight have played four;
   scaling everyone by 38/4 hands the twelve a 25% bonus they did not earn,
   and scaling by 38/5 docks the eight for fixtures they have not had yet.
   So each player is divided by *his own club's* fixtures played, carried
   in a :class:`fpl_data.SeasonProgress`.

2. **Shrink toward a prior.** The naive projection is blended with what the
   player actually did last season, weighted by how much of this season has
   been played: ``w = gw / (gw + k)``. At gameweek 3 with the default k=6
   that is one third this season, two thirds last -- which is roughly the
   right confidence to have in three games. By gameweek 30 it is 83% this
   season and the prior has faded out of the way.

3. **Clamp to the fitted range.** Whatever survives the blend is held
   inside the training min/max, so the model is never asked to extrapolate
   even when a player genuinely is having a record-breaking season.

Ratios (``points_per_game``, ``value_season``) are never scaled -- they are
recomputed from the projected totals, since a per-game rate is already
season-length independent and multiplying one by 38 is meaningless.
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

MODES = {
    "shrunk": "Shrink toward last season",
    "naive": "Naive × full season",
    "asis": "As-is (no projection)",
}

DEFAULT_K = 6.0


def shrinkage_weight(games_played: float, k: float = DEFAULT_K) -> float:
    """How much to trust this season over last, in [0, 1].

    ``gw / (gw + k)`` is the standard shrinkage form: zero games means zero
    weight on this season, and the weight approaches 1 as evidence
    accumulates. ``k`` is the number of gameweeks at which the two sources
    are trusted equally.

    Games are fractional, not integer, because a club can be 60 minutes
    into its fifth fixture. Rounding that to 5 would credit a full match
    that is still being played.
    """
    games = max(0.0, float(games_played))
    return games / (games + k) if (games + k) else 0.0


def build_priors(previous: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Last season's totals per player, plus a fallback for newcomers.

    Returns ``(by_code, by_group)``. Roughly a quarter of any season's
    players have no previous-season row -- promoted clubs, new signings from
    abroad, academy graduates -- so they fall back to the median player of
    their position and price bracket, which is a far better guess than
    either zero or their own three games.
    """
    by_code = previous.set_index("code")[COUNTING_FIELDS].astype(float)

    grouped = previous.copy()
    grouped["price_tier"] = _price_tier(grouped["start_cost"])
    by_group = (
        grouped.groupby(["element_type", "price_tier"], observed=True)[COUNTING_FIELDS]
        .median()
        .astype(float)
    )
    return by_code, by_group


def _price_tier(start_cost: pd.Series) -> pd.Series:
    """Coarse price brackets, used only to match newcomers to a prior."""
    return pd.cut(
        start_cost.astype(float),
        bins=[0, 4.5, 5.5, 7.0, 9.0, 100.0],
        labels=["budget", "cheap", "mid", "premium", "elite"],
    )


def _prior_row(player: pd.Series, by_code: pd.DataFrame, by_group: pd.DataFrame) -> pd.Series:
    """The prior for one player: their own last season, or their group's."""
    code = player.get("code")
    if code in by_code.index:
        return by_code.loc[code]

    key = (player.get("element_type"), _price_tier(pd.Series([player["start_cost"]])).iloc[0])
    if key in by_group.index:
        return by_group.loc[key]

    return pd.Series(by_group.median(), index=COUNTING_FIELDS)


def project_row(
    player: pd.Series,
    games_played: float,
    by_code: pd.DataFrame,
    by_group: pd.DataFrame,
    ranges: dict,
    mode: str = "shrunk",
    k: float = DEFAULT_K,
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

    # A club that has not kicked off has no rate to extrapolate. Its
    # players' totals are all zero, and zero times anything is still zero,
    # so the prior carries them -- which is exactly what a weight of
    # ``0 / (0 + k)`` delivers.
    scale = TOTAL_GAMEWEEKS / games if games else 0.0
    league_scale = TOTAL_GAMEWEEKS / league if league else 0.0
    weight = shrinkage_weight(games, k) if mode == "shrunk" else 1.0

    values: dict[str, float] = {}

    for field in schema.NUMERIC_NAMES:
        current = float(player.get(field, 0.0) or 0.0)

        if field in FIXED_FIELDS or mode == "asis":
            values[field] = current
            continue
        if field in RATIO_FIELDS:
            continue  # recomputed below, once the totals are known

        extrapolated = current * (league_scale if field in LEAGUE_FIELDS else scale)
        if mode == "shrunk":
            prior = float(_prior_row(player, by_code, by_group).get(field, 0.0))
            values[field] = weight * extrapolated + (1 - weight) * prior
        else:
            values[field] = extrapolated

    # Ratios follow from the projected totals. Appearances are derived from
    # the projected minutes, not counted off the real season, so the rate
    # stays consistent with the totals it is divided into.
    appearances = max(1.0, values["minutes"] / 90.0)
    values["points_per_game"] = values["total_points"] / appearances

    final_cost = float(player.get("final_cost") or player.get("start_cost") or 1.0)
    values["value_season"] = values["total_points"] / max(final_cost, 0.1)

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
    previous: pd.DataFrame,
    games_played,
    ranges: dict,
    mode: str = "shrunk",
    k: float = DEFAULT_K,
    league_games: float | None = None,
) -> pd.DataFrame:
    """Project every current player, for the page's table.

    ``games_played`` is either one number for the whole league or one per
    player; see :func:`resolve_games`. The projected frame carries the
    figure each player was actually divided by, so the page can show it
    rather than leave the reader to assume everyone shared a denominator.
    """
    by_code, by_group = build_priors(previous)

    games = resolve_games(current, games_played)
    league = float(np.mean(games)) if league_games is None else float(league_games)

    rows, clamp_counts = [], []
    for position, (_, player) in enumerate(current.iterrows()):
        values, clamped = project_row(
            player, games[position], by_code, by_group, ranges, mode, k, league
        )
        values["code"] = player["code"]
        values["web_name"] = player["web_name"]
        values["games_played"] = round(float(games[position]), 2)
        rows.append(values)
        clamp_counts.append(len(clamped))

    projected = pd.DataFrame(rows)
    projected["n_clamped"] = clamp_counts
    return projected
