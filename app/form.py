"""Shared form widgets, row assembly and result rendering.

Every page builds the same 14 inputs and renders the same result card, so
all of that lives here. The one rule this module enforces is that the app
never computes a feature itself: :func:`row_from_values` assembles a raw
row and hands it to the fitted model, letting
:func:`features.build_design_matrix` derive the rates, encode the dummies
and order the columns exactly as it did at fit time. Re-implementing any of
that here would let the app and the pipeline drift apart silently.
"""

from __future__ import annotations

import sys
from pathlib import Path

import dash_bootstrap_components as dbc
import numpy as np
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


def build_fields(page: str, values: dict, ranges: dict) -> list:
    """The numeric grid plus the two dropdowns, as Bootstrap rows."""
    cells = []
    for name, label, step, integer in schema.NUMERIC_FIELDS:
        bounds = ranges.get(name, {})
        hint = schema.FIELD_HELP.get(name, "")
        if bounds:
            span = f"fitted {_fmt(bounds['min'])} – {_fmt(bounds['max'])}"
            hint = f"{hint} {span}".strip() if hint else span

        cells.append(
            dbc.Col(
                [
                    dbc.Label(label, html_for=str(field_id(page, name)), size="sm",
                              className="mb-1 fw-semibold"),
                    dbc.Input(
                        id=field_id(page, name),
                        type="number",
                        value=values.get(name),
                        step=step,
                        debounce=True,
                        size="sm",
                    ),
                    html.Small(hint, className="text-muted d-block mt-1",
                               style={"fontSize": "0.72rem", "lineHeight": "1.2"}),
                ],
                md=3, sm=6, xs=12, className="mb-3",
            )
        )

    categorical = dbc.Row(
        [
            dbc.Col(
                [
                    dbc.Label("Position", size="sm", className="mb-1 fw-semibold"),
                    dcc.Dropdown(
                        id=field_id(page, schema.POSITION_FIELD),
                        options=[{"label": p, "value": p} for p in schema.POSITIONS],
                        value=values.get(schema.POSITION_FIELD, "MID"),
                        clearable=False,
                    ),
                ],
                md=3, sm=6, xs=12, className="mb-3",
            ),
            dbc.Col(
                [
                    dbc.Label("Team", size="sm", className="mb-1 fw-semibold"),
                    dcc.Dropdown(
                        id=field_id(page, schema.TEAM_FIELD),
                        options=team_dropdown_options(),
                        value=values.get(schema.TEAM_FIELD, config.OTHER_TEAM),
                        clearable=False,
                    ),
                    html.Small(
                        "Clubs outside the model's fitted set score as “other”.",
                        className="text-muted d-block mt-1",
                        style={"fontSize": "0.72rem"},
                    ),
                ],
                md=5, sm=6, xs=12, className="mb-3",
            ),
        ]
    )

    return [dbc.Row(cells), categorical]


def team_dropdown_options() -> list[dict]:
    """Fitted teams, with the pooled reference level called out.

    Teams that fell below ``step_other``'s threshold or never appeared in
    training share a single "other" coefficient. Listing that explicitly is
    more honest than omitting those clubs and letting the user wonder why
    Fulham is missing.
    """
    kept = model_store.team_options()
    options = [{"label": f"Other / not fitted ({config.OTHER_TEAM})",
                "value": config.OTHER_TEAM}]
    options += [{"label": team, "value": team} for team in kept]
    return options


#: The form's fields in a fixed order, for wiring callbacks. Listing them
#: explicitly rather than matching on ALL keeps the callback signature
#: aligned with the field names -- pattern matching returns values in id
#: order, which is not the order they were declared in.
ALL_FIELDS = schema.NUMERIC_NAMES + [schema.POSITION_FIELD, schema.TEAM_FIELD]


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

    Deliberately raw: no rates, no dummies, no column ordering. The model's
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


