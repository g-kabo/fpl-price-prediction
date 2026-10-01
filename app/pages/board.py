"""Price Watch: who the model thinks FPL should reprice next season.

The landing page. Reads the daily snapshot of the official FPL API (see
:mod:`live`) rather than the mirror's cached CSV, extends
each player's part-season to 38 gameweeks from his current-season form alone
(see :mod:`projection`), and prices the season after next.

Each player is divided by his own club's fixtures played rather than by a
league-wide gameweek number, because mid-gameweek those differ: half the
division can be a match ahead of the other half for most of a weekend.

The filters scope the transfer list *and* the market map together, and
narrow what is displayed, never what is computed: the projection always
runs on the whole league first, because the league-average denominator is a
league-wide quantity.
"""

from __future__ import annotations

import time
import unicodedata

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

import charts
import config
import forecast_history
import form
import live
import model_store
import projection
import schema
import theme
import ui

dash.register_page(__name__, path="/", name="Price Watch", order=0,
                   title="Price Watch · FPL Price Prediction",
                   redirect_from=["/projected"])

_meta = model_store.get_meta()
_history = model_store.get_price_history()

SEASON = _meta["predict_season"]
TARGET = SEASON + 1

#: Shape of the XI on the pitch, goalkeeper first, the way FPL draws a team.
FORMATION = [("GK", 1), ("DEF", 4), ("MID", 4), ("FWD", 2)]

PAGE_SIZE = 20

#: How often an open page checks for a new daily snapshot. Hourly is plenty
#: for data that changes once a day.
POLL_MS = 60 * 60 * 1000

#: The transfer list's columns: ``(key, frame column, numeric?)``. Every
#: header sorts by its own column; a numeric one starts biggest-first, the
#: player name A to Z, and a second click on the same header reverses it.
COLUMNS = [
    ("player", "name_key", False),
    ("points", "points_now", True),
    ("minutes", "minutes_now", True),
    ("selected", "selected_by_percent", True),
    ("ref", "ref", True),
    ("pred", "pred", True),
    ("move", "delta", True),
]
_COLUMN = {key: (column, numeric) for key, column, numeric in COLUMNS}

DEFAULT_SORT = {"col": "move", "desc": True}

REFERENCE_WORDS = {"price_now": "today's price", "start_cost": "his August price"}

#: Forecast movers' comparison windows: ``key: (label, days back)``. None
#: means the first recorded day. A window reaching back before the record
#: starts falls back to that first day, and the note names the day used.
MOVER_WINDOWS = {
    "day": ("Since yesterday", 1),
    "week": ("Past week", 7),
    "all": ("Since tracking began", None),
}
DEFAULT_WINDOW = "week"

#: Players shown on each side of the forecast movers.
MOVERS_EACH = 5

#: Smallest forecast change worth listing: anything less rounds to £0.00m.
MOVER_FLOOR = 0.005

#: Columns the page keeps per player, in the browser-side store.
_KEEP = (schema.NUMERIC_NAMES
         + ["code", "web_name", "team_name", "element_type", "pred", "price_now",
            "points_now", "minutes_now", "selected_by_percent", "games_played"])


