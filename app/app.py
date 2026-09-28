"""Interactive front end for the FPL price model.

    python app/app.py        ->  http://127.0.0.1:8051

Three pages:

    /               Price Watch: live current-season form, projected to 38
                    gameweeks and priced for next season (was /projected)
    /lab            What if: a completed season, prefilled or blank, edited
                    by hand (was /player and /manual)
    /how-it-works   the method, and how accurate it has been

Runs on 8051 so it can sit alongside the FPL dashboard on 8050 rather than
fighting it for the port.
"""

from __future__ import annotations

import sys
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
from dash import html

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR.parent))

import model_store  # noqa: E402

PORT = 8051

FONTS = ("https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800"
         "&family=Barlow:wght@400;500;600;700&display=swap")

app = dash.Dash(
    __name__,
    use_pages=True,
    pages_folder=str(APP_DIR / "pages"),
    assets_folder=str(APP_DIR / "assets"),
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP, FONTS],
    suppress_callback_exceptions=True,
    title="FPL Price Prediction",
)


def _header() -> html.Header:
    """Brand and page links on the aubergine bar."""
    return html.Header(
        html.Div(
            [
                html.A(
                    [html.Span(html.I(className="bi bi-tag-fill"), className="brand-mark"),
                     html.Span(["FPL ", html.Strong("Price Prediction")])],
                    href="/", className="brand",
                ),
                dbc.Nav(
                    [
                        dbc.NavLink(page["name"], href=page["relative_path"],
                                    active="exact", className="nav-tab")
                        for page in dash.page_registry.values()
                    ],
                    className="nav-tabs-row",
                ),
            ],
            className="wrap header-inner",
        ),
        className="site-header",
    )


def _footer() -> html.Footer:
    meta = model_store.get_meta()
    return html.Footer(
        html.Div(
            [
                html.P(
                    f"Linear model · {meta['n_predictors']} predictors · trained on "
                    f"{meta['training_rows']:,} player-seasons · explains "
                    f"{meta['rsquared_adj']:.1%} of the variation in price (adjusted R²).",
                ),
                html.P(
                    [
                        "Data from the official FPL API and ",
                        html.A("vaastav/Fantasy-Premier-League",
                               href="https://github.com/vaastav/Fantasy-Premier-League",
                               target="_blank", rel="noopener"),
                        ". A fan project, not affiliated with the Premier League or "
                        "Fantasy Premier League.",
                    ],
                ),
            ],
            className="wrap",
        ),
        className="site-footer",
    )


app.layout = html.Div([_header(), html.Main(dash.page_container), _footer()],
                      className="app-shell")

server = app.server

if __name__ == "__main__":
    # Load the model before serving so a stale-artifact refit happens here,
    # with its progress visible, rather than inside the first callback.
    model_store.get_model()
    app.run(debug=True, port=PORT)
