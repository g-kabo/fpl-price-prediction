"""Rendering shared by every page: shirts, pills, price tags, the answer.

:mod:`form` owns the numbers -- assembling a row, predicting, decomposing a
prediction into its terms. This module only draws them, in the app's
transfer-market vocabulary, so every page shows a player the same way.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
import pandas as pd
from dash import dcc, html

import charts
import features
import form
import schema
import theme


# ---------------------------------------------------------------- atoms


def shirt(team: str | None, size: str = "md") -> html.Img:
    return html.Img(src=theme.shirt_uri(team), alt=f"{team or 'Unknown club'} shirt",
                    className=f"shirt shirt-{size}")


def position_pill(position: str | None) -> html.Span:
    position = position or "?"
    return html.Span(position, className=f"pos-pill pos-{position.lower()}")


_ICONS = {"rise": "bi-caret-up-fill", "fall": "bi-caret-down-fill", "hold": "bi-dash"}


def delta_chip(delta: float, size: str = "md") -> html.Span:
    """The predicted move, as a filled chip: +£0.6m, −£0.4m, or holds."""
    way = theme.direction(delta)
    text = "Holds" if way == "hold" else theme.money(delta, signed=True)
    return html.Span([html.I(className=f"bi {_ICONS[way]}"), text],
                     className=f"delta delta-{way} delta-{size}")


# ---------------------------------------------------------------- the answer


def range_bar(lower: float, upper: float, pred: float,
              reference: float | None, reference_label: str) -> html.Div:
    """The likely range drawn, with the prediction and today's price on it.

    The span is padded so a reference price just outside the range still
    lands on the bar rather than being pinned to its end, where it would
    read as sitting on the boundary.
    """
    points = [lower, upper, pred] + ([reference] if reference is not None else [])
    low, high = min(points), max(points)
    pad = max((high - low) * 0.12, 0.1)
    low, high = low - pad, high + pad

    def at(value: float) -> str:
        return f"{(value - low) / (high - low) * 100:.1f}%"

    marks = [
        html.Div(className="range-band",
                 style={"left": at(lower), "width": f"calc({at(upper)} - {at(lower)})"}),
        html.Div(className="range-pred", style={"left": at(pred)}),
    ]
    if reference is not None:
        marks.insert(1, html.Div(
            html.Span(f"{reference_label} {theme.money(reference)}", className="range-ref-label"),
            className="range-ref", style={"left": at(reference)},
        ))

    return html.Div(
        [
            html.Div(marks, className="range-track"),
            html.Div(
                [html.Span(theme.money(lower)),
                 html.Span("95% likely range", className="range-caption"),
                 html.Span(theme.money(upper))],
                className="range-ends",
            ),
        ],
        className="range",
    )


def verdict(delta: float, lower: float, upper: float,
            reference: float | None, against: str) -> str:
    """One plain sentence: which way, how far, and how sure.

    ``against`` is the reference as it reads mid-sentence: "today's price".
    """
    way = theme.direction(delta)
    if way == "rise":
        text = f"The model would price him {theme.money(abs(delta))} above {against}."
    elif way == "fall":
        text = f"The model would price him {theme.money(abs(delta))} below {against}."
    else:
        text = f"The model would keep him at about {against}."

    if reference is not None and way != "hold" and lower <= reference <= upper:
        text += f" Its likely range still includes {against}, so treat the call as soft."
    return text


def _interval(interval: pd.DataFrame) -> tuple[float, float, float]:
    return (float(interval["pred"].iloc[0]), float(interval["pred_lower"].iloc[0]),
            float(interval["pred_upper"].iloc[0]))


def answer_tag(interval: pd.DataFrame, reference: float | None, target_label: str) -> html.Div:
    """Next season's price as a price tag, with the move beside it."""
    pred, _, _ = _interval(interval)
    on_grid = round(pred / form.PRICE_GRID) * form.PRICE_GRID
    delta = pred - reference if reference is not None else 0.0
    return html.Div(
        [
            html.Div([html.Div(target_label, className="answer-label"),
                      html.Div(theme.money(on_grid), className="answer-price")],
                     className="tag"),
            delta_chip(delta, size="lg") if reference is not None else None,
        ],
        className="answer-head",
    )


