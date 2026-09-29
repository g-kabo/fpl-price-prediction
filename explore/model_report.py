"""Draft exploration report on the current price model. Not used by the app.

    python explore/model_report.py [--refresh]

Writes ``output/model_report.html``: numbered charts (F1, F2, ...) and tables
(T1, T2, ...) for picking what belongs on the app's "Inside the model" page.
Everything here is about the current model specification only.

Two sets of errors, both ``predicted - actual`` (positive = the model priced
a player too high):

* **Out-of-sample, 2020-21 to 2025-26.** For each season ``s``, the current
  specification is fitted on every transition before ``s`` and predicts the
  ``s -> s+1`` start prices. Pooled, that is one honest prediction per
  player-season -- enough rows to cut by position and price tier.
* **The served model vs 2026-27.** The model the app serves, scored against
  the prices FPL actually set (``output/backtest_2026.csv``). Real, but one
  season: most position x tier cells are thin.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import clean  # noqa: E402
import config  # noqa: E402
import fpl_data  # noqa: E402
import model  # noqa: E402
import price_analysis  # noqa: E402
from feature_experiments import FIRST_TEST_SEASON  # noqa: E402
import report_notes as notes  # noqa: E402

OUT = config.OUTPUT_DIR / "model_report.html"

POS_COLOURS = {"GK": "#f5b400", "DEF": "#00b8d4", "MID": "#7c4dff", "FWD": "#ff6d00"}
POS_SYMBOLS = {"GK": "diamond", "DEF": "square", "MID": "triangle-up", "FWD": "circle"}
INK, INK_SOFT, LINE, ACCENT = "#1b0a21", "#5b4a63", "#e6e0ea", "#8a3aa0"
#: Diverging for signed error: violet (too low) - neutral - orange (too high).
DIVERGING = [[0, "#4b2a86"], [0.5, "#f4f1f6"], [1, "#d9600a"]]
SEQUENTIAL = [[0, "#f4eef7"], [1, "#4b1560"]]
FONT = "Barlow, system-ui, sans-serif"

TIERS = config.TIER_NAMES
POSITIONS = config.POSITIONS

#: Readable names for design-matrix groups.
GROUP_LABELS = {
    "price": "Price (start, end, both squared)", "position": "Position", "club": "Club",
    "total_points": "Total points", "minutes": "Minutes", "goals_scored": "Goals",
    "assists": "Assists", "points_per_game": "Points per game",
    "value_season": "Points per £m", "selected_by_percent": "Selected by %",
    "no_mins": "Never played",
}


# ---------------------------------------------------------------- data


def load(refresh: bool) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    seasons = list(range(config.FIRST_SEASON, config.PREDICT_SEASON + 1))
    master = fpl_data.load_master_teams(seasons, refresh)
    cleaned = clean.clean_all(fpl_data.load_all_seasons(seasons, refresh), master)
    return price_analysis.all_transitions(cleaned), cleaned[config.SCORE_SEASON], cleaned


def out_of_sample(frame: pd.DataFrame) -> pd.DataFrame:
    folds = []
    for season in range(FIRST_TEST_SEASON, int(frame["season"].max()) + 1):
        train, test = frame[frame["season"] < season], frame[frame["season"] == season].copy()
        interval = model.PriceModel().fit(train).predict_with_interval(test)
        # Only for the squared-terms section: the same model minus the squares.
        test["pred_linear"] = model.PriceModel(
            numeric=price_analysis.LINEAR_NUMERIC).fit(train).predict(test)
        folds.append(pd.concat([test, interval], axis=1))
    df = pd.concat(folds)
    df = df[df["pred"].notna() & df[model.TARGET].notna()].copy()
    df["actual"] = df[model.TARGET]
    return tag(df)


def with_next_season(df: pd.DataFrame, cleaned: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Club and position the season after, for reading the misses.

    Not model inputs: the model never sees these. They are here because a
    club move or a reclassification is often why FPL's price differed.
    """
    nxt = pd.concat(cleaned.values())[["code", "season", "team_name", "element_type"]]
    nxt = nxt.rename(columns={"team_name": "next_team", "element_type": "next_pos"})
    nxt["season"] -= 1
    df = df.merge(nxt, on=["code", "season"], how="left")
    df["moved_club"] = df["next_team"] != df["team_name"]
    df["changed_pos"] = df["next_pos"].astype(str) != df["element_type"].astype(str)
    return df


def served_backtest() -> pd.DataFrame | None:
    path = config.OUTPUT_DIR / f"backtest_{config.PREDICT_SEASON}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, encoding="utf-8").rename(columns={"actual_start_cost": "actual"})
    df["season"] = config.SCORE_SEASON
    return tag(df)


