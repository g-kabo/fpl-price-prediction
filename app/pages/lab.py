"""What if: take a completed season, change it, and see the price move.

The old player and manual pages, folded into one. Picking a player fills
every field from his real season; "Start from an average player"
seeds them at the training medians instead. Medians rather than zeros: an
all-zero form describes a free player who never played, which is outside
the fitted range and not what anyone means by "blank".

Because the season being edited is complete, the price being predicted has
already been set by FPL. Where the batch backtest knows it, the page says
what FPL actually did -- the most honest check on the model there is.

The batch pipeline's own prediction is still compared against, but quietly:
on an unedited prefill the two must agree, which keeps this page a
continuous check that the saved artifact matches ``run_pipeline.py``.
"""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

import config
import form
import model_store
import schema
import ui

dash.register_page(__name__, path="/lab", name="What if", order=1,
                   title="What if · FPL Price Prediction",
                   redirect_from=["/player", "/manual"])

PAGE = "lab"

_scores = model_store.get_scores()
_meta = model_store.get_meta()
_published = model_store.get_published_predictions()

SCORE_SEASON = _meta["score_season"]
PREDICT_SEASON = _meta["predict_season"]


def _actual_prices() -> pd.Series:
    """What FPL really set each player at, from the pipeline's backtest."""
    path = config.OUTPUT_DIR / f"backtest_{PREDICT_SEASON}.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    frame = pd.read_csv(path, encoding="utf-8")
    return frame.dropna(subset=["actual_start_cost"]).set_index("code")["actual_start_cost"]


_actual = _actual_prices()


def _player_options() -> list[dict]:
    ordered = _scores.sort_values("total_points", ascending=False)
    return [
        {"label": f"{row.web_name} · {row.team_name}, {row.element_type}",
         "value": int(row.code), "search": f"{row.web_name} {row.team_name}"}
        for row in ordered.itertuples()
    ]


def _default_code() -> int:
    return int(_scores.nlargest(1, "total_points")["code"].iloc[0])


def _medians() -> dict:
    values = schema.field_defaults(_meta["ranges"])
    values[schema.POSITION_FIELD] = "MID"
    values[schema.TEAM_FIELD] = config.OTHER_TEAM
    return values


def _values_for(code) -> dict:
    match = _scores[_scores["code"] == code]
    if match.empty:
        return _medians()
    player = match.iloc[0]
    values = schema.form_values(player)
    values[schema.POSITION_FIELD] = player[schema.POSITION_FIELD]
    values[schema.TEAM_FIELD] = (player[schema.TEAM_FIELD]
                                 if player[schema.TEAM_FIELD] in model_store.team_options()
                                 else config.OTHER_TEAM)
    return values


def layout() -> html.Div:
    default = _values_for(_default_code())
    return html.Div(
        [
            html.Section(
                html.Div(
                    [
                        html.H1("What if…"),
                        html.P(
                            f"Take any {config.season_label(SCORE_SEASON)} season, change "
                            "anything, and see what the model would have priced him at for "
                            f"{config.season_label(PREDICT_SEASON)}.",
                            className="lede",
                        ),
                        html.Div(
                            [
                                html.Div(
                                    dcc.Dropdown(id="lab-player", options=_player_options(),
                                                 value=_default_code(), clearable=False,
                                                 placeholder="Find a player",
                                                 className="lab-picker"),
                                    className="lab-picker-wrap",
                                ),
                                ui.dbc_button("Start from an average player", "lab-blank",
                                              icon="bi-person-dash", kind="on-dark"),
                            ],
                            className="lab-pick-row",
                        ),
                    ],
                    className="wrap",
                ),
                className="hero hero-compact",
            ),
            html.Div(
                html.Div(
                    [
                        html.Div(id="lab-head", className="sheet-head"),
                        html.Div(
                            [
                                html.Div(
                                    html.Div([html.Div(id="lab-tag"), html.Div(id="lab-answer"),
                                              html.Div(id="lab-flags")],
                                             className="sheet-answer-pin"),
                                    className="sheet-answer",
                                ),
                                html.Div(
                                    [
                                        html.Div(
                                            [html.H2("The season", className="sheet-title"),
                                             ui.dbc_button("Reset", "lab-reset",
                                                           icon="bi-arrow-counterclockwise",
                                                           kind="ghost")],
                                            className="sheet-title-row",
                                        ),
                                        html.P("Type a figure or use − and +; the price "
                                               "follows.", className="block-note"),
                                        html.Div(form.build_fields(PAGE, default, _meta["ranges"]),
                                                 className="groups"),
                                    ],
                                    className="sheet-editor",
                                ),
                            ],
                            className="sheet-grid",
                        ),
                        html.Div(id="lab-why", className="sheet-why"),
                    ],
                    className="sheet",
                ),
                className="wrap sheet-wrap",
            ),
        ],
    )


