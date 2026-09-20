"""Interactive front end for the FPL price model.

    python app/app.py        ->  http://127.0.0.1:8051

Three ways to ask the same model the same question:

    /            prefill from a completed season, then edit
    /manual      type a hypothetical season from scratch
    /projected   live current-season form, projected to 38 gameweeks

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

app = dash.Dash(
    __name__,
    use_pages=True,
    pages_folder=str(APP_DIR / "pages"),
    assets_folder=str(APP_DIR / "assets"),
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP],
    suppress_callback_exceptions=True,
    title="FPL Price Prediction",
)


def _navbar() -> dbc.Navbar:
    """Top bar: brand, page links, and what the model behind them is.

    ``dark=False`` is load-bearing. ``dbc.Navbar`` defaults to
    ``dark=True``, which styles its links for a dark background -- on a
    white bar that renders them white on white, i.e. invisible. (There is
    no matching ``light`` prop in dbc 2.x; the absence of ``dark`` is it.)
    """
    meta = model_store.get_meta()
    return dbc.Navbar(
        dbc.Container(
            [
                dbc.NavbarBrand(
                    [
                        html.I(className="bi bi-graph-up-arrow me-2"),
                        "FPL Price Prediction",
                    ],
                    href="/", className="fw-bold",
                ),
                dbc.Nav(
                    [
                        dbc.NavLink(page["name"], href=page["relative_path"],
                                    active="exact", className="nav-pill")
                        for page in dash.page_registry.values()
                    ],
                    navbar=True, pills=True, className="me-auto gap-1",
                ),
                html.Span(
                    f"OLS · {meta['n_predictors']} predictors · "
                    f"{meta['training_rows']:,} seasons · adj R² {meta['rsquared_adj']:.3f}",
                    className="navbar-text small d-none d-lg-inline model-stamp",
                ),
            ],
            fluid=True,
        ),
        color="white", dark=False,
        className="border-bottom shadow-sm mb-0 py-2", sticky="top",
    )


app.layout = html.Div([_navbar(), dash.page_container])

server = app.server

if __name__ == "__main__":
    # Load the model before serving so a stale-artifact refit happens here,
    # with its progress visible, rather than inside the first callback.
    model_store.get_model()
    app.run(debug=True, port=PORT)