def tag(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["error"] = df["pred"] - df["actual"]
    df["move"] = df["actual"] - df["start_cost"]
    df["tier"] = pd.Categorical(price_analysis.price_tier(df), TIERS, ordered=True)
    df["band"] = pd.Categorical(price_analysis.price_band(df),
                                [b for b, _, _ in price_analysis.PRICE_BANDS], ordered=True)
    df["element_type"] = pd.Categorical(df["element_type"], POSITIONS, ordered=True)
    return df


def metrics(g: pd.DataFrame) -> pd.Series:
    e = g["error"]
    covered = (g["actual"] >= g["pred_lower"]) & (g["actual"] <= g["pred_upper"])
    return pd.Series({
        "n": len(g),
        "Mean error": e.mean(),
        "SD of error": e.std(ddof=1) if len(g) > 1 else np.nan,
        "MAE": e.abs().mean(),
        "RMSE": np.sqrt((e ** 2).mean()),
        "Within £0.1m": (e.abs() <= 0.1 + 1e-9).mean(),
        "Within £0.25m": (e.abs() <= 0.25 + 1e-9).mean(),
        "95% range held": covered.mean(),
        "Avg actual move": g["move"].mean(),
    })


def by(df: pd.DataFrame, keys) -> pd.DataFrame:
    return df.groupby(keys, observed=True).apply(metrics, include_groups=False)


# ---------------------------------------------------------------- the served model


def contributions(fitted: model.PriceModel, train: pd.DataFrame,
                  score: pd.DataFrame) -> pd.DataFrame:
    """Each input group's push on each scored player's price, in £m.

    Measured from an average training player: beta * (x - training mean),
    summed within a group. The four price terms are one group because they
    only make sense together; so are the position and club dummies.
    """
    X, X0 = fitted._matrix(score), fitted._matrix(train)
    push = (X - X0.mean()) * fitted.result.params
    groups = {}
    for column in fitted.columns:
        if column in price_analysis.PRICE_TERMS:
            key = "price"
        elif column.startswith("element_type_"):
            key = "position"
        elif column.startswith("team_name_"):
            key = "club"
        else:
            key = column
        groups.setdefault(key, []).append(column)
    out = pd.DataFrame({k: push[cols].sum(axis=1) for k, cols in groups.items()})
    out["element_type"] = score["element_type"].to_numpy()
    return out


def push_example(fitted: model.PriceModel, train: pd.DataFrame, score: pd.DataFrame,
                 push: pd.DataFrame) -> pd.DataFrame:
    """Two real players' pushes, signed, bridging from the average player.

    The most-selected player, and the most-selected Budget-tier player: one
    premium and one cheap, so the pushes point in opposite directions.
    """
    X0 = fitted._matrix(train)
    baseline = float((X0.mean() * fitted.result.params).sum())
    tiers = price_analysis.price_tier(score)
    picks = [score["selected_by_percent"].idxmax(),
             score[tiers == "Budget"]["selected_by_percent"].idxmax()]
    groups = [c for c in push.columns if c != "element_type"]
    out = {}
    for i in picks:
        row = score.loc[i]
        name = f"{row['web_name']} ({row['element_type']}, £{row['start_cost']:.1f}m)"
        values = push.loc[i, groups].astype(float)
        out[name] = [baseline, *values, baseline + values.sum()]
    labels = ["Average training player", *[GROUP_LABELS.get(g, g) for g in groups],
              "Predicted price"]
    return pd.DataFrame(out, index=labels)


def price_slope(fitted: model.PriceModel, top: float, linear: model.PriceModel) -> pd.DataFrame:
    """How much of £1 of this season's price carries into next season's.

    Three readings per price level ``p``, each with a 95% interval from the
    fit's covariance matrix (the slopes are linear in the coefficients, so
    their variance is exact, g' Sigma g):

    * ``carried``: start and end price moved together, a player whose price
      did not change in-season: b_s + b_f + 2p (b_ssq + b_fsq).
    * ``via_start`` / ``via_end``: one of the two moved alone.
    * ``linear``: the same model without the squares, one number at every p.
    """
    b, cov = fitted.result.params, fitted.result.cov_params()
    terms = ["start_cost", "final_cost", "start_cost_sq", "final_cost_sq"]
    grid = np.arange(4.0, top + 0.01, 0.5)
    out = {"price": grid}
    for name, weights in (("carried", lambda q: [1, 1, 2 * q, 2 * q]),
                          ("via_start", lambda q: [1, 0, 2 * q, 0]),
                          ("via_end", lambda q: [0, 1, 0, 2 * q])):
        est, half = [], []
        for q in grid:
            g = np.array(weights(q), dtype=float)
            est.append(float(g @ b[terms].to_numpy()))
            half.append(1.96 * float(np.sqrt(g @ cov.loc[terms, terms].to_numpy() @ g)))
        out[name], out[f"{name}_ci"] = est, half
    lb, lcov = linear.result.params, linear.result.cov_params()
    g = np.array([1.0, 1.0])
    out["linear"] = float(g @ lb[terms[:2]].to_numpy())
    out["linear_ci"] = 1.96 * float(np.sqrt(g @ lcov.loc[terms[:2], terms[:2]].to_numpy() @ g))
    return pd.DataFrame(out)


# ---------------------------------------------------------------- charts


def _layout(fig: go.Figure, height: int, **extra) -> go.Figure:
    fig.update_layout(template="plotly_white", height=height, font=dict(family=FONT, color=INK),
                      margin=dict(l=10, r=20, t=50, b=10), hoverlabel=dict(font_family=FONT),
                      **extra)
    fig.update_xaxes(gridcolor=LINE, automargin=True)
    fig.update_yaxes(gridcolor=LINE, automargin=True)
    return fig


def f_histogram(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Histogram(x=df["error"], xbins=dict(size=0.1), marker_color=ACCENT,
                                 marker_line=dict(width=1, color="white"),
                                 hovertemplate="error %{x}<br>%{y} player-seasons<extra></extra>"))
    mean, sd = df["error"].mean(), df["error"].std()
    for x, dash, label in ((mean, "solid", f"mean {mean:+.3f}"),
                           (mean - sd, "dot", f"−1 SD"), (mean + sd, "dot", f"+1 SD ({sd:.3f})")):
        fig.add_vline(x=x, line=dict(color=INK_SOFT, dash=dash, width=1.5),
                      annotation_text=label, annotation_position="top")
    fig.update_xaxes(title="Predicted − actual (£m)", range=[-2, 2])
    fig.update_yaxes(title="Player-seasons")
    return _layout(fig, 360)


def f_histogram_by_position(df: pd.DataFrame) -> go.Figure:
    """One error histogram per position, stacked on a shared x-axis.

    Each panel keeps its own count scale -- MID has four times the rows of
    GK -- so compare shapes and spreads, not bar heights, across panels.
    """
    fig = make_subplots(rows=len(POSITIONS), cols=1, shared_xaxes=True,
                        vertical_spacing=0.06, subplot_titles=POSITIONS)
    for row, pos in enumerate(POSITIONS, start=1):
        e = df.loc[df["element_type"] == pos, "error"]
        fig.add_trace(go.Histogram(
            x=e, xbins=dict(start=-2, end=2, size=0.1), marker_color=POS_COLOURS[pos],
            marker_line=dict(width=1, color="white"), name=pos,
            hovertemplate=f"{pos}: error %{{x}}<br>%{{y}} player-seasons<extra></extra>",
        ), row=row, col=1)
        mean, sd = e.mean(), e.std()
        for x, dash in ((mean, "solid"), (mean - sd, "dot"), (mean + sd, "dot")):
            fig.add_vline(x=x, line=dict(color=INK_SOFT, dash=dash, width=1.5), row=row, col=1)
        fig.add_annotation(x=1, xref="x domain", xanchor="right", y=1, yref="y domain",
                           yanchor="top", showarrow=False, align="right",
                           text=f"n={len(e):,} · mean {mean:+.3f} · SD {sd:.3f}",
                           font=dict(size=12, color=INK_SOFT), row=row, col=1)
        fig.update_yaxes(title="Count", row=row, col=1)
    fig.update_xaxes(range=[-2, 2], dtick=0.5)
    fig.update_xaxes(title="Predicted − actual (£m)", row=len(POSITIONS), col=1)
    return _layout(fig, 760, showlegend=False, bargap=0)


def _whisker(fig, table: pd.DataFrame, x, row=None, col=None, colour=ACCENT, name=None,
             symbol="circle", showlegend=False):
    fig.add_trace(go.Scatter(
        x=x, y=table["Mean error"], mode="markers", name=name, showlegend=showlegend,
        marker=dict(size=11, color=colour, symbol=symbol, line=dict(width=1.5, color="white")),
        error_y=dict(type="data", array=table["SD of error"], color=colour, thickness=2, width=6),
        customdata=np.c_[table["n"], table["SD of error"], table["RMSE"]],
        hovertemplate=("%{x}<br>mean %{y:+.3f} · SD %{customdata[1]:.3f}<br>"
                       "RMSE %{customdata[2]:.3f} · n=%{customdata[0]:.0f}<extra></extra>"),
    ), row=row, col=col)


def f_tier_whiskers(table: pd.DataFrame, title: str) -> go.Figure:
    fig = make_subplots(rows=1, cols=4, shared_yaxes=True, subplot_titles=POSITIONS,
                        horizontal_spacing=0.03)
    for i, pos in enumerate(POSITIONS, start=1):
        t = table.loc[pos] if pos in table.index.get_level_values(0) else None
        if t is None:
            continue
        t = t.reindex([x for x in TIERS if x in t.index])
        _whisker(fig, t, [f"{x}<br>n={int(n)}" for x, n in zip(t.index, t["n"])],
                 row=1, col=i, colour=POS_COLOURS[pos], symbol=POS_SYMBOLS[pos])
        fig.add_hline(y=0, line=dict(color=INK_SOFT, width=1), row=1, col=i)
    fig.update_yaxes(title="Mean error ± 1 SD (£m)", row=1, col=1)
    return _layout(fig, 430, title=dict(text=title, font_size=13))


def f_heatmap(table: pd.DataFrame, metric: str, diverging: bool) -> go.Figure:
    grid = table[metric].unstack().reindex(index=POSITIONS, columns=TIERS)
    n = table["n"].unstack().reindex(index=POSITIONS, columns=TIERS)
    text = [[("" if pd.isna(v) else f"{v:+.3f}" if diverging else f"{v:.3f}")
             + ("" if pd.isna(c) else f"<br><span style='font-size:11px'>n={int(c)}</span>")
             for v, c in zip(rv, rc)] for rv, rc in zip(grid.values, n.values)]
    lim = float(np.nanmax(np.abs(grid.values)))
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=TIERS, y=POSITIONS, text=text, texttemplate="%{text}",
        textfont=dict(size=15, family=FONT),
        colorscale=DIVERGING if diverging else SEQUENTIAL,
        zmid=0 if diverging else None, zmin=-lim if diverging else 0, zmax=lim,
        colorbar=dict(title="£m", thickness=12), xgap=3, ygap=3,
        hovertemplate="%{y} %{x}: %{z:.3f}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed")
    return _layout(fig, 340, title=dict(text=metric, font_size=13))


def f_band_whiskers(table: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    _whisker(fig, table, [f"{b}<br>n={int(n)}" for b, n in zip(table.index, table["n"])])
    fig.add_hline(y=0, line=dict(color=INK_SOFT, width=1))
    fig.update_yaxes(title="Mean error ± 1 SD (£m)")
    return _layout(fig, 380)


def by_predicted_price(df: pd.DataFrame, min_n: int = 20) -> pd.DataFrame:
    """Error metrics per £0.5m bin of predicted price, bins with n >= min_n."""
    bins = np.arange(3.5, df["pred"].max() + 0.5, 0.5)
    g = df.assign(bin=pd.cut(df["pred"], bins)).groupby("bin", observed=True)
    t = g.apply(metrics, include_groups=False)
    return t[t["n"] >= min_n]


def f_spread_by_prediction(df: pd.DataFrame) -> go.Figure:
    t = by_predicted_price(df)
    mid = [b.mid for b in t.index]
    fig = make_subplots(rows=1, cols=2, subplot_titles=("SD of error", "Mean error"),
                        horizontal_spacing=0.08)
    fig.add_trace(go.Bar(x=mid, y=t["SD of error"], marker_color=ACCENT, width=0.4,
                         customdata=t["n"], hovertemplate="predicted ~£%{x}m<br>SD %{y:.3f}"
                         "<br>n=%{customdata:.0f}<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Bar(x=mid, y=t["Mean error"], marker_color=ACCENT, width=0.4,
                         customdata=t["n"], hovertemplate="predicted ~£%{x}m<br>mean %{y:+.3f}"
                         "<br>n=%{customdata:.0f}<extra></extra>"), row=1, col=2)
    fig.update_xaxes(title="Predicted price (£m, 0.5 bins with n ≥ 20)")
    return _layout(fig, 360, showlegend=False)


def f_error_path(df: pd.DataFrame) -> go.Figure:
    """SD against mean error per predicted-price bin, joined in price order.

    The same bins as F9. Up means priced too high on average, right means
    less predictable; the path shows how both change together with price.
    """
    t = by_predicted_price(df)
    mid = np.array([b.mid for b in t.index])
    labels = [f"£{b.left:.1f}–{b.right:.1f}m" for b in t.index]
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color=INK_SOFT, width=1))
    fig.add_trace(go.Scatter(
        x=t["SD of error"], y=t["Mean error"], mode="lines+markers+text",
        line=dict(color="#cbbfd2", width=2),
        marker=dict(size=13, color=mid, colorscale=SEQUENTIAL, cmin=mid.min() - 0.5,
                    line=dict(width=1.5, color="white"),
                    colorbar=dict(title="Predicted<br>price (£m)", thickness=12)),
        text=[f"£{m:g}m" for m in mid - 0.25], textposition="top center",
        textfont=dict(size=12, color=INK_SOFT),
        customdata=np.c_[labels, t["n"], t["RMSE"]],
        hovertemplate=("<b>Predicted %{customdata[0]}</b><br>SD %{x:.3f} · mean %{y:+.3f}"
                       "<br>RMSE %{customdata[2]:.3f} · n=%{customdata[1]:.0f}<extra></extra>"),
    ))
    # Arrowheads along the path so its direction reads without the colour.
    _arrows(fig, t["SD of error"].to_numpy(), t["Mean error"].to_numpy(), "#a898b3")
    fig.update_xaxes(title="SD of error (£m)")
    fig.update_yaxes(title="Mean error (£m) · above 0 = priced too high", zeroline=False)
    return _layout(fig, 480, showlegend=False)


