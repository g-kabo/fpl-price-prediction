"""What if: take a season, change it, and see the price move.

The old player and manual pages, folded into one. Picking a season and a
player fills every field from his real season; "Start from an average
player" seeds them at the training medians instead. Medians rather than
zeros: an all-zero form describes a free player who never played, which is
outside the fitted range and not what anyone means by "blank".

The seasons are every completed one since 2017-18, plus the season in
progress as Price Watch projects it to 38 gameweeks, so a Price Watch
player can be opened here and tweaked (``?season=<year>&player=<code>``).

For a completed season the price being predicted has already been set by
FPL, and the page says what FPL actually did. Only the scoring season is a
fair test: the model was trained on every season before it, and the page
says so rather than let an in-sample match pass as accuracy.

Two quiet parity checks keep the page honest about itself: an unedited
scoring season must match ``run_pipeline.py``, and an unedited projected
season must match Price Watch, each to the penny.
"""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

import config
import form
import live
import model_store
import projection
import schema
import ui

dash.register_page(__name__, path="/lab", name="What if", order=1,
                   title="What if · FPL Price Prediction",
                   redirect_from=["/player", "/manual"])

PAGE = "lab"

_seasons = model_store.get_seasons()
_meta = model_store.get_meta()
_published = model_store.get_published_predictions()

SCORE_SEASON = _meta["score_season"]
TRAIN_THROUGH = _meta["train_through"]
#: The season being played now, which What if projects as Price Watch does.
CURRENT = _meta["predict_season"]

#: Newest first: the projected season, then every completed one.
SEASONS = [CURRENT] + sorted(_seasons["season"].unique().tolist(), reverse=True)

_projected_cache: tuple[str, pd.DataFrame] | None = None


def _projected() -> pd.DataFrame:
    """The season in progress, projected to 38 gameweeks as Price Watch does.

    Recomputed only when the daily snapshot changes. ``pred`` is Price
    Watch's own prediction, for the parity check.
    """
    global _projected_cache
    season = live.get_live_season()
    if _projected_cache is not None and _projected_cache[0] == season.token:
        return _projected_cache[1]
    projected = projection.project_frame(season.players, season.player_games,
                                         _meta["ranges"],
                                         league_games=season.progress.league_games)
    projected["pred"] = model_store.get_model().predict(
        projected[schema.MODEL_INPUT_COLUMNS]).to_numpy()
    _projected_cache = (season.token, projected)
    return projected


def _players(season: int) -> pd.DataFrame:
    if season == CURRENT:
        return _projected()
    return _seasons[_seasons["season"] == season]


def _season_options() -> list[dict]:
    return [{"label": (f"{config.season_label(s)} · projected" if s == CURRENT
                       else config.season_label(s)), "value": s} for s in SEASONS]


def _player_options(season: int) -> list[dict]:
    ordered = _players(season).sort_values("total_points", ascending=False)
    return [
        {"label": f"{row.web_name} · {row.team_name}, {row.element_type}",
         "value": int(row.code), "search": f"{row.web_name} {row.team_name}"}
        for row in ordered.itertuples()
    ]


def _default_code(season: int) -> int:
    return int(_players(season).nlargest(1, "total_points")["code"].iloc[0])


def _row(season: int, code) -> pd.Series | None:
    """One player's season, or None if he did not play in it."""
    if code is None:
        return None
    players = _players(season)
    match = players[players["code"] == code]
    return None if match.empty else match.iloc[0]


def _medians() -> dict:
    values = schema.field_defaults(_meta["ranges"])
    values[schema.POSITION_FIELD] = "MID"
    values[schema.TEAM_FIELD] = config.OTHER_TEAM
    return values


def _values_for(season: int, code) -> dict:
    player = _row(season, code)
    if player is None:
        return _medians()
    values = schema.form_values(player)
    if season == CURRENT:
        # Price Watch's own projected games, fractional as it is there, so
        # points per game comes out as it did on the board.
        values[schema.APPEARANCES_FIELD] = float(player[schema.APPEARANCES_FIELD])
    values[schema.POSITION_FIELD] = player[schema.POSITION_FIELD]
    values[schema.TEAM_FIELD] = (player[schema.TEAM_FIELD]
                                 if player[schema.TEAM_FIELD] in model_store.team_options()
                                 else config.OTHER_TEAM)
    return values


