"""Add today's snapshot and predictions to the season's history file.

    python record_predictions.py              ->  data/history/<season>/<date>.csv
    python record_predictions.py --backfill   ->  also every earlier snapshot in git

Run once a day by ``.github/workflows/snapshot.yml``, straight after
``snapshot.py``. The snapshot in ``data/live/`` is overwritten every day, so
this is where the day-by-day record lives: one file per day, one row per
player, with the FPL figures as they stood that morning, the full-season projection
Price Watch makes from them, and the model's predicted start price for next
season -- exactly what Price Watch showed that day.

Files are named for the snapshot's UTC date, so running twice in a day
replaces that day's file rather than duplicating it. One file per day rather
than one per season because a day is ~300 KB: a season in one file would
approach GitHub's 100 MB limit, while daily files each land as a small new
file in the day's commit. :func:`load_history` stacks them back together.

``--backfill`` restores each earlier ``data/live/`` from git history and
records it too, so the history can start before this script did. It needs
the full git history, which the workflow's shallow checkout does not have:
run it locally. Snapshots from before the extra columns were saved leave
those columns blank.

The history lives in ``data/history/``, a subfolder, so that
``train_and_save.is_stale`` (which watches ``data/*.csv``) never mistakes
it for training data.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

import config
import snapshot

sys.path.insert(0, str(config.PROJECT_DIR / "app"))

import live  # noqa: E402
import model_store  # noqa: E402
import projection  # noqa: E402
import schema  # noqa: E402

HISTORY_DIR = config.DATA_DIR / "history"

#: Cleaned figures kept as they are, after the identity columns.
STAT_COLS = [
    "total_points", "minutes", "appearances", "goals_scored", "assists",
    "clean_sheets", "bonus", "bps", "points_per_game", "value_season",
    "selected_by_percent", "transfers_in", "transfers_out",
    "transfers_in_share", "transfers_out_share", "net_transfers_share",
    "ict_index", "influence", "creativity", "threat",
]

#: Totals Price Watch scales to a full season. The other model inputs are
#: today's figures (prices, ownership), so a projected copy would repeat them.
PROJECTED_COLS = ["minutes", "total_points", "goals_scored", "assists",
                  "points_per_game", "value_season"]


def history_path(date: str, season: int = config.PREDICT_SEASON) -> Path:
    return HISTORY_DIR / str(season) / f"{date}.csv"


def load_history(season: int = config.PREDICT_SEASON) -> pd.DataFrame:
    """Every recorded day of ``season`` in one frame, oldest first.

    Days recorded before a column was added have it blank.
    """
    paths = sorted((HISTORY_DIR / str(season)).glob("*.csv"))
    if not paths:
        return pd.DataFrame()
    return pd.concat([pd.read_csv(p, encoding="utf-8", low_memory=False) for p in paths],
                     ignore_index=True)


def build_rows(snap: snapshot.Snapshot) -> pd.DataFrame:
    """One row per player: the day's figures, projection and prediction.

    The projection and prediction are computed as Price Watch's ``compute``
    does, so a day's row matches what the page showed.
    """
    season = live.from_snapshot(snap)
    players = projection.with_appearances(season.players)

    projected = projection.project_frame(
        season.players, season.player_games, model_store.get_meta()["ranges"],
        league_games=season.progress.league_games,
    )
    interval = model_store.get_model().predict_with_interval(
        projected[schema.MODEL_INPUT_COLUMNS])

    rows = pd.DataFrame({
        "date": snap.fetched_at.date().isoformat(),
        "fetched_at": snap.fetched_at.isoformat(),
        "season": config.PREDICT_SEASON,
        "gameweeks_finished": snap.progress.gameweeks_finished,
        "current_event": snap.progress.current_event,
    }, index=players.index)

    for col in ["code", "id", "web_name", "first_name", "second_name",
                "element_type", "team", "team_code", "team_name"]:
        rows[col] = players[col]
    rows["element_type"] = rows["element_type"].astype(str)

    # Prices in £m. clean_season has already divided these by ten.
    rows["price"] = players["final_cost"]
    rows["start_price"] = players["start_cost"]
    rows["price_change_season"] = players["cost_change_start"].round(1)

    for col in STAT_COLS:
        rows[col] = players[col]

    # Everything the snapshot saved beyond what the model reads, by player.
    raw = snap.players.drop_duplicates("code").set_index("code")
    extras = [col for col in raw.columns if col not in rows.columns
              and (col in snapshot.EXTRA_COLS or col.startswith("price_change_proj"))]
    for col in extras:
        rows[col] = rows["code"].map(raw[col])
    if "cost_change_event" in rows:
        rows["cost_change_event"] = (rows["cost_change_event"] / 10).round(1)
        rows = rows.rename(columns={"cost_change_event": "price_change_event"})

    # Price Watch's full-season projection. project_frame keeps row order.
    rows["games_played"] = projected["games_played"].to_numpy()
    for col in PROJECTED_COLS:
        rows[f"proj_{col}"] = projected[col].to_numpy()
    rows["n_clamped"] = projected["n_clamped"].to_numpy()

    # The model's answer: next season's start price, with its 95% interval.
    rows["pred_next_start"] = interval["pred"].round(3).to_numpy()
    rows["pred_next_lower"] = interval["pred_lower"].round(3).to_numpy()
    rows["pred_next_upper"] = interval["pred_upper"].round(3).to_numpy()
    rows["pred_change"] = (rows["pred_next_start"] - rows["price"]).round(3)

    for col in ["transfers_in_share", "transfers_out_share", "net_transfers_share"]:
        rows[col] = rows[col].round(4)
    return rows.sort_values("code").reset_index(drop=True)


def record(snap: snapshot.Snapshot) -> tuple[pd.DataFrame, Path]:
    """Write the day's rows to its file, replacing any earlier run that day."""
    rows = build_rows(snap)
    path = history_path(rows["date"].iloc[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(path, index=False, encoding="utf-8")
    return rows, path


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=config.PROJECT_DIR, check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout


def past_snapshots(season: int = config.PREDICT_SEASON):
    """Every committed ``data/live/`` for ``season``, oldest first."""
    live_dir = snapshot.SNAPSHOT_DIR.relative_to(config.PROJECT_DIR).as_posix()
    commits = _git("log", "--reverse", "--format=%H", "--",
                   f"{live_dir}/{snapshot.PROGRESS_PATH.name}").split()
    for commit in commits:
        with tempfile.TemporaryDirectory() as tmp:
            for name in (snapshot.PLAYERS_PATH.name, snapshot.TEAMS_PATH.name,
                         snapshot.PROGRESS_PATH.name):
                (Path(tmp) / name).write_text(
                    _git("show", f"{commit}:{live_dir}/{name}"), encoding="utf-8")
            snap = snapshot.load(season, directory=Path(tmp))
        if snap is not None:
            yield snap


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backfill", action="store_true",
                        help="also record every earlier snapshot in git history")
    args = parser.parse_args(argv)

    if args.backfill:
        for snap in past_snapshots():
            record(snap)
            print(f"Backfilled {snap.fetched_at:%Y-%m-%d %H:%M} UTC")

    snap = snapshot.load()
    if snap is None:
        print(f"No {config.PREDICT_SEASON} snapshot in {snapshot.SNAPSHOT_DIR}; "
              "run snapshot.py first.", file=sys.stderr)
        return 1

    rows, path = record(snap)
    days = len(list(path.parent.glob("*.csv")))
    print(f"Recorded {len(rows)} players for {rows['date'].iloc[0]} "
          f"({days} days so far) -> {path.relative_to(config.PROJECT_DIR).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