def f_tier_path(table: pd.DataFrame) -> go.Figure:
    """F9a's axes for position x tier, one panel per position, tiers in order.

    ``table`` is the position x tier metrics table from §3 (T4). All four
    panels are pinned to one range: make_subplots only shares axes along a
    row or column, and positions are only comparable on a common scale.
    """
    fig = make_subplots(rows=2, cols=2, subplot_titles=POSITIONS, horizontal_spacing=0.06,
                        vertical_spacing=0.12)
    for i, pos in enumerate(POSITIONS):
        row, col = i // 2 + 1, i % 2 + 1
        t = table.loc[pos].reindex([x for x in TIERS if x in table.loc[pos].index])
        x, y = t["SD of error"].to_numpy(), t["Mean error"].to_numpy()
        fig.add_hline(y=0, line=dict(color=INK_SOFT, width=1), row=row, col=col)
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines+markers+text", name=pos,
            line=dict(color=POS_COLOURS[pos], width=2),
            marker=dict(size=12, symbol=POS_SYMBOLS[pos], color=POS_COLOURS[pos],
                        line=dict(width=1.5, color="white")),
            text=list(t.index), textposition="top center",
            textfont=dict(size=11, color=INK_SOFT),
            customdata=np.c_[t.index, t["n"], t["RMSE"]],
            hovertemplate=(f"<b>{pos} %{{customdata[0]}}</b><br>SD %{{x:.3f}} · mean "
                           "%{y:+.3f}<br>RMSE %{customdata[2]:.3f} · n=%{customdata[1]:.0f}"
                           "<extra></extra>"),
        ), row=row, col=col)
        _arrows(fig, x, y, POS_COLOURS[pos], subplot=i + 1)

    def span(values, pad):
        return [float(values.min()) - pad, float(values.max()) + pad]
    fig.update_xaxes(range=span(table["SD of error"], 0.05))
    fig.update_yaxes(range=span(table["Mean error"], 0.04))
    fig.update_xaxes(title="SD of error (£m)", row=2)
    fig.update_yaxes(title="Mean error (£m)", col=1)
    return _layout(fig, 720, showlegend=False)


def f_residuals(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for pos in sorted(POSITIONS, key=lambda p: -(df["element_type"] == p).sum()):
        g = df[df["element_type"] == pos]
        fig.add_trace(go.Scatter(
            x=g["pred"], y=g["error"], mode="markers", name=pos,
            marker=dict(size=7, color=POS_COLOURS[pos], symbol=POS_SYMBOLS[pos], opacity=0.55,
                        line=dict(width=0.5, color="white")),
            customdata=np.c_[g["web_name"], g["season"].map(config.season_label),
                             g["start_cost"], g["actual"]],
            hovertemplate=("<b>%{customdata[0]}</b> %{customdata[1]}<br>start £%{customdata[2]}m"
                           " → pred £%{x:.2f}m, actual £%{customdata[3]}m<extra></extra>")))
    fig.add_hline(y=0, line=dict(color=INK_SOFT, width=1))
    fig.update_xaxes(title="Predicted price (£m)")
    fig.update_yaxes(title="Predicted − actual (£m)")
    return _layout(fig, 460)


def f_season(table: pd.DataFrame) -> go.Figure:
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Mean error", "SD of error"),
                        horizontal_spacing=0.08)
    for pos in POSITIONS:
        t = table.loc[(slice(None), pos), :].droplevel(1)
        x = [config.season_label(int(s) + 1) for s in t.index]
        for col, metric in ((1, "Mean error"), (2, "SD of error")):
            fig.add_trace(go.Scatter(
                x=x, y=t[metric], mode="lines+markers", name=pos, showlegend=col == 1,
                line=dict(color=POS_COLOURS[pos], width=2),
                marker=dict(symbol=POS_SYMBOLS[pos], size=9, color=POS_COLOURS[pos]),
                hovertemplate=f"{pos} %{{x}}: %{{y:.3f}}<extra></extra>"), row=1, col=col)
    fig.add_hline(y=0, line=dict(color=INK_SOFT, width=1), row=1, col=1)
    fig.update_xaxes(title="Prices predicted for")
    return _layout(fig, 380)


def _arrows(fig: go.Figure, x, y, colour: str, subplot: int = 1) -> None:
    """Arrowheads at each segment's midpoint, pointing along the path.

    ``subplot`` is the 1-based subplot number, which picks Plotly's axis
    pair: x/y for the first, x2/y2 for the second, and so on.
    """
    ref = "" if subplot == 1 else str(subplot)
    for i in range(len(x) - 1):
        fig.add_annotation(x=(x[i] + x[i + 1]) / 2, y=(y[i] + y[i + 1]) / 2, ax=x[i], ay=y[i],
                           xref=f"x{ref}", yref=f"y{ref}", axref=f"x{ref}", ayref=f"y{ref}",
                           showarrow=True, arrowhead=2, arrowsize=1.2, arrowwidth=1.5,
                           arrowcolor=colour, text="")


def f_calibration(df: pd.DataFrame) -> go.Figure:
    bins = np.arange(3.5, df["pred"].max() + 0.5, 0.5)
    t = (df.assign(bin=pd.cut(df["pred"], bins)).groupby("bin", observed=True)
         .agg(pred=("pred", "mean"), actual=("actual", "mean"), n=("pred", "size")))
    t = t[t["n"] >= 10]
    lo, hi = 3.8, float(max(t["pred"].max(), t["actual"].max())) + 0.3
    fig = go.Figure(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines",
                               line=dict(color=INK_SOFT, dash="dash"), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=t["pred"], y=t["actual"], mode="markers+lines",
                             marker=dict(size=10, color=ACCENT), line=dict(color=ACCENT),
                             customdata=t["n"], hovertemplate="pred £%{x:.2f}m → actual "
                             "£%{y:.2f}m<br>n=%{customdata}<extra></extra>"))
    fig.update_xaxes(title="Mean predicted (0.5 bins, n ≥ 10)", range=[lo, hi])
    fig.update_yaxes(title="Mean actual", range=[lo, hi])
    return _layout(fig, 420, showlegend=False)


def f_contributions(push: pd.DataFrame) -> go.Figure:
    groups = [c for c in push.columns if c != "element_type"]
    typical = push[groups].abs().mean().sort_values()
    fig = go.Figure()
    for pos in POSITIONS:
        g = push[push["element_type"] == pos][groups].abs().mean().reindex(typical.index)
        fig.add_trace(go.Bar(y=[GROUP_LABELS.get(k, k) for k in g.index], x=g, orientation="h",
                             name=pos, marker_color=POS_COLOURS[pos],
                             hovertemplate=f"{pos}: %{{x:.3f}}<extra></extra>"))
    fig.update_xaxes(title="Typical push on a player's price (£m, mean |β·(x − avg)|)")
    return _layout(fig, 520, barmode="group")


def _band(fig, x, y, half, colour, name, row=None, col=None, showlegend=True, dash=None):
    """A line with a shaded 95% band."""
    x, y, half = np.asarray(x), np.asarray(y), np.asarray(half)
    fig.add_trace(go.Scatter(x=np.r_[x, x[::-1]], y=np.r_[y + half, (y - half)[::-1]],
                             fill="toself", fillcolor=colour, opacity=0.15, line=dict(width=0),
                             hoverinfo="skip", showlegend=False), row=row, col=col)
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers", name=name, showlegend=showlegend,
                             line=dict(color=colour, width=2, dash=dash),
                             marker=dict(size=6, color=colour),
                             customdata=half,
                             hovertemplate=f"{name}<br>£%{{x:.1f}}m: £%{{y:.2f}} ± "
                                           "%{customdata:.2f}<extra></extra>"),
                  row=row, col=col)


