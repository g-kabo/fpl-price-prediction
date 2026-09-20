"""Today's current-season table, from the official FPL API.

The projection page needs live numbers: prices move daily and the GitHub
mirror the pipeline reads is refreshed on someone else's schedule, so its
current-season CSV can be weeks behind. This module fetches
``bootstrap-static`` directly, runs it through the pipeline's own
:func:`clean.clean_season`, and caches the result for a few minutes.

Falling back to the cached CSV on a network failure is deliberate: an
offline laptop should still get a working page, as long as it is told the
numbers are old.

How far into the season each club is comes back with the players, as a
:class:`fpl_data.SeasonProgress`, because mid-gameweek the two halves of
the league are not at the same point and the projection needs to know it.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import clean  # noqa: E402
import config  # noqa: E402
import fpl_data  # noqa: E402

#: Long enough to survive a burst of callbacks, short enough that a price
#: change shows up within the same sitting.
TTL_SECONDS = 15 * 60

TOTAL_GAMEWEEKS = 38


@dataclass
class LiveSeason:
    """The current season as the model sees it, plus how it was obtained."""

    players: pd.DataFrame
    progress: fpl_data.SeasonProgress
    fetched_at: float
    is_live: bool
    error: str = ""

    @property
    def age_minutes(self) -> float:
        return (time.time() - self.fetched_at) / 60

    @property
    def player_games(self) -> pd.Series:
        """Fixtures played, per player, for the projection's denominator."""
        return self.progress.for_players(self.players)

    @property
    def gameweek_label(self) -> str:
        """Where the season is, honestly, including a half-played gameweek."""
        _low, high = self.progress.spread
        if self.progress.is_split:
            behind = int((self.progress.team_games < high - 0.01).sum())
            return (
                f"gameweek {high:.0f} of {TOTAL_GAMEWEEKS} in progress, "
                f"{behind} of {len(self.progress.team_games)} teams yet to play"
            )
        return f"{high:.0f} of {TOTAL_GAMEWEEKS} gameweeks played"

    @property
    def source_label(self) -> str:
        if not self.is_live:
            return f"Offline — cached snapshot ({self.error}), {self.gameweek_label}"
        age = self.age_minutes
        when = "just now" if age < 1 else f"{age:.0f} min ago"
        return f"Live — {self.gameweek_label}, fetched {when}"


_cache: LiveSeason | None = None


def _from_api() -> LiveSeason:
    raw, teams, progress = fpl_data.load_live_season(config.PREDICT_SEASON)
    players = clean.clean_season(raw, config.PREDICT_SEASON, teams)
    return LiveSeason(
        players=players,
        progress=progress,
        fetched_at=time.time(),
        is_live=True,
    )


def _from_cache_file(error: str) -> LiveSeason:
    """The pipeline's cached CSV, as a last resort."""
    raw = fpl_data.load_players_raw(config.PREDICT_SEASON)
    teams = fpl_data.load_master_teams([config.PREDICT_SEASON])
    players = clean.clean_season(raw, config.PREDICT_SEASON, teams)

    # No fixture list offline, so games played is inferred per team from
    # the busiest player's minutes. Crude, but it only has to be close, and
    # this path is already the degraded one.
    return LiveSeason(
        players=players,
        progress=fpl_data.infer_progress(players),
        fetched_at=time.time(),
        is_live=False,
        error=error,
    )


def get_live_season(force_refresh: bool = False) -> LiveSeason:
    """Cached current-season frame, refetched when the TTL expires."""
    global _cache

    fresh_enough = (
        _cache is not None
        and _cache.is_live
        and (time.time() - _cache.fetched_at) < TTL_SECONDS
    )
    if fresh_enough and not force_refresh:
        return _cache

    try:
        _cache = _from_api()
    except Exception as exc:  # network down, API shape changed, timeout
        if _cache is not None and not force_refresh:
            return _cache
        _cache = _from_cache_file(type(exc).__name__)

    return _cache
