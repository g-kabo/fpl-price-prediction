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


def test_historic_high_passes_past_seasons_but_not_this_season():
    mark = record([5.0, 7.3], 7.0, past=(4.8,))
    assert (mark["direction"], mark["scope"]) == ("high", "historic")
    assert mark["past_best"] == 4.8
    assert mark["season_best"] == 7.3
    assert mark["season_best_on"] == "2026-10-02"


def test_historic_low_mirrors_it():
    mark = record([4.0, 6.0], 5.0, past=(5.5, 5.2))
    assert (mark["direction"], mark["scope"]) == ("low", "historic")
    assert mark["past_best"] == 5.2
    assert mark["season_best"] == 4.0


def test_historic_needs_a_clear_gap_and_a_past_season():
    assert record([5.0, 5.3], 5.1, past=(5.06,)) is None
    assert record([5.0, 5.3], 5.1, past=(5.05,))["scope"] == "historic"
    assert record([5.0, 5.3], 5.1, past=(5.2, 5.0)) is None
    assert record([5.0, 5.3], 5.1) is None


def test_season_label_beats_historic():
    mark = record([5.5, 5.3], 5.2, past=(4.8,))
    assert (mark["direction"], mark["scope"]) == ("low", "season")


def test_flat_season_can_still_be_historic():
    assert record([5.0, 5.0], 5.0, past=(4.8,))["scope"] == "historic"


def test_historic_skips_players_who_have_not_played():
    history_, today = history(5.0, 5.3), pd.Series({1: 5.1})
    assert forecast_history.records(history_, today, calls(4.8), played=set()) == {}
    assert forecast_history.records(history_, today, calls(4.8), played={1})[1]["scope"] == "historic"
    assert forecast_history.records(history(5.0, 5.1), pd.Series({1: 5.2}), calls(), played=set())[1]["scope"] == "season"


def test_historic_reached_today_has_no_earlier_date():
    mark = record([5.02, 5.01], 5.0, past=(5.5,))
    assert (mark["direction"], mark["scope"]) == ("low", "historic")
    assert mark["season_best"] == 5.0
    assert mark["season_best_on"] is None


def mornings(*days):
    """History with minutes, as export_static reads it."""
    return history(*days).assign(minutes=90)


def test_new_when_the_tag_was_not_held_on_the_last_morning():
    marks, changes = forecast_history.with_changes(mornings(5.0, 5.05, 5.0), pd.Series({1: 5.2}), calls())
    assert marks[1]["new"] is True
    assert changes == {"since": "2026-10-03", "lost": []}


def test_same_tag_climbing_again_is_not_new():
    marks, _ = forecast_history.with_changes(mornings(5.0, 5.1), pd.Series({1: 5.2}), calls())
    assert marks[1]["scope"] == "season"
    assert "new" not in marks[1]


def test_moving_to_a_different_tag_is_new_and_not_lost():
    marks, changes = forecast_history.with_changes(mornings(5.0, 5.3), pd.Series({1: 5.2}), calls(4.8))
    assert marks[1]["scope"] == "historic"
    assert marks[1]["new"] is True
    assert changes["lost"] == []


def test_dropping_a_tag_is_lost():
    marks, changes = forecast_history.with_changes(mornings(5.0, 5.3), pd.Series({1: 5.2}), calls())
    assert marks == {}
    assert changes["lost"] == [{"code": 1, "was": "season-high"}]


def test_no_changes_until_two_mornings_exist():
    marks, changes = forecast_history.with_changes(mornings(5.0), pd.Series({1: 5.2}), calls())
    assert marks[1]["direction"] == "high"
    assert changes is None
    assert forecast_history.with_changes(pd.DataFrame(), pd.Series({1: 5.2}), calls()) == ({}, None)


def test_few_minutes_is_noted_only_under_the_threshold():
    marks = {1: {}, 2: {}, 3: {}, 4: {}}
    forecast_history.mark_few_minutes(marks, pd.Series({1: 19, 2: 270, 3: 0}))
    assert marks[1]["few_minutes"] == 19
    assert "few_minutes" not in marks[2]
    assert marks[3]["few_minutes"] == 0
    assert marks[4]["few_minutes"] == 0