def f_slope(curve: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    flat = np.full(len(curve), curve["linear"].iloc[0])
    _band(fig, curve["price"], flat, np.full(len(curve), curve["linear_ci"].iloc[0]),
          "#9a8ea3", "Without the squares", dash="dash")
    _band(fig, curve["price"], curve["carried"], curve["carried_ci"], ACCENT, "With the squares")
    fig.update_xaxes(title="This season's price (£m)", dtick=1)
    fig.update_yaxes(title="Carried into next season, per £1", tickformat=".2f")
    return _layout(fig, 380, legend=dict(orientation="h", y=1.08, x=0))


def f_slope_split(curve: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color=INK_SOFT, width=1))
    _band(fig, curve["price"], curve["via_start"], curve["via_start_ci"], "#c98a00",
          "Start price moved alone")
    _band(fig, curve["price"], curve["via_end"], curve["via_end_ci"], "#1f6fb2",
          "End price moved alone")
    fig.update_xaxes(title="This season's price (£m)", dtick=1)
    fig.update_yaxes(title="Carried into next season, per £1", tickformat=".2f")
    return _layout(fig, 380, legend=dict(orientation="h", y=1.08, x=0))


def f_what_fpl_did(frame: pd.DataFrame) -> go.Figure:
    """Mean next-season start price at each start price: the raw curve."""
    df = frame.assign(price=frame["start_cost"].round(1))
    t = df.groupby("price").agg(next=(model.TARGET, "mean"), n=(model.TARGET, "size"),
                                sd=(model.TARGET, "std"))
    t = t[t["n"] >= 8]
    lo, hi = 3.8, float(t.index.max()) + 0.4
    fig = go.Figure(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", name="No change",
                               line=dict(color=INK_SOFT, dash="dash", width=1.5), hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=t.index, y=t["next"], mode="markers+lines", name="Average next start price",
        line=dict(color=ACCENT, width=2),
        marker=dict(size=np.clip(np.sqrt(t["n"]) * 1.2, 7, 26), color=ACCENT,
                    line=dict(width=1.5, color="white")),
        customdata=np.c_[t["n"], t["sd"]],
        hovertemplate=("Started at £%{x:.1f}m → next August £%{y:.2f}m on average"
                       "<br>SD %{customdata[1]:.2f} · n=%{customdata[0]:.0f}<extra></extra>")))
    fig.update_xaxes(title="Start price this season (£m)", range=[lo, hi], dtick=1)
    fig.update_yaxes(title="Average start price next season (£m)", range=[lo, hi], dtick=1)
    return _layout(fig, 460, legend=dict(orientation="h", y=1.06, x=0))


def f_squares_bands(t: pd.DataFrame) -> go.Figure:
    """Mean error ± 1 SD per band, with and without the squares, side by side."""
    x = np.arange(len(t))
    fig = go.Figure()
    for offset, prefix, name, colour, symbol in ((-0.12, "lin_", "Without the squares", "#9a8ea3", "diamond"),
                                                 (0.12, "", "With the squares", ACCENT, "circle")):
        fig.add_trace(go.Scatter(
            x=x + offset, y=t[f"{prefix}mean"], mode="markers", name=name,
            marker=dict(size=11, color=colour, symbol=symbol, line=dict(width=1.5, color="white")),
            error_y=dict(type="data", array=t[f"{prefix}sd"], color=colour, thickness=2, width=5),
            customdata=np.c_[t.index, t[f"{prefix}sd"], t[f"{prefix}rmse"], t["n"]],
            hovertemplate=("<b>%{customdata[0]}</b> · " + name + "<br>mean %{y:+.3f} · SD "
                           "%{customdata[1]:.3f}<br>RMSE %{customdata[2]:.3f} · n=%{customdata[3]}"
                           "<extra></extra>")))
    fig.add_hline(y=0, line=dict(color=INK_SOFT, width=1))
    fig.update_xaxes(tickvals=x, ticktext=[f"{b}<br>n={n}" for b, n in zip(t.index, t["n"])])
    fig.update_yaxes(title="Mean error ± 1 SD (£m)")
    return _layout(fig, 420, legend=dict(orientation="h", y=1.08, x=0))


def f_coef_dots(rows: pd.DataFrame, reference: str, colours: dict | None = None,
                symbols: dict | None = None) -> go.Figure:
    """Coefficients with 95% intervals, one row each, the reference level at 0."""
    rows = rows.sort_values("estimate")
    labels = list(rows.index)
    fig = go.Figure()
    fig.add_vline(x=0, line=dict(color=INK_SOFT, width=1))
    colour = [colours.get(k, ACCENT) if colours else ACCENT for k in labels]
    symbol = [symbols.get(k, "circle") if symbols else "circle" for k in labels]
    fig.add_trace(go.Scatter(
        x=rows["estimate"], y=labels, mode="markers",
        marker=dict(size=12, color=colour, symbol=symbol, line=dict(width=1.5, color="white")),
        error_x=dict(type="data", symmetric=False, array=rows["conf_high"] - rows["estimate"],
                     arrayminus=rows["estimate"] - rows["conf_low"], color="#b9abc3",
                     thickness=2, width=5),
        customdata=np.c_[rows["conf_low"], rows["conf_high"], rows["p_value"]],
        hovertemplate=("<b>%{y}</b><br>%{x:+.3f} (95%: %{customdata[0]:+.3f} to "
                       "%{customdata[1]:+.3f})<br>p = %{customdata[2]:.2g}<extra></extra>")))
    fig.add_trace(go.Scatter(x=[0], y=[reference], mode="markers", hoverinfo="skip",
                             marker=dict(size=12, color=INK_SOFT, symbol="circle-open",
                                         line=dict(width=2, color=INK_SOFT))))
    fig.update_xaxes(title="Coefficient: £m added to next season's price, vs the reference")
    return _layout(fig, 34 * (len(labels) + 1) + 90, showlegend=False)


#: FPL's between-season moves, by size. "Sharp" is a move of £1.0m or more,
#: two of FPL's usual £0.5m steps.
MOVE_BANDS = [
    ("sharp fall", lambda m: m <= -1.0 + 1e-9, "#8a0033", "white"),
    ("fall", lambda m: (m <= -0.1 + 1e-9) & (m > -1.0 + 1e-9), "#ec7ea2", INK),
    ("held", lambda m: m.abs() < 0.1 - 1e-9, "#d9d2de", INK),
    ("rise", lambda m: (m >= 0.1 - 1e-9) & (m < 1.0 - 1e-9), "#6cc39a", INK),
    ("sharp rise", lambda m: m >= 1.0 - 1e-9, "#005c2e", "white"),
]


def f_moves(frame: pd.DataFrame) -> go.Figure:
    df = tag(frame.assign(pred=np.nan, actual=frame[model.TARGET]))
    fig = make_subplots(rows=1, cols=4, shared_yaxes=True, subplot_titles=POSITIONS,
                        horizontal_spacing=0.03)
    for i, pos in enumerate(POSITIONS, start=1):
        g = df[df["element_type"] == pos]
        shares = g.groupby("tier", observed=True)["move"].agg(
            **{name: (lambda m, test=test: test(m).mean()) for name, test, _, _ in MOVE_BANDS})
        n = g.groupby("tier", observed=True).size()
        for name, _, colour, text_colour in MOVE_BANDS:
            fig.add_trace(go.Bar(x=[f"{t}<br>n={n[t]}" for t in shares.index],
                                 y=shares[name], name=name, marker_color=colour,
                                 showlegend=i == 1,
                                 text=[f"{v:.0%}" if v >= 0.04 else "" for v in shares[name]],
                                 textposition="inside", textfont=dict(color=text_colour),
                                 hovertemplate=f"{pos} %{{x}} {name}: %{{y:.0%}}<extra></extra>"),
                          row=1, col=i)
    fig.update_yaxes(tickformat=".0%", row=1, col=1)
    return _layout(fig, 440, barmode="stack", legend=dict(orientation="h", y=1.14, x=0,
                                                          traceorder="normal"))


#: Half-width of the jitter on the reset scatter. Prices sit on a £0.1m grid,
#: so without it hundreds of players share one point; £0.04m keeps every
#: point inside its own £0.1m cell.
JITTER = 0.04


