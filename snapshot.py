"""Save today's current-season table from the official FPL API.

    python snapshot.py       ->  data/live/

Run once a day by ``.github/workflows/snapshot.yml``, shortly after FPL's
overnight price changes. The app reads what this writes instead of calling
the API itself, so a visitor never waits on the API, every visitor on a
given day sees the same numbers, and the host never needs to reach
``fantasy.premierleague.com`` at all -- only the machine running this does.

Three files, all small enough to commit daily:

    players.csv     bootstrap-static's elements, trimmed to clean.RAW_COLS
    teams.csv       team id -> name, in the master_teams schema
    progress.json   when it was fetched, and fixtures played per club

The players are stored *raw*, before :func:`clean.clean_season`, so the
cleaning stays in one place and a change to it applies to the snapshot
without refetching.

``data/live/`` is a subfolder on purpose: ``train_and_save.is_stale`` watches
``data/*.csv``, and a daily snapshot must not look like new training data.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

import clean
import config
import fpl_data

SNAPSHOT_DIR = config.DATA_DIR / "live"
PLAYERS_PATH = SNAPSHOT_DIR / "players.csv"
TEAMS_PATH = SNAPSHOT_DIR / "teams.csv"
PROGRESS_PATH = SNAPSHOT_DIR / "progress.json"


@dataclass
class Snapshot:
    """One day's saved table, ready for :func:`clean.clean_season`."""

    players: pd.DataFrame
    teams: pd.DataFrame
    progress: fpl_data.SeasonProgress
    fetched_at: datetime


def save(season: int = config.PREDICT_SEASON) -> datetime:
    """Fetch the live season and write it to ``data/live/``."""
    players, teams, progress = fpl_data.load_live_season(season)
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0)

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    players[clean.RAW_COLS].sort_values("id").to_csv(
        PLAYERS_PATH, index=False, encoding="utf-8")
    teams.to_csv(TEAMS_PATH, index=False, encoding="utf-8")
    PROGRESS_PATH.write_text(
        json.dumps(
            {
                "season": season,
                "fetched_at": fetched_at.isoformat(),
                "gameweeks_finished": progress.gameweeks_finished,
                "current_event": progress.current_event,
                "is_exact": progress.is_exact,
                # JSON keys are strings; load() turns them back into team ids.
                "team_games": {str(int(team)): round(float(games), 4)
                               for team, games in progress.team_games.items()},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return fetched_at


def load(season: int = config.PREDICT_SEASON) -> Snapshot | None:
    """The saved snapshot, or None if there is none for ``season``.

    A snapshot left over from last season is treated as missing rather than
    served: after ``config.PREDICT_SEASON`` is bumped, its players are the
    wrong year's.
    """
    if not (PLAYERS_PATH.exists() and TEAMS_PATH.exists() and PROGRESS_PATH.exists()):
        return None

    meta = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    if meta.get("season") != season:
        return None

    team_games = pd.Series(
        {int(team): float(games) for team, games in meta["team_games"].items()},
        dtype=float,
    ).sort_index()
    progress = fpl_data.SeasonProgress(
        team_games=team_games,
        gameweeks_finished=int(meta.get("gameweeks_finished", 0)),
        current_event=meta.get("current_event"),
        is_exact=bool(meta.get("is_exact", True)),
    )
    return Snapshot(
        players=pd.read_csv(PLAYERS_PATH, encoding="utf-8"),
        teams=pd.read_csv(TEAMS_PATH, encoding="utf-8"),
        progress=progress,
        fetched_at=datetime.fromisoformat(meta["fetched_at"]),
    )


def mtime() -> float:
    """When the snapshot was last written, or 0 if it has not been."""
    return PROGRESS_PATH.stat().st_mtime if PROGRESS_PATH.exists() else 0.0


def main() -> int:
    try:
        fetched_at = save()
    except Exception as exc:  # a failed run should fail the workflow, loudly
        print(f"Snapshot failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    snap = load()
    print(f"Saved {len(snap.players)} players, "
          f"{snap.progress.gameweeks_finished} gameweeks finished, "
          f"fetched {fetched_at:%Y-%m-%d %H:%M} UTC -> {SNAPSHOT_DIR.relative_to(config.PROJECT_DIR)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
