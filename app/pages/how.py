"""How it works: the served model, written out.

The app's version of §11 of ``explore/model_report.py``. Every weight is read
from the served model itself (``model_store.get_model()``), so the equation
on this page is the one pricing players.
"""

from __future__ import annotations

import dash
import numpy as np
from dash import html

import charts
import config
import model_store
import theme
import ui

dash.register_page(__name__, path="/how-it-works", name="How it works", order=2,
                   title="How it works · FPL Price Prediction")

_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")

#: Numeric terms in the equation, by the name a reader sees in the formula.
_VAR_NAMES = {
    "start_cost": "start", "final_cost": "end",
    "start_cost_sq": "start²", "final_cost_sq": "end²",
    "total_points": "points", "minutes": "minutes", "goals_scored": "goals",
    "assists": "assists", "points_per_game": "ppg", "value_season": "value",
    "selected_by_percent": "selected", "no_mins": "never_played",
}


def _p(*children, cls: str = "prose") -> html.P:
    return html.P(list(children), className=cls)


def _coef(value: float) -> str:
    """Four significant figures, never in scientific notation."""
    return np.format_float_positional(abs(value), precision=4, unique=False,
                                      fractional=False, trim="-")


def _equations(params, numeric: list[str]) -> list:
    lhs = html.Span([html.Var("next start price"), " ="], className="eq-lhs")
    symbolic, filled = [html.Span("β₀", className="eq-term")], [
        html.Span(_coef(params["const"]), className="eq-term")]
    for i, column in enumerate(numeric, start=1):
        name = html.Var(_VAR_NAMES.get(column, column))
        symbolic.append(html.Span([" + ", f"β{str(i).translate(_SUB)}", " · ", name],
                                  className="eq-term"))
        filled.append(html.Span([" − " if params[column] < 0 else " + ",
                                 _coef(params[column]), " · ", name], className="eq-term"))
    symbolic.append(html.Span([" + β", html.Sub("position"), " + β", html.Sub("club")],
                              className="eq-term"))
    filled.append(html.Span([" + ", html.Var("position adjustment"), " + ",
                             html.Var("club adjustment")], className="eq-term"))
    return [
        html.H3("In symbols", className="step-title"),
        _p("One weight (β) per input, plus a position and a club adjustment.", cls="fine"),
        html.Div([lhs, *symbolic], className="equation"),
        html.H3("With its fitted weights", className="step-title"),
        _p("Rounded to four significant figures; the app computes with the full ones.",
           cls="fine"),
        html.Div([lhs, *filled], className="equation"),
    ]


def _adjustments(fitted, params) -> html.Div:
    positions = [("GK", 0.0)] + [(c.split("_")[-1], params[c]) for c in fitted.columns
                                 if c.startswith("element_type_")]
    clubs = sorted(((c[len("team_name_"):].replace("_", " "), params[c]) for c in fitted.columns
                    if c.startswith("team_name_")), key=lambda kv: -kv[1])
    clubs.append(("Every other club", 0.0))

    def chip(label, value, reference):
        return html.Div([html.Span(label, className="adj-label"),
                         html.Span("0 (reference)" if reference else
                                   theme.money(value, signed=True, places=3),
                                   className="adj-value")], className="adj")

    return html.Div(
        [
            html.Div([html.H3("Position adjustment", className="step-title"),
                      html.Div([chip(p, v, p == "GK") for p, v in positions],
                               className="adj-grid")]),
            html.Div([html.H3("Club adjustment", className="step-title"),
                      html.Div([chip(c, v, c == "Every other club") for c, v in clubs],
                               className="adj-grid adj-clubs")]),
        ],
        className="adj-row",
    )


def _reading(params, numeric: list[str]) -> html.Div:
    """How to read the fitted weights, in a manager's units."""
    bend = params["start_cost_sq"] + params["final_cost_sq"]
    linear = params["start_cost"] + params["final_cost"]
    negative = [_VAR_NAMES.get(c, c) for c in numeric if params[c] < 0]
    items = [
        html.Li(f"Each goal adds {theme.money(params['goals_scored'], signed=True, places=3)} "
                f"and each assist {theme.money(params['assists'], signed=True, places=3)} to "
                "next season's price; each 1% of ownership adds "
                f"{theme.money(params['selected_by_percent'], signed=True, places=3)}."),
        html.Li(f"Minutes carry {theme.money(params['minutes'] * 90, signed=True, places=4)} "
                "per 90 played: with points, goals and ppg held fixed, more minutes means "
                "those returns came less efficiently."),
        html.Li(f"start² and end² together add {bend:+.4f} × price². That is the bend: a £1 "
                f"price difference carries about £{linear + 2 * bend * 4:.2f} at £4m and "
                f"£{linear + 2 * bend * 12:.2f} at £12m, because FPL props cheap players "
                "against a floor and keeps its stars expensive."),
    ]
    if negative:
        items.append(html.Li(f"Negative weights ({', '.join(negative)}) look odd alone "
                             "because the inputs overlap heavily; their combined effect is "
                             "what the model means. The breakdown on every player card shows "
                             "those combined effects for one player."))
    return html.Div([html.Strong("Read the weights in FPL units, and read the four price "
                                 "terms together."), html.Ul(items)], className="prose note")


def layout() -> html.Div:
    meta = model_store.get_meta()
    fitted = model_store.get_model()
    params = fitted.result.params
    numeric = [c for c in fitted.columns if not c.startswith(("element_type_", "team_name_"))]
    legend = [html.Tr([html.Td(html.Var(_VAR_NAMES.get(c, c))),
                       html.Td(c, className="muted mono"), html.Td(charts.term_label(c))])
              for c in numeric]
    return html.Div(
        [
            html.Section(
                html.Div(
                    [
                        html.H1("How it works"),
                        html.P(f"The model is fitted on {meta['training_rows']:,} player-seasons "
                               f"({config.season_label(config.FIRST_SEASON)} to "
                               f"{config.season_label(meta['train_through'])}). Every price in "
                               "the app is this one line of arithmetic.",
                               className="lede"),
                    ],
                    className="wrap",
                ),
                className="hero hero-compact",
            ),
            html.Div(
                [
                    ui.section(
                        "The model, written out",
                        *_equations(params, numeric),
                        _p("Prices in £m, minutes in minutes, selected in percent; "
                           "never_played is 1 for a player with no minutes, else 0.",
                           cls="fine"),
                        _adjustments(fitted, params),
                        _p("What each adjustment adds to the price, against goalkeepers and "
                           f"against every other club. Clubs under "
                           f"{config.TEAM_LUMP_THRESHOLD:.0%} of training rows, and promoted "
                           "clubs the model has never seen, share the reference level.",
                           cls="fine"),
                        html.Details(
                            [html.Summary("What each name in the equation means"),
                             html.Table([html.Thead(html.Tr([html.Th("In the equation"),
                                                             html.Th("Column"),
                                                             html.Th("Meaning")])),
                                         html.Tbody(legend)], className="terms")],
                            className="details",
                        ),
                        _reading(params, numeric),
                        class_name="how-block",
                    ),
                ],
                className="wrap how inside",
            ),
        ],
    )