def f_reset_scatter(frame: pd.DataFrame) -> go.Figure:
    """The summer change (new start price - last final price) against the final price.

    Read left to right in time: where a player finished, then how far FPL
    moved him for the new season. Above zero he started dearer. The black
    steps are the median change in each final-price band.
    """
    df = notes.summer(frame)
    rng = np.random.default_rng(config.SEED)
    lo, hi = float(df["final_cost"].min()) - 0.3, float(df["final_cost"].max()) + 0.3
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color=INK_SOFT, dash="dash", width=1.5))
    # Biggest group first, so the smaller ones are drawn on top of it.
    for pos in sorted(POSITIONS, key=lambda q: -(df["element_type"] == q).sum()):
        g = df[df["element_type"] == pos]
        fig.add_trace(go.Scattergl(
            x=g["final_cost"] + rng.uniform(-JITTER, JITTER, len(g)),
            y=g["summer"] + rng.uniform(-JITTER, JITTER, len(g)),
            mode="markers", name=pos, legendrank=POSITIONS.index(pos),
            marker=dict(size=6, color=POS_COLOURS[pos], symbol=POS_SYMBOLS[pos], opacity=0.5,
                        line=dict(width=0.5, color="white")),
            customdata=np.c_[g["web_name"], g["season"].map(config.season_label),
                             g["season"].map(lambda v: config.season_label(int(v) + 1)),
                             g["final_cost"], g["next_cost"], g["summer"]],
            hovertemplate=("<b>%{customdata[0]}</b> (" + pos + ")<br>ended %{customdata[1]} "
                           "at £%{customdata[3]:.1f}m<br>started %{customdata[2]} at "
                           "£%{customdata[4]:.1f}m (%{customdata[5]:+.1f})<extra></extra>")))
    med = df.groupby("reset_band", observed=True)["summer"].median()
    edges = dict(zip(notes.RESET_LABELS, zip(notes.RESET_EDGES[:-1], notes.RESET_EDGES[1:])))
    xs, ys = [], []
    for band, v in med.items():
        left, right = edges[band]
        xs += [max(left, lo), min(right, hi), None]
        ys += [v, v, None]
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name="Median per band",
                             line=dict(color=INK, width=3), hoverinfo="skip"))
    for band, v in med.items():
        left, right = edges[band]
        fig.add_annotation(x=(max(left, lo) + min(right, hi)) / 2, y=v, yshift=12,
                           text=f"median {v:+.1f}", showarrow=False, bgcolor="rgba(255,255,255,0.85)",
                           font=dict(size=11, color=INK))
    fig.add_annotation(x=hi, y=1, xanchor="right", text="raised over the summer ↑", showarrow=False,
                       font=dict(size=12, color=INK_SOFT))
    fig.add_annotation(x=hi, y=-1, xanchor="right", text="cut over the summer ↓",
                       showarrow=False, font=dict(size=12, color=INK_SOFT))
    fig.update_xaxes(title="Last season's final price (£m)", range=[lo, hi], dtick=1)
    for edge in notes.RESET_EDGES[1:-1]:
        fig.add_vline(x=edge, line=dict(color=LINE, width=1))
    fig.update_yaxes(title="Summer change (£m): new start − last final", dtick=0.5,
                     zeroline=False)
    return _layout(fig, 560, legend=dict(orientation="h", y=1.08, x=0,
                                         itemsizing="constant"))


#: Short names used in the written-out equation.
EQ_NAMES = {
    "start_cost": "start", "final_cost": "end", "start_cost_sq": "start²",
    "final_cost_sq": "end²", "total_points": "points", "minutes": "minutes",
    "goals_scored": "goals", "assists": "assists", "points_per_game": "ppg",
    "value_season": "value", "selected_by_percent": "selected", "no_mins": "never_played",
}
_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def _numeric_terms(fitted: model.PriceModel) -> list[str]:
    return [c for c in fitted.columns if not c.startswith(("element_type_", "team_name_"))]


def _sig4(v: float) -> str:
    """Four significant figures, never in scientific notation."""
    return np.format_float_positional(abs(v), precision=4, unique=False, fractional=False,
                                      trim="-")


def _term(sign: str, coef: str, name: str) -> str:
    return f'<span class="eq-t">{sign} {coef} · <var>{name}</var></span>'


def equation_symbolic(fitted: model.PriceModel) -> str:
    terms = [f'<span class="eq-t">β₀</span>']
    for i, col in enumerate(_numeric_terms(fitted), start=1):
        terms.append(_term("+", f"β{str(i).translate(_SUB)}", EQ_NAMES.get(col, col)))
    terms.append('<span class="eq-t">+ β<sub>position</sub></span>')
    terms.append('<span class="eq-t">+ β<sub>club</sub></span>')
    return ('<div class="eq"><span class="eq-lhs"><var>next start price</var> =</span>'
            + "".join(terms) + "</div>")


def equation_numeric(fitted: model.PriceModel) -> str:
    b = fitted.result.params
    terms = [f'<span class="eq-t">{_sig4(b["const"])}</span>']
    for col in _numeric_terms(fitted):
        terms.append(_term("−" if b[col] < 0 else "+", _sig4(b[col]), EQ_NAMES.get(col, col)))
    terms.append('<span class="eq-t">+ <var>position adjustment</var></span>')
    terms.append('<span class="eq-t">+ <var>club adjustment</var></span>')
    return ('<div class="eq"><span class="eq-lhs"><var>next start price</var> =</span>'
            + "".join(terms) + "</div>")


def adjustments_html(fitted: model.PriceModel) -> str:
    """Position and club adjustments side by side, each against its reference level."""
    b = fitted.result.params
    pos = [("GK", 0.0, True)] + [(c.split("_")[-1], b[c], False) for c in fitted.columns
                                 if c.startswith("element_type_")]
    clubs = sorted(((c[len("team_name_"):].replace("_", " "), b[c], False)
                    for c in fitted.columns if c.startswith("team_name_")), key=lambda r: -r[1])
    clubs.append((f"Every other club (“{config.OTHER_TEAM}”)", 0.0, True))

    def table(title, rows):
        body = "".join(f"<tr><th>{name}</th><td>{'0 (reference)' if ref else f'{v:+.4f}'}"
                       "</td></tr>" for name, v, ref in rows)
        return (f'<table class="t"><thead><tr><th>{title}</th><th>£m added</th></tr></thead>'
                f"<tbody>{body}</tbody></table>")

    return f'<div class="adj">{table("Position", pos)}{table("Club", clubs)}</div>'


def legend_html(fitted: model.PriceModel) -> str:
    meaning = {
        "start_cost": "Price at the start of the season (£m)",
        "final_cost": "Price at the end of the season (£m)",
        "start_cost_sq": "Start price × start price",
        "final_cost_sq": "End price × end price",
        "total_points": "FPL points over the season",
        "minutes": "Minutes played over the season",
        "goals_scored": "Goals scored", "assists": "Assists",
        "points_per_game": "FPL points per appearance",
        "value_season": "Points per £m of price (FPL's value_season)",
        "selected_by_percent": "Share of FPL managers owning him at season end (%)",
        "no_mins": "1 if he played no minutes at all, else 0",
    }
    rows = "".join(f"<tr><th><var>{EQ_NAMES.get(c, c)}</var></th><td>{c}</td>"
                   f"<td>{meaning.get(c, '')}</td></tr>" for c in _numeric_terms(fitted))
    return ('<table class="t legend"><thead><tr><th>In the equation</th><th>Column</th>'
            f"<th>Meaning</th></tr></thead><tbody>{rows}</tbody></table>")


# ---------------------------------------------------------------- tables and page


PCT = {"Within £0.1m", "Within £0.25m", "95% range held"}
SIGNED = {"Mean error", "Avg actual move", "Mean error (no squares)"}


def table_html(t: pd.DataFrame, index_names: list[str] | None = None) -> str:
    t = t.copy()
    fmt = {}
    for c in t.columns:
        if c == "n":
            fmt[c] = lambda v: f"{int(v):,}"
        elif c in PCT:
            fmt[c] = lambda v: "" if pd.isna(v) else f"{v:.0%}"
        elif c in SIGNED:
            fmt[c] = lambda v: "" if pd.isna(v) else f"{v:+.3f}"
        elif t[c].dtype.kind == "f":
            fmt[c] = lambda v: "" if pd.isna(v) else f"{v:.3f}"
    if index_names:
        t.index.names = index_names
    return t.to_html(formatters=fmt, border=0, classes="t", na_rep="", escape=False)


class Report:
    def __init__(self):
        self.parts, self.fig_n, self.tab_n, self.sec_n, self.toc = [], 0, 0, 0, []
        self.first_fig = True

    def section(self, title: str, intro: str = ""):
        self.sec_n += 1
        anchor = f"s{self.sec_n}"
        self.toc.append(f'<li><a href="#{anchor}">§{self.sec_n} {title}</a></li>')
        self.parts.append(f'<h2 id="{anchor}">§{self.sec_n} {title}</h2>'
                          + (f"<p class='intro'>{intro}</p>" if intro else ""))

    def fig(self, figure: go.Figure, caption: str, sub: str = ""):
        """``sub`` ("a", "b") attaches the figure to the previous number: F9a."""
        if not sub:
            self.fig_n += 1
        label = f"F{self.fig_n}{sub}"
        html = figure.to_html(full_html=False, include_plotlyjs=self.first_fig,
                              config={"displaylogo": False, "responsive": True})
        self.first_fig = False
        self.parts.append(f'<figure id="{label}"><figcaption><b>{label}</b> '
                          f'{caption}</figcaption>{html}</figure>')

    def table(self, html: str, caption: str):
        self.tab_n += 1
        self.parts.append(f'<div class="tbl" id="T{self.tab_n}"><div class="cap"><b>T{self.tab_n}'
                          f'</b> {caption}</div>{html}</div>')

    def equation(self, html: str, caption: str):
        self.eq_n = getattr(self, "eq_n", 0) + 1
        self.parts.append(f'<div class="tbl" id="E{self.eq_n}"><div class="cap"><b>E{self.eq_n}'
                          f'</b> {caption}</div>{html}</div>')

    def commentary(self, html: str):
        self.parts.append(f"<div class='commentary'>{html}</div>")

    def note(self, text: str):
        self.parts.append(f"<p class='note'>{text}</p>")

    def write(self, path: Path, header: str):
        page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Price model report (draft)</title>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700&family=Barlow+Condensed:wght@700;800&display=swap" rel="stylesheet">