@callback(
    [dash.Output(form.field_id(PAGE, name), "value") for name in form.ALL_FIELDS],
    Output("lab-player", "value"),
    Input("lab-player", "value"),
    Input("lab-blank", "n_clicks"),
    Input("lab-reset", "n_clicks"),
)
def prefill(code, _blank, _reset):
    """Fill the form from a real season, from the medians, or back again."""
    if ctx.triggered_id == "lab-blank":
        values = _medians()
        return [values.get(name) for name in form.ALL_FIELDS] + [None]
    if ctx.triggered_id == "lab-reset" and code is None:
        values = _medians()
        return [values.get(name) for name in form.ALL_FIELDS] + [no_update]
    values = _values_for(code)
    return [values.get(name) for name in form.ALL_FIELDS] + [no_update]


@callback(
    [Output(form.field_id(PAGE, name), "value", allow_duplicate=True)
     for name in schema.FORM_NAMES],
    Input({"page": PAGE, "step": ALL, "dir": ALL}, "n_clicks"),
    [State(form.field_id(PAGE, name), "value") for name in schema.FORM_NAMES],
    prevent_initial_call=True,
)
def step(_clicks, *current):
    """A stepper press: move one figure by its unit, never below zero --
    no input on the form can genuinely be negative."""
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or not ctx.triggered or not ctx.triggered[0]["value"]:
        return [no_update] * len(schema.FORM_NAMES)

    field, direction = trigger["step"], trigger["dir"]
    index = schema.FORM_NAMES.index(field)
    value = form._as_float(current[index]) + direction * form.STEPS.get(field, 1)
    value = max(value, 0.0)
    if field == schema.APPEARANCES_FIELD:
        value = min(value, schema.MAX_APPEARANCES)
    integer = next(i for n, _, _, i in schema.FORM_FIELDS if n == field)
    value = int(round(value)) if integer else round(value, 2)

    out = [no_update] * len(schema.FORM_NAMES)
    out[index] = value
    return out


@callback(
    Output("lab-head", "children"),
    Output("lab-tag", "children"),
    Output("lab-answer", "children"),
    Output("lab-flags", "children"),
    Output("lab-why", "children"),
    *form.input_inputs(PAGE),
    Input("lab-player", "value"),
)
def update(*args):
    # The form holds games played; the model wants FPL's two ratios.
    values = schema.with_ratios(form.values_from_args(args[:-1]))
    code = args[-1]
    interval, _ = form.predict(values)
    predicted = float(interval["pred"].iloc[0])
    start = form._as_float(values.get("start_cost"))

    match = _scores[_scores["code"] == code] if code is not None else _scores.iloc[0:0]
    if not match.empty:
        player = match.iloc[0]
        who = ui.player_header(player.web_name, player.team_name, player.element_type,
                               meta=html.Div(f"{config.season_label(SCORE_SEASON)} season",
                                             className="player-meta"))
    else:
        who = ui.player_header("An average player", None, values.get(schema.POSITION_FIELD),
                               meta=html.Div("Every figure starts at the median of the "
                                             f"{_meta['training_rows']:,} seasons the model "
                                             "learned from.", className="player-meta"))

    tag = ui.answer_tag(interval, start, f"Predicted {config.season_label(PREDICT_SEASON)} price")
    body = ui.answer_body(interval, start, "his start price", "Start",
                          extra=_reality(code, values, predicted))
    why = [ui.why_this_price(values, reference=("Start price", start))]
    return who, tag, body, ui.out_of_range(values, _meta["ranges"]), why


def _reality(code, values: dict, predicted: float):
    """What FPL actually did, and the pipeline check, for an unedited season."""
    if code is None:
        return None
    unedited = _values_for(code)
    edited = any(
        form._as_float(values.get(name)) != form._as_float(unedited.get(name))
        for name in schema.FORM_NAMES
    ) or any(values.get(f) != unedited.get(f)
             for f in (schema.POSITION_FIELD, schema.TEAM_FIELD))

    if edited:
        return html.P("Edited: this is no longer his real season, so there is no real "
                      "price to compare against.", className="fine")

    lines = []
    if code in _actual.index:
        actual = float(_actual.loc[code])
        miss = predicted - actual
        lines.append(html.Div(
            [html.Span("What FPL actually did", className="reality-label"),
             html.Span([f"Priced him at £{actual:.1f}m in August "
                        f"{PREDICT_SEASON}, ",
                        html.Strong(f"£{abs(miss):.2f}m {'below' if miss > 0 else 'above'}"
                                    if abs(miss) >= 0.05 else "on the money"),
                        " the model's call." if abs(miss) >= 0.05 else "."],
                       className="reality-text")],
            className="reality",
        ))
    if not _published.empty and code in _published.index:
        published = float(_published.loc[code, "pred"])
        if abs(published - predicted) < 0.005:
            lines.append(html.P([html.I(className="bi bi-check2-circle"),
                                 " Same answer as the batch pipeline, to the penny."],
                                className="fine verified"))
    return html.Div(lines) if lines else None
