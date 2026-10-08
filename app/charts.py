"""Plotly figures for the app's pages.

Separate from :mod:`plots`, which renders the pipeline's matplotlib PNGs for
``output/plots/``. Colours and type come from :mod:`theme`, so a chart is
drawn in the same vocabulary as the page around it.

The app has no dark mode, so these are built for the light surface only --
a dark variant is a set of steps you choose and validate, not a flip of the
light one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import theme  # noqa: E402

SURFACE = theme.SURFACE
INK = theme.INK
INK_SOFT = theme.INK_SOFT
LINE = theme.LINE
RISE = theme.RISE
FALL = theme.FALL

#: Price history: one hue at two lightnesses for the two ends of a season,
#: because they are the same measurement taken twice, and a different hue
#: for the forecast, because it is a different kind of number -- observed
#: against predicted.
PRICE_START = "#c3a6cf"
PRICE_FINAL = "#5a1f6b"
PRICE_FORECAST = "#0091a8"

#: Marker diameter in px, fixed for every view. Deliberately not scaled to
#: the number of points on screen: a mark that changes size when a filter
#: changes reads as an encoding when it means nothing of the kind.
MARK_SIZE = 16

#: Surface-coloured ring, so an overlapping mark still reads as its own dot.
MARK_RING = 1.5

#: What a current price can be. ``price_now`` is the API's ``now_cost``;
#: ``start_cost`` is what he cost in August. Against today's price the
#: question is "is the model repricing him from where he is now?"; against
#: August it is the like-for-like reading, since the forecast is itself a
#: start price.
X_FIELDS = {
    "price_now": "Price today",
    "start_cost": "Start price (August)",
}

DEFAULT_X = "price_now"

FONT = theme.FONT

_HOVER = dict(bgcolor=theme.AUBERGINE, bordercolor=theme.AUBERGINE,
              font=dict(family=FONT, size=13, color="#ffffff"), align="left")

#: Design-matrix columns as a manager would say them.
_TERM_LABELS = {
    "start_cost": "Start price this season",
    "final_cost": "End price this season",
    "start_cost_sq": "Start price, squared",
    "final_cost_sq": "End price, squared",
    "selected_by_percent": "Selected by %",
    "cost_change_start": "Price movement this season",
    "total_points": "Total points",
    "minutes": "Minutes",
    "transfers_in": "Transfers in",
    "transfers_out": "Transfers out",
    "goals_scored": "Goals",
    "assists": "Assists",
    "bps": "BPS",
    "clean_sheets": "Clean sheets",
    "points_per_game": "Points per game",
    "value_season": "Points per £m",
    "goals_per_min": "Goals per 90",
    "assists_per_min": "Assists per 90",
    "bps_per_min": "BPS per 90",
    "points_per_mins": "Points per 90",
    "cleansheets_per_min": "Clean sheets per 90",
    "no_mins": "Never played",
}


def term_label(column: str) -> str:
    """A design-matrix column name, as a person would say it."""
    if column.startswith("team_name_"):
        return "Plays for " + column[len("team_name_"):].replace("_", " ")
    if column.startswith("element_type_"):
        return "Plays as " + column[len("element_type_"):]
    return _TERM_LABELS.get(column, column.replace("_", " "))


def _base_layout(**extra) -> dict:
    layout = dict(
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font=dict(family=FONT, color=INK, size=13),
        hoverlabel=_HOVER,
        showlegend=False,
    )
    layout.update(extra)
    return layout


def price_history_bars(
    seasons: pd.DataFrame, forecast_season: int, forecast_price: float
) -> go.Figure:
    """One player's price at each end of every season, plus what is coming.

    Clustered rather than stacked: a start and a finishing price are two
    readings of the same thing, not two parts of it. The forecast is its own
    series, which leaves a gap where a finishing price would go -- the
    season it belongs to has not been played, and the gap says so.
    """
    labels = [config.season_label(int(s)) for s in seasons["season"]]
    labels.append(config.season_label(int(forecast_season)))

    pad = [None]
    starts = list(seasons["start_cost"]) + pad
    finals = list(seasons["final_cost"]) + pad
    forecast = [None] * len(seasons) + [forecast_price]

    figure = go.Figure()
    for name, values, colour in (
        ("Start", starts, PRICE_START),
        ("End", finals, PRICE_FINAL),
        ("Forecast", forecast, PRICE_FORECAST),
    ):
        figure.add_trace(
            go.Bar(
                name=name, x=labels, y=values,
                marker=dict(color=colour, line=dict(width=0)),
                text=[f"{v:.1f}" if v is not None else "" for v in values],
                textposition="outside",
                textfont=dict(size=12, color=INK_SOFT, family=theme.FONT_FIGURES),
                cliponaxis=False,
                hovertemplate=f"<b>%{{x}}</b><br>{name} £%{{y:.1f}}m<extra></extra>",
            )
        )

    figure.update_layout(**_base_layout(
        barmode="group", bargap=0.28, bargroupgap=0.06,
        margin=dict(l=8, r=8, t=30, b=8), height=230, showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=12, color=INK_SOFT), itemsizing="constant"),
        xaxis=dict(tickfont=dict(size=12, color=INK_SOFT), showgrid=False,
                   showline=True, linecolor=LINE, automargin=True),
        yaxis=dict(visible=False, rangemode="tozero"),
    ))
    return figure


def _faint(hex_colour: str, alpha: float) -> str:
    red, green, blue = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({red}, {green}, {blue}, {alpha})"


def forecast_trend(days: pd.DataFrame, target_season: int) -> go.Figure:
    """One player's forecast as it stood each morning, against his price.

    ``days`` holds one row per day: ``date``, ``price``, ``pred``, ``lower``,
    ``upper`` and ``gameweeks_finished``. The forecast is drawn in the same
    hue as the price history's forecast bar, with its 95% range as a faint
    band; the price that day is a step line, because FPL prices jump
    overnight rather than drift. Both are prices in £m, so one axis serves.
    """
    dates = pd.to_datetime(days["date"])
    gameweeks = days["gameweeks_finished"].fillna(0).astype(int)
    when = [f"{d.day} {d:%b} · after GW{gw}" for d, gw in zip(dates, gameweeks)]
    marker = dict(size=8, line=dict(width=MARK_RING, color=SURFACE)) if len(days) <= 14 else None
    target = config.season_label(target_season)

    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=dates, y=days["upper"], mode="lines", line=dict(width=0),
        hoverinfo="skip", showlegend=False,
    ))
    figure.add_trace(go.Scatter(
        x=dates, y=days["lower"], mode="lines", line=dict(width=0),
        fill="tonexty", fillcolor=_faint(PRICE_FORECAST, 0.16),
        name="95% likely range", hoverinfo="skip",
    ))
    figure.add_trace(go.Scatter(
        x=dates, y=days["price"], mode="lines+markers" if marker else "lines",
        line=dict(color=PRICE_FINAL, width=2, shape="hv"),
        marker=dict(color=PRICE_FINAL, **marker) if marker else None,
        name="Price that day", customdata=when,
        hovertemplate="<b>%{customdata}</b><br>Price £%{y:.1f}m<extra></extra>",
    ))
    figure.add_trace(go.Scatter(
        x=dates, y=days["pred"], mode="lines+markers" if marker else "lines",
        line=dict(color=PRICE_FORECAST, width=2),
        marker=dict(color=PRICE_FORECAST, **marker) if marker else None,
        name=f"{target} forecast",
        customdata=list(zip(when, days["lower"], days["upper"])),
        hovertemplate=("<b>%{customdata[0]}</b><br>Forecast £%{y:.2f}m"
                       "<br>Likely £%{customdata[1]:.1f}m – £%{customdata[2]:.1f}m"
                       "<extra></extra>"),
    ))

    # The latest value of each line, labelled at its end, so the two read
    # without a trip to the legend.
    last = days.iloc[-1]
    for value, places in ((last["pred"], 2), (last["price"], 1)):
        figure.add_annotation(
            x=dates.iloc[-1], y=float(value), text=f"£{float(value):.{places}f}m",
            showarrow=False, xanchor="left", xshift=8,
            font=dict(size=13, family=theme.FONT_FIGURES, color=INK),
        )

    low = float(min(days["lower"].min(), days["price"].min()))
    high = float(max(days["upper"].max(), days["price"].max()))
    pad = max((high - low) * 0.08, 0.1)
    figure.update_layout(**_base_layout(
        margin=dict(l=8, r=64, t=30, b=8), height=250, showlegend=True,
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=12, color=INK_SOFT), itemsizing="constant"),
        xaxis=dict(tickformat="%-d %b", tickfont=dict(size=12, color=INK_SOFT),
                   showgrid=False, showline=True, linecolor=LINE, automargin=True,
                   dtick=86_400_000 if len(days) <= 10 else None),
        yaxis=dict(range=[low - pad, high + pad], tickprefix="£", ticksuffix="m",
                   tickfont=dict(size=12, color=INK_SOFT), gridcolor=LINE,
                   zeroline=False, automargin=True),
    ))
    return figure


def contribution_bars(
    steps: list[tuple[str, float, str]],
    reference: tuple[str, float] | None = None,
) -> go.Figure:
    """Per-term contributions to one price, as a running total, sideways.

    Horizontal so every term's name reads flat instead of at 42 degrees.
    It is still a waterfall -- the model is linear, so the contributions sum
    to the prediction exactly, and the bridge from baseline to price is the
    thing worth seeing. Anchors are neutral: the baseline and the total are
    not movements, and colouring them green or red would imply a direction.

    ``reference`` draws the price he is already on as a dashed line, so the
    gap between it and the final bar is the predicted move.
    """
    labels = [label for label, _, _ in steps]
    amounts = [amount for _, amount, _ in steps]
    measures = [measure for _, _, measure in steps]

    text = [
        f"£{amount:.2f}m" if measure != "relative"
        else ("~0" if abs(amount) < 0.005 else theme.money(amount, signed=True, places=2))
        for amount, measure in zip(amounts, measures)
    ]

    # Preformatted: Plotly resolves %{x} on a waterfall to the running
    # total and ignores any format spec, printing the raw double.
    detail, running = [], 0.0
    for amount, measure in zip(amounts, measures):
        if measure == "relative":
            running += amount
            detail.append(f"{theme.money(amount, signed=True, places=2)} · running total "
                          f"£{running:.2f}m")
        else:
            running = amount
            detail.append(f"£{amount:.2f}m")

    figure = go.Figure(
        go.Waterfall(
            orientation="h",
            y=labels, x=amounts, measure=measures,
            customdata=detail,
            textposition="none",
            increasing=dict(marker=dict(color=RISE)),
            decreasing=dict(marker=dict(color=FALL)),
            totals=dict(marker=dict(color=theme.AUBERGINE)),
            connector=dict(line=dict(color="#cbbfd2", width=1)),
            hovertemplate="<b>%{y}</b><br>%{customdata}<extra></extra>",
        )
    )

    # Faint banding on alternate rows, so a value in the right-hand column
    # reads across to its own bar.
    for index in range(0, len(labels), 2):
        figure.add_shape(type="rect", xref="paper", x0=0, x1=1, yref="y",
                         y0=index - 0.5, y1=index + 0.5, layer="below",
                         fillcolor="#f7f3f9", line=dict(width=0))

    # Values in a column of their own at the right edge, rather than at the
    # end of each bar: there, the reference line runs straight through the
    # labels of every bar that finishes near it, which is most of them.
    for label, amount_text, measure in zip(labels, text, measures):
        figure.add_annotation(
            x=1.0, xref="paper", xanchor="left", xshift=10, y=label, yref="y",
            text=f"<b>{amount_text}</b>" if measure != "relative" else amount_text,
            showarrow=False, align="left",
            font=dict(size=13, family=theme.FONT_FIGURES,
                      color=INK if measure != "relative" else INK_SOFT),
        )

    if reference:
        label, price = reference
        if price is not None and np.isfinite(price):
            figure.add_vline(
                x=float(price),
                line=dict(color=INK_SOFT, width=1.5, dash="dash"),
                layer="below",
                annotation=dict(text=f"{label} £{float(price):.1f}m",
                                font=dict(size=12, color=INK_SOFT)),
                annotation_position="top",
            )

    figure.update_layout(**_base_layout(
        margin=dict(l=8, r=78, t=28, b=8),
        height=34 * len(steps) + 60,
        bargap=0.35,
        yaxis=dict(autorange="reversed", tickfont=dict(size=13, color=INK),
                   showgrid=False, automargin=True, ticksuffix="  "),
        xaxis=dict(tickprefix="£", ticksuffix="m", tickfont=dict(size=12, color=INK_SOFT),
                   gridcolor=LINE, zeroline=True, zerolinecolor="#cbbfd2",
                   automargin=True),
    ))
    return figure


def _axis(title: str, bounds: tuple[float, float]) -> dict:
    """A money axis: recessive grid, £ ticks, shared range with its twin."""
    return dict(
        title=dict(text=title, font=dict(size=13, color=INK_SOFT)),
        range=list(bounds),
        tickprefix="£", ticksuffix="m",
        tickfont=dict(size=12, color=INK_SOFT),
        gridcolor=LINE, zeroline=False, showline=True, linecolor=LINE,
        constrain="domain",
    )


def price_scatter(
    frame: pd.DataFrame, target_season: int, x_field: str = DEFAULT_X
) -> go.Figure:
    """A current price against the predicted one, one mark per player.

    The dashed diagonal is the line of no change: above it the model wants
    him dearer, below it cheaper, and distance from the line is the size of
    the call. Position is encoded in hue *and* marker shape, so colour is
    never the only cue. Both axes share a range, so "above the line" means
    the same everywhere; they are not locked to the same pixel scale, which
    would strand the marks in a column down the middle of a wide card.

    Every mark carries the player's ``code``, so a click can open his card.
    """
    x_field = x_field if x_field in X_FIELDS else DEFAULT_X
    frame = frame.dropna(subset=[x_field, "pred"])

    span = pd.concat([frame[x_field], frame["pred"]])
    pad = max(0.35, (span.max() - span.min()) * 0.04) if len(span) else 0.35
    low = float(span.min()) - pad if len(span) else 0.0
    high = float(span.max()) + pad if len(span) else 1.0
    bounds = (low, high)

    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=list(bounds), y=list(bounds), mode="lines",
        line=dict(color=INK_SOFT, width=1.2, dash="dash"),
        hoverinfo="skip", showlegend=False, name="no change",
    ))

    # Biggest group first, so the smallest lands on top rather than buried.
    groups = [(pos, frame[frame["element_type"] == pos]) for pos in config.POSITIONS]
    groups.sort(key=lambda pair: len(pair[1]), reverse=True)

    reference = X_FIELDS[x_field].split(" (")[0].lower()
    for position, group in groups:
        if group.empty:
            continue
        figure.add_trace(go.Scatter(
            x=group[x_field], y=group["pred"], mode="markers", name=position,
            legendrank=config.POSITIONS.index(position),
            marker=dict(color=theme.POSITION_COLOURS[position],
                        symbol=theme.POSITION_SYMBOLS[position],
                        size=MARK_SIZE, opacity=0.85,
                        line=dict(width=MARK_RING, color=SURFACE)),
            customdata=group[["web_name", "team_name", "element_type", "code"]],
            hovertemplate=(
                "<b>%{customdata[0]}</b> · %{customdata[1]}<br>"
                f"{reference} £%{{x:.1f}}m → £%{{y:.1f}}m"
                "<br><i>click to open</i><extra></extra>"
            ),
        ))

    corner = bounds[1] - (bounds[1] - bounds[0]) * 0.02
    figure.add_annotation(
        x=corner, y=corner, text="no change", showarrow=False,
        xanchor="right", yanchor="top", yshift=-12, xshift=-4,
        font=dict(size=12, color=INK_SOFT),
    )

    figure.update_layout(**_base_layout(
        margin=dict(l=8, r=16, t=40, b=8), height=460,
        hovermode="closest", showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
                    font=dict(size=13, color=INK), itemsizing="constant"),
        xaxis=_axis(X_FIELDS[x_field], bounds),
        yaxis=_axis(f"Predicted {config.season_label(target_season)} price", bounds),
    ))
    figure.update_xaxes(automargin=True)
    figure.update_yaxes(automargin=True)
    return figure
