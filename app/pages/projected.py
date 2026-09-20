"""Current players, projected to a full season, priced for the year after.

Reads the live FPL API rather than the cached CSV, so the table reflects
today's prices and points. Each player's part-season is extended to 38
gameweeks (see :mod:`projection` for why that is not a simple
multiplication), and the model prices the season after next.

Each player is divided by his own club's fixtures played rather than by a
league-wide gameweek number, because mid-gameweek those differ: half the
division can be a match ahead of the other half for most of a weekend.

Early in the campaign this page is closer to a prior than a forecast, and
says so. The warning fades as the shrinkage weight rises.

The club filter scopes the chart *and* the table beneath it. Filtering one
and not the other is how a page ends up showing three marks above a
six-hundred-row table and inviting the reader to reconcile them.
"""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, State, callback, dash_table, dcc, html

import charts
import config
import form
import live
import model_store
import projection
import schema

dash.register_page(__name__, path="/projected", name="Projected season",
                   title="Projected · Price Prediction")

PAGE = "projected"

_meta = model_store.get_meta()
_previous = model_store.get_scores()
_history = model_store.get_price_history()

#: Shape-only frame for the first render, before the API has answered. The
#: figure needs the same columns whether or not there are rows to put in it.
_EMPTY_SCATTER = pd.DataFrame(
    columns=["price_now", "start_cost", "pred", "web_name", "team_name",
             "element_type"]
)

TABLE_COLUMNS = [
    {"name": "Player", "id": "web_name"},
    {"name": "Team", "id": "team_name"},
    {"name": "Pos", "id": "element_type"},
    {"name": "Start price", "id": "start_cost", "type": "numeric",
     "format": {"specifier": ".1f"}},
    {"name": "Price now", "id": "price_now", "type": "numeric",
     "format": {"specifier": ".1f"}},
    {"name": "GWs", "id": "games_played", "type": "numeric",
     "format": {"specifier": ".1f"}},
    {"name": "Pts so far", "id": "points_now", "type": "numeric"},
    {"name": "Proj pts", "id": "total_points", "type": "numeric",
     "format": {"specifier": ".0f"}},
    {"name": "Proj mins", "id": "minutes", "type": "numeric",
     "format": {"specifier": ".0f"}},
    {"name": "Pred price", "id": "pred", "type": "numeric",
     "format": {"specifier": ".2f"}},
    {"name": "Change", "id": "price_change", "type": "numeric",
     "format": {"specifier": "+.2f"}},
]


