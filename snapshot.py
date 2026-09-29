"""Save today's current-season table from the official FPL API.

    python snapshot.py       ->  data/live/

Run once a day by ``.github/workflows/snapshot.yml``, shortly after FPL's
overnight price changes. The app reads what this writes instead of calling
the API itself, so a visitor never waits on the API, every visitor on a
given day sees the same numbers, and the host never needs to reach
``fantasy.premierleague.com`` at all -- only the machine running this does.

Three files, all small enough to commit daily:

    players.csv     bootstrap-static's elements: clean.RAW_COLS plus EXTRA_COLS
    teams.csv       team id -> name, in the master_teams schema
    progress.json   when it was fetched, and fixtures played per club

The players are stored *raw*, before :func:`clean.clean_season`, so the
cleaning stays in one place and a change to it applies to the snapshot
without refetching. The model reads only ``clean.RAW_COLS``; the extra
columns are there for the daily history ``record_predictions.py`` keeps.

``data/live/`` is a subfolder on purpose: ``train_and_save.is_stale`` watches
``data/*.csv``, and a daily snapshot must not look like new training data.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import clean
import config
import fpl_data

SNAPSHOT_DIR = config.DATA_DIR / "live"
PLAYERS_PATH = SNAPSHOT_DIR / "players.csv"
TEAMS_PATH = SNAPSHOT_DIR / "teams.csv"
PROGRESS_PATH = SNAPSHOT_DIR / "progress.json"

#: Fields the model does not read but the daily history keeps: availability,
#: FPL's own form and expected stats, set pieces, and its price-change
#: pressure. Any the API stops sending are skipped rather than failing the run.
EXTRA_COLS = [
    "status", "news", "news_added",
    "chance_of_playing_this_round", "chance_of_playing_next_round",
    "form", "value_form", "ep_this", "ep_next", "event_points",
    "starts", "saves", "goals_conceded", "own_goals",
    "penalties_saved", "penalties_missed", "yellow_cards", "red_cards",
    "expected_goals", "expected_assists", "expected_goal_involvements",
    "expected_goals_conceded", "defensive_contribution", "tackles",
    "recoveries", "clearances_blocks_interceptions",
    "penalties_order", "direct_freekicks_order", "corners_and_indirect_freekicks_order",
    "dreamteam_count", "in_dreamteam", "selected_rank",
    "cost_change_event", "transfers_in_event", "transfers_out_event",
    "price_change_percent", "price_change_hourly_rate",
    "price_change_calibrating", "price_change_locked_until",
]

#: ``price_change_projections`` is a list per player, one entry per step
#: ahead (FPL does not document the step's length), flattened to columns.
PROJECTION_STEPS = 3


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
    extras = [col for col in EXTRA_COLS if col in players.columns]
    _with_projections(players)[clean.RAW_COLS + extras + _projection_cols()].sort_values(
        "id").to_csv(
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


def _projection_cols() -> list[str]:
    return [f"price_change_proj{step}_{part}"
            for step in range(PROJECTION_STEPS) for part in ("percent", "likelihood")]


def _with_projections(players: pd.DataFrame) -> pd.DataFrame:
    """``players`` with ``price_change_projections`` spread over columns."""
    players = players.copy()
    projections = players.get("price_change_projections",
                              pd.Series([None] * len(players), index=players.index))
    for step in range(PROJECTION_STEPS):
        entries = [p[step] if isinstance(p, list) and len(p) > step else {}
                   for p in projections]
        players[f"price_change_proj{step}_percent"] = pd.to_numeric(
            [e.get("projected_percent") for e in entries], errors="coerce")
        players[f"price_change_proj{step}_likelihood"] = pd.to_numeric(
            [e.get("likelihood") for e in entries], errors="coerce")
    return players


def load(season: int = config.PREDICT_SEASON, directory: Path = SNAPSHOT_DIR) -> Snapshot | None:
    """The saved snapshot, or None if there is none for ``season``.

    A snapshot left over from last season is treated as missing rather than
    served: after ``config.PREDICT_SEASON`` is bumped, its players are the
    wrong year's. ``directory`` is for reading an old snapshot restored from
    git history; the app always reads ``data/live/``.
    """
    players_path = directory / PLAYERS_PATH.name
    teams_path = directory / TEAMS_PATH.name
    progress_path = directory / PROGRESS_PATH.name
    if not (players_path.exists() and teams_path.exists() and progress_path.exists()):
        return None

    meta = json.loads(progress_path.read_text(encoding="utf-8"))
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
        players=pd.read_csv(players_path, encoding="utf-8"),
        teams=pd.read_csv(teams_path, encoding="utf-8"),
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