def layout(season=None, player=None, **_query) -> html.Div:
    """``?season=<year>&player=<code>`` opens that season, as Price Watch links."""
    try:
        season = int(season)
    except (TypeError, ValueError):
        season = SCORE_SEASON
    season = season if season in SEASONS else SCORE_SEASON
    try:
        code = int(player)
    except (TypeError, ValueError):
        code = None
    if _row(season, code) is None:
        code = _default_code(season)
    default = _values_for(season, code)
    return html.Div(
        [
            html.Section(
                html.Div(
                    [
                        html.H1("What if…"),
                        html.P(
                            "Take any season since 2017-18, or this one projected to 38 "
                            "gameweeks, change anything, and see what the model would price "
                            "him at for the season after.",
                            className="lede",
                        ),
                        html.Div(
                            [
                                html.Div(
                                    dcc.Dropdown(id="lab-season", options=_season_options(),
                                                 value=season, clearable=False,
                                                 searchable=False, className="lab-season"),
                                    className="lab-season-wrap",
                                ),
                                html.Div(
                                    dcc.Dropdown(id="lab-player", options=_player_options(season),
                                                 value=code, clearable=False,
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
    Output("lab-player", "options"),
    Output("lab-player", "value", allow_duplicate=True),
    Input("lab-season", "value"),
    State("lab-player", "value"),
    prevent_initial_call=True,
)
def pick_season(season, code):
    """New season, new player list: the same player if he played in it."""
    keep = code if _row(season, code) is not None else _default_code(season)
    return _player_options(season), keep


@callback(
    [dash.Output(form.field_id(PAGE, name), "value") for name in form.ALL_FIELDS],
    Output("lab-player", "value"),
    Input("lab-player", "value"),
    Input("lab-season", "value"),
    Input("lab-blank", "n_clicks"),
    Input("lab-reset", "n_clicks"),
)
def prefill(code, season, _blank, _reset):
    """Fill the form from a real season, from the medians, or back again."""
    if ctx.triggered_id == "lab-blank":
        values = _medians()
        return [values.get(name) for name in form.ALL_FIELDS] + [None]
    if ctx.triggered_id == "lab-reset" and code is None:
        values = _medians()
        return [values.get(name) for name in form.ALL_FIELDS] + [no_update]
    if ctx.triggered_id == "lab-season" and _row(season, code) is None:
        # pick_season is swapping the player; fill when his value lands.
        return [no_update] * (len(form.ALL_FIELDS) + 1)
    values = _values_for(season, code)
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
    State("lab-season", "value"),
)
def update(*args):
    # The form holds games played; the model wants FPL's two ratios.
    values = schema.with_ratios(form.values_from_args(args[:-2]))
    code, season = args[-2], args[-1]
    # The end price as typed, before any clamping below: the bar shows his
    # real price, not the edge of the training range.
    end_price = form._as_float(values.get("final_cost"))
    held = []
    if season == CURRENT:
        # Priced as Price Watch prices it: every input held inside the
        # training range. Otherwise a projected 344 points over a £4.6m
        # price derives a points-per-£m no player has ever had.
        for name in schema.NUMERIC_NAMES:
            values[name] = form._as_float(values.get(name))
        held = projection.clamp(values, _meta["ranges"])
    interval, _ = form.predict(values)
    predicted = float(interval["pred"].iloc[0])
    start = form._as_float(values.get("start_cost"))

    player = _row(season, code)
    if player is not None:
        if season == CURRENT:
            meta = (f"{config.season_label(season)} so far, projected from "
                    f"{float(player['games_played']):g} gameweeks to 38")
        else:
            meta = f"{config.season_label(season)} season"
        who = ui.player_header(player.web_name, player.team_name, player.element_type,
                               meta=html.Div(meta, className="player-meta"))
    else:
        who = ui.player_header("An average player", None, values.get(schema.POSITION_FIELD),
                               meta=html.Div("Every figure starts at the median of the "
                                             f"{_meta['training_rows']:,} seasons the model "
                                             "learned from.", className="player-meta"))

    tag = ui.answer_tag(interval, start, f"Predicted {config.season_label(season + 1)} price")
    # Start and end price (today's, for a season still running) as cards
    # rather than ticks on the bar; for an unedited completed season, the
    # price FPL went on to set too, which also stays on the bar.
    actual = None
    if player is not None and season != CURRENT and not _edited(season, code, values):
        next_cost = player.get("next_cost")
        actual = float(next_cost) if pd.notna(next_cost) else None
    cards = [("Start price", start, "start"),
             ("Today's price" if season == CURRENT else "End price", end_price, "end")]
    if actual is not None:
        cards.append((f"FPL set, {config.season_label(season + 1)}", actual, "actual"))
    body = ui.answer_body(interval, start, "his start price", "Start",
                          extra=_reality(season, code, values, predicted),
                          actual=actual, reference_on_bar=False,
                          cards=ui.price_cards(cards))
    why = [ui.why_this_price(values, reference=("Start price", start))]
    flags = _held_note(held, values) if season == CURRENT else ui.out_of_range(values, _meta["ranges"])
    return who, tag, body, flags, why


def _held_note(held: list[str], values: dict):
    """Which projected figures were held at the edge of the training range."""
    if not held:
        return None
    labels = {name: label for name, label, _, _ in schema.NUMERIC_FIELDS}
    items = [html.Li(f"{labels.get(name, name)} held at {form._fmt(values[name])}.")
             for name in held]
    return html.Div(
        [html.Div([html.I(className="bi bi-info-circle-fill"),
                   " Held inside what the model has seen"], className="flag-title"),
         html.Ul(items),
         html.P("Projected figures beyond the training range are held at its edge, as "
                "Price Watch does, rather than extrapolated.", className="fine")],
        className="flag",
    )


def _edited(season: int, code, values: dict) -> bool:
    """True once any figure differs from his real season as loaded."""
    unedited = _values_for(season, code)
    return any(
        form._as_float(values.get(name)) != form._as_float(unedited.get(name))
        for name in schema.FORM_NAMES
    ) or any(values.get(f) != unedited.get(f)
             for f in (schema.POSITION_FIELD, schema.TEAM_FIELD))


def _reality(season: int, code, values: dict, predicted: float):
    """What FPL actually did, and the parity checks, for an unedited season."""
    player = _row(season, code)
    if player is None:
        return None
    if _edited(season, code, values):
        return html.P("Edited: this is no longer his real season, so there is no real "
                      "price to compare against.", className="fine")

    if season == CURRENT:
        return _projected_reality(player, predicted)

    lines = []
    actual = player.get("next_cost")
    if pd.notna(actual):
        actual = float(actual)
        miss = predicted - actual
        lines.append(html.Div(
            [html.Span("What FPL actually did", className="reality-label"),
             html.Span([f"Priced him at £{actual:.1f}m in August {season + 1}, ",
                        html.Strong(f"£{abs(miss):.2f}m {'below' if miss > 0 else 'above'}"
                                    if abs(miss) >= 0.05 else "on the money"),
                        " the model's call." if abs(miss) >= 0.05 else "."],
                       className="reality-text")],
            className="reality",
        ))
        if season <= TRAIN_THROUGH:
            lines.append(html.P(
                "The model learned from this season, so a close call here is not a test "
                f"of it. {config.season_label(SCORE_SEASON)} is the season it never saw.",
                className="fine"))
        elif season == SCORE_SEASON:
            lines.append(html.P("The model never saw this season, so this is a fair test.",
                                className="fine"))
    else:
        lines.append(html.P(f"He did not return for {config.season_label(season + 1)}, so "
                            "FPL never priced him.", className="fine"))
    if season == SCORE_SEASON and not _published.empty and code in _published.index:
        published = float(_published.loc[code, "pred"])
        if abs(published - predicted) < 0.005:
            lines.append(html.P([html.I(className="bi bi-check2-circle"),
                                 " Same answer as the batch pipeline, to the penny."],
                                className="fine verified"))
    return html.Div(lines) if lines else None


def _projected_reality(player: pd.Series, predicted: float) -> html.Div:
    """For the season in progress: nothing to compare yet, bar Price Watch."""
    lines = [html.P(f"FPL sets his {config.season_label(CURRENT + 1)} price in August "
                    f"{CURRENT + 1}. Until then, this is the forecast Price Watch shows "
                    "from his form so far.", className="fine")]
    # Price Watch works points per game and per £m out from the unrounded
    # projected totals; the form holds whole points, so a few players land
    # a penny or two apart. Said rather than hidden.
    gap = abs(float(player["pred"]) - predicted)
    if gap < 0.005:
        lines.append(html.P([html.I(className="bi bi-check2-circle"),
                             " Same answer as Price Watch, to the penny."],
                            className="fine verified"))
    elif gap < 0.05:
        lines.append(html.P(f"Within £{gap:.2f}m of Price Watch, which works its ratios out "
                            "from the projected totals before rounding them to whole "
                            "numbers.", className="fine"))
    return html.Div(lines)
