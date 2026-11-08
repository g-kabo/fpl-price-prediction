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

COLUMNS = ["date", "gameweeks_finished", "code", "price", "minutes",
           "pred_next_start", "pred_next_lower", "pred_next_upper"]

#: What the model was given that morning, for "what changed" (see
#: ``export_static.drivers_payload``). Read only when asked for.
INPUT_COLUMNS = ["start_price", "proj_minutes", "proj_total_points", "proj_points_per_game",
                 "proj_value_season", "proj_goals_scored", "proj_assists",
                 "selected_by_percent", "element_type", "team_name"]


#: The least a forecast must have moved this season, in £m, to earn a record.
RECORD_MIN_RANGE = 0.05

#: Under this many minutes a record is marked as resting on a small sample.
FEW_MINUTES = 270

#: Records compare forecasts at the precision the site shows them, £0.01m, so
#: two forecasts that read the same are a tie, and a change too small to see
#: can't take a tag away. Only the comparison rounds: the history, club totals
#: and day-by-day splits keep the full figure.
RECORD_PLACES = 2


def _shown(values: pd.Series) -> pd.Series:
    """Forecasts as the site shows them. Python's ``round``, like the site's
    ``fixed``; ``Series.round`` can land the other way on a tie (2.675)."""
    return values.map(lambda value: round(float(value), RECORD_PLACES))


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


def records(history: pd.DataFrame, today: pd.Series, past_prices: pd.DataFrame,
            played: set[int] | None = None) -> dict[int, dict]:
    """Players whose forecast today is at a season, all-time or historic extreme.

    ``history`` holds the earlier mornings (``date``, ``code``,
    ``pred_next_start``), ``today`` is today's forecast by code, and
    ``past_prices`` every start and end price from past and current seasons
    (``code``, ``season``, ``price``). Forecasts compare to the nearest £0.01m. A record
    holds until the forecast leaves it, and ties count. A season whose forecasts have stayed within
    :data:`RECORD_MIN_RANGE` has no record worth naming, and with no earlier
    morning there is nothing to compare with. All-time needs a past season
    to beat, or it would only repeat the season label.

    A player with neither can still be at a historic high or low: past every
    start and end price by at least :data:`RECORD_MIN_RANGE`, whatever this
    season's own peak or trough. Only for those in ``played`` (everyone if
    None), as a forecast with no minutes behind it comes from the price alone.
    """
    if history.empty:
        return {}
    tracked_from = min(history["date"])
    earlier = dict(tuple(history.groupby("code")))
    past = dict(tuple(past_prices.groupby("code"))) if not past_prices.empty else {}

    out: dict[int, dict] = {}
    for code, value in today.dropna().items():
        rows = earlier.get(code)
        if rows is None:
            continue
        value = round(float(value), RECORD_PLACES)
        days = _shown(rows["pred_next_start"])
        low, high = min(days.min(), value), max(days.max(), value)
        if round(high - low, 3) < RECORD_MIN_RANGE or value not in (low, high):
            if played is None or code in played:
                mark = _historic(value, rows, past.get(code))
                if mark:
                    out[int(code)] = mark
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
            rounded = _shown(calls["price"])
            target = best(rounded)
            if best(value, target) == value:
                record.update(
                    scope="all",
                    past_best=float(target),
                    past_best_for=int(calls.loc[rounded == target, "season"].max()),
                    past_from=int(calls["season"].min()),
                )
        if record["scope"] == "season" and (played is None or code in played):
            # Past every earlier season says more than a season extreme.
            record = _historic(value, rows, calls) or record
        out[int(code)] = record
    return out


def _historic(value: float, rows: pd.DataFrame, calls: pd.DataFrame | None) -> dict | None:
    """A forecast past every past start and end price, or None."""
    if calls is None:
        return None
    rounded = _shown(calls["price"])
    if round(value - rounded.max(), 3) >= RECORD_MIN_RANGE:
        direction, best, target = "high", max, rounded.max()
    elif round(rounded.min() - value, 3) >= RECORD_MIN_RANGE:
        direction, best, target = "low", min, rounded.min()
    else:
        return None
    days = _shown(rows["pred_next_start"])
    season_best = best(days.max() if direction == "high" else days.min(), value)
    reached = rows.loc[days == season_best, "date"]
    return {
        "direction": direction,
        "scope": "historic",
        "value": value,
        "past_best": float(target),
        "past_best_for": int(calls.loc[rounded == target, "season"].max()),
        "past_from": int(calls["season"].min()),
        "season_best": float(season_best),
        "season_best_on": min(reached).isoformat() if len(reached) else None,
    }


def with_changes(history: pd.DataFrame, today: pd.Series, past_prices: pd.DataFrame,
                 played: set[int] | None = None) -> tuple[dict[int, dict], dict | None]:
    """:func:`records`, plus what changed since the last recorded morning.

    A record gets ``new`` when its player did not hold that kind of record
    that morning, whether he had none or a different one. The second value
    names that morning and who held a record then and holds none now; it is
    None until there are two mornings to compare. That morning is judged as
    today is, with today's past prices.
    """
    marks = records(history, today, past_prices, played)
    if history.empty or history["date"].nunique() < 2:
        return marks, None

    last = max(history["date"])
    morning = history[history["date"] == last]
    before = records(history[history["date"] < last], morning.set_index("code")["pred_next_start"],
                     past_prices, set(morning.loc[morning["minutes"] > 0, "code"].astype(int)))

    def kind(mark: dict | None) -> str | None:
        return f"{mark['scope']}-{mark['direction']}" if mark else None

    for code, mark in marks.items():
        if kind(mark) != kind(before.get(code)):
            mark["new"] = True
    today_codes = {int(code) for code in today.dropna().index}
    lost = [{"code": code, "was": kind(mark)} for code, mark in before.items()
            if code in today_codes and code not in marks]
    return marks, {"since": last.isoformat(), "lost": lost}


def mark_few_minutes(marks: dict[int, dict], minutes: pd.Series) -> None:
    """Note the minutes on each record that rests on under FEW_MINUTES."""
    for code, mark in marks.items():
        played = minutes.get(code, 0)
        played = 0 if pd.isna(played) else int(played)
        if played < FEW_MINUTES:
            mark["few_minutes"] = played