def layout(player=None, **_query) -> html.Div:
    """``?player=<code>`` opens that player's card once the data lands."""
    try:
        deeplink = int(player) if player else None
    except ValueError:
        deeplink = None
    return html.Div(
        [
            html.Section(
                html.Div(
                    [
                        html.Div(
                            [
                                html.H1(["Price Watch ",
                                         html.Span(config.season_label(TARGET),
                                                   className="h1-season")]),
                                html.P(
                                    f"Who the model thinks FPL should reprice for "
                                    f"{config.season_label(TARGET)}, from current "
                                    f"{config.season_label(SEASON)} form projected to a "
                                    "full 38-gameweek season.",
                                    className="lede",
                                ),
                            ],
                        ),
                        html.Div(
                            [
                                html.Div(id="board-status", className="chips"),
                                html.Div(
                                    [
                                        ui.dbc_button("Projection settings", "board-settings-toggle",
                                                      icon="bi-sliders", kind="on-dark"),
                                    ],
                                    className="hero-actions",
                                ),
                            ],
                            className="hero-side",
                        ),
                    ],
                    className="wrap hero-inner",
                ),
                className="hero",
            ),
            dbc.Collapse(_settings(), id="board-settings", is_open=False),
            html.Section(
                html.Div(
                    [
                        html.Div(
                            html.Div([html.H2("The model's XI", className="block-title"),
                                      html.P(id="board-xi-note", className="block-note")]),
                            className="block-head",
                        ),
                        html.Div(
                            [
                                dcc.Loading(html.Div(id="board-pitch", className="pitch"),
                                            type="dot", color=theme.CYAN),
                                dbc.RadioItems(
                                    id="board-xi",
                                    options=[{"label": "Risers", "value": "rise"},
                                             {"label": "Fallers", "value": "fall"}],
                                    value="rise", inline=True,
                                    className="segmented segmented-pitch",
                                ),
                            ],
                            className="pitch-wrap",
                        ),
                    ],
                    className="wrap",
                ),
                className="block block-pitch",
            ),
            html.Section(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div([html.H2("Forecast movers", className="block-title"),
                                          html.P(id="board-movers-note", className="block-note")]),
                                dbc.RadioItems(
                                    id="board-movers-window",
                                    options=[{"label": label, "value": key}
                                             for key, (label, _) in MOVER_WINDOWS.items()],
                                    value=DEFAULT_WINDOW, inline=True, className="segmented",
                                ),
                            ],
                            className="block-head",
                        ),
                        html.Div(id="board-movers", className="movers"),
                    ],
                    className="wrap",
                ),
                className="block",
            ),
            html.Section(
                html.Div(
                    [
                        html.Div(
                            html.Div([html.H2("Transfer list", className="block-title"),
                                      html.P("Every current player. Filters apply to the list "
                                             "and the market map below it.",
                                             className="block-note")]),
                            className="block-head",
                        ),
                        _filters(),
                        html.Div(id="board-count", className="list-count"),
                        html.Div(id="board-list", className="tlist"),
                        html.Div(ui.dbc_button("Show more players", "board-more",
                                               icon="bi-chevron-down", kind="ghost"),
                                 id="board-more-wrap", className="more"),
                    ],
                    className="wrap",
                ),
                className="block",
            ),
            html.Section(
                html.Div(
                    [
                        html.Div(
                            html.Div([html.H2("Market map", className="block-title"),
                                      html.P(id="board-map-note", className="block-note")]),
                            className="block-head",
                        ),
                        html.Div(
                            dcc.Graph(id="board-map",
                                      config={"displayModeBar": False, "responsive": True}),
                            className="panel",
                        ),
                    ],
                    className="wrap",
                ),
                className="block",
            ),
            dbc.Offcanvas(html.Div(id="board-card-body"), id="board-card",
                          placement="end", is_open=False, scrollable=True,
                          className="player-card", title=""),
            dcc.Store(id="board-token"),
            # Picks up a new daily snapshot in a tab left open overnight.
            dcc.Interval(id="board-poll", interval=POLL_MS),
            dcc.Store(id="board-data"),
            dcc.Store(id="board-selected"),
            dcc.Store(id="board-sort", data=DEFAULT_SORT),
            dcc.Store(id="board-deeplink", data=deeplink),
        ],
    )


def _settings() -> html.Div:
    """The projection's knobs, out of the way until someone asks."""
    return html.Div(
        html.Div(
            [
                html.Div(
                    [
                        html.Div("Compare against", className="field-label"),
                        dbc.RadioItems(
                            id="board-xref",
                            options=[{"label": label, "value": key}
                                     for key, label in charts.X_FIELDS.items()],
                            value=charts.DEFAULT_X, className="segmented segmented-light",
                            inline=True,
                        ),
                        html.Div("Today's price is what a manager holding him pays now. "
                                 "August is like-for-like, since the forecast is itself a "
                                 "start price.", className="field-hint"),
                    ],
                    className="field",
                ),
            ],
            className="wrap settings-grid",
        ),
        className="settings",
    )


