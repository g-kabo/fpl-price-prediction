"""Load the saved model once per process, refitting if it went stale.

The app treats ``models/`` as a cache, not as state: if the artifacts are
missing or older than the code and data they were built from,
:func:`train_and_save.main` is invoked to rebuild them. That keeps the app
from ever serving predictions from a model that no longer matches
``features.py`` -- a failure that would otherwise be silent, since a stale
pickle loads and predicts perfectly happily.
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import train_and_save  # noqa: E402


def _ensure_fresh() -> None:
    if train_and_save.is_stale():
        print("Model artifacts are stale -- refitting (this takes ~20s)...")
        # Empty argv: under gunicorn, sys.argv holds the server's own flags.
        train_and_save.main([])


@lru_cache(maxsize=1)
def get_model():
    """The fitted :class:`model.PriceModel`, preprocessing included."""
    _ensure_fresh()
    return joblib.load(train_and_save.MODEL_PATH)


@lru_cache(maxsize=1)
def get_meta() -> dict:
    """Training ranges, team levels and fit statistics."""
    _ensure_fresh()
    return json.loads(train_and_save.META_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def get_scores() -> pd.DataFrame:
    """The cleaned scoring season, for the player page's prefill list."""
    _ensure_fresh()
    return pd.read_csv(train_and_save.SCORES_PATH, encoding="utf-8")


@lru_cache(maxsize=1)
def get_seasons() -> pd.DataFrame:
    """Every completed season, with the price FPL set for the next one.

    What if's season picker reads this; ``next_cost`` is blank for a
    player who did not return.
    """
    _ensure_fresh()
    return pd.read_csv(train_and_save.SEASONS_PATH, encoding="utf-8")


@lru_cache(maxsize=1)
def get_price_history() -> pd.DataFrame:
    """Start and finishing price per player per season, keyed by ``code``.

    Indexed on ``code`` so a player page is a single ``.loc`` rather than a
    scan of ten seasons' worth of rows on every selection.
    """
    _ensure_fresh()
    history = pd.read_csv(train_and_save.PRICES_PATH, encoding="utf-8")
    return history.set_index("code").sort_values("season")


@lru_cache(maxsize=1)
def get_published_predictions() -> pd.DataFrame:
    """The batch pipeline's own predictions, keyed by player code.

    Shown on the player page beside the live prediction so an unedited
    prefill visibly agrees with ``run_pipeline.py``. Optional -- the app
    works without it, it just loses the cross-check.
    """
    path = config.OUTPUT_DIR / f"pred_price_{config.PREDICT_SEASON}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8").set_index("code")


def team_options() -> list[str]:
    """Team levels the model actually carries a coefficient for."""
    return list(get_meta()["teams_retained"])
