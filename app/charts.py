"""Plotly figures for the app's pages.

Separate from :mod:`plots`, which renders the pipeline's matplotlib PNGs for
``output/plots/``. Both read their colours from :data:`config.POSITION_COLOURS`
so a position is the same hue in a saved figure and on screen.

The app has no dark mode, so these are built for the light surface only --
a dark variant is a set of steps you choose and validate, not a flip of the
light one, and there is nothing here to flip it against yet.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

#: Chart surface. Matches the Bootstrap card the figure sits in, not the
#: page's grey, so the marks are measured against what is actually behind
#: them.
SURFACE = "#ffffff"

INK = "#1a1d21"
INK_SOFT = "#5c636a"
INK_FAINT = "#868e96"
LINE = "#e3e6ea"

#: Direction of a price movement, matching ``--rise`` / ``--fall`` in
#: ``assets/style.css`` so a contribution is the same green on a bar as it
#: is in the table beside it.
#:
#: Green against red is 6.5 OKLab Delta E apart under a simulated
#: deuteranope -- above the floor of 6 but under the target of 8, which
#: makes it legal only where something other than hue carries the same
#: information. A waterfall does that by construction: a bar rises or falls
#: from the connector, and every bar is labelled with its signed value.
RISE = "#0f7b4a"
FALL = "#c92a3d"

#: Price history: one hue at two lightnesses for the two ends of a season,
#: because they are the same measurement taken twice, and a different hue
#: for the forecast, because it is a different kind of number -- observed
#: against predicted. Worst all-pairs separation is 24.6 OKLab Delta E
#: under a simulated deuteranope, comfortably clear of the target of 8.
PRICE_START = "#7fa8e8"
PRICE_FINAL = "#1f4bb8"
PRICE_FORECAST = "#d97d0d"

#: Marker diameter in px, fixed for every view. Deliberately not scaled to
#: the number of points on screen: a mark that changes size when a filter
#: changes reads as an encoding -- bigger dot, bigger something -- when it
#: means nothing of the kind, and the smaller end of any such range is too
#: small to pick out on a wide monitor, which is where this page is used.
MARK_SIZE = 20

#: Surface-coloured ring, so an overlapping mark still reads as its own dot.
#: The dense £4-5.5 columns are where this earns its keep: at 1px they fuse
#: into a mushy stripe, at 2px the same stack resolves into countable marks.
MARK_RING = 2.0

#: What the x-axis can be measured against, and how to name it. Both are
#: real prices with a real difference: ``price_now`` is the API's
#: ``now_cost``, what the player costs today, and ``start_cost`` is what he
#: cost in August, which is ``now_cost`` less the season's price movement.
#:
#: Against today's price the chart asks "is the model repricing this player
#: from where he is now?" -- the question a manager holding him has.
#: Against the August price it asks "where will he have ended up across the
#: two seasons?", which folds this season's drift into the comparison and
#: is the like-for-like reading, since the y-axis is itself a *start* price.
X_FIELDS = {
    "price_now": "Price today",
    "start_cost": "Start price (August)",
}

DEFAULT_X = "price_now"

FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def price_history_bars(
    seasons: pd.DataFrame, forecast_season: int, forecast_price: float
) -> go.Figure:
    """One player's price at each end of every season, plus what is coming.

    ``seasons`` carries ``season``, ``start_cost`` and ``final_cost``, in
    order and already including the season in progress -- whose "final"
    price is simply the latest one, which the caption says.

    Clustered rather than stacked: a start and a finishing price are two
    readings of the same thing, not two parts of it, and stacking them
    would draw a £12m player as £24m of bar.

    The forecast is its own series rather than a differently-coloured start
    price. That costs it the start slot -- it sits third in its group,
    leaving a gap where the other two would be -- and the gap is the point:
    the season it belongs to has not been played, so there is no finishing
    price to draw, and an empty slot says that more plainly than a footnote.
    """
    labels = [config.season_label(int(s)) for s in seasons["season"]]
    labels.append(config.season_label(int(forecast_season)))

    pad = [None]
    starts = list(seasons["start_cost"]) + pad
    finals = list(seasons["final_cost"]) + pad
    forecast = [None] * len(seasons) + [forecast_price]

    figure = go.Figure()
    for name, values, colour in (
        ("Start price", starts, PRICE_START),
        ("Final price", finals, PRICE_FINAL),
        ("Forecast", forecast, PRICE_FORECAST),
    ):
        figure.add_trace(
            go.Bar(
                name=name,
                x=labels,
                y=values,
                marker=dict(color=colour, line=dict(width=0)),
                text=[f"{v:.1f}" if v is not None else "" for v in values],
                textposition="outside",
                textfont=dict(size=9, color=INK_SOFT),
                cliponaxis=False,
                hovertemplate=f"<b>%{{x}}</b><br>{name} £%{{y:.1f}}m<extra></extra>",
            )
        )

    figure.update_layout(
        barmode="group",
        bargap=0.25,
        bargroupgap=0.05,
        margin=dict(l=44, r=10, t=24, b=8),
        height=240,
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font=dict(family=FONT, color=INK),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=LINE,
                        font=dict(family=FONT, size=12, color=INK), align="left"),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                    title=None, font=dict(size=11, color=INK_SOFT),
                    itemsizing="constant"),
        xaxis=dict(tickfont=dict(size=10, color=INK_SOFT), showgrid=False,
                   showline=True, linecolor=LINE, automargin=True),
        yaxis=dict(tickprefix="£", ticksuffix="m",
                   tickfont=dict(size=10, color=INK_FAINT),
                   gridcolor=LINE, zeroline=False, showline=False,
                   automargin=True, rangemode="tozero"),
    )

    return figure


def term_label(column: str) -> str:
    """A design-matrix column name, as a person would say it.

    ``team_name_Man_City`` and ``element_type_FWD`` are dummy columns whose
    prefixes say which factor they came from, which is worth knowing once
    and not sixteen times across an axis.
    """
    if column.startswith("team_name_"):
        return column[len("team_name_"):].replace("_", " ")
    if column.startswith("element_type_"):
        return f"pos: {column[len('element_type_'):]}"
    return column.replace("_", " ")


def contribution_waterfall(
    steps: list[tuple[str, float, str]],
    reference: tuple[str, float] | None = None,
) -> go.Figure:
    """Per-term contributions to one price, as a running total.

    ``steps`` is ordered ``(label, amount, measure)``, where measure is
    Plotly's ``absolute`` for the intercept the model starts from,
    ``relative`` for each term, and ``total`` for the price they add up to.

    A waterfall rather than a bar chart because the quantity is a
    decomposition, not a set of independent magnitudes: the model is linear,
    so these contributions *sum* to the prediction exactly, and the bridge
    from intercept to price is the thing worth seeing. Anchors are neutral
    rather than green or red -- the intercept and the total are not
    movements, and colouring them as though they were would imply a
    direction they do not have.

    ``reference`` draws a dashed line at a price the player already has --
    ``("Price today", 8.6)`` or ``("Start price", 8.4)``. It turns the chart
    from "how is this price built" into "does it clear the price he is on",
    which is the question being asked: the term where the running total
    crosses the line is the one that pays for the current price, everything
    after it is the model's markup, and the gap between the line and the
    final bar is the predicted change.
    """
    labels = [label for label, _, _ in steps]
    amounts = [amount for _, amount, _ in steps]
    measures = [measure for _, _, measure in steps]

    # Three decimals on the steps, matching the table beside them. At two,
    # every term under half a penny prints as "+0.00", which reads as "this
    # does nothing" when the real statement is "this does very little".
    text = [
        f"£{amount:.2f}m" if measure != "relative"
        else ("~0" if abs(amount) < 0.0005 else f"{amount:+.3f}")
        for amount, measure in zip(amounts, measures)
    ]

    # Hover text is built here rather than left to a format spec in the
    # template. Plotly resolves ``%{y}`` on a waterfall to the running
    # total and ignores the ``:.2f`` attached to it, so the tooltip printed
    # the raw double -- "8.630764965700738 £m". Preformatting is the only
    # way to be sure of the rounding.
    detail, running = [], 0.0
    for amount, measure in zip(amounts, measures):
        if measure == "relative":
            running += amount
            delta = "~£0.00m" if abs(amount) < 0.005 else f"{amount:+.2f}"
            detail.append(f"{delta} · running total £{running:.2f}m")
        else:
            running = amount
            detail.append(f"£{amount:.2f}m")

    figure = go.Figure(
        go.Waterfall(
            orientation="v",
            x=labels,
            y=amounts,
            measure=measures,
            text=text,
            customdata=detail,
            textposition="outside",
            textfont=dict(size=9, color=INK_SOFT),
            cliponaxis=False,
            increasing=dict(marker=dict(color=RISE)),
            decreasing=dict(marker=dict(color=FALL)),
            totals=dict(marker=dict(color=INK_FAINT)),
            # A shade darker than the gridlines: the connector is part of
            # the mark, not chrome -- it is what makes the bars read as one
            # running total rather than fifteen floating blocks.
            connector=dict(line=dict(color="#c2c8cf", width=1)),
            hovertemplate="<b>%{x}</b><br>%{customdata}<extra></extra>",
        )
    )

    if reference:
        label, price = reference
        if price is not None and np.isfinite(price):
            figure.add_hline(
                y=float(price),
                line=dict(color=INK_FAINT, width=1.5, dash="dash"),
                # Behind the bars, because a reference price usually lands
                # close to the predicted one -- and drawn on top, the dash
                # runs straight through the value labels on every bar in
                # that neighbourhood.
                layer="below",
                # Anchored left: the bars climb rightwards, so the space
                # above the intercept is the one place on this chart that is
                # reliably empty at the height a current price sits at.
                annotation=dict(
                    text=f"{label} £{float(price):.2f}m",
                    font=dict(size=10, color=INK_FAINT),
                    xanchor="left",
                    yanchor="bottom",
                ),
                annotation_position="top left",
            )

    figure.update_layout(
        margin=dict(l=56, r=16, t=26, b=8),
        height=400,
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font=dict(family=FONT, color=INK),
        showlegend=False,
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=LINE,
                        font=dict(family=FONT, size=12, color=INK), align="left"),
        xaxis=dict(
            tickangle=-42,
            tickfont=dict(size=10, color=INK_SOFT),
            showgrid=False,
            showline=True,
            linecolor=LINE,
            automargin=True,
        ),
        yaxis=dict(
            title=dict(text="Contribution to price", font=dict(size=12, color=INK_SOFT)),
            tickprefix="£",
            ticksuffix="m",
            tickfont=dict(size=11, color=INK_FAINT),
            gridcolor=LINE,
            zeroline=True,
            zerolinecolor=LINE,
            showline=False,
            automargin=True,
        ),
    )

    return figure


def _axis(title: str, bounds: tuple[float, float]) -> dict:
    """A money axis: recessive grid, £ ticks, shared range with its twin."""
    return dict(
        title=dict(text=title, font=dict(size=12, color=INK_SOFT)),
        range=list(bounds),
        tickprefix="£",
        ticksuffix="m",
        tickfont=dict(size=11, color=INK_FAINT),
        gridcolor=LINE,
        zeroline=False,
        showline=True,
        linecolor=LINE,
        constrain="domain",
    )


def price_scatter(
    frame: pd.DataFrame, target_season: int, x_field: str = DEFAULT_X
) -> go.Figure:
    """A current price against the predicted one, one mark per player.

    The question the chart answers is "who is the model repricing, and in
    which direction?", so the reference is the line of no change. Points
    above ``y = x`` are players it wants to make more expensive, points
    below are the ones it is marking down, and distance from the line is
    the size of the call. That makes the dashed diagonal the baseline the
    eye measures against, which is why it is drawn first and kept
    recessive -- it is an annotation, not a fifth series.

    Position is encoded twice, in hue *and* in marker shape. Set1's blue
    and purple collapse to a Delta E of 3.5 under a simulated deuteranope,
    so on a scatter where MID and GK marks overlap, colour alone would
    leave the two indistinguishable for those readers.