def _filters() -> html.Div:
    return html.Div(
        [
            html.Div(
                [html.I(className="bi bi-search"),
                 dcc.Input(id="board-search", type="search", debounce=0.3,
                           placeholder="Find a player", className="search-input")],
                className="search",
            ),
            dbc.Checklist(
                id="board-pos",
                options=[{"label": p, "value": p} for p in schema.POSITIONS],
                value=[], inline=True, className="pos-filter",
            ),
            dcc.Dropdown(id="board-clubs", options=[], value=[], multi=True,
                         placeholder="All clubs", className="club-filter"),
        ],
        className="filters",
    )


# ---------------------------------------------------------------- data


@callback(
    Output("board-settings", "is_open"),
    Output("board-settings-toggle", "className"),
    Input("board-settings-toggle", "n_clicks"),
    State("board-settings", "is_open"),
    prevent_initial_call=True,
)
def toggle_settings(_n_clicks, is_open):
    """Open or close the projection settings drawer under the header."""
    opening = not is_open
    return opening, "btn-on-dark is-open" if opening else "btn-on-dark"


@callback(
    Output("board-token", "data"),
    Output("board-clubs", "options"),
    Input("board-poll", "n_intervals"),
    State("board-token", "data"),
)
def fetch(_n, current):
    """Load the daily snapshot, or fall back to the mirror's cached CSV.

    The frame itself stays in :mod:`live`'s cache; the store carries only a
    token that changes when the data does, which is enough to retrigger the
    projection -- and, left unchanged, keeps an hourly poll from recomputing
    the whole league for nothing.
    """
    season = live.get_live_season()
    if season.token == current:
        return no_update, no_update
    clubs = sorted(season.players["team_name"].dropna().unique())
    return season.token, clubs


@callback(
    Output("board-data", "data"),
    Output("board-status", "children"),
    Input("board-token", "data"),
)
def compute(token):
    """Price every current player on a projected full season.

    Each club is divided by its own fixtures played, so a Sunday kickoff is
    not scaled as though it were a week behind the Saturday games.
    """
    if token is None:
        return no_update, no_update

    season = live.get_live_season()
    current = season.players
    games, league = season.player_games, season.progress.league_games

    projected = projection.project_frame(
        current, games, _meta["ranges"], league_games=league
    )
    projected["pred"] = model_store.get_model().predict(
        projected[schema.MODEL_INPUT_COLUMNS]).round(3)

    lookup = current.set_index("code")
    for column, source in (("team_name", "team_name"), ("element_type", "element_type"),
                           ("points_now", "total_points"), ("minutes_now", "minutes"),
                           ("price_now", "final_cost"),
                           ("selected_by_percent", "selected_by_percent")):
        projected[column] = projected["code"].map(lookup[source])
    projected["element_type"] = projected["element_type"].astype(str)

    records = projected[[c for c in _KEEP if c in projected.columns]].to_dict("records")
    return records, _status(season)


def _status(season) -> list:
    """How fresh the data is, and how the season was projected."""
    if not season.is_live:
        source = html.Span([html.I(className="bi bi-cloud-slash"), "Offline: cached snapshot"],
                           className="chip chip-warn",
                           title=f"No daily FPL snapshot could be read ({season.error}), so "
                                 "this is the GitHub mirror's copy, which can be weeks old.")
    elif season.is_stale:
        source = html.Span([html.I(className="bi bi-exclamation-triangle"),
                            f"Prices as of {season.as_of_label}"],
                           className="chip chip-warn",
                           title="The daily snapshot has not updated for over a day, so "
                                 "recent price changes are missing.")
    else:
        source = html.Span([html.I(className="bi bi-broadcast"),
                            f"Prices as of {season.as_of_label}"],
                           className="chip chip-live",
                           title="Read from the official FPL API once a day, after the "
                                 "overnight price changes.")

    gameweek = season.gameweek_label
    chips = [source, html.Span(gameweek[:1].upper() + gameweek[1:], className="chip")]

    chips.append(html.Span(
        "Form scaled to a full season",
        className="chip",
        title="Each player's totals so far are multiplied up to 38 gameweeks, "
              "using his own club's fixtures played.",
    ))
    return chips


# ---------------------------------------------------------------- views


def _frame(data) -> pd.DataFrame:
    return pd.DataFrame(data or [])


