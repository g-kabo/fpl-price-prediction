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


#: Range bar geometry, in px: one line of labels, the track's height, and the
#: gap between the track and the first line of labels under it.
_ROW = 22
_TRACK = 14
_BELOW_GAP = 6

#: Labels closer than this (in % of the bar) would overlap, so the later
#: one moves to another line.
_CROWDED = 30.0


def _rows(positions: list[float]) -> list[int]:
    """A line for each label, in order: the nearest line it fits on."""
    placed: list[list[float]] = []
    rows = []
    for x in positions:
        row = next((i for i, line in enumerate(placed)
                    if all(abs(x - other) >= _CROWDED for other in line)), len(placed))
        if row == len(placed):
            placed.append([])
        placed[row].append(x)
        rows.append(row)
    return rows


def range_bar(lower: float, upper: float, pred: float,
              reference: float | None, reference_label: str,
              actual: float | None = None) -> html.Div:
    """The likely range drawn, with the prediction and the prices around it.

    Above the track: the prediction and, optionally, the reference price
    (start or today). Below it: the range's two ends and, optionally,
    ``actual``, the price FPL really set. That one is an outcome rather than
    an input, so it gets its own mark (a diamond) and its own side.

    The span is padded so a price just outside the range still lands on the
    bar rather than being pinned to its end, where it would read as sitting
    on the boundary. Labels take the nearest line they fit on, so a crowded
    bar grows taller instead of overprinting.
    """
    points = [lower, upper, pred] + [v for v in (reference, actual) if v is not None]
    low, high = min(points), max(points)
    pad = max((high - low) * 0.12, 0.1)
    low, high = low - pad, high + pad

    def pct(value: float) -> float:
        return (value - low) / (high - low) * 100

    # Above the track, the prediction first so it always takes the line
    # nearest the track, then the prices it is read against.
    above = [(["Predicted ", html.Strong(theme.money(pred))], pred, "rl-pred", None)]
    if reference is not None:
        above.append((f"{reference_label} {theme.money(reference)}", reference, "rl-ref",
                      "range-ref"))
    above_rows = _rows([pct(value) for _, value, _, _ in above])
    n_above = max(above_rows) + 1
    track_top = 30 + (n_above - 1) * _ROW

    # Below: the range's ends, or one combined label when the band is too
    # narrow to hold them apart; then FPL's actual price.
    if pct(upper) - pct(lower) < 18:
        below = [(f"{theme.money(lower)} – {theme.money(upper)}", (lower + upper) / 2, "", None)]
    else:
        below = [(theme.money(lower), lower, "", None), (theme.money(upper), upper, "", None)]
    if actual is not None:
        below.append((["FPL set ", html.Strong(theme.money(actual))], actual, "rl-actual",
                      "range-actual-tick"))
    below_rows = _rows([pct(value) for _, value, _, _ in below])
    n_below = max(below_rows) + 1

    # Every label sits at its own value on the one scale -- the range's
    # ends under the band's ends, not at the edges of the bar, which the
    # padding above places somewhere else entirely.
    def label(text, value, top: float, extra: str, below_track: bool = False):
        x = pct(value)
        anchor = "start" if x < 10 else "end" if x > 90 else "mid"
        kind = "rl-below" if below_track else "rl-above"
        return html.Span(text, className=f"rl {kind} rl-{anchor} {extra}".strip(),
                         style={"left": f"{x:.1f}%", "top": f"{top}px"})

    labels, marks = [], [
        html.Div(className="range-band",
                 style={"left": f"{pct(lower):.1f}%",
                        "width": f"{pct(upper) - pct(lower):.1f}%"}),
        html.Div(className="range-pred", style={"left": f"{pct(pred):.1f}%"}),
    ]
    for (text, value, extra, tick), row in zip(above, above_rows):
        # The nearest line clears the track by 30px, room for a tick to
        # reach up to the label without running through it.
        labels.append(label(text, value, track_top - 30 - row * _ROW, extra))
        if tick:
            # A tick rises from the track to its own label's line; one whose
            # label sits higher stops short, so it never cuts a label below.
            rise = 14 if row == 0 else 6
            marks.append(html.Div(className=tick, style={"left": f"{pct(value):.1f}%",
                                                         "top": f"-{rise}px"}))
    first_below = track_top + _TRACK + _BELOW_GAP
    for (text, value, extra, tick), row in zip(below, below_rows):
        labels.append(label(text, value, first_below + row * _ROW, extra, below_track=True))
        if tick:
            marks.append(html.Div(className=tick, style={"left": f"{pct(value):.1f}%",
                                                         "bottom": f"-{6 if row == 0 else 2}px"}))
            marks.append(html.Div(className="range-actual",
                                  style={"left": f"{pct(value):.1f}%"}))

    legend = [html.Span(className="range-swatch"), "95% likely range"]
    if actual is not None:
        legend += [html.Span(className="range-actual-key"), "FPL's actual price"]
    return html.Div(
        [
            html.Div([*labels, html.Div(marks, className="range-track",
                                        style={"top": f"{track_top}px"})],
                     className="range-scale",
                     style={"height": f"{first_below + n_below * _ROW}px"}),
            html.Div(legend, className="range-legend"),
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
                marker: str, extra=None, actual: float | None = None,
                reference_on_bar: bool = True, cards=None) -> html.Div:
    """The likely range, drawn, and the verdict in one sentence.

    ``actual`` adds the price FPL really set to the bar; see
    :func:`range_bar`. ``reference_on_bar=False`` keeps the reference for
    the verdict but off the bar, for a page that shows it in ``cards``
    (see :func:`price_cards`) instead.
    """
    pred, lower, upper = _interval(interval)
    delta = pred - reference if reference is not None else 0.0
    return html.Div(
        [range_bar(lower, upper, pred, reference if reference_on_bar else None, marker,
                   actual=actual),
         cards,
         html.P(verdict(delta, lower, upper, reference, against), className="answer-verdict"),
         extra],
        className="answer-body",
    )


def price_cards(items: list[tuple[str, float, str]]) -> html.Div:
    """The prices a prediction is read against, as a row of small cards.

    ``items`` are ``(label, price, kind)``; kind ``"actual"`` carries the
    range bar's diamond, so FPL's real price reads as the same thing in
    both places.
    """
    cards = []
    for label, price, kind in items:
        key = [html.Span(className="range-actual-key")] if kind == "actual" else []
        cards.append(html.Div(
            [html.Span([*key, label], className="price-card-label"),
             html.Span(theme.money(price), className="price-card-value")],
            className=f"price-card price-card-{kind}",
        ))
    return html.Div(cards, className="price-cards")


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