``x_field`` picks which current price to measure against; see
    :data:`X_FIELDS`. It changes what the chart asks, not how it answers.

    Both axes take the same range, so the diagonal runs corner to corner
    and "above the line" means the same thing everywhere. They are *not*
    locked to the same pixel scale: a Plotly ``scaleanchor`` would hold the
    plot square inside a card three times as wide as it is tall, stranding
    the marks in a column down the middle with the rest of the card blank.
    Matching ranges is what makes the reference line honest; matching pixel
    scales only makes it 45 degrees.
    """
    x_field = x_field if x_field in X_FIELDS else DEFAULT_X
    frame = frame.dropna(subset=[x_field, "pred"])

    span = pd.concat([frame[x_field], frame["pred"]])
    pad = max(0.35, (span.max() - span.min()) * 0.04) if len(span) else 0.35
    low = float(span.min()) - pad if len(span) else 0.0
    high = float(span.max()) + pad if len(span) else 1.0
    bounds = (low, high)

    figure = go.Figure()

    # Drawn before the players so it sits underneath them.
    figure.add_trace(
        go.Scatter(
            x=list(bounds),
            y=list(bounds),
            mode="lines",
            line=dict(color=INK_FAINT, width=1.5, dash="dash"),
            hoverinfo="skip",
            showlegend=False,
            name="no change",
        )
    )

    # Biggest group first, so the smallest lands on top. Drawing in
    # config order buries GK: there are 73 of them against 298 midfielders,
    # in the same £4-5.5 huddle, and a first-drawn series is the one every
    # later mark paints over. ``legendrank`` keeps the legend in the
    # declared GK-DEF-MID-FWD order regardless of draw order.
    groups = [(pos, frame[frame["element_type"] == pos]) for pos in config.POSITIONS]
    groups.sort(key=lambda pair: len(pair[1]), reverse=True)

    for position, group in groups:
        if group.empty:
            continue

        figure.add_trace(
            go.Scatter(
                x=group[x_field],
                y=group["pred"],
                mode="markers",
                name=position,
                legendrank=config.POSITIONS.index(position),
                marker=dict(
                    color=config.POSITION_COLOURS[position],
                    symbol=config.POSITION_SYMBOLS[position],
                    size=MARK_SIZE,
                    opacity=0.75,
                    line=dict(width=MARK_RING, color=SURFACE),
                ),
                customdata=group[["web_name", "team_name", "element_type"]],
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "%{customdata[1]} · %{customdata[2]}<br>"
                    f"{X_FIELDS[x_field].split(' (')[0].lower()} "
                    "£%{x:.1f}m → predicted £%{y:.2f}m"
                    "<extra></extra>"
                ),
            )
        )

    # Labelled on the line itself, just inside the top-right corner, so the
    # dashed diagonal does not need the legend or the caption to be read.
    # ``yshift`` drops it clear of the line rather than across it -- an
    # anchor alone only positions the text box, whose top edge is exactly
    # where the line is.
    corner = bounds[1] - (bounds[1] - bounds[0]) * 0.015
    figure.add_annotation(
        x=corner,
        y=corner,
        text="no change",
        showarrow=False,
        xanchor="right",
        yanchor="top",
        yshift=-9,
        font=dict(size=10, color=INK_FAINT),
    )

    figure.update_layout(
        margin=dict(l=64, r=24, t=14, b=46),
        height=440,
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font=dict(family=FONT, color=INK),
        hovermode="closest",
        hoverlabel=dict(
            bgcolor=SURFACE,
            bordercolor=LINE,
            font=dict(family=FONT, size=12, color=INK),
            align="left",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            title=None,
            font=dict(size=12, color=INK_SOFT),
            itemsizing="constant",
        ),
        xaxis=_axis(X_FIELDS[x_field], bounds),
        yaxis=_axis(f"Predicted {config.season_label(target_season)} start price", bounds),
    )

    return figure