def _with_delta(frame: pd.DataFrame, xref: str) -> pd.DataFrame:
    xref = xref if xref in charts.X_FIELDS else charts.DEFAULT_X
    frame = frame.copy()
    frame["ref"] = frame[xref]
    frame["delta"] = frame["pred"] - frame["ref"]
    return frame


def _pick_button(row, origin: str, children, class_name: str) -> html.Button:
    return html.Button(children, id={"type": "pick", "code": int(row.code), "from": origin},
                       className=class_name, n_clicks=0, type="button")


def _spot(row) -> html.Button:
    """One shirt on the pitch: name plate, then the price tag."""
    return _pick_button(
        row, "pitch",
        [
            ui.shirt(row.team_name, size="pitch"),
            html.Span(row.web_name, className="spot-name"),
            html.Span([html.Span(theme.money(row.ref), className="spot-now"),
                       html.I(className="bi bi-arrow-right"),
                       html.Span(theme.money(row.pred), className="spot-pred")],
                      className=f"spot-tag spot-{theme.direction(row.delta)}"),
        ],
        "spot",
    )


@callback(
    Output("board-pitch", "children"),
    Output("board-xi-note", "children"),
    Input("board-data", "data"),
    Input("board-xi", "value"),
    Input("board-xref", "value"),
)
def pitch(data, xi, xref):
    """The biggest predicted movers per position, in formation.

    Drawn from players who have played this season, league-wide -- the
    filters below scope the list and the map, not the XI.
    """
    frame = _frame(data)
    if frame.empty:
        return ui.empty("Waiting for the live data.", icon="bi-hourglass-split"), ""
    frame = _with_delta(frame, xref)
    pool = frame[frame["minutes_now"] > 0]

    rows = []
    for position, count in FORMATION:
        group = pool[pool["element_type"] == position]
        group = group.nlargest(count, "delta") if xi == "rise" else group.nsmallest(count, "delta")
        rows.append(html.Div([_spot(r) for r in group.itertuples()], className="pitch-row"))

    against = REFERENCE_WORDS.get(xref, "today's price")
    note = (f"Biggest predicted {'rises' if xi == 'rise' else 'falls'} against {against}, "
            "by position, from players who have featured this season. Each tag reads "
            f"{'today' if xref == 'price_now' else 'August'} → {config.season_label(TARGET)}.")
    chalk = [html.Div(className="pitch-lines"), html.Div(className="pitch-six"),
             html.Div(className="pitch-halfway")]
    return [*chalk, *rows], note


def _mover(row) -> html.Button:
    """One forecast mover: who, his forecast then and now, and the change."""
    return _pick_button(
        row, "movers",
        [
            html.Span([ui.shirt(row.team_name, size="sm"),
                       html.Span([html.Span(row.web_name, className="tl-name"),
                                  html.Span([ui.position_pill(row.element_type),
                                             html.Span(row.team_name, className="tl-club")],
                                            className="tl-sub")],
                                 className="tl-who")],
                      className="tl-player"),
            html.Span([theme.money(row.then, places=2), html.I(className="bi bi-arrow-right"),
                       html.Strong(theme.money(row.pred, places=2))],
                      className="num mv-path"),
            html.Span(ui.change_chip(row.change), className="num"),
        ],
        "mv-row",
    )


def _movers_side(title: str, icon: str, rows: pd.DataFrame, none: str) -> html.Div:
    body = ([_mover(r) for r in rows.itertuples()] if not rows.empty
            else [html.P(none, className="mv-none")])
    return html.Div([html.Div([html.I(className=f"bi {icon}"), title], className="mv-head"),
                     *body],
                    className="mv-side")


