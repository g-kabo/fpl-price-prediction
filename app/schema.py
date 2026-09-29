"""The inputs a user supplies, defined once for all three pages.

Not every model input is anyone's to type: the two squared prices are
*derived* from the start and end price, and ``no_mins`` from minutes, by
:mod:`features`. Offering them as inputs would let the form state contradict
itself -- a 5.0m player whose squared price is not 25 -- so they are left
out of the form.

The same goes for FPL's two ratios, points per game and points per £m. The
model reads them, but they are FPL's own arithmetic on other figures, so the
What if form asks for games played instead and works both out
(:func:`with_ratios`) -- otherwise doubling a player's points would leave his
points per game where it was.

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
#: they appear on the form. The names are the raw inputs behind
#: :data:`features.DEFAULT_NUMERIC`; the presentation is ours.
NUMERIC_FIELDS: list[tuple[str, str, float, bool]] = [
    ("start_cost",          "Start price",          0.1,  False),
    ("final_cost",          "End price",            0.1,  False),
    ("minutes",             "Minutes",              1,    True),
    ("total_points",        "Total points",         1,    True),
    ("points_per_game",     "Points per game",      0.1,  False),
    ("value_season",        "Points per £m",        0.1,  False),
    ("goals_scored",        "Goals",                1,    True),
    ("assists",             "Assists",              1,    True),
    ("selected_by_percent", "Selected by",          0.1,  False),
]

#: Hints for the traps that would otherwise fail silently -- a wrong unit
#: still predicts a plausible-looking number, it is just the wrong one.
FIELD_HELP: dict[str, str] = {
    "start_cost": "In £m, e.g. 5.5.",
    "final_cost": "His price at the end of the season (or today), in £m.",
    "appearances": "Matches he played in, including off the bench.",
    "selected_by_percent": "Share of FPL managers who own him, in %, e.g. 12.5.",
}

NUMERIC_NAMES = [name for name, _, _, _ in NUMERIC_FIELDS]

#: Model inputs FPL computes from other figures, so the form derives them.
RATIO_FIELDS = ["points_per_game", "value_season"]

#: Games played, i.e. appearances: the one figure the ratios need that the
#: model does not read itself. Not ``games_played``, which Price Watch uses
#: for a club's fixtures.
APPEARANCES_FIELD = "appearances"

#: Most matches a player can appear in: one per gameweek, double gameweeks
#: aside, which FPL's season totals fold in anyway.
MAX_APPEARANCES = 38

#: What the What if form asks for: the model's inputs with the two ratios
#: swapped for games played.
FORM_FIELDS: list[tuple[str, str, float, bool]] = []
for _field in NUMERIC_FIELDS:
    if _field[0] == "minutes":
        FORM_FIELDS += [_field, (APPEARANCES_FIELD, "Games played", 1, True)]
    elif _field[0] not in RATIO_FIELDS:
        FORM_FIELDS.append(_field)
del _field

FORM_NAMES = [name for name, _, _, _ in FORM_FIELDS]

#: The two categorical inputs. Team levels are resolved at runtime from the
#: fitted lumper rather than hard-coded, since which teams survive
#: ``step_other`` depends on the training window.
POSITION_FIELD = "element_type"
TEAM_FIELD = "team_name"

POSITIONS = list(config.POSITIONS)

#: Minutes in a full match, for guessing games played from minutes.
MINUTES_PER_MATCH = 90.0

#: Every column :func:`features.build_design_matrix` reads off a raw row.
MODEL_INPUT_COLUMNS = NUMERIC_NAMES + [POSITION_FIELD, TEAM_FIELD]


def field_defaults(ranges: dict) -> dict[str, float]:
    """Median training value per numeric field.

    A blank or all-zero form is not a neutral starting point -- it
    describes a player who cost nothing and never played, and the model
    prices that incoherently. Medians give the manual page a real player to
    start from.
    """
    median = {name: float(ranges.get(name, {}).get("median", 0.0)) for name in NUMERIC_NAMES}
    defaults = {}
    for name, _, step, integer in NUMERIC_FIELDS:
        defaults[name] = int(round(median[name])) if integer else round(median[name], 2)
    defaults[APPEARANCES_FIELD] = infer_appearances(
        median["total_points"], median["points_per_game"], median["minutes"])
    return {name: defaults[name] for name in FORM_NAMES}


def _fpl_round(value: float) -> float:
    """FPL publishes both ratios to one decimal place."""
    return round(value, 1)


def infer_appearances(total_points: float, points_per_game: float, minutes: float) -> int:
    """Games played, recovered from FPL's own points per game.

    The season files carry points per game but not the appearances behind
    it, so this finds the count that reproduces FPL's rounded figure,
    nearest to points / ppg. That makes an unedited season derive exactly
    the ratio FPL published, which keeps the form's prediction identical to
    the pipeline's. It does for 99.6% of players since 2017; the rest, mostly
    2017-18, have a published figure no whole number of games produces.
    """
    total_points, points_per_game, minutes = (
        float(total_points or 0), float(points_per_game or 0), float(minutes or 0))
    if minutes <= 0:
        return 0
    if points_per_game == 0:
        # No points: any count gives 0 per game, so go by minutes.
        return int(min(MAX_APPEARANCES, max(1, round(minutes / MINUTES_PER_MATCH))))

    guess = total_points / points_per_game
    exact = [games for games in range(1, MAX_APPEARANCES + 1)
             if abs(_fpl_round(total_points / games) - points_per_game) < 1e-6]
    if exact:
        return min(exact, key=lambda games: abs(games - guess))
    return int(min(MAX_APPEARANCES, max(1, round(guess))))


def form_values(player) -> dict:
    """A real season as the What if form holds it: games played, no ratios."""
    values = {name: player[name] for name in NUMERIC_NAMES if name in FORM_NAMES}
    values[APPEARANCES_FIELD] = infer_appearances(
        player["total_points"], player["points_per_game"], player["minutes"])
    return values


def with_ratios(values: dict) -> dict:
    """The form's values plus the two ratios, worked out as FPL does.

    Points per game is points over games played; points per £m is points
    over the end price, which is FPL's ``value_season`` to the decimal.
    """
    def number(name: str) -> float:
        try:
            return float(values.get(name) or 0)
        except (TypeError, ValueError):
            return 0.0

    points, games, price = number("total_points"), number(APPEARANCES_FIELD), number("final_cost")
    out = dict(values)
    out["points_per_game"] = _fpl_round(points / games) if games > 0 else 0.0
    out["value_season"] = _fpl_round(points / price) if price > 0 else 0.0
    return out