def answer_body(interval: pd.DataFrame, reference: float | None, against: str,
                marker: str, extra=None) -> html.Div:
    """The likely range, drawn, and the verdict in one sentence."""
    pred, lower, upper = _interval(interval)
    delta = pred - reference if reference is not None else 0.0
    return html.Div(
        [range_bar(lower, upper, pred, reference, marker),
         html.P(verdict(delta, lower, upper, reference, against), className="answer-verdict"),
         extra],
        className="answer-body",
    )


def answer(interval: pd.DataFrame, reference: float | None, against: str,
           marker: str, target_label: str, extra=None) -> html.Div:
    """The headline: next season's price, the move, the range, the verdict."""
    return html.Div([answer_tag(interval, reference, target_label),
                     answer_body(interval, reference, against, marker, extra)],
                    className="answer")


def stat_strip(items: list[tuple[str, str]]) -> html.Div:
    """FPL's player-popup strip: a row of small labelled figures."""
    return html.Div([html.Div([html.Span(value, className="strip-value"),
                               html.Span(label, className="strip-label")],
                              className="strip-item") for label, value in items],
                    className="strip")


# ---------------------------------------------------------------- why this price


def _narrate(parts: dict) -> list:
    """The breakdown as a sentence, before anyone has to read a chart."""
    total = parts["total"]
    shown = parts["shown"]

    anchor = next((t for t in shown if t[0] == "start_cost"), None)
    movers = [t for t in shown if t[0] != "start_cost"]
    ups = [t for t in movers if t[3] > 0][:2]
    downs = [t for t in movers if t[3] < 0][:2]

    def named(terms):
        return ", ".join(f"{charts.term_label(c).lower()} ({theme.money(v, signed=True, places=2)})"
                         for c, _, _, v in terms)

    sentence = [f"Of {theme.money(total, places=2)}, "]
    if anchor:
        sentence += [html.Strong(theme.money(anchor[3], places=2)),
                     " comes straight from what he cost this season: prices are sticky. "]
    if ups:
        sentence += ["Pushing it up: ", named(ups), ". "]
    if downs:
        sentence += ["Pulling it down: ", named(downs), "."]
    return sentence


def why_this_price(values: dict, reference: tuple[str, float] | None) -> html.Div:
    """Narrated breakdown, the bars behind it, and the model's own units."""
    parts = form.contributions(values)
    return html.Div(
        [
            html.H3("Why this price", className="section-title"),
            html.P(_narrate(parts), className="why-lede"),
            dcc.Graph(
                figure=charts.contribution_bars(form.contribution_steps(parts), reference),
                config={"displayModeBar": False, "responsive": True},
                className="why-chart",
            ),
            html.P(
                "Each bar is one ingredient of the price, and they add up exactly: "
                "the model is linear, so nothing is approximated.",
                className="fine",
            ),
        ],
        className="why",
    )


#: Coefficients in a unit someone could picture. Per transfer or per
#: minute, most of these are too small to print without an exponent.
_UNITS = {
    "transfers_in": (100_000, "per 100k"),
    "transfers_out": (100_000, "per 100k"),
    "minutes": (90, "per 90 min"),
    "bps": (100, "per 100"),
    "total_points": (10, "per 10 pts"),
}


def _effect(column: str, beta: float) -> str:
    if column in features.RATE_FEATURES:
        # A per-minute rate times beta equals the per-90 rate times beta/90.
        return f"{theme.money(beta / schema.MINUTES_PER_MATCH, signed=True, places=3)} per 1.0 /90"
    scale, unit = _UNITS.get(column, (1, "each"))
    return f"{theme.money(beta * scale, signed=True, places=3)} {unit}"


def model_details(values: dict, row: pd.DataFrame) -> html.Details:
    """Everything a sceptic needs, folded away until asked for."""
    parts = form.contributions(values, top_n=40)

    rows = [html.Tr([html.Td("Model baseline"), html.Td(""), html.Td(""),
                     html.Td(theme.money(parts["intercept"], places=3), className="num")])]
    for column, value, beta, contribution in parts["shown"]:
        rows.append(html.Tr([
            html.Td(charts.term_label(column)),
            html.Td(form._fmt(value), className="num"),
            html.Td(_effect(column, beta), className="num muted"),
            html.Td(theme.money(contribution, signed=True, places=3),
                    className=f"num tone-{'rise' if contribution > 0 else 'fall'}"),
        ]))
    if parts["n_rest"]:
        rows.append(html.Tr([html.Td(f"{parts['n_rest']} negligible terms"), html.Td(""),
                             html.Td(""),
                             html.Td(theme.money(parts["rest"], signed=True, places=3),
                                     className="num")]))
    rows.append(html.Tr([html.Td("Predicted price"), html.Td(""), html.Td(""),
                         html.Td(theme.money(parts["total"], places=3), className="num")],
                        className="total-row"))

    return html.Details(
        [
            html.Summary("Model details: every term, in the model's own units"),
            derived_rates(row),
            html.Table(
                [html.Thead(html.Tr([html.Th("Term"), html.Th("Value", className="num"),
                                     html.Th("Effect", className="num"),
                                     html.Th("Adds", className="num")])),
                 html.Tbody(rows)],
                className="terms",
            ),
        ],
        className="details",
    )


