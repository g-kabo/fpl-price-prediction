"""Season and all-time forecast records, on small made-up histories."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import forecast_history  # noqa: E402


def history(*days):
    rows = [{"date": date(2026, 10, i + 1), "code": 1, "pred_next_start": pred}
            for i, pred in enumerate(days)]
    return pd.DataFrame(rows)


def calls(*preds):
    return pd.DataFrame({"code": 1, "season": range(2020, 2020 + len(preds)), "call": list(preds)})


def record(days, today, past=()):
    return forecast_history.records(history(*days), pd.Series({1: today}), calls(*past)).get(1)


def test_new_high_is_a_season_high():
    mark = record([5.0, 5.1], 5.2)
    assert (mark["direction"], mark["scope"]) == ("high", "season")
    assert mark["tracked_from"] == "2026-10-01"
    assert mark["since"] is None


def test_new_low_is_a_season_low():
    mark = record([5.2, 5.1], 5.0)
    assert (mark["direction"], mark["scope"]) == ("low", "season")


def test_a_record_holds_and_dates_from_when_it_was_reached():
    mark = record([5.0, 5.2, 5.2], 5.2)
    assert mark["direction"] == "high"
    assert mark["since"] == "2026-10-02"


def test_between_the_extremes_has_no_record():
    assert record([5.0, 5.3], 5.1) is None


def test_small_range_has_no_record():
    assert record([5.00, 5.02], 5.04) is None
    assert record([5.00, 5.02], 5.05) is not None


def test_all_time_needs_to_pass_every_past_season():
    assert record([5.0], 5.2, past=(5.1, 5.3))["scope"] == "season"
    mark = record([5.0], 5.2, past=(5.1, 4.9))
    assert mark["scope"] == "all"
    assert mark["past_best"] == 5.1
    assert mark["past_best_for"] == 2021
    assert mark["past_from"] == 2021


def test_all_time_low_mirrors_it():
    mark = record([5.2], 5.0, past=(5.1, 5.4))
    assert (mark["direction"], mark["scope"]) == ("low", "all")
    assert mark["past_best"] == 5.1


def test_no_past_season_stays_a_season_record():
    assert record([5.0], 5.2)["scope"] == "season"


def test_no_earlier_morning_means_no_record():
    assert forecast_history.records(pd.DataFrame(), pd.Series({1: 5.0}), calls()) == {}
    other = history(5.0).assign(code=2)
    assert forecast_history.records(other, pd.Series({1: 5.2}), calls()) == {}
