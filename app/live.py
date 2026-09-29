"""Today's current-season table, from the daily FPL snapshot.

The projection page needs current numbers: prices move daily and the GitHub
mirror the pipeline reads is refreshed on someone else's schedule, so its
current-season CSV can be weeks behind. ``snapshot.py`` saves the official
API's table once a day, just after the overnight price changes; this module
reads that file and runs it through the pipeline's own
:func:`clean.clean_season`.

Reading a saved file rather than the API means the app never has to reach
``fantasy.premierleague.com`` -- which hosting providers' addresses are not
always allowed to -- and every visitor on a given day sees the same prices.
Prices only change once a day, so nothing is lost by it.

With no snapshot at all, the page falls back to the mirror's cached CSV and
says so, rather than failing.

How far into the season each club is comes back with the players, as a
:class:`fpl_data.SeasonProgress`, because mid-gameweek the two halves of
the league are not at the same point and the projection needs to know it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import clean  # noqa: E402
import config  # noqa: E402
import fpl_data  # noqa: E402
import snapshot  # noqa: E402

TOTAL_GAMEWEEKS = 38

#: A day's snapshot plus slack for a late workflow run. Older than this and
#: the daily job has probably failed, which the page should say.
STALE_AFTER_HOURS = 36


@dataclass
class LiveSeason:
    """The current season as the model sees it, plus where it came from."""

    players: pd.DataFrame
    progress: fpl_data.SeasonProgress
    #: When the FPL API was read, in UTC. None for the mirror fallback.
    fetched_at: datetime | None
    #: True for the daily snapshot of the official API, False for the mirror.
    is_live: bool
    error: str = ""

    @property
    def token(self) -> str:
        """Changes whenever the underlying data does."""
        return self.fetched_at.isoformat() if self.fetched_at else f"fallback:{self.error}"

    @property
    def age_hours(self) -> float:
        if self.fetched_at is None:
            return float("inf")
        return (datetime.now(timezone.utc) - self.fetched_at).total_seconds() / 3600

    @property
    def is_stale(self) -> bool:
        return self.age_hours > STALE_AFTER_HOURS

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
    def as_of_label(self) -> str:
        """When the snapshot was taken, e.g. ``29 Sep, 03:02 UTC``."""
        if self.fetched_at is None:
            return "unknown"
        return f"{self.fetched_at.day} {self.fetched_at:%b, %H:%M} UTC"

    @property
    def source_label(self) -> str:
        if not self.is_live:
            return f"Offline — cached snapshot ({self.error}), {self.gameweek_label}"
        return f"FPL data as of {self.as_of_label}, {self.gameweek_label}"


_cache: LiveSeason | None = None
_cache_mtime: float = -1.0


def from_snapshot(snap: snapshot.Snapshot) -> LiveSeason:
    players = clean.clean_season(snap.players, config.PREDICT_SEASON, snap.teams)
    return LiveSeason(
        players=players,
        progress=snap.progress,
        fetched_at=snap.fetched_at,
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
        fetched_at=None,
        is_live=False,
        error=error,
    )


def get_live_season() -> LiveSeason:
    """The current-season frame, reloaded only when the snapshot changes.

    Keyed on the snapshot file's modification time, so a fresh
    ``python snapshot.py`` is picked up by a running app without a restart.
    """
    global _cache, _cache_mtime

    stamp = snapshot.mtime()
    if _cache is not None and stamp == _cache_mtime:
        return _cache

    try:
        snap = snapshot.load()
        _cache = from_snapshot(snap) if snap else _from_cache_file("no snapshot yet")
    except Exception as exc:  # unreadable file, or cleaning it failed
        _cache = _from_cache_file(type(exc).__name__)
    _cache_mtime = stamp
    return _cache