def result_card(interval: pd.DataFrame, start_cost: float, subtitle: str = "") -> html.Div:
    """Headline price, interval and the change against the current price."""
    pred = float(interval["pred"].iloc[0])
    lower = float(interval["pred_lower"].iloc[0])
    upper = float(interval["pred_upper"].iloc[0])
    on_grid = round(pred / PRICE_GRID) * PRICE_GRID
    delta = pred - float(start_cost or 0.0)

    if delta > 0.05:
        tone, arrow, word = "success", "▲", "rise"
    elif delta < -0.05:
        tone, arrow, word = "danger", "▼", "fall"
    else:
        tone, arrow, word = "secondary", "—", "no change"

    # A prediction interval spanning £1.2m on a £6m player is the honest
    # headline the point estimate hides, so draw it rather than only
    # printing it: the marker's position within the bar shows at a glance
    # whether the prediction sits above or below today's price.
    span = max(upper - lower, 0.01)
    marker = min(max((pred - lower) / span, 0.0), 1.0)
    current_pos = min(max((float(start_cost or 0.0) - lower) / span, 0.0), 1.0)

    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(subtitle or "Predicted starting price",
                         className="result-label"),
                html.Div(f"£{on_grid:.1f}m", className="fw-bold lh-1 my-2 result-price"),
                html.Div(f"point estimate £{pred:.2f}m",
                         className="text-muted", style={"fontSize": "0.78rem"}),

                html.Div(
                    [
                        html.Div(className="interval-track"),
                        html.Div(className="interval-current",
                                 style={"left": f"{current_pos * 100:.1f}%"}),
                        html.Div(className="interval-marker",
                                 style={"left": f"{marker * 100:.1f}%"}),
                    ],
                    className="interval-bar mt-4 mb-2",
                ),
                html.Div(
                    [
                        html.Span(f"£{lower:.2f}m"),
                        html.Span("95% prediction interval", className="interval-caption"),
                        html.Span(f"£{upper:.2f}m"),
                    ],
                    className="d-flex justify-content-between interval-ends",
                ),

                html.Hr(className="my-3"),
                html.Div(
                    [
                        html.Span("vs current price", className="text-muted",
                                  style={"fontSize": "0.75rem"}),
                        html.Span(
                            f"{arrow} £{abs(delta):.2f}m {word}" if word != "no change"
                            else f"{arrow} no change",
                            className=f"fw-semibold text-{tone}",
                        ),
                    ],
                    className="d-flex justify-content-between align-items-center",
                ),
            ]
        ),
        className="shadow-sm result-card",
    )


def derived_panel(row: pd.DataFrame) -> html.Div:
    """What the model derived from the entered values.

    Worth showing because the derivation has a discontinuity: at zero
    minutes every rate is defined as 0 rather than undefined, and
    ``no_mins`` flips on. Without this panel that behaviour is invisible.

    Rates are shown per 90 minutes rather than per minute, because a match
    is the unit anyone thinks in: 0.22 goals per 90 is a striker having a
    quiet season, while the same number written as 0.0024 per minute is
    just small. The per-minute figure is kept underneath each one, since
    that is what the coefficients multiply and what the contribution table
    names, and a panel that showed only the readable version would leave
    the two impossible to reconcile.
    """
    derived = features.add_rate_features(row)

    minutes = float(row["minutes"].iloc[0])
    derived[schema.MATCHES_FIELD] = minutes / schema.MINUTES_PER_MATCH

    items = []
    for name in schema.DERIVED_FIELDS:
        value = float(derived[name].iloc[0])

        if name == "no_mins":
            text, sub = ("yes" if value else "no"), ""
        elif name == schema.MATCHES_FIELD:
            text, sub = f"{value:.1f}", f"{minutes:,.0f} min"
        else:
            text = f"{value * schema.MINUTES_PER_MATCH:.2f}"
            sub = f"{value:.4f} / min"

        items.append(
            dbc.Col(
                [
                    html.Div(schema.DERIVED_LABELS[name], className="text-muted",
                             style={"fontSize": "0.7rem"}),
                    html.Div(text, className="fw-semibold", style={"fontSize": "0.85rem"}),
                    html.Div(sub, className="text-muted",
                             style={"fontSize": "0.62rem", "lineHeight": "1.1"}),
                ],
                width="auto", className="me-4 mb-2",
            )
        )

    return html.Div(
        [
            html.Div("Derived by the model — not editable",
                     className="text-muted text-uppercase mb-2",
                     style={"fontSize": "0.68rem", "letterSpacing": "0.08em"}),
            dbc.Row(items),
            html.Div(
                "Rates are shown per 90 minutes. The model reads them per "
                "minute — that figure is under each one, and is what the "
                "breakdown below names.",
                className="text-muted mt-2",
                style={"fontSize": "0.68rem"},
            ),
        ],
        className="p-3 bg-light rounded border",
    )


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
    steps: list[tuple[str, float, str]] = [("intercept", parts["intercept"], "absolute")]
    steps += [(charts.term_label(column), contribution, "relative")
              for column, _, _, contribution in parts["shown"]]

    if parts["n_rest"]:
        steps.append((f"{parts['n_rest']} smaller", parts["rest"], "relative"))

    steps.append(("predicted price", parts["total"], "total"))
    return steps