def layout() -> html.Div:
    season = _meta["predict_season"]
    target = season + 1
    return dbc.Container(
        [
            html.H4("Project the current season forward", className="mb-1"),
            html.P(
                f"Live {season}-{(season + 1) % 100:02d} form extended to a full 38 "
                f"gameweeks, then priced for {target}-{(target + 1) % 100:02d}.",
                className="text-muted",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Label("Gameweeks played", size="sm",
                                      className="fw-semibold mb-1"),
                            dbc.Input(id="proj-gw", type="number", min=0.5, max=38,
                                      step=0.5, size="sm", value=None,
                                      placeholder="auto"),
                            html.Small("Blank uses each club's own fixtures "
                                       "played. Set a number to override.",
                                       className="text-muted",
                                       style={"fontSize": "0.7rem"}),
                        ],
                        md=2, sm=4,
                    ),
                    dbc.Col(
                        [
                            dbc.Label("Projection mode", size="sm",
                                      className="fw-semibold mb-1"),
                            dcc.Dropdown(
                                id="proj-mode",
                                options=[{"label": label, "value": key}
                                         for key, label in projection.MODES.items()],
                                value="shrunk", clearable=False,
                            ),
                        ],
                        md=3, sm=8,
                    ),
                    dbc.Col(
                        [
                            dbc.Label("Shrinkage k", size="sm",
                                      className="fw-semibold mb-1"),
                            dbc.Input(id="proj-k", type="number", min=0, max=38,
                                      step=1, value=projection.DEFAULT_K, size="sm"),
                            html.Small("Gameweeks at which this season and last "
                                       "are trusted equally.",
                                       className="text-muted",
                                       style={"fontSize": "0.7rem"}),
                        ],
                        md=2, sm=4,
                    ),
                    dbc.Col(
                        [
                            dbc.Label("Clubs", size="sm",
                                      className="fw-semibold mb-1"),
                            dcc.Dropdown(
                                id="proj-clubs",
                                options=[],
                                value=[],
                                multi=True,
                                placeholder="All clubs",
                                className="proj-clubs",
                            ),
                            html.Small("Scopes the chart and the table. Empty "
                                       "means every club.",
                                       className="text-muted",
                                       style={"fontSize": "0.7rem"}),
                        ],
                        md=3, sm=8,
                    ),
                    dbc.Col(
                        dbc.Button("Refresh from API", id="proj-refresh",
                                   color="primary", outline=True, size="sm",
                                   className="mt-4"),
                        md=2, sm=4,
                    ),
                ],
                className="g-3 mb-3 align-items-start",
            ),
            html.Div(id="proj-status", className="mb-3"),
            html.Div(id="proj-banner", className="mb-3"),
            dbc.Card(
                dbc.CardBody(
                    [
                        html.Div(
                            [
                                html.H6("Repricing, by position",
                                        className="mb-0"),
                                dbc.RadioItems(
                                    id="proj-xaxis",
                                    options=[{"label": label, "value": key}
                                             for key, label in charts.X_FIELDS.items()],
                                    value=charts.DEFAULT_X,
                                    inline=True,
                                    className="proj-xaxis small",
                                ),
                            ],
                            className="d-flex justify-content-between "
                                      "align-items-center flex-wrap gap-2",
                        ),
                        html.Small(
                            "Above the dashed line the model wants a higher "
                            "price than today's, below it a lower one; distance "
                            "from the line is the size of the call.",
                            className="text-muted d-block",
                        ),
                        html.Small(id="proj-scatter-note",
                                   className="text-muted d-block mt-1"),
                        dcc.Loading(
                            dcc.Graph(
                                id="proj-scatter",
                                config={"displayModeBar": False,
                                        "responsive": True},
                                style={"height": "440px"},
                            ),
                        ),
                    ],
                    className="pb-2",
                ),
                className="shadow-sm mb-3",
            ),
            dcc.Loading(
                dash_table.DataTable(
                    id="proj-table",
                    columns=TABLE_COLUMNS,
                    page_size=15,
                    sort_action="native",
                    filter_action="native",
                    row_selectable="single",
                    style_table={"overflowX": "auto"},
                    style_cell={"fontSize": "0.82rem", "padding": "6px 10px",
                                "fontFamily": "system-ui, sans-serif"},
                    style_header={"fontWeight": "600", "backgroundColor": "#f8f9fa"},
                    style_data_conditional=[
                        {"if": {"filter_query": "{price_change} > 0.15",
                                "column_id": "price_change"},
                         "color": "#198754", "fontWeight": "600"},
                        {"if": {"filter_query": "{price_change} < -0.15",
                                "column_id": "price_change"},
                         "color": "#dc3545", "fontWeight": "600"},
                    ],
                ),
            ),
            html.Hr(className="my-4"),
            html.Div(id="proj-detail"),
            dcc.Store(id="proj-store"),
        ],
        fluid=True,
        className="py-4",
    )


@callback(
    Output("proj-store", "data"),
    Output("proj-status", "children"),
    Output("proj-clubs", "options"),
    Input("proj-refresh", "n_clicks"),
)
def fetch(n_clicks):
    """Pull the live table, or fall back to the cached snapshot.

    The frame itself stays in :mod:`live`'s cache rather than travelling
    through the store -- a JSON round-trip would cost a megabyte per
    callback and silently drop the categorical dtype on ``element_type``.
    The store carries only a token that changes when the data does, which
    is enough to retrigger the table.
    """
    season = live.get_live_season(force_refresh=bool(n_clicks))

    status = dbc.Alert(
        [
            html.Span(season.source_label, className="fw-semibold"),
            html.Span(f" · {len(season.players)} players", className="text-muted"),
        ],
        color="light" if season.is_live else "warning",
        className="py-2 mb-0 small border",
    )

    clubs = sorted(season.players["team_name"].dropna().unique())

    return season.fetched_at, status, clubs