@callback(
    Output("board-movers", "children"),
    Output("board-movers-note", "children"),
    Input("board-data", "data"),
    Input("board-movers-window", "value"),
)
def movers(data, window):
    """Whose forecast has moved most since an earlier recorded morning.

    Today's side is the live frame the rest of the page shows; the earlier
    side is the forecast recorded that morning. League-wide, like the XI:
    the filters belong to the list and the map.
    """
    frame = _frame(data)
    if frame.empty:
        return ui.empty("Waiting for the live data.", icon="bi-hourglass-split"), ""
    season = live.get_live_season()
    if not season.is_live:
        return ui.empty("Forecast movers need the daily FPL snapshot, which could not be read.",
                        icon="bi-cloud-slash"), ""

    _label, days = MOVER_WINDOWS.get(window, MOVER_WINDOWS[DEFAULT_WINDOW])
    today = season.fetched_at.date()
    day = forecast_history.baseline_day(today, days)
    if day is None:
        return ui.empty("Forecasts are recorded every morning. Movers appear from the "
                        "second day.", icon="bi-calendar-plus"), ""

    then = forecast_history.predictions_on(day)
    frame = frame.assign(then=frame["code"].map(then)).dropna(subset=["then"])
    frame["change"] = frame["pred"] - frame["then"]
    ups = frame[frame["change"] >= MOVER_FLOOR].nlargest(MOVERS_EACH, "change")
    downs = frame[frame["change"] <= -MOVER_FLOOR].nsmallest(MOVERS_EACH, "change")

    since = f"{day.day} {day:%b}"
    note = (f"Whose {config.season_label(TARGET)} forecast has moved most since the morning "
            f"of {since}. Forecasts move most after a gameweek, as points and minutes come "
            "in, and a little with each price change.")
    if ups.empty and downs.empty:
        return ui.empty(f"No forecast has moved by £0.01m or more since {since}. Expect movement "
                        "after the next gameweek.", icon="bi-pause-circle"), note
    return [
        _movers_side("Forecast up", "bi-graph-up-arrow", ups, f"No forecast up since {since}."),
        _movers_side("Forecast down", "bi-graph-down-arrow", downs,
                     f"No forecast down since {since}."),
    ], note