def derived_rates(row: pd.DataFrame) -> html.Div:
    """The per-90 rates the model works out from the season's totals.

    Shown per 90 because a match is the unit anyone thinks in, with the
    per-minute figure the model actually multiplies kept beneath, so the
    two can be reconciled against the term table.
    """
    derived = features.add_rate_features(row)
    minutes = float(row["minutes"].iloc[0])
    derived[schema.MATCHES_FIELD] = minutes / schema.MINUTES_PER_MATCH

    cells = []
    for name in schema.DERIVED_FIELDS:
        value = float(derived[name].iloc[0])
        if name == "no_mins":
            text, sub = ("Yes" if value else "No"), ""
        elif name == schema.MATCHES_FIELD:
            text, sub = f"{value:.1f}", f"{minutes:,.0f} min"
        else:
            text, sub = f"{value * schema.MINUTES_PER_MATCH:.2f}", f"{value:.4f} per min"
        cells.append(html.Div([html.Div(schema.DERIVED_LABELS[name], className="rate-label"),
                               html.Div(text, className="rate-value"),
                               html.Div(sub, className="rate-sub")], className="rate"))

    return html.Div(
        [html.Div("Worked out by the model from the totals", className="rates-title"),
         html.Div(cells, className="rates")],
        className="rates-block",
    )


def out_of_range(values: dict, ranges: dict):
    """A quiet flag per field outside what the model has ever seen."""
    flags = []
    for name, label, _, _ in schema.NUMERIC_FIELDS:
        bounds = ranges.get(name)
        value = form._as_float(values.get(name))
        if bounds and (value < bounds["min"] or value > bounds["max"]):
            flags.append(html.Li(
                f"{label}: {form._fmt(value)} is outside anything in the training data "
                f"({form._fmt(bounds['min'])} to {form._fmt(bounds['max'])})."
            ))
    if not flags:
        return None
    return html.Div(
        [html.Div([html.I(className="bi bi-exclamation-triangle-fill"),
                   " Beyond what the model has seen"], className="flag-title"),
         html.Ul(flags),
         html.P("A linear model keeps answering past its data, but the answer is a guess.",
                className="fine")],
        className="flag",
    )


def price_history(seasons: pd.DataFrame, forecast_season: int, predicted: float,
                  note: str) -> html.Div:
    return html.Div(
        [
            html.H3("Price history", className="section-title"),
            dcc.Graph(figure=charts.price_history_bars(seasons, forecast_season, predicted),
                      config={"displayModeBar": False, "responsive": True},
                      className="history-chart"),
            html.P(note, className="fine"),
        ],
        className="history",
    )


def player_header(name: str, team: str | None, position: str | None, meta=None) -> html.Div:
    """Shirt, name plate, club and position: the top of a player card."""
    return html.Div(
        [
            shirt(team, size="lg"),
            html.Div(
                [html.H2(name, className="player-name"),
                 html.Div([position_pill(position), html.Span(team or "", className="player-club")],
                          className="player-sub"),
                 meta],
            ),
        ],
        className="player-header",
    )


def section(title: str, *children, class_name: str = "") -> html.Section:
    return html.Section([html.H2(title, className="block-title"), *children],
                        className=f"block {class_name}".strip())


def empty(message: str, icon: str = "bi-search") -> html.Div:
    return html.Div([html.I(className=f"bi {icon}"), html.P(message)], className="empty")


def dbc_button(label, id, icon=None, kind="ghost", **kwargs):
    content = [html.I(className=f"bi {icon}"), label] if icon else label
    return dbc.Button(content, id=id, className=f"btn-{kind}", color="link", **kwargs)
