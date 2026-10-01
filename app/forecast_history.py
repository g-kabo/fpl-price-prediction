"""What Price Watch predicted on each day so far, read back for the app.

``record_predictions.py`` writes one file per day to ``data/history/``, each
holding every player's price that morning and the model's prediction from
it. This module reads those files back for the player card's forecast trend
and the board's forecast movers.

Only the handful of columns the app draws are read, so a season of daily
files stays small in memory. The frame is cached and reloaded only when a
file is added or rewritten, so a running app picks up the next morning's
day without a restart.

The latest day can be today, the same snapshot the page computes live. The
callers compare against *earlier* days only and take today from the live
frame, so a day recorded later than the snapshot it came from (or never
recorded, on a local machine) does not matter.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from record_predictions import HISTORY_DIR  # noqa: E402

COLUMNS = ["date", "gameweeks_finished", "code", "price",
           "pred_next_start", "pred_next_lower", "pred_next_upper"]

_cache: pd.DataFrame | None = None
_cache_key: tuple = ()


def load(season: int = config.PREDICT_SEASON) -> pd.DataFrame:
    """Every recorded day of ``season``, oldest first. Empty if none."""
    global _cache, _cache_key

    paths = sorted((HISTORY_DIR / str(season)).glob("*.csv"))
    key = tuple((p.name, p.stat().st_mtime) for p in paths)
    if _cache is not None and key == _cache_key:
        return _cache

    if paths:
        frame = pd.concat(
            [pd.read_csv(p, usecols=lambda c: c in COLUMNS, encoding="utf-8") for p in paths],
            ignore_index=True,
        )
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
    else:
        frame = pd.DataFrame(columns=COLUMNS)
    _cache, _cache_key = frame, key
    return frame


def player(code: int, before: date | None = None) -> pd.DataFrame:
    """One player's recorded days, oldest first, optionally only before a date."""
    history = load()
    rows = history[history["code"] == int(code)]
    if before is not None:
        rows = rows[rows["date"] < before]
    return rows.sort_values("date").reset_index(drop=True)


def baseline_day(before: date, days: int | None) -> date | None:
    """The recorded day to measure a change from.

    The latest day at least ``days`` before ``before``; or, when there is no
    day that far back (or ``days`` is None), the first day recorded. None
    when nothing was recorded before ``before`` at all.
    """
    dates = sorted(d for d in load()["date"].unique() if d < before)
    if not dates:
        return None
    if days is not None:
        far_enough = [d for d in dates if d <= before - timedelta(days=days)]
        if far_enough:
            return far_enough[-1]
    return dates[0]


def predictions_on(day: date) -> pd.Series:
    """Each player's predicted price as recorded on ``day``, by ``code``."""
    history = load()
    rows = history[history["date"] == day]
    return rows.set_index("code")["pred_next_start"]
