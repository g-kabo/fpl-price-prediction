"""What Price Watch predicted on each day so far, read back for the site.

``record_predictions.py`` writes one file per day to ``data/history/``, each
holding every player's price that morning and the model's prediction from
it. ``export_static.py`` reads them back through :func:`load` for the
player card's forecast trend and the board's forecast movers.

Only the handful of columns the site draws are read, so a season of daily
files stays small in memory.

The latest day can be today, the same snapshot the export prices. The
export keeps *earlier* days only and the page takes today from
``board.json``, so a day recorded later than the snapshot it came from (or
never recorded, on a local machine) does not matter.
"""

from __future__ import annotations

import pandas as pd

import config
from record_predictions import HISTORY_DIR

COLUMNS = ["date", "gameweeks_finished", "code", "price",
           "pred_next_start", "pred_next_lower", "pred_next_upper"]

#: What the model was given that morning, for "what changed" (see
#: ``export_static.drivers_payload``). Read only when asked for.
INPUT_COLUMNS = ["start_price", "proj_minutes", "proj_total_points", "proj_points_per_game",
                 "proj_value_season", "proj_goals_scored", "proj_assists",
                 "selected_by_percent", "element_type", "team_name"]


def load(season: int = config.PREDICT_SEASON, inputs: bool = False) -> pd.DataFrame:
    """Every recorded day of ``season``, oldest first. Empty if none.

    With ``inputs``, also the figures the model was given each morning.
    """
    columns = COLUMNS + INPUT_COLUMNS if inputs else COLUMNS
    paths = sorted((HISTORY_DIR / str(season)).glob("*.csv"))
    if not paths:
        return pd.DataFrame(columns=columns)
    frame = pd.concat(
        [pd.read_csv(p, usecols=lambda c: c in columns, encoding="utf-8") for p in paths],
        ignore_index=True,
    )
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    return frame