def contribution_table(
    values: dict, top_n: int = 12, reference: tuple[str, float] | None = None
) -> html.Div:
    """The "why this price" panel: the waterfall, and the numbers behind it.

    ``reference`` is the price the player already carries, drawn across the
    waterfall as a dashed line. Which price that is belongs to the caller:
    ``/manual`` and ``/player`` only have a start price, while ``/projected``
    has both and lets the reader pick.
    """
    parts = contributions(values, top_n)
    intercept = parts["intercept"]
    shown = parts["shown"]
    rest = parts["rest"]
    terms_total = len(shown) + parts["n_rest"]

    header = html.Thead(
        html.Tr(
            [
                html.Th("Term"),
                html.Th("Value", className="text-end"),
                html.Th("Coefficient", className="text-end"),
                html.Th("Contribution", className="text-end"),
            ]
        )
    )

    body_rows = [
        html.Tr(
            [
                html.Td("intercept", className="text-muted fst-italic"),
                html.Td("—", className="text-end text-muted"),
                html.Td("—", className="text-end text-muted"),
                html.Td(f"£{intercept:+.3f}m", className="text-end"),
            ]
        )
    ]
    for column, value, beta, contribution in shown:
        tone = "text-success" if contribution > 0 else "text-danger"
        body_rows.append(
            html.Tr(
                [
                    html.Td(charts.term_label(column)),
                    html.Td(_fmt(value), className="text-end"),
                    html.Td(f"{beta:+.3e}" if abs(beta) < 0.001 else f"{beta:+.4f}",
                            className="text-end text-muted"),
                    html.Td(f"£{contribution:+.3f}m", className=f"text-end fw-semibold {tone}"),
                ]
            )
        )
    if parts["n_rest"]:
        body_rows.append(
            html.Tr(
                [
                    html.Td(f"{parts['n_rest']} smaller terms",
                            className="text-muted fst-italic"),
                    html.Td("—", className="text-end text-muted"),
                    html.Td("—", className="text-end text-muted"),
                    html.Td(f"£{rest:+.3f}m", className="text-end"),
                ]
            )
        )

    return html.Div(
        [
            html.Div("Why this price", className="fw-semibold mb-1"),
            html.Small(
                "The model is linear, so these contributions sum exactly to the "
                f"point estimate. {terms_total} terms carry a non-zero weight; "
                f"the {len(shown)} largest are drawn.",
                className="text-muted d-block mb-2",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Graph(
                            figure=charts.contribution_waterfall(
                                contribution_steps(parts), reference
                            ),
                            config={"displayModeBar": False, "responsive": True},
                            style={"height": "400px"},
                        ),
                        lg=7, className="mb-3 mb-lg-0",
                    ),
                    dbc.Col(
                        dbc.Table([header, html.Tbody(body_rows)],
                                  bordered=False, hover=True, size="sm",
                                  striped=True, className="mb-0 contribution-table"),
                        lg=5,
                    ),
                ],
                className="g-3 align-items-start",
            ),
        ]
    )


def range_warnings(values: dict, ranges: dict) -> list:
    """One badge per field sitting outside the range the model was fitted on.

    Not an error -- the model will happily return a number -- but an OLS
    extrapolating past its training range is guessing, and the user should
    know which field caused it.
    """
    warnings = []
    for name, label, _, _ in schema.NUMERIC_FIELDS:
        bounds = ranges.get(name)
        value = _as_float(values.get(name))
        if not bounds or value is None:
            continue
        if value < bounds["min"] or value > bounds["max"]:
            warnings.append(
                dbc.Badge(
                    f"{label}: {_fmt(value)} is outside the fitted range "
                    f"{_fmt(bounds['min'])}–{_fmt(bounds['max'])}",
                    color="warning", text_color="dark", className="me-2 mb-1",
                )
            )
    return warnings


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
