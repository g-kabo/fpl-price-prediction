"""A blank form: describe a hypothetical season, get a price.

Seeded with the training medians rather than zeros. An all-zero form is not
a neutral starting point -- it describes a free player who never played,
which is both outside the fitted range and not what anyone means by
"blank". Starting from the median player means every edit reads as a change
from something real.
"""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, html

import form
import model_store
import schema

dash.register_page(__name__, path="/manual", name="Manual entry",
                   title="Manual entry · Price Prediction")

PAGE = "manual"

_meta = model_store.get_meta()


def _defaults() -> dict:
    values = schema.field_defaults(_meta["ranges"])
    values[schema.POSITION_FIELD] = "MID"
    values[schema.TEAM_FIELD] = "other"
    return values


def layout() -> html.Div:
    return dbc.Container(
        [
            html.H4("Enter a season by hand", className="mb-1"),
            html.P(
                [
                    "Every field starts at the median of the ",
                    html.Strong(f"{_meta['training_rows']:,}"),
                    " seasons the model was fitted on. Hints under each input give "
                    "the range it was fitted over.",
                ],
                className="text-muted",
            ),
            dbc.Button("Reset to medians", id="manual-reset", color="secondary",
                       outline=True, size="sm", className="mb-3"),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(form.build_fields(PAGE, _defaults(), _meta["ranges"])),
                            className="shadow-sm",
                        ),
                        lg=8,
                    ),
                    dbc.Col(html.Div(id="manual-result"), lg=4),
                ],
                className="g-3",
            ),
            html.Div(id="manual-warnings", className="mt-3"),
            html.Div(id="manual-derived", className="mt-3"),
            dbc.Card(dbc.CardBody(html.Div(id="manual-contributions")),
                     className="mt-3 shadow-sm"),
        ],
        fluid=True,
        className="py-4",
    )


@callback(
    [Output(form.field_id(PAGE, name), "value") for name in form.ALL_FIELDS],
    Input("manual-reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset(_n_clicks):
    values = _defaults()
    return [values.get(name) for name in form.ALL_FIELDS]


@callback(
    Output("manual-result", "children"),
    Output("manual-warnings", "children"),
    Output("manual-derived", "children"),
    Output("manual-contributions", "children"),
    *form.input_inputs(PAGE),
)
def update(*args):
    values = form.values_from_args(args)
    interval, row = form.predict(values)

    warnings = form.range_warnings(values, _meta["ranges"])
    warning_block = (
        dbc.Alert(
            [
                html.Div("Outside the model's fitted range", className="fw-semibold mb-2"),
                *warnings,
                html.Div(
                    "A linear model extrapolates without complaint, but the "
                    "prediction is no longer supported by the data it was fitted on.",
                    className="small mt-2",
                ),
            ],
            color="warning", className="mb-0",
        )
        if warnings else None
    )

    return (
        form.result_card(
            interval, values.get("start_cost"),
            subtitle=f"Predicted {_meta['predict_season']}-"
                     f"{(_meta['predict_season'] + 1) % 100:02d} start price",
        ),
        warning_block,
        form.derived_panel(row),
        # A typed season has no "today" -- start price is the only price
        # this page knows, so it is the only line worth drawing.
        form.contribution_table(
            values, reference=("Start price", form._as_float(values.get("start_cost")))
        ),
    )