def _fold(text: str) -> str:
    """Case- and accent-insensitive, so "joao" finds João and "gross" Groß."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return text.lower().replace("ß", "ss")


def _filtered(frame: pd.DataFrame, search, positions, clubs) -> pd.DataFrame:
    if search:
        needle = _fold(search).replace("ss", "s")
        names = frame["web_name"].map(lambda n: _fold(n).replace("ss", "s"))
        frame = frame[names.str.contains(needle, regex=False)]
    if positions:
        frame = frame[frame["element_type"].isin(positions)]
    if clubs:
        frame = frame[frame["team_name"].isin(clubs)]
    return frame


@callback(
    Output("board-list", "children"),
    Output("board-count", "children"),
    Output("board-more-wrap", "hidden"),
    Input("board-data", "data"),
    Input("board-search", "value"),
    Input("board-pos", "value"),
    Input("board-clubs", "value"),
    Input("board-sort", "data"),
    Input("board-xref", "value"),
    Input("board-more", "n_clicks"),
)
def transfer_list(data, search, positions, clubs, sort, xref, more):
    frame = _frame(data)
    if frame.empty:
        return ui.empty("Waiting for the live data.", icon="bi-hourglass-split"), "", True
    frame = _filtered(_with_delta(frame, xref), search, positions, clubs)

    sort = sort or DEFAULT_SORT
    column, _numeric = _COLUMN.get(sort["col"], _COLUMN["move"])
    frame = frame.assign(name_key=frame["web_name"].map(_fold))
    # Ties fall back to the predicted move, so equal points or minutes still
    # come out in a meaningful order rather than whatever order they arrived.
    frame = frame.sort_values([column, "delta"], ascending=[not sort["desc"], False],
                              na_position="last")

    limit = PAGE_SIZE * (1 + (more or 0))
    shown = frame.head(limit)
    if shown.empty:
        return ui.empty("No players match these filters."), "No players match.", True

    now_label = "Today" if xref != "start_cost" else "August"
    labels = {"player": "Player", "points": "Pts", "minutes": "Mins", "selected": "Sel.",
              "ref": now_label, "pred": config.season_label(TARGET), "move": "Move"}
    header = html.Div([_sort_header(key, labels[key], sort) for key, _, _ in COLUMNS],
                      className="tlist-head")
    rows = [
        _pick_button(
            r, "list",
            [
                html.Span([ui.shirt(r.team_name, size="sm"),
                           html.Span([html.Span(r.web_name, className="tl-name"),
                                      html.Span([ui.position_pill(r.element_type),
                                                 html.Span(r.team_name, className="tl-club")],
                                                className="tl-sub")],
                                     className="tl-who")],
                          className="tl-player"),
                html.Span(f"{int(r.points_now or 0)}", className="num tl-stat"),
                html.Span(f"{int(r.minutes_now or 0):,}", className="num tl-stat"),
                html.Span(f"{float(r.selected_by_percent or 0):.1f}%", className="num tl-stat"),
                html.Span(theme.money(r.ref), className="num tl-now"),
                html.Span(theme.money(r.pred), className="num tl-pred"),
                html.Span(ui.delta_chip(r.delta, size="sm"), className="num"),
            ],
            "tl-row",
        )
        for r in shown.itertuples()
    ]
    count = f"Showing {len(shown)} of {len(frame)} players"
    return [header, *rows], count, len(shown) >= len(frame)


def _sort_header(key: str, label: str, sort: dict) -> html.Button:
    """A column header you can click to sort by, showing which way it runs."""
    active = sort["col"] == key
    icon = ("bi-caret-down-fill" if sort["desc"] else "bi-caret-up-fill") if active else "bi-chevron-expand"
    return html.Button(
        [label, html.I(className=f"bi {icon}")],
        id={"type": "sort-col", "col": key}, n_clicks=0, type="button",
        className=f"sort-col{' num' if key != 'player' else ''}{' is-active' if active else ''}",
        title=f"Sort by {label}",
    )


@callback(
    Output("board-sort", "data"),
    Input({"type": "sort-col", "col": ALL}, "n_clicks"),
    State("board-sort", "data"),
    prevent_initial_call=True,
)
def sort_by(_clicks, sort):
    """Same header again reverses the order; a new one starts at its natural end."""
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update
    sort = sort or DEFAULT_SORT
    key = trigger["col"]
    if key == sort["col"]:
        return {"col": key, "desc": not sort["desc"]}
    return {"col": key, "desc": _COLUMN[key][1]}


@callback(
    Output("board-map", "figure"),
    Output("board-map-note", "children"),
    Input("board-data", "data"),
    Input("board-search", "value"),
    Input("board-pos", "value"),
    Input("board-clubs", "value"),
    Input("board-xref", "value"),
)
def market_map(data, search, positions, clubs, xref):
    frame = _frame(data)
    empty = pd.DataFrame(columns=["price_now", "start_cost", "pred", "web_name",
                                  "team_name", "element_type", "code"])
    if frame.empty:
        return charts.price_scatter(empty, TARGET, xref), ""
    shown = _filtered(frame, search, positions, clubs)
    against = REFERENCE_WORDS.get(xref, "today's price")
    note = (f"Every player in the list, {against} against the {config.season_label(TARGET)} "
            "prediction. Above the dashed line the model wants him dearer, below it cheaper; "
            "the further from the line, the bigger the call. Click a mark to open the player.")
    return charts.price_scatter(shown, TARGET, xref), note


@callback(
    Output("board-selected", "data"),
    Input({"type": "pick", "code": ALL, "from": ALL}, "n_clicks"),
    Input("board-map", "clickData"),
    prevent_initial_call=True,
)
def select(_clicks, click_data):
    """A shirt, a list row or a map mark: all open the same card."""
    trigger = ctx.triggered_id
    if trigger == "board-map":
        if not click_data:
            return no_update
        point = click_data["points"][0]
        custom = point.get("customdata")
        return {"code": int(custom[3]), "at": time.time()} if custom else no_update
    if isinstance(trigger, dict) and ctx.triggered and ctx.triggered[0]["value"]:
        # Stamped, so picking the same player again after closing his card
        # still changes the store and reopens it.
        return {"code": trigger["code"], "at": time.time()}
    return no_update


# ---------------------------------------------------------------- player card


def _player_seasons(record: dict) -> pd.DataFrame:
    """This player's completed seasons, plus the one in progress.

    The cached history carries the season in progress too, but from the
    GitHub mirror, which lags -- it had one player finishing on £15.5m while
    the live table already said £15.6m. So the in-progress row is rebuilt
    from the record the page is holding, which came from the API minutes ago.
    """
    code = record.get("code")
    past = pd.DataFrame(columns=["season", "start_cost", "final_cost"])
    if code in _history.index:
        rows = _history.loc[[code]]
        past = rows[rows["season"] < SEASON][["season", "start_cost", "final_cost"]]
    now = pd.DataFrame([{"season": SEASON, "start_cost": record.get("start_cost"),
                         "final_cost": record.get("price_now")}])
    return pd.concat([past, now], ignore_index=True)


def _trend_days(record: dict, interval: pd.DataFrame) -> pd.DataFrame:
    """This player's recorded mornings, with today taken from the live card.

    Today comes from the frame the card is drawn from rather than from the
    history file, so the trend always ends on the number shown above it.
    """
    season = live.get_live_season()
    today = season.fetched_at.date() if season.is_live else None
    past = forecast_history.player(record["code"], before=today).rename(columns={
        "pred_next_start": "pred", "pred_next_lower": "lower", "pred_next_upper": "upper"})
    columns = ["date", "gameweeks_finished", "price", "pred", "lower", "upper"]
    past = past[columns]
    if today is None:
        return past
    now = pd.DataFrame([{
        "date": today, "gameweeks_finished": season.progress.gameweeks_finished,
        "price": record.get("price_now"), "pred": float(interval["pred"].iloc[0]),
        "lower": float(interval["pred_lower"].iloc[0]),
        "upper": float(interval["pred_upper"].iloc[0]),
    }])
    return pd.concat([past, now], ignore_index=True) if not past.empty else now


@callback(
    Output("board-card-body", "children"),
    Output("board-card", "is_open"),
    Output("board-deeplink", "data"),
    Input("board-selected", "data"),
    Input("board-xref", "value"),
    Input("board-data", "data"),
    State("board-deeplink", "data"),
    State("board-card", "is_open"),
)
def card(selected, xref, data, deeplink, is_open):
    """Open (or refresh) the player card.

    New data or a new reference price redraws a card that is already open;
    it never pops one open by itself, except once for a ``?player=`` link.
    """
    trigger = ctx.triggered_id
    code = (selected or {}).get("code")
    if not data:
        return no_update, no_update, no_update
    if trigger == "board-data" and deeplink is not None and not is_open:
        code = deeplink
    elif trigger in ("board-data", "board-xref") and not is_open:
        return no_update, no_update, no_update
    if code is None:
        return no_update, no_update, no_update

    record = next((r for r in data if int(r["code"]) == int(code)), None)
    if record is None:
        return ui.empty("That player is no longer in the live data."), True, None

    values = {name: record.get(name) for name in schema.NUMERIC_NAMES}
    values[schema.POSITION_FIELD] = record.get(schema.POSITION_FIELD)
    values[schema.TEAM_FIELD] = record.get(schema.TEAM_FIELD)
    interval, _ = form.predict(values)

    xref = xref if xref in charts.X_FIELDS else charts.DEFAULT_X
    reference = float(record.get(xref))
    words = REFERENCE_WORDS[xref]
    short = "Today" if xref == "price_now" else "August"

    games = float(record.get("games_played") or 0)
    projected_note = html.P(
        f"Projected from {games:g} gameweeks to a full 38: "
        f"{form._fmt(record.get('total_points'))} points and "
        f"{form._fmt(record.get('minutes'))} minutes.",
        className="fine",
    )

    return [
        ui.player_header(
            record["web_name"], record.get("team_name"), record.get("element_type"),
            meta=ui.stat_strip([
                ("Points", f"{int(record.get('points_now') or 0)}"),
                ("Minutes", f"{int(record.get('minutes_now') or 0):,}"),
                ("Selected", f"{float(record.get('selected_by_percent') or 0):.1f}%"),
                ("Gameweeks", f"{float(record.get('games_played') or 0):g}"),
            ]),
        ),
        ui.answer(interval, reference, words, short,
                  f"Predicted {config.season_label(TARGET)} price", extra=projected_note),
        ui.why_this_price(values, reference=(short, reference)),
        ui.forecast_trend(_trend_days(record, interval), TARGET),
        ui.price_history(_player_seasons(record), TARGET, float(interval["pred"].iloc[0]),
                         f"The {config.season_label(SEASON)} season is still running, so its "
                         "end price is today's."),
    ], True, None