@callback(
    Output("proj-table", "data"),
    Output("proj-banner", "children"),
    Output("proj-scatter", "figure"),
    Output("proj-scatter-note", "children"),
    Input("proj-store", "data"),
    Input("proj-gw", "value"),
    Input("proj-mode", "value"),
    Input("proj-k", "value"),
    Input("proj-clubs", "value"),
    Input("proj-xaxis", "value"),
)
def build_table(token, override, mode, k, clubs, x_field):
    """Price every current player on a projected full season.

    ``override`` forces one games-played figure on the whole league, for
    asking "what would these players be worth on a full season's form?".
    Left blank -- the normal case -- each club is divided by its own
    fixtures played, so a Sunday kickoff is not scaled as though it were a
    week behind the Saturday games.

    ``clubs`` narrows what is *displayed*, never what is computed. The
    projection runs on the whole league first, because the priors, the
    league-average denominator behind the transfer fields and the clamping
    counts are all league-wide quantities -- projecting Arsenal alone would
    quietly give Arsenal a different denominator.
    """
    if token is None:
        empty = charts.price_scatter(_EMPTY_SCATTER, _meta["predict_season"] + 1,
                                     x_field)
        return [], None, empty, ""

    season = live.get_live_season()
    current = season.players
    k = float(k if k is not None else projection.DEFAULT_K)

    if override:
        games = float(override)
        league = float(override)
    else:
        games = season.player_games
        league = season.progress.league_games

    projected = projection.project_frame(
        current, _previous, games, _meta["ranges"], mode, k, league_games=league
    )

    fitted = model_store.get_model()
    design_input = projected[schema.MODEL_INPUT_COLUMNS]
    projected["pred"] = fitted.predict(design_input).round(2)

    lookup = current.set_index("code")
    projected["team_name"] = projected["code"].map(lookup["team_name"])
    projected["element_type"] = projected["code"].map(lookup["element_type"])
    projected["points_now"] = projected["code"].map(lookup["total_points"])
    # Today's price, as distinct from what the player cost in August. The
    # scatter plots this one; the table shows both.
    projected["price_now"] = projected["code"].map(lookup["final_cost"])
    projected["price_change"] = (projected["pred"] - projected["start_cost"]).round(2)

    banner = _banner(mode, k, projected, bool(override))

    # Filter last: everything above needed the whole league.
    shown = projected
    if clubs:
        shown = projected[projected["team_name"].isin(clubs)]

    table = shown.sort_values("pred", ascending=False)
    figure = charts.price_scatter(shown, _meta["predict_season"] + 1, x_field)

    return (table.to_dict("records"), banner, figure,
            _scatter_note(len(shown), len(projected), clubs))


def _scatter_note(shown: int, total: int, clubs):
    """Say what slice is on screen, and warn when it is empty."""
    if not clubs:
        return f"All {total} current players."
    if not shown:
        return "No players at the selected club(s)."

    names = ", ".join(sorted(clubs))
    return f"{shown} of {total} players · {names}"


def _banner(mode: str, k: float, projected: pd.DataFrame, overridden: bool):
    """Say plainly how much of this is evidence and how much is prior."""
    clamped = int((projected["n_clamped"] > 0).sum())

    games = projected["games_played"]
    low, high = float(games.min()), float(games.max())
    average = float(games.mean())
    gw_text = f"{average:g}" if low == high else f"{low:g}–{high:g}"

    split = None
    if not overridden and high - low > 0.01:
        behind = int((games < high - 0.01).sum())
        split = (
            f" Gameweek {high:g} is in progress: {behind} of {len(games)} players "
            f"are at clubs that have not played it yet, and are divided by "
            f"{low:g} games rather than {high:g}."
        )

    if mode == "naive":
        return dbc.Alert(
            [
                html.Strong("Naive projection. "),
                f"Stats are multiplied by {projection.TOTAL_GAMEWEEKS}/{gw_text} "
                f"with no shrinkage, which pushes {clamped} players past the range "
                "the model was fitted on — their values are clamped to that range "
                "rather than extrapolated.",
                split or "",
            ],
            color="danger", className="py-2 mb-0 small",
        )

    if mode == "asis":
        return dbc.Alert(
            [
                html.Strong("No projection. "),
                f"Players are priced on {gw_text} gameweeks of raw totals, as if "
                "the season had already ended. Useful as a baseline, not as a "
                "forecast — and while a gameweek is in progress it is not even a "
                "level baseline, since some clubs have played it and some have not.",
            ],
            color="secondary", className="py-2 mb-0 small",
        )

    weight = projection.shrinkage_weight(average, k)
    colour = "warning" if weight < 0.5 else "light"
    return dbc.Alert(
        [
            html.Strong(f"{weight:.0%} this season, {1 - weight:.0%} last season. "),
            f"After {gw_text} gameweeks the projection still leans on last "
            f"season's form; it shifts toward current form as the season runs. "
            f"{clamped} player(s) clamped to the fitted range.",
            split or "",
        ],
        color=colour, className="py-2 mb-0 small border",
    )


