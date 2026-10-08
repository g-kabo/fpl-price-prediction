"""One player's prediction from What if's form values, and its breakdown.

The static site redoes this arithmetic in ``web/js/model.js``;
``export_static.py --parity`` writes this module's answers for
``web/tests/parity.mjs`` to check it against, and ships the form's layout
(:data:`FIELD_GROUPS`, :data:`STEPS`) with the model.

The one rule this module enforces is that it never computes a feature
itself: :func:`row_from_values` assembles a raw row and hands it to the
fitted model, letting :func:`features.build_design_matrix` derive the
squared prices, encode the dummies and order the columns exactly as it did
at fit time. Re-implementing any of that here would let this and the
pipeline drift apart silently.

The form's *fields* are :data:`schema.FORM_FIELDS`, not the model's inputs:
it asks for games played and leaves points per game and points per £m to
:func:`schema.with_ratios`, which the page applies before predicting.
"""

from __future__ import annotations

import pandas as pd

import config
import features
import model_store
import schema

#: FPL prices move in tenths of a million, so a headline of £6.43m is
#: precision the game itself does not have.
PRICE_GRID = 0.1

#: Smallest contribution worth a row of its own, in £m. Anything under it
#: prints as "£+0.000m" at the precision the breakdown uses, which reads as
#: "this does nothing" and takes a row and a bar to say it. Such terms are
#: pooled instead -- pooled, not dropped, so the parts still sum exactly to
#: the prediction.
MATERIAL_CONTRIBUTION = 0.0005


#: The form in chunks a manager would recognise, rather than one flat grid
#: of boxes. Every numeric field appears exactly once.
FIELD_GROUPS: list[tuple[str, list[str]]] = [
    ("Price", ["start_cost", "final_cost"]),
    ("Playing time", ["minutes", "appearances", "total_points"]),
    ("Returns", ["goals_scored", "assists"]),
    ("Popularity", ["selected_by_percent"]),
]


#: How far one press of a stepper moves each figure: a unit someone would
#: actually nudge by. A minute at a time would take ninety presses to
#: add a match.
STEPS: dict[str, float] = {
    "start_cost": 0.1, "final_cost": 0.1,
    "minutes": 90, "appearances": 1, "total_points": 5,
    "goals_scored": 1, "assists": 1, "selected_by_percent": 1.0,
}


def row_from_values(values: dict) -> pd.DataFrame:
    """A one-row raw frame, ready for ``PriceModel.predict_*``.

    Deliberately raw: no squared prices, no dummies, no column ordering. The model's
    own pipeline does all of that.
    """
    row = {name: _as_float(values.get(name)) for name in schema.NUMERIC_NAMES}
    row[schema.POSITION_FIELD] = values.get(schema.POSITION_FIELD) or "MID"
    row[schema.TEAM_FIELD] = values.get(schema.TEAM_FIELD) or config.OTHER_TEAM
    return pd.DataFrame([row])


def predict(values: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Predict one player. Returns ``(interval_frame, raw_row)``."""
    fitted = model_store.get_model()
    row = row_from_values(values)
    return fitted.predict_with_interval(row), row


def contributions(values: dict, top_n: int = 12) -> dict:
    """Decompose one prediction into its per-term contributions.

    The model is linear, so the prediction is exactly ``const + Σ βx`` and
    the breakdown is not an approximation the way it would be for a tree
    ensemble. Sorting by ``|βx|`` answers "why this price for this player",
    which is the one thing a single-player view offers that the batch CSV
    cannot.

    Computed once and read by both the chart and the table beside it, so
    the two cannot drift into disagreeing about the same player.
    """
    fitted = model_store.get_model()
    row = row_from_values(values)
    design = features.build_design_matrix(row, fitted.lumper, fitted.columns)

    params = fitted.result.params
    intercept = float(params.get("const", 0.0))

    terms = []
    for column in fitted.columns:
        value = float(design[column].iloc[0])
        beta = float(params.get(column, 0.0))
        contribution = beta * value
        if abs(contribution) < 1e-9:
            continue
        terms.append((column, value, beta, contribution))

    terms.sort(key=lambda t: abs(t[3]), reverse=True)

    material = [t for t in terms if abs(t[3]) >= MATERIAL_CONTRIBUTION]
    shown = material[:top_n]

    drawn = {t[0] for t in shown}
    pooled = [t for t in terms if t[0] not in drawn]
    rest = sum(t[3] for t in pooled)

    return {
        "intercept": intercept,
        "shown": shown,
        "rest": rest,
        "n_rest": len(pooled),
        "total": intercept + sum(t[3] for t in terms),
    }


def _as_float(value) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
