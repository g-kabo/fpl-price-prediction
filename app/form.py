"""Shared form widgets, row assembly and result rendering.

Every page builds the same inputs and renders the same result card, so
all of that lives here. The one rule this module enforces is that the app
never computes a feature itself: :func:`row_from_values` assembles a raw
row and hands it to the fitted model, letting
:func:`features.build_design_matrix` derive the squared prices, encode the dummies
and order the columns exactly as it did at fit time. Re-implementing any of
that here would let the app and the pipeline drift apart silently.

The form's *fields* are :data:`schema.FORM_FIELDS`, not the model's inputs:
it asks for games played and leaves points per game and points per £m to
:func:`schema.with_ratios`, which the page applies before predicting.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import dash_bootstrap_components as dbc
import pandas as pd
from dash import dcc, html

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import charts  # noqa: E402
import config  # noqa: E402
import features  # noqa: E402
import model_store  # noqa: E402
import schema  # noqa: E402

#: FPL prices move in tenths of a million, so a headline of £6.43m is
#: precision the game itself does not have.
PRICE_GRID = 0.1

#: Smallest contribution worth a row of its own, in £m. Anything under it
#: prints as "£+0.000m" at the precision the breakdown uses, which reads as
#: "this does nothing" and takes a row and a bar to say it. Such terms are
#: pooled instead -- pooled, not dropped, so the parts still sum exactly to
#: the prediction.
MATERIAL_CONTRIBUTION = 0.0005


def field_id(page: str, field: str) -> dict:
    """Pattern-matching id, so one callback can collect a whole form."""
    return {"page": page, "field": field}


#: The form in chunks a manager would recognise, rather than one flat grid
#: of boxes. Every numeric field appears exactly once.
FIELD_GROUPS: list[tuple[str, list[str]]] = [
    ("Price", ["start_cost", "final_cost"]),
    ("Playing time", ["minutes", "appearances", "total_points"]),
    ("Returns", ["goals_scored", "assists"]),
    ("Popularity", ["selected_by_percent"]),
]


def dom_id(component_id: dict) -> str:
    """The id Dash actually renders for a pattern-matching component.

    Dash serialises a dict id as compact JSON with sorted keys, so a
    ``<label for=...>`` built from ``str(dict)`` points at nothing.
    """
    return json.dumps(component_id, sort_keys=True, separators=(",", ":"))


#: How far one press of a stepper moves each figure: a unit someone would
#: actually nudge by. A minute at a time would take ninety presses to
#: add a match.
STEPS: dict[str, float] = {
    "start_cost": 0.1, "final_cost": 0.1,
    "minutes": 90, "appearances": 1, "total_points": 5,
    "goals_scored": 1, "assists": 1, "selected_by_percent": 1.0,
}


def step_id(page: str, field: str, direction: int) -> dict:
    return {"page": page, "step": field, "dir": direction}


def _field(page: str, name: str, label: str, step: float, values: dict, ranges: dict):
    """One figure as a stat chip: label, the number, and a stepper each side."""
    bounds = ranges.get(name, {})
    hint = schema.FIELD_HELP.get(name, "")
    if bounds:
        seen = f"Seen {_fmt(bounds['min'])} to {_fmt(bounds['max'])}."
        hint = f"{hint} {seen}".strip()
    nudge = _fmt(STEPS.get(name, step))

    return html.Div(
        [
            html.Label(label, htmlFor=dom_id(field_id(page, name)), className="chip-label"),
            html.Div(
                [
                    html.Button(html.I(className="bi bi-dash-lg"), id=step_id(page, name, -1),
                                n_clicks=0, type="button", className="stepper",
                                title=f"Down {nudge}"),
                    dbc.Input(id=field_id(page, name), type="number", value=values.get(name),
                              step=step, debounce=True, className="chip-input"),
                    html.Button(html.I(className="bi bi-plus-lg"), id=step_id(page, name, 1),
                                n_clicks=0, type="button", className="stepper",
                                title=f"Up {nudge}"),
                ],
                className="chip-row",
            ),
            html.Div(hint, className="chip-hint"),
        ],
        className="stat-chip",
    )


def build_fields(page: str, values: dict, ranges: dict) -> list:
    """The editable season, grouped, plus position and club."""
    spec = {name: (label, step) for name, label, step, _ in schema.FORM_FIELDS}

    groups = [
        html.Fieldset(
            [html.Legend(title, className="group-title"),
             html.Div([_field(page, name, *spec[name], values, ranges) for name in names],
                      className="group-fields")],
            className="group",
        )
        for title, names in FIELD_GROUPS
    ]

    role = html.Fieldset(
        [
            html.Legend("Role", className="group-title"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Position", className="field-label"),
                            dbc.RadioItems(
                                id=field_id(page, schema.POSITION_FIELD),
                                options=[{"label": p, "value": p} for p in schema.POSITIONS],
                                value=values.get(schema.POSITION_FIELD, "MID"),
                                inline=True, className="pos-picker",
                            ),
                        ],
                        className="field",
                    ),
                    html.Div(
                        [
                            html.Div("Club", className="field-label"),
                            dcc.Dropdown(
                                id=field_id(page, schema.TEAM_FIELD),
                                options=team_dropdown_options(),
                                value=values.get(schema.TEAM_FIELD, config.OTHER_TEAM),
                                clearable=False,
                            ),
                            html.Div("Clubs with too little history in the data "
                                     "share one setting.", className="field-hint"),
                        ],
                        className="field field-wide",
                    ),
                ],
                className="group-fields role-fields",
            ),
        ],
        className="group",
    )

    return [*groups, role]


def team_dropdown_options() -> list[dict]:
    """Fitted teams, with the pooled reference level called out.

    Teams that fell below ``step_other``'s threshold or never appeared in
    training share a single "other" coefficient. Listing that explicitly is
    more honest than omitting those clubs and letting the user wonder why
    Fulham is missing.
    """
    kept = model_store.team_options()
    options = [{"label": "Any other club",
                "value": config.OTHER_TEAM}]
    options += [{"label": team, "value": team} for team in kept]
    return options


#: The form's fields in a fixed order, for wiring callbacks. Listing them
#: explicitly rather than matching on ALL keeps the callback signature
#: aligned with the field names -- pattern matching returns values in id
#: order, which is not the order they were declared in.
ALL_FIELDS = schema.FORM_NAMES + [schema.POSITION_FIELD, schema.TEAM_FIELD]


def input_states(page: str, prop: str = "value") -> list:
    """``State`` for every field on ``page``, in :data:`ALL_FIELDS` order."""
    from dash import State

    return [State(field_id(page, name), prop) for name in ALL_FIELDS]


def input_inputs(page: str, prop: str = "value") -> list:
    """As :func:`input_states`, but as ``Input`` so edits retrigger."""
    from dash import Input

    return [Input(field_id(page, name), prop) for name in ALL_FIELDS]


def values_from_args(args) -> dict:
    """Rebuild the value dict from a callback's positional arguments."""
    return dict(zip(ALL_FIELDS, args))


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


def contribution_steps(parts: dict) -> list[tuple[str, float, str]]:
    """:func:`contributions` as ordered waterfall steps.

    ``absolute`` starts the running total at the intercept, each term is a
    ``relative`` step, and ``total`` closes on the predicted price rather
    than re-summing it -- Plotly draws that bar from the running total, so
    a mismatch here would be visible instead of silent.
    """
    steps: list[tuple[str, float, str]] = [("Model baseline", parts["intercept"], "absolute")]
    steps += [(charts.term_label(column), contribution, "relative")
              for column, _, _, contribution in parts["shown"]]

    if parts["n_rest"]:
        steps.append((f"{parts['n_rest']} smaller terms", parts["rest"], "relative"))

    steps.append(("Predicted price", parts["total"], "total"))
    return steps


def _as_float(value) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fmt(value: float) -> str:
    """Compact number formatting for hints and table cells."""
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs(value) >= 10_000:
        return f"{value / 1_000:.0f}k"
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}"