def _player_seasons(record: dict) -> pd.DataFrame:
    """This player's completed seasons, plus the one in progress.

    The cached history carries the season in progress too, but from the
    GitHub mirror, which lags -- it had this player finishing on £15.5m
    while the live table already said £15.6m. So the in-progress row is
    dropped and rebuilt from the record the page is already holding, which
    came from the API minutes ago.
    """
    current = _meta["predict_season"]
    code = record.get("code")

    past = pd.DataFrame(columns=["season", "start_cost", "final_cost"])
    if code in _history.index:
        rows = _history.loc[[code]]
        past = rows[rows["season"] < current][["season", "start_cost", "final_cost"]]

    live = pd.DataFrame([{
        "season": current,
        "start_cost": record.get("start_cost"),
        "final_cost": record.get("price_now"),
    }])

    return pd.concat([past, live], ignore_index=True)


def _price_history_card(record: dict, interval: pd.DataFrame):
    """The small price-history chart that sits under the derived panel."""
    seasons = _player_seasons(record)
    target = _meta["predict_season"] + 1
    predicted = float(interval["pred"].iloc[0])

    return dbc.Card(
        dbc.CardBody(
            [
                html.Div("Price history", className="fw-semibold mb-1"),
                dcc.Graph(
                    figure=charts.price_history_bars(seasons, target, predicted),
                    config={"displayModeBar": False, "responsive": True},
                    style={"height": "240px"},
                ),
                html.Small(
                    f"The {config.season_label(_meta['predict_season'])} season is "
                    "still running, so its final price is today's.",
                    className="text-muted d-block",
                    style={"fontSize": "0.68rem"},
                ),
            ],
            className="pb-2",
        ),
        className="shadow-sm",
    )


@callback(
    Output("proj-detail", "children"),
    Input("proj-table", "selected_rows"),
    Input("proj-xaxis", "value"),
    State("proj-table", "data"),
)
def detail(selected_rows, x_field, rows):
    """Break down one projected player the way the other pages do.

    ``proj-xaxis`` is an Input rather than State so the breakdown's
    reference line follows the scatter's: flipping the axis above and
    leaving the line below it pointing at the other price is the kind of
    quiet disagreement this page has already been bitten by once.
    """
    if not selected_rows or not rows:
        return html.Div(
            "Select a player above to see their projected inputs and a breakdown "
            "of the predicted price.",
            className="text-muted small",
        )

    record = rows[selected_rows[0]]
    values = {name: record.get(name) for name in schema.NUMERIC_NAMES}
    values[schema.POSITION_FIELD] = record.get(schema.POSITION_FIELD)
    values[schema.TEAM_FIELD] = record.get(schema.TEAM_FIELD)

    interval, row = form.predict(values)
    target = _meta["predict_season"] + 1

    # Whichever price the scatter is measuring against, measured against
    # here too.
    reference = (
        (charts.X_FIELDS.get(x_field or charts.DEFAULT_X, "Price today").split(" (")[0],
         record.get(x_field if x_field in charts.X_FIELDS else charts.DEFAULT_X))
    )

    # The breakdown sits on its own full-width row rather than in a column
    # beside the result card: it now carries a sixteen-bar waterfall, and
    # nesting that inside seven twelfths of seven twelfths leaves the bars
    # too narrow to label.
    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.H5(f"{record['web_name']} — {record.get('team_name')}, "
                                    f"{record.get('element_type')}", className="mb-3"),
                            form.result_card(
                                interval, record.get("start_cost"),
                                subtitle=f"Predicted {target}-{(target + 1) % 100:02d} "
                                         f"start price",
                            ),
                        ],
                        lg=5,
                    ),
                    dbc.Col(
                        [
                            form.derived_panel(row),
                            html.Div(_price_history_card(record, interval),
                                     className="mt-3"),
                        ],
                        lg=7,
                    ),
                ],
                className="g-3",
            ),
            dbc.Card(
                dbc.CardBody(form.contribution_table(values, reference=reference)),
                className="shadow-sm mt-3",
            ),
        ]
    )
