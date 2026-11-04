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


#: The least a forecast must have moved this season, in £m, to earn a record.
RECORD_MIN_RANGE = 0.05


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


def records(history: pd.DataFrame, today: pd.Series, past_calls: pd.DataFrame) -> dict[int, dict]:
    """Players whose forecast today is at a season or all-time high or low.

    ``history`` holds the earlier mornings (``date``, ``code``,
    ``pred_next_start``), ``today`` is today's forecast by code, and
    ``past_calls`` the model's call from each completed season (``code``,
    ``season``, ``call``). A record holds until the forecast leaves it, and
    ties count. A season whose forecasts have stayed within
    :data:`RECORD_MIN_RANGE` has no record worth naming, and with no earlier
    morning there is nothing to compare with. All-time needs a past season
    to beat, or it would only repeat the season label.
    """
    if history.empty:
        return {}
    tracked_from = min(history["date"])
    earlier = dict(tuple(history.groupby("code")))
    past = dict(tuple(past_calls.groupby("code"))) if not past_calls.empty else {}

    out: dict[int, dict] = {}
    for code, value in today.dropna().items():
        rows = earlier.get(code)
        if rows is None:
            continue
        value = round(float(value), 3)
        days = rows["pred_next_start"]
        low, high = min(days.min(), value), max(days.max(), value)
        if round(high - low, 3) < RECORD_MIN_RANGE or value not in (low, high):
            continue

        direction = "high" if value == high else "low"
        best = max if direction == "high" else min
        reached = rows.loc[days == value, "date"]
        record = {
            "direction": direction,
            "scope": "season",
            "value": value,
            "since": min(reached).isoformat() if len(reached) else None,
            "tracked_from": tracked_from.isoformat(),
        }
        calls = past.get(code)
        if calls is not None:
            rounded = calls["call"].round(3)
            target = best(rounded)
            if best(value, target) == value:
                record.update(
                    scope="all",
                    past_best=float(target),
                    # A call from a season forecasts the one after it.
                    past_best_for=int(calls.loc[rounded == target, "season"].max()) + 1,
                    past_from=int(calls["season"].min()) + 1,
                )
        out[int(code)] = record
    return out
