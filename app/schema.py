"""The inputs a user supplies, defined once for all three pages.

The model reads 20 columns but only 14 of them are anyone's to type: the
five per-minute rates and ``no_mins`` are *derived* from minutes and the
counting stats by :func:`features.add_rate_features`. Offering them as
inputs would let the form state contradict itself -- 10 goals in 0 minutes
with a goals-per-minute of 0.4 -- so they are shown read-only instead.

Keeping the list here rather than in each page is what stops the three
forms from drifting apart as fields are added.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import features  # noqa: E402

#: ``(field, label, step, integer?)`` for every numeric input, in the order
#: they appear on the form. The names and their order are
#: :data:`features.BASE_NUMERIC`; the presentation is ours.
NUMERIC_FIELDS: list[tuple[str, str, float, bool]] = [
    ("start_cost",        "Start price (£m)",     0.1,  False),
    ("cost_change_start", "Price change (£m)",    0.1,  False),
    ("minutes",           "Minutes",              1,    True),
    ("total_points",      "Total points",         1,    True),
    ("points_per_game",   "Points per game",      0.1,  False),
    ("value_season",      "Value (pts per £m)",   0.1,  False),
    ("goals_scored",      "Goals",                1,    True),
    ("assists",           "Assists",              1,    True),
    ("clean_sheets",      "Clean sheets",         1,    True),
    ("bps",               "Bonus point system",   1,    True),
    ("transfers_in",      "Transfers in",         1000, True),
    ("transfers_out",     "Transfers out",        1000, True),
]

#: Hints for the traps that would otherwise fail silently -- a wrong unit
#: still predicts a plausible-looking number, it is just the wrong one.
FIELD_HELP: dict[str, str] = {
    "start_cost": "In £m (5.5), not the API's tenths (55).",
    "cost_change_start": "Season-to-date price movement, in £m.",
    "value_season": "Total points ÷ current price.",
    "transfers_in": "Cumulative for the whole season — runs to millions.",
    "transfers_out": "Cumulative for the whole season — runs to millions.",
    "bps": "Raw BPS total, not bonus points awarded.",
}

NUMERIC_NAMES = [name for name, _, _, _ in NUMERIC_FIELDS]

#: The two categorical inputs. Team levels are resolved at runtime from the
#: fitted lumper rather than hard-coded, since which teams survive
#: ``step_other`` depends on the training window.
POSITION_FIELD = "element_type"
TEAM_FIELD = "team_name"

POSITIONS = list(config.POSITIONS)

#: Minutes in a full match. The model's rates are per *minute*, which is
#: an awkward unit to read -- 0.0024 goals per minute says less at a glance
#: than 0.22 goals per 90. The panel scales by this for display only; the
#: number fed to the coefficients is unchanged, and is shown underneath so
#: the two can be reconciled against the contribution table.
MINUTES_PER_MATCH = 90.0

#: Minutes expressed in matches. Display-only, so it is deliberately not a
#: member of :data:`features.RATE_FEATURES` -- the model never sees it.
MATCHES_FIELD = "minutes_per_90"

#: Derived and displayed, never entered.
DERIVED_FIELDS = list(features.RATE_FEATURES) + [MATCHES_FIELD, "no_mins"]

DERIVED_LABELS = {
    "goals_per_min": "Goals / 90",
    "assists_per_min": "Assists / 90",
    "bps_per_min": "BPS / 90",
    "points_per_mins": "Points / 90",
    "cleansheets_per_min": "Clean sheets / 90",
    MATCHES_FIELD: "90s played",
    "no_mins": "Never played",
}

#: Every column :func:`features.build_design_matrix` reads off a raw row.
MODEL_INPUT_COLUMNS = NUMERIC_NAMES + [POSITION_FIELD, TEAM_FIELD]


def field_defaults(ranges: dict) -> dict[str, float]:
    """Median training value per numeric field.

    A blank or all-zero form is not a neutral starting point -- it
    describes a player who cost nothing and never played, and the model
    prices that incoherently. Medians give the manual page a real player to
    start from.
    """
    defaults = {}
    for name, _, step, integer in NUMERIC_FIELDS:
        median = ranges.get(name, {}).get("median", 0.0)
        defaults[name] = int(round(median)) if integer else round(float(median), 2)
    return defaults