<style>
body {{ font-family: Barlow, system-ui, sans-serif; color: {INK}; background: #f6f4f8; margin: 0; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 24px 24px 80px; }}
h1, h2 {{ font-family: 'Barlow Condensed', Barlow, sans-serif; text-transform: uppercase; color: #2b0033; }}
h1 {{ font-size: 2.4rem; margin: 8px 0 4px; }} h2 {{ font-size: 1.7rem; margin: 48px 0 6px; }}
.intro, .note, header p {{ max-width: 80ch; line-height: 1.5; }}
.note {{ color: {INK_SOFT}; font-size: 0.92rem; }}
.commentary {{ max-width: 90ch; line-height: 1.5; margin: -4px 0 18px; padding: 10px 16px;
  background: #fff; border: 1px solid {LINE}; border-radius: 8px; }}
.eq {{ font-family: 'Barlow Condensed', Barlow, sans-serif; font-size: 1.25rem;
  line-height: 2; font-variant-numeric: tabular-nums; padding: 4px 2px; }}
.eq var {{ font-family: Barlow, sans-serif; font-size: 1rem; color: #57206a; }}
.eq-lhs {{ display: block; }}
.eq-t {{ display: inline-block; white-space: nowrap; margin-right: 0.45em; }}
.adj {{ display: flex; gap: 32px; flex-wrap: wrap; align-items: flex-start; }}
table.t.legend td, table.t.legend th {{ text-align: left; white-space: normal; }}
.adj thead th:first-child {{ text-align: left; }}
.commentary ul {{ margin: 6px 0 0; padding-left: 1.2rem; }} .commentary li {{ margin-bottom: 4px; }}
figure, .tbl {{ background: #fff; border: 1px solid {LINE}; border-radius: 10px; padding: 12px 14px; margin: 14px 0; }}
figcaption, .cap {{ font-size: 0.95rem; margin-bottom: 6px; }}
figcaption b, .cap b {{ background: #2b0033; color: #fff; border-radius: 4px; padding: 1px 7px; margin-right: 6px; }}
.tbl {{ overflow-x: auto; }}
table.t {{ border-collapse: collapse; font-variant-numeric: tabular-nums; font-size: 0.92rem; }}
table.t th, table.t td {{ padding: 5px 10px; border-bottom: 1px solid {LINE}; text-align: right; white-space: nowrap; }}
table.t thead th {{ border-bottom: 2px solid #cbbfd2; }}
table.t tbody th {{ text-align: left; }}
nav ol {{ columns: 2; font-size: 0.95rem; }}
nav a {{ color: #57206a; }}
</style></head><body><main>
{header}
<nav><ol>{''.join(self.toc)}</ol></nav>
{''.join(self.parts)}
</main></body></html>"""
        path.write_text(page, encoding="utf-8")


# ---------------------------------------------------------------- commentary
#
# The patterns below were read off the current data. The named examples are
# fixed text; every count and share is computed, so a rerun keeps them honest.


def _share(rows: pd.DataFrame, column: str) -> str:
    return f"{int(rows[column].sum())} of {len(rows)}"


def _named(rows: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    return rows[rows["web_name"].isin(names)]


def _range(v: pd.Series) -> str:
    lo, hi = float(v.min()), float(v.max())
    return f"£{lo:.1f}m" if round(lo, 1) == round(hi, 1) else f"£{lo:.1f}–{hi:.1f}m"


def _comment_high(rows: pd.DataFrame, everyone: pd.DataFrame) -> str:
    fwd = int((rows["element_type"] == "FWD").sum())
    fwd_all = (everyone["element_type"] == "FWD").mean()
    latest = rows[(rows["season"] == everyone["season"].max()) & (rows["element_type"] == "FWD")]
    chelsea = int((rows["team_name"] == "Chelsea").sum())
    poor = _named(rows, ["Rashford", "Sterling", "Pulisic", "Ziyech", "Pépé"])
    huge = _named(rows, ["Mbeumo", "Watkins"])
    stars = _named(rows, ["Son", "De Bruyne"])
    return f"""<b>Why the model priced these players too high</b><ul>
<li><b>Big-club attackers after a poor or injury-hit season</b> (Rashford, Sterling, Pulisic,
Ziyech, Pépé). FPL cut them by {_range(poor["start_cost"] - poor["actual"])}; the model cut
only {_range(poor["start_cost"] - poor["pred"])}. A poor season shrinks the goals, points-per-game
and value pushes, but most of the prediction comes from the price itself, so the model cannot
follow a cut that deep. {chelsea} of the 15 are Chelsea players.</li>
<li><b>Forwards:</b> {fwd} of 15, against {fwd_all:.0%} of all rows, and {len(latest)} from the
latest season ({", ".join(latest["web_name"])}). FPL priced 2026-27 strikers below what the
same numbers earned in earlier seasons.</li>
<li><b>Huge seasons FPL only partly rewarded</b> (Mbeumo 236 pts, Watkins 228 pts). FPL
raised them {_range(huge["actual"] - huge["start_cost"])}; the model adds goals, assists and
points per game in a straight line and wanted
{_range(huge["pred"] - huge["start_cost"])}.</li>
<li><b>Premiums FPL cut hard</b> ({", ".join(
        f"{r.web_name} £{r.start_cost:.1f}m → £{r.actual:.1f}m" for r in stars.itertuples())}):
deeper cuts than their seasons predicted. Nothing the model sees explains them.</li>
<li><b>Reclassification:</b> Sessegnon moved from MID to DEF, where prices are lower.
Only {_share(rows, "changed_pos")} changed position and {_share(rows, "moved_club")} changed
club: most of these misses stayed where they were.</li></ul>"""


def _comment_low(rows: pd.DataFrame, everyone: pd.DataFrame) -> str:
    quiet = rows[rows["minutes"] < 900]
    return f"""<b>Why the model priced these players too low</b><ul>
<li><b>Breakout seasons from a cheap start</b> (Palmer £5.0m → £10.5m, João Pedro,
Kulusevski, Kroupi). The model adds goals, assists and points per game in a straight line on
top of the old price, so it cannot jump as far as FPL did. FPL re-priced them as the players
they had become.</li>
<li><b>Little or no football, then a bigger role</b>: {len(quiet)} of 15 played under 900
minutes ({", ".join(quiet["web_name"])}). With few minutes the model has little to go on and
stays close to the old price. FPL priced the expected role instead: a move (O'Brien to Everton,
Philogene to Ipswich), a return from injury (Timber), or a rising youngster (Ngumoha).</li>
<li><b>Reclassified FWD → MID</b> (Kroupi, Marmoush): FPL set a price for the new role.
{_share(rows, "changed_pos")} changed position and {_share(rows, "moved_club")} changed club,
against {everyone["changed_pos"].mean():.0%} and {everyone["moved_club"].mean():.0%} of all
players.</li>
<li><b>Premiums FPL held at £11–12m after ordinary seasons</b> (Mané, De Bruyne, Sterling, all
from 2020-21): the reverse of the too-high list. For 2021-22 FPL protected its stars
rather than cutting them.</li></ul>"""


def _comment_tails(df: pd.DataFrame) -> str:
    over = df[df["error"] >= df["error"].quantile(0.975)]
    under = df[df["error"] <= df["error"].quantile(0.025)]
    return (f"<b>Beyond the top 15.</b> In the worst 2.5% each way ({len(over)} players each), "
            f"under-priced players changed club {under['moved_club'].mean():.0%} and position "
            f"{under['changed_pos'].mean():.0%} of the time, against "
            f"{df['moved_club'].mean():.0%} and {df['changed_pos'].mean():.0%} for everyone. "
            f"They played a median {under['minutes'].median():,.0f} minutes, against "
            f"{over['minutes'].median():,.0f} for the over-priced. The common thread: the model "
            "sees only last season's numbers. Where FPL priced the next season's role (a new "
            "club, a new position, a return from injury, a star's age or reputation), the "
            "model missed.")


# ---------------------------------------------------------------- main


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--refresh", action="store_true")
    args = p.parse_args()

    frame, score, cleaned = load(args.refresh)
    oos = with_next_season(out_of_sample(frame), cleaned)
    served = served_backtest()
    train = frame[frame["season"] <= config.TRAIN_THROUGH]
    fitted = model.PriceModel().fit(train)
    first, last = config.season_label(FIRST_TEST_SEASON + 1), config.season_label(int(oos["season"].max()) + 1)
    oos_label = f"out-of-sample, prices for {first} to {last}"

    r = Report()
    header = (f"<h1>Price model: draft report</h1><p>Exploration only; not read by the app. "
              f"Generated {date.today():%d %b %Y} by <code>explore/model_report.py</code>. "
              f"Error = predicted − actual start price, so <b>positive means the model priced "
              f"the player too high</b>. Tiers are <code>config.PRICE_TIERS</code>, applied to "
              f"the season's start price and the position that season.</p>"
              f"<p>Main error set: the current model specification refitted season by season "
              f"— fit on every season before <i>s</i>, predict <i>s → s+1</i> — pooled over "
              f"{len(oos):,} player-seasons ({oos_label}). Second set: the served model "
              f"(trained to {config.season_label(config.TRAIN_THROUGH)}) against the "
              f"{config.season_label(config.PREDICT_SEASON)} prices FPL set"
              + (f", {len(served):,} returning players.</p>" if served is not None else
                 " — not available (run backtest.py).</p>"))
    if served is not None and int(oos["season"].max()) == config.SCORE_SEASON:
        header += (f"<p>The two sets overlap: the last out-of-sample season is fitted on the "
                   f"same seasons as the served model, so its {config.season_label(config.PREDICT_SEASON)} "
                   "predictions are the served model's, and those players are also counted "
                   "in the pooled figures.</p>")

    # §1 overview
    r.section("Overview")
    overview = pd.DataFrame({f"Out-of-sample ({first} to {last})": metrics(oos)})
    if served is not None:
        overview[f"Served model vs {config.season_label(config.PREDICT_SEASON)}"] = metrics(served)
    r.table(table_html(overview.T), "Headline error metrics.")
    served_label = config.season_label(config.PREDICT_SEASON)
    r.commentary(notes.overview(metrics(oos), metrics(served) if served is not None else None,
                                served_label))
    r.fig(f_histogram(oos), f"Distribution of errors, {oos_label}, with mean and ±1 SD.")
    r.commentary(notes.histogram(oos["error"]))

    # §2 position
    r.section("By position")
    t_pos = by(oos, "element_type")
    r.table(table_html(t_pos, ["Position"]), f"Errors by position, {oos_label}.")
    r.commentary(notes.positions(t_pos))
    r.fig(f_histogram_by_position(oos), "Error distribution by position, one histogram "
          "each on a shared axis (solid line = mean, dotted = ±1 SD). Count scales differ "
          "by panel.")
    r.commentary(notes.position_hists(oos))
    if served is not None:
        t_served_pos = by(served, "element_type")
        r.table(table_html(t_served_pos, ["Position"]),
                f"Errors by position, served model vs {config.season_label(config.PREDICT_SEASON)}.")
        r.commentary(notes.served_positions(t_served_pos))

    # §3 position x tier
    r.section("By position and price tier",
              "Tier bounds: " + "; ".join(
                  f"{pos} " + ", ".join(f"{name} {rng}" for name, rng in
                                        zip(TIERS, price_analysis.tier_ranges()[pos]))
                  for pos in POSITIONS) + ".")
    t_tier = by(oos, ["element_type", "tier"])
    r.table(table_html(t_tier, ["Position", "Tier"]), f"Errors by position and tier, {oos_label}.")
    r.commentary(notes.tiers(t_tier))
    r.fig(f_tier_whiskers(t_tier, "Mean error ± 1 SD, by tier"),
          "Mean error with ±1 SD whiskers per tier, one panel per position.")
    r.commentary(notes.tier_whiskers(t_tier))
    r.fig(f_heatmap(t_tier, "Mean error", True), "Mean error by position × tier (orange = priced too high).")
    r.commentary(notes.heat_mean(t_tier))
    r.fig(f_heatmap(t_tier, "SD of error", False), "SD of error by position × tier.")
    r.commentary(notes.heat_sd(t_tier))
    r.fig(f_heatmap(t_tier, "RMSE", False), "RMSE by position × tier.")
    r.commentary(notes.heat_rmse(t_tier))
    if served is not None:
        t_served = by(served, ["element_type", "tier"])
        r.table(table_html(t_served, ["Position", "Tier"]),
                f"The same for the served model vs {config.season_label(config.PREDICT_SEASON)} "
                "(one season: many cells are thin).")
        r.commentary(notes.served_tiers(t_served))
        r.fig(f_tier_whiskers(t_served, "Served model, one season"),
              f"Mean error ± 1 SD by tier, served model vs {config.season_label(config.PREDICT_SEASON)}.")
        r.commentary(notes.served_whiskers(t_served))

    # §4 price bands
    r.section("By price band (all positions)")
    t_band = by(oos, "band")
    r.table(table_html(t_band, ["Start price"]), f"Errors by start-price band, {oos_label}.")
    r.commentary(notes.bands(t_band))
    r.fig(f_band_whiskers(t_band), "Mean error ± 1 SD by start-price band.")
    r.commentary(notes.band_whiskers(t_band))
    t_pred = by_predicted_price(oos)
    r.fig(f_spread_by_prediction(oos), "SD and mean of the error, by predicted price. Mean error above 0 = priced too high on average.")
    r.commentary(notes.by_predicted(t_pred))
    r.fig(f_error_path(oos), "The same bins as F9 as one path: SD of error across, mean error "
          "up, joined in order of predicted price (labels are each bin's lower edge; arrows "
          "point to dearer bins).", sub="a")
    r.commentary(notes.error_path(t_pred))
    r.fig(f_tier_path(t_tier), "Position × tier on F9a's axes, one panel per position: each "
          "path runs through that position's tiers, Budget → Low-Mid → High-Mid → Premium "
          "(arrows point to the dearer tier). All panels share one scale; hover for n.", sub="b")
    r.commentary(notes.tier_path(t_tier))
    r.fig(f_residuals(oos), "Every out-of-sample prediction: predicted price against its error. "
          "The diagonal stripes are FPL's price grid: each stripe is one actual price.")
    r.commentary(notes.residuals(oos))

    # §5 seasons
    r.section("By season")
    t_season = by(oos, ["season", "element_type"])
    r.fig(f_season(t_season), "Mean and SD of error per position, season by season.")
    r.commentary(notes.seasons_by_position(t_season))
    t_season_all = by(oos, "season")
    t_season_all.index = [config.season_label(int(s) + 1) for s in t_season_all.index]
    r.table(table_html(t_season_all, ["Prices predicted for"]), "Errors per season, all positions.")
    r.commentary(notes.seasons_all(t_season_all))

    # §6 calibration
    r.section("Calibration")
    r.fig(f_calibration(oos), "Mean actual against mean predicted, in 0.5 bins. On the dashed "
          "line, the model is right on average at that price.")
    r.commentary(notes.calibration(oos))

    # §7 misses
    r.section("Biggest misses", f"{oos_label}. Next club and next position are the "
              "following season's, which the model never sees.")
    cols = {"web_name": "Player", "season": "Season", "element_type": "Pos", "tier": "Tier",
            "team_name": "Club", "minutes": "Mins", "total_points": "Pts",
            "start_cost": "Start", "final_cost": "End", "pred": "Predicted",
            "actual": "Actual", "error": "Error", "next_team": "Next club", "next_pos": "Next pos"}
    high, low = oos.nlargest(15, "error"), oos.nsmallest(15, "error")
    for label, rows, comment in (("Priced too high", high, _comment_high(high, oos)),
                                 ("Priced too low", low, _comment_low(low, oos))):
        t = rows[list(cols)].rename(columns=cols)
        t["Season"] = t["Season"].map(lambda s: config.season_label(int(s)))
        t["Next club"] = [n if m else "same" for n, m in zip(t["Next club"], rows["moved_club"])]
        t["Next pos"] = [n if c else "same" for n, c in zip(t["Next pos"], rows["changed_pos"])]
        t = t.reset_index(drop=True)
        t.index = t.index + 1
        r.table(t.to_html(border=0, classes="t", float_format=lambda v: f"{v:.2f}"),
                f"{label}: 15 largest.")
        r.commentary(comment)
    r.commentary(_comment_tails(oos))

    # §8 what drives the served model
    r.section("What drives the served model",
              f"The model trained to {config.season_label(config.TRAIN_THROUGH)}, applied to "
              f"{len(score):,} players from {config.season_label(config.SCORE_SEASON)}.")
    push = contributions(fitted, train, score)
    r.commentary(
        "<b>What “push” means.</b> Start from the price the model would give a perfectly "
        "average training player. Each input group then pushes a real player's price up or "
        "down from there: the group's weight × (his value − the average value), summed over "
        "the group's terms. A player with far more goals than average gets a big upward goals "
        "push; a cheap player gets a big downward price push. The pushes plus the average "
        "player's price add up exactly to his predicted price (see the worked example below). F13 and T10 show the "
        "<i>typical size</i> of each push across all players, ignoring its direction: how much "
        "that group usually moves a price, either way.")
    typical = (push.drop(columns="element_type").abs().groupby(push["element_type"]).mean().T
               .reindex(columns=POSITIONS))
    typical.columns.name = None
    typical["All"] = push.drop(columns="element_type").abs().mean()
    typical = typical.sort_values("All", ascending=False)
    typical.index = [GROUP_LABELS.get(k, k) for k in typical.index]
    r.fig(f_contributions(push), "Typical size of each input group's push, by position.")
    r.commentary(notes.contributions(typical))
    r.table(table_html(typical, ["Input group"]), "Typical push (£m) by input group and position.")
    r.commentary(notes.typical_table(typical, float(fitted.result.params["value_season"])))
    example = push_example(fitted, train, score, push)
    r.table(example.to_html(border=0, classes="t", float_format=lambda v: f"{v:+.3f}"),
            "Worked example: two players' pushes, signed, from the average player to the "
            "predicted price.")
    r.commentary(notes.worked_example(example))
    coefs = fitted.coefficients().set_index("term")
    r.table(coefs[["estimate", "std_error", "conf_low", "conf_high", "p_value"]]
            .to_html(border=0, classes="t", float_format=lambda v: f"{v:.5g}"),
            "Fitted coefficients with 95% confidence intervals.")
    r.commentary(notes.coefficients(coefs))
    clubs = coefs[coefs.index.str.startswith("team_name_")].copy()
    clubs.index = clubs.index.str.replace("team_name_", "").str.replace("_", " ")
    r.fig(f_coef_dots(clubs, "Other clubs (reference)"),
          "Club coefficients with 95% intervals: what playing for each club adds to next "
          "season's price, against the pooled “other” clubs (hollow, 0). Clubs under "
          f"{config.TEAM_LUMP_THRESHOLD:.0%} of training rows, and clubs the training seasons never saw "
          "(newly promoted sides), are pooled there.")
    r.commentary(notes.clubs(clubs))
    positions = coefs[coefs.index.str.startswith("element_type_")].copy()
    positions.index = positions.index.str.replace("element_type_", "")
    r.fig(f_coef_dots(positions, "GK", POS_COLOURS, POS_SYMBOLS),
          "Position coefficients with 95% intervals, against goalkeepers (hollow, 0), with "
          "everything else about the season held equal.")
    r.commentary(notes.positions_coef(positions))

    # §9 the squared price terms
    linear = model.PriceModel(numeric=price_analysis.LINEAR_NUMERIC).fit(train)
    curve = price_slope(fitted, float(train["start_cost"].round(1).max()), linear)
    r.section("Why the price terms are squared",
              "Price enters the model four times: start price, end price, and each squared. "
              "The squares let the relationship between this season's price and next "
              "season's bend, instead of being one straight line for every player.")
    r.fig(f_what_fpl_did(frame), "What FPL actually did: the average next-season start price "
          "for players who started this season at each price (dot size = number of players). "
          "Above the dashed line, prices rose on average; below it, they fell.")
    r.commentary(notes.fpl_curve(frame))
    fig_fpl = f"F{r.fig_n}"
    r.fig(f_slope(curve), "How much of each £1 of this season's price the model carries into "
          "next season (start and end price moved together), with and without the squared "
          "terms. Shaded: 95% interval.")
    r.commentary(notes.slope(curve))
    r.fig(f_slope_split(curve), "The same, split: moving only the start price, or only the "
          "end price. Shaded: 95% interval. Start and end price move together for most "
          "players, so each line alone is less certain than their sum in the chart above.")
    r.commentary(notes.slope_split(curve))
    both = []
    for label, g in oos.groupby("band", observed=True):
        e, el = g["error"], g["pred_linear"] - g["actual"]
        both.append({"band": label, "n": len(g), "mean": e.mean(), "sd": e.std(),
                     "rmse": np.sqrt((e ** 2).mean()), "lin_mean": el.mean(),
                     "lin_sd": el.std(), "lin_rmse": np.sqrt((el ** 2).mean())})
    both = pd.DataFrame(both).set_index("band")
    r.fig(f_squares_bands(both), f"Mean error ± 1 SD per start-price band, {oos_label}, "
          "with and without the squared terms.")
    r.commentary(notes.squares_bands(both))
    shown = both.rename(columns={"mean": "Mean error", "sd": "SD of error", "rmse": "RMSE",
                                 "lin_mean": "Mean error (no squares)",
                                 "lin_sd": "SD (no squares)", "lin_rmse": "RMSE (no squares)"})
    r.table(table_html(shown, ["Start price"]), "The numbers behind the chart above.")
    r.commentary(notes.squares_table(both))
    at = curve.set_index("price")
    lo, hi = at.index.min(), at.index.max()
    mid = 8.0 if 8.0 in at.index else at.index[len(at) // 2]
    floor = frame.assign(p=frame["start_cost"].round(1)).groupby("element_type",
                                                                 observed=True)["p"].min()
    floor_text = " or ".join(
        f"£{v:.1f}m ({', '.join(floor[floor == v].index)})" for v in sorted(floor.unique()))
    fpl = (frame.assign(price=frame["start_cost"].round(1)).groupby("price")
           .agg(next=(model.TARGET, "mean"), n=(model.TARGET, "size")))
    fpl = fpl[fpl["n"] >= 8]
    fpl["diff"] = fpl["next"] - fpl.index
    falls_from = next(p for p in fpl.index if (fpl.loc[p:, "diff"] < 0).all())
    deepest = fpl["diff"].idxmin()
    r.commentary(f"""<b>Reading §9 together: what the squares capture, in FPL terms</b><ul>
<li><b>The price floor.</b> No start price in the data is below {floor_text}, so cheap
players have little room to fall. In {fig_fpl}
the bottom of the curve sits above the no-change line: cheap players more often rise than
fall. Near the floor, next season's price depends more on the floor than on this season's
price, so the model carries only £{at.loc[lo, "carried"]:.2f} of each £1 at £{lo:.1f}m.</li>
<li><b>At the top, price gaps carry over.</b> Stars are cut too: in {fig_fpl} the average
£{deepest:.1f}m starter begins next season £{-fpl.loc[deepest, "diff"]:.2f}m cheaper. But the fit
says a £1 price difference between two premiums mostly survives the summer:
£{at.loc[hi, "carried"]:.2f} of each £1 at £{hi:.1f}m, against £{at.loc[mid, "carried"]:.2f}
at £{mid:.1f}m. This is a slope, not a level: it says how far apart two stars stay, not how
much of his price one star keeps.</li>
<li><b>Above the floor, FPL trims.</b> From £{falls_from:.1f}m up, the average next price sits
below the no-change line in {fig_fpl}: FPL tends to take back some of a player's value each
August. A straight line has to pick one slope
(£{curve["linear"].iloc[0]:.2f} per £1, everywhere): too steep at the floor, too shallow for
stars, and it mis-prices both ends. That shows in the errors: without the squares the model
leans further off zero in most bands, and at £10m+ it flips to under-pricing the stars.</li>
<li><b>At the top, the end price matters more.</b> Split apart, the model leans on where a
premium <i>finished</i> the season (the market's verdict, through transfers) more than where he
started. For cheap players the two count about equally. Treat this split as indicative:
start and end price are closely tied, so their separate effects are much less certain than
their total.</li>
<li><b>Why a square, not tiers or splines.</b> Two extra numbers give a smooth curve that
bends the right way at both ends, and keep the model linear, so every price still breaks
down exactly into its parts. Natural splines and per-tier adjustments were tried during the
feature work and did no better out of sample (see the README); that comparison is not
rerun here.</li></ul>""")

    # §10 what FPL did
    r.section("What FPL actually did", "Descriptive: every transition "
              f"{config.season_label(int(frame['season'].min()))} to "
              f"{config.season_label(int(frame['season'].max()))}, no model involved.")
    moved = tag(frame.assign(pred=np.nan, actual=frame[model.TARGET]))
    for name, test, _, _ in MOVE_BANDS:
        moved[name] = test(moved["move"])
    shares = moved.groupby(["element_type", "tier"], observed=True)[
        [b[0] for b in MOVE_BANDS]].mean()
    r.fig(f_moves(frame), "Share of players whose price fell sharply (£1.0m or more), fell, "
          "held (unchanged), rose, or rose sharply (£1.0m or more), by position and tier.")
    r.commentary(notes.moves(shares))
    r.fig(f_reset_scatter(frame), "The summer change: each player's start price for the new "
          "season minus his final price last season, one point per player-season. Above the "
          "dashed line FPL raised his price over the summer; below it, FPL cut it. Black "
          "steps: the median change in each final-price band (bands split by the thin "
          "vertical lines). The diagonal stripes are "
          "FPL's start prices, which sit on a £0.5m grid. Points are spread by up to "
          f"±£{JITTER:.2f}m so ones sharing a price stay visible; hover shows the exact prices.")
    r.commentary(notes.reset(frame))

    # §11 the model, written out
    r.section("The model, written out",
              f"The served model: fitted on {len(train):,} player-seasons "
              f"({config.season_label(config.FIRST_SEASON)} to "
              f"{config.season_label(config.TRAIN_THROUGH)}). Every price in the app is this "
              "one line of arithmetic.")
    r.equation(equation_symbolic(fitted), "The model in symbols: one weight (β) per input, "
               "plus a position and a club adjustment.")
    r.equation(equation_numeric(fitted), "The same model with its fitted weights, rounded to "
               "four significant figures (the app computes with the full ones).")
    r.table(adjustments_html(fitted), "The position and club adjustments: what each adds to "
            "the price, against goalkeepers and against the pooled “other” clubs.")
    r.table(legend_html(fitted), "What each name in the equation stands for.")
    r.commentary(notes.equation(fitted.result.params, _numeric_terms(fitted), EQ_NAMES))

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    r.write(OUT, header)
    print(f"Wrote {OUT.relative_to(config.PROJECT_DIR)}: {r.fig_n} figures, {r.tab_n} tables")


if __name__ == "__main__":
    main()
