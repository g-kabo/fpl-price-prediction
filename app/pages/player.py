"""Prefill from a real completed season, then change whatever you like.

The quickest way to a sensible set of inputs is to start from a player who
actually produced them. Picking someone fills all fourteen fields from
their 2025-26 season; from there the form is a what-if machine.

The batch pipeline's own prediction for the same player is shown alongside.
On an unedited prefill the two must agree, which makes this page a
continuous check that the saved artifact still matches ``run_pipeline.py``.
"""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html

import form
import model_store
import schema

dash.register_page(__name__, path="/", name="Player", title="Player · Price Prediction")

PAGE = "player"

_scores = model_store.get_scores()
_meta = model_store.get_meta()
_published = model_store.get_published_predictions()


def _player_options() -> list[dict]:
    ordered = _scores.sort_values("total_points", ascending=False)
    return [
        {
            "label": f"{row.web_name} — {row.team_name}, {row.element_type} "
                     f"(£{row.start_cost:.1f}m, {int(row.total_points)} pts)",
            "value": int(row.code),
        }
        for row in ordered.itertuples()
    ]


def _default_code() -> int:
    return int(_scores.nlargest(1, "total_points")["code"].iloc[0])


def layout() -> html.Div:
    default = _values_for(_default_code())
    return dbc.Container(
        [
            html.H4("Predict from a completed season", className="mb-1"),
            html.P(
                f"Start from any {_meta['score_season']}-"
                f"{(_meta['score_season'] + 1) % 100:02d} player, then edit the inputs "
                f"to see how next season's price responds.",
                className="text-muted",
            ),
            dbc.Row(
                dbc.Col(
                    [
                        dbc.Label("Player", className="fw-semibold"),
                        dcc.Dropdown(
                            id="player-picker",
                            options=_player_options(),
                            value=_default_code(),
                            clearable=False,
                            placeholder="Search for a player...",
                        ),
                    ],
                    lg=6, md=8,
                ),
                className="mb-4",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(form.build_fields(PAGE, default, _meta["ranges"])),
                            className="shadow-sm",
                        ),
                        lg=8,
                    ),
                    dbc.Col(
                        [
                            html.Div(id="player-result"),
                            html.Div(id="player-crosscheck", className="mt-3"),
                        ],
                        lg=4,
                    ),
                ],
                className="g-3",
            ),
            html.Div(id="player-warnings", className="mt-3"),
            html.Div(id="player-derived", className="mt-3"),
            dbc.Card(dbc.CardBody(html.Div(id="player-contributions")),
                     className="mt-3 shadow-sm"),
        ],
        fluid=True,
        className="py-4",
    )


def _values_for(code: int) -> dict:
    match = _scores[_scores["code"] == code]
    if match.empty:
        return schema.field_defaults(_meta["ranges"])

    player = match.iloc[0]
    values = {name: player[name] for name in schema.NUMERIC_NAMES}
    values[schema.POSITION_FIELD] = player[schema.POSITION_FIELD]
    values[schema.TEAM_FIELD] = (
        player[schema.TEAM_FIELD]
        if player[schema.TEAM_FIELD] in model_store.team_options()
        else "other"
    )
    return values


@callback(
    [Output(form.field_id(PAGE, name), "value") for name in form.ALL_FIELDS],
    Input("player-picker", "value"),
)
def prefill(code):
    """Load the chosen player's real season into the form."""
    values = _values_for(code)
    return [values.get(name) for name in form.ALL_FIELDS]


@callback(
    Output("player-result", "children"),
    Output("player-crosscheck", "children"),
    Output("player-warnings", "children"),
    Output("player-derived", "children"),
    Output("player-contributions", "children"),
    *form.input_inputs(PAGE),
    Input("player-picker", "value"),
)
def update(*args):
    values = form.values_from_args(args[:-1])
    code = args[-1]

    interval, row = form.predict(values)
    card = form.result_card(
        interval, values.get("start_cost"),
        subtitle=f"Predicted {_meta['predict_season']}-"
                 f"{(_meta['predict_season'] + 1) % 100:02d} start price",
    )

    warnings = form.range_warnings(values, _meta["ranges"])
    warning_block = (
        dbc.Alert([html.Div("Outside the model's fitted range", className="fw-semibold mb-2"),
                   *warnings], color="warning", className="mb-0")
        if warnings else None
    )

    return (
        card,
        _crosscheck(code, float(interval["pred"].iloc[0])),
        warning_block,
        form.derived_panel(row),
        # ``final_cost`` is on the prefilled row too, but it is not a form
        # field: editing start price would leave it pointing at whatever the
        # originally-picked player happened to finish on. Start price is the
        # one that stays true to what is on screen, and it is what the result
        # card compares against.
        form.contribution_table(
            values, reference=("Start price", form._as_float(values.get("start_cost")))
        ),
    )


def _crosscheck(code, predicted: float):
    """Compare against the batch pipeline's published number for this player."""
    if _published.empty or code not in _published.index:
        return None

    published = float(_published.loc[code, "pred"])
    matches = abs(published - predicted) < 0.005

    if matches:
        body = html.Span(
            [html.Span("✓ ", className="text-success fw-bold"),
             f"matches the pipeline's £{published:.2f}m"],
            className="small",
        )
    else:
        body = html.Span(
            f"pipeline predicts £{published:.2f}m for the unedited season",
            className="small text-muted",
        )

    return html.Div(body, className="px-3 py-2 bg-light border rounded")
