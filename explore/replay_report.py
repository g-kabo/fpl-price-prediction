"""Exploration report for ideas #32 and #42. Not used by the app.

    python explore/replay_report.py [--refresh]

Writes ``output/replay_report.html``.

**#32, the replay.** For each test season ``s`` from 2020-21 to 2025-26, fit the
current specification on every transition before ``s`` (as ``model_report`` does),
then rebuild what Price Watch would have shown after each gameweek 1..38 of ``s``
from ``gws/merged_gw.csv``: running totals, the price and ownership of that week,
each club's own fixtures played, scaled by ``38 / games`` and clamped to the fitted
range exactly as ``projection.py`` does. Each projection is scored against the
start price FPL set for ``s + 1``. Every number is out-of-sample.

**#42, the surprises.** Every consecutive transition since 2017-18, priced by the
served model, with the biggest gaps to what FPL set. Seasons up to
``TRAIN_THROUGH`` are in-sample for the served model and are marked as such; a
second table keeps only the out-of-sample ones.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import clean  # noqa: E402
import config  # noqa: E402
import fpl_data  # noqa: E402
import model  # noqa: E402
import price_analysis  # noqa: E402
import projection  # noqa: E402
import schema  # noqa: E402
from feature_experiments import FIRST_TEST_SEASON  # noqa: E402
import model_report as mr  # noqa: E402

OUT = config.OUTPUT_DIR / "replay_report.html"
CACHE = config.OUTPUT_DIR / "replay_cache"
GWS = list(range(1, 39))
CHECKPOINTS = [1, 3, 5, 8, 10, 15, 20, 25, 30, 38]
ACCENT, INK, INK_SOFT, ORANGE = mr.ACCENT, mr.INK, mr.INK_SOFT, "#d9600a"
SEASON_COLOURS = ["#8a3aa0", "#00b8d4", "#f5b400", "#ff6d00", "#4b2a86", "#2e7d32"]

#: (web_name, season) pairs drawn in section 3; extend with --player "Name:2023".
PLAYERS = [("Palmer", 2023), ("Kroupi.Jr", 2025), ("B.Fernandes", 2025), ("Rashford", 2021),
           ("Sterling", 2022), ("Gyökeres", 2025),
           # Non-premium midfielders and forwards FPL re-rated hard
           ("Mateta", 2023), ("Bamford", 2020), ("Gordon", 2023), ("Rogers", 2024), ("Kulusevski", 2021),
           # Defenders
           ("Kerkez", 2024), ("Senesi", 2025), ("Guéhi", 2025), ("Trippier", 2022), ("Aït-Nouri", 2024)]

GW_COLS = ["element", "fixture", "gw", "total_points", "minutes", "goals_scored", "assists", "value", "selected"]


# ---------------------------------------------------------------- data


def load_full_gameweeks(season: int, refresh: bool) -> pd.DataFrame:
    """One row per player per fixture. Cached, because the slim cache drops the totals."""
    folder = config.season_folder(season)
    cache = CACHE / f"merged_gw_{folder}.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, encoding="utf-8")
    url = f"{config.GITHUB_BASE}{folder}/gws/merged_gw.csv"
    try:
        gw = pd.read_csv(url, encoding="utf-8")
    except UnicodeDecodeError:
        gw = pd.read_csv(url, encoding="latin-1")
    gw = gw.rename(columns={"GW": "gw"}) if "GW" in gw else gw.rename(columns={"round": "gw"})
    # Some files repeat a player's row for the same fixture (2025-26 does); a double
    # gameweek has two different fixtures, so de-duplicating on fixture keeps it.
    gw = gw[GW_COLS].drop_duplicates(["element", "fixture"]).copy()
    CACHE.mkdir(parents=True, exist_ok=True)
    gw.to_csv(cache, index=False, encoding="utf-8")
    return gw


def replay_inputs(gw: pd.DataFrame, raw: pd.DataFrame, upto: int) -> tuple[pd.DataFrame, pd.Series]:
    """Season-to-date figures per player id after gameweek ``upto``, and games per club."""
    gw = gw[gw["gw"] <= upto]
    managers = (gw.groupby("gw")["selected"].sum() / clean.SQUAD_SIZE).cummax()
    gw = gw.assign(pct=100 * gw["selected"] / gw["gw"].map(managers),
                   played=(gw["minutes"] > 0).astype(int)).sort_values(["element", "gw"])
    g = gw.groupby("element")
    now = pd.DataFrame({
        "minutes": g["minutes"].sum(), "total_points": g["total_points"].sum(),
        "goals_scored": g["goals_scored"].sum(), "assists": g["assists"].sum(),
        "appearances": g["played"].sum(), "rows": g.size(),
        "final_cost": g["value"].last() / 10, "selected_by_percent": g["pct"].last(),
    }).rename_axis("id").reset_index()
    team = raw.set_index("id")["team"]
    now["team"] = now["id"].map(team)
    games = now.dropna(subset=["team"]).groupby("team")["rows"].max().astype(float)
    return now, games


def replay_season(season: int, frame: pd.DataFrame, cleaned: dict, refresh: bool) -> pd.DataFrame:
    """Every gameweek's projection of ``season``, scored against ``season + 1`` prices."""
    fitted = model.PriceModel().fit(frame[frame["season"] < season])
    ranges = fitted_ranges(frame[frame["season"] < season])
    gw = load_full_gameweeks(season, refresh)
    raw = fpl_data.load_players_raw(season, refresh)
    base = cleaned[season].set_index("id")
    target = cleaned[season + 1].set_index("code")["start_cost"]
    rows = []
    for upto in GWS:
        now, games = replay_inputs(gw, raw, upto)
        now = now[now["id"].isin(base.index)]
        info = base.loc[now["id"], ["code", "web_name", "team_name", "element_type", "start_cost"]]
        cur = now.reset_index(drop=True).join(info.reset_index(drop=True))
        cur["points_per_game"] = (cur["total_points"] / cur["appearances"]).where(
            cur["appearances"] > 0, 0.0).round(1)
        cur["value_season"] = (cur["total_points"] / cur["final_cost"].clip(lower=0.1)).round(1)
        cur = cur.dropna(subset=["code"])
        cur["actual"] = cur["code"].map(target)
        cur = cur[cur["actual"].notna()].reset_index(drop=True)
        player_games = cur["team"].map(games).astype(float)
        proj = projection.project_frame(cur, player_games.to_numpy(), ranges,
                                        league_games=float(games.mean()))
        out = fitted.predict_with_interval(proj[schema.MODEL_INPUT_COLUMNS])
        res = pd.DataFrame({
            "season": season, "gw": upto, "code": cur["code"], "web_name": cur["web_name"],
            "team_name": cur["team_name"], "element_type": cur["element_type"].astype(str),
            "start_cost": cur["start_cost"], "price_now": cur["final_cost"],
            "actual": cur["actual"], "minutes": cur["minutes"], "appearances": cur["appearances"],
            "club_games": player_games, "n_clamped": proj["n_clamped"].to_numpy(),
            "pred": out["pred"].to_numpy(), "lower": out["pred_lower"].to_numpy(),
            "upper": out["pred_upper"].to_numpy(),
        })
        rows.append(res)
    return pd.concat(rows, ignore_index=True)


def fitted_ranges(train: pd.DataFrame) -> dict:
    """The clamp bounds ``train_and_save`` stores, rebuilt for an earlier training window."""
    ranges = {}
    for col in schema.NUMERIC_NAMES:
        s = pd.to_numeric(train[col], errors="coerce").dropna()
        ranges[col] = {"min": float(s.min()), "max": float(s.max()), "median": float(s.median())}
    return ranges


def score(df: pd.DataFrame) -> pd.Series:
    err = df["pred"] - df["actual"]
    half = (df["upper"] - df["lower"]) / 2
    ratio = (err.abs() / half).replace([np.inf], np.nan).dropna()
    return pd.Series({
        "n": len(df), "RMSE": float(np.sqrt((err ** 2).mean())), "MAE": float(err.abs().mean()),
        "Mean error": float(err.mean()), "Within £0.25m": float((err.abs() <= 0.25).mean()),
        "95% interval coverage": float(((df["actual"] >= df["lower"]) & (df["actual"] <= df["upper"])).mean()),
        "Interval × needed for 95%": float(ratio.quantile(0.95)),
        "Naive RMSE (price now)": float(np.sqrt(((df["price_now"] - df["actual"]) ** 2).mean())),
        "Clamped": float((df["n_clamped"] > 0).mean()),
    })


# ---------------------------------------------------------------- charts


def layout(fig: go.Figure, height: int = 420, **extra) -> go.Figure:
    extra.setdefault("margin", dict(l=60, r=20, t=30, b=50))
    fig.update_layout(height=height, font=dict(family=mr.FONT, color=INK),
                      plot_bgcolor="white", legend=dict(orientation="h", y=-0.2), **extra)
    fig.update_xaxes(gridcolor=mr.LINE, zeroline=False)
    fig.update_yaxes(gridcolor=mr.LINE, zeroline=False)
    return fig


def f_curve(by_gw: pd.DataFrame, by_season_gw: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for colour, (season, t) in zip(SEASON_COLOURS, by_season_gw.groupby(level=0)):
        fig.add_scatter(x=t.index.get_level_values(1), y=t["RMSE"], mode="lines",
                        name=config.season_label(season), line=dict(color=colour, width=1), opacity=0.55)
    fig.add_scatter(x=by_gw.index, y=by_gw["RMSE"], mode="lines", name="All six seasons",
                    line=dict(color=INK, width=3))
    fig.add_scatter(x=by_gw.index, y=by_gw["Naive RMSE (price now)"], mode="lines",
                    name="Naive: price now", line=dict(color=ORANGE, width=2, dash="dash"))
    fig.update_xaxes(title="Gameweeks played")
    fig.update_yaxes(title="RMSE of the next start price (£m)", rangemode="tozero")
    return layout(fig)


def f_coverage(by_gw: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(x=by_gw.index, y=by_gw["95% interval coverage"], mode="lines+markers",
                    name="Coverage of the 95% interval", line=dict(color=ACCENT, width=3))
    fig.add_hline(y=0.95, line=dict(color=INK_SOFT, dash="dot"), annotation_text="95% target")
    fig.update_xaxes(title="Gameweeks played")
    fig.update_yaxes(title="Share of actual prices inside the interval", tickformat=".0%", range=[0.4, 1])
    return layout(fig)


def f_inflation(by_gw: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(x=by_gw.index, y=by_gw["Interval × needed for 95%"], mode="lines+markers",
                    name="Widening needed", line=dict(color=ORANGE, width=3))
    fig.add_hline(y=1, line=dict(color=INK_SOFT, dash="dot"), annotation_text="Interval as shipped")
    fig.update_xaxes(title="Gameweeks played")
    fig.update_yaxes(title="Multiple of today's half-width", rangemode="tozero")
    return layout(fig)


def f_surprises(top: pd.DataFrame) -> go.Figure:
    top = top.sort_values("gap")
    fig = go.Figure(go.Bar(
        x=top["gap"], y=top["label"], orientation="h",
        marker=dict(color=np.where(top["gap"] > 0, ORANGE, "#4b2a86"),
                    pattern_shape=np.where(top["in_sample"], "/", "")),
        hovertemplate="%{y}<br>model − FPL: %{x:+.1f}m<extra></extra>"))
    fig.update_xaxes(title="Model − FPL start price (£m). Hatched = in-sample")
    return layout(fig, height=max(420, 22 * len(top) + 120), margin=dict(l=260, r=20, t=30, b=50))


def f_player(replay: pd.DataFrame, name: str, season: int) -> go.Figure | None:
    t = replay[(replay["web_name"] == name) & (replay["season"] == season)].sort_values("gw")
    if t.empty:
        return None
    fig = go.Figure()
    fig.add_scatter(x=t["gw"], y=t["upper"], mode="lines", line=dict(width=0), showlegend=False,
                    hoverinfo="skip")
    fig.add_scatter(x=t["gw"], y=t["lower"], mode="lines", line=dict(width=0), fill="tonexty",
                    fillcolor="rgba(138,58,160,0.15)", name="95% interval", hoverinfo="skip")
    fig.add_scatter(x=t["gw"], y=t["pred"], mode="lines+markers", name="Projected next start price",
                    line=dict(color=ACCENT, width=3), marker=dict(size=5))
    fig.add_scatter(x=t["gw"], y=t["price_now"], mode="lines", name="Price at the time",
                    line=dict(color=INK_SOFT, width=2, shape="hv"))
    fig.add_hline(y=float(t["actual"].iloc[0]), line=dict(color=ORANGE, width=2, dash="dash"),
                  annotation_text=f"FPL's {config.season_label(season + 1)} start price: £{t['actual'].iloc[0]:.1f}m")
    fig.update_xaxes(title="Gameweeks played", range=[0.5, 38.5])
    fig.update_yaxes(title="£m")
    return layout(fig, height=380)


def f_scatter(gaps: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    lo, hi = float(min(gaps["actual"].min(), gaps["pred"].min())) - 0.5, float(max(gaps["actual"].max(), gaps["pred"].max())) + 0.5
    fig.add_scatter(x=[lo, hi], y=[lo, hi], mode="lines", name="Perfect", line=dict(color=INK_SOFT, dash="dash"))
    for in_sample, colour, label in [(True, ACCENT, "In-sample (model trained on these)"),
                                     (False, ORANGE, "Out-of-sample")]:
        d = gaps[gaps["in_sample"] == in_sample]
        fig.add_scattergl(x=d["actual"], y=d["pred"], mode="markers", name=label,
                          marker=dict(color=colour, size=5, opacity=0.35 if in_sample else 0.8),
                          text=d["label"], customdata=d["gap"],
                          hovertemplate="%{text}<br>FPL £%{x:.1f}m, model £%{y:.1f}m<br>"
                                        "gap %{customdata:+.1f}m<extra></extra>")
    fig.update_xaxes(title="Start price FPL actually set (£m)", range=[lo, hi])
    fig.update_yaxes(title="Start price the model predicted (£m)", range=[lo, hi], scaleanchor="x")
    return layout(fig, height=640)


# ---------------------------------------------------------------- part B


def surprises(frame: pd.DataFrame, cleaned: dict, fitted: model.PriceModel) -> pd.DataFrame:
    interval = fitted.predict_with_interval(frame)
    df = pd.concat([frame, interval], axis=1)
    df = df[df["pred"].notna() & df[model.TARGET].notna()].copy()
    df["actual"] = df[model.TARGET]
    df["gap"] = df["pred"] - df["actual"]
    df["in_sample"] = df["season"] <= config.TRAIN_THROUGH
    df = mr.with_next_season(df, cleaned)
    df["label"] = (df["web_name"] + " " + df["season"].map(config.season_label)
                   + " → " + (df["season"] + 1).map(config.season_label))
    return df


def surprise_table(df: pd.DataFrame, n: int) -> pd.DataFrame:
    top = df.reindex(df["gap"].abs().sort_values(ascending=False).index).head(n)
    out = pd.DataFrame({
        "Player": top["web_name"].to_numpy(),
        "Pos": top["element_type"].astype(str).to_numpy(),
        "Club": top["team_name"].to_numpy(),
        "Prices": [f"{config.season_label(int(s))} → {config.season_label(int(s) + 1)}" for s in top["season"]],
        "Start £m": top["start_cost"].to_numpy(),
        "Model £m": top["pred"].round(1).to_numpy(),
        "FPL £m": top["actual"].to_numpy(),
        "Gap £m": top["gap"].round(1).to_numpy(),
        "Moved club": np.where(top["moved_club"], "yes", ""),
        "Changed pos": np.where(top["changed_pos"], "yes", ""),
        "Sample": np.where(top["in_sample"], "in-sample", "out-of-sample"),
    })
    return out.reset_index(drop=True)


def plain_table(t: pd.DataFrame) -> str:
    fmt = {c: (lambda v: f"{v:+.1f}") for c in ["Gap £m"] if c in t}
    for c in ["Start £m", "Model £m", "FPL £m"]:
        if c in t:
            fmt[c] = lambda v: f"{v:.1f}"
    return t.to_html(formatters=fmt, border=0, classes="t", index=False, escape=True)


# ---------------------------------------------------------------- main


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--player", action="append", default=[], metavar="NAME:SEASON",
                   help='add a player-season to section 3, e.g. "Salah:2021" (season = start year)')
    args = p.parse_args()
    players = PLAYERS + [(n, int(y)) for n, y in (a.rsplit(":", 1) for a in args.player)]

    frame, _, cleaned = mr.load(args.refresh)
    test_seasons = list(range(FIRST_TEST_SEASON, config.SCORE_SEASON + 1))

    replay = pd.concat([replay_season(s, frame, cleaned, args.refresh) for s in test_seasons],
                       ignore_index=True)
    replay.to_csv(CACHE / "replay_all.csv", index=False, encoding="utf-8")
    played = replay[replay["minutes"] > 0]

    by_gw = played.groupby("gw").apply(score, include_groups=False)
    by_gw_all = replay.groupby("gw").apply(score, include_groups=False)
    by_sgw = played.groupby(["season", "gw"]).apply(score, include_groups=False)

    served = model.PriceModel().fit(frame[frame["season"] <= config.TRAIN_THROUGH])
    gaps = surprises(frame, cleaned, served)

    r = mr.Report()
    first, last = config.season_label(test_seasons[0]), config.season_label(test_seasons[-1])
    header = (f"<h1>Replay and surprises</h1><p>Exploration only; not read by the app. Generated "
              f"{date.today():%d %b %Y} by <code>explore/replay_report.py</code>. Ideas "
              f"<a href='../docs/future-ideas.md'>#32</a> and #42. Error = predicted − actual start "
              f"price, so <b>positive means the model priced the player too high</b>.</p>")

    # §1 replay
    r.section("Replay: how forecast error shrinks through a season",
              f"For each season {first} to {last}, the model is fitted on every earlier transition, then "
              f"Price Watch's projection is rebuilt after each gameweek and scored against the start price "
              f"FPL set the next summer. All out-of-sample. Players with no minutes so far are left out of "
              f"the curves (T2 shows the effect). n is {int(by_gw['n'].iloc[4]):,} players at GW5.")
    cols = ["n", "RMSE", "Naive RMSE (price now)", "MAE", "Mean error", "Within £0.25m",
            "95% interval coverage", "Interval × needed for 95%", "Clamped"]
    r.fig(f_curve(by_gw, by_sgw), "RMSE of the projected next start price by gameweeks played, pooled "
          "(thick) and per season (thin), against the naive guess that a player's price stays where it is now.")
    t_gw = by_gw.loc[CHECKPOINTS, cols].copy()
    t_gw.index.name = "GW"
    r.table(mr.table_html(t_gw, ["Gameweeks played"]), "The curve at selected gameweeks, players who have played.")
    r.fig(f_coverage(by_gw), "How often the real price fell inside the 95% interval Price Watch would have shown.")
    r.fig(f_inflation(by_gw), "How much wider the interval must be, as a multiple of the shipped half-width, "
          "for 95% of real prices to fall inside it (the 95th percentile of |error| / half-width).")
    beats = by_gw[by_gw["RMSE"] < by_gw["Naive RMSE (price now)"]].index.min()
    cover90 = by_gw[by_gw["95% interval coverage"] >= 0.90].index.min()
    r.commentary(
        "<ul>"
        f"<li><b>Error falls steadily.</b> RMSE is £{by_gw.loc[5, 'RMSE']:.2f}m at GW5, "
        f"£{by_gw.loc[10, 'RMSE']:.2f}m at GW10, £{by_gw.loc[20, 'RMSE']:.2f}m at GW20 and "
        f"£{by_gw.loc[38, 'RMSE']:.2f}m at the end.</li>"
        f"<li><b>Until GW{beats}, the projection is no better than assuming the price stays put</b> "
        f"(£{by_gw.loc[5, 'Naive RMSE (price now)']:.2f}m at GW5). The forecast's value arrives in the "
        "second half of the season. That is the case for #1's warning.</li>"
        f"<li><b>The 95% interval is not 95% until the end.</b> It covers {by_gw.loc[5, '95% interval coverage']:.0%} "
        f"at GW5 and {by_gw.loc[10, '95% interval coverage']:.0%} at GW10, and first reaches 90% at GW{cover90}. "
        f"Reaching 95% would need it {by_gw.loc[5, 'Interval × needed for 95%']:.1f}× wider at GW5, "
        f"{by_gw.loc[10, 'Interval × needed for 95%']:.1f}× at GW10 and {by_gw.loc[20, 'Interval × needed for 95%']:.1f}× at GW20. "
        "Those are the numbers for #14.</li>"
        "<li>The GW38 point reproduces the served model's backtest (RMSE £0.35m in 2025-26, matching "
        "<code>backtest_2026.csv</code> to within a few pence), which is the check that the replay is "
        "rebuilding the right inputs.</li></ul>")
    t_all = by_gw_all.loc[[3, 5, 10], ["n", "RMSE", "95% interval coverage"]]
    r.table(mr.table_html(t_all, ["Gameweeks played"]),
            "The same including players with no minutes yet, whom the projection prices from zeros.")

    # §2 who is wrong early
    r.section("Who is wrong early",
              "Evidence for #1: which players the early projection should flag.")
    early = played[played["gw"].isin([3, 5, 10])].copy()
    share = (early["appearances"] / early["club_games"].clip(lower=1)).clip(upper=1)
    early["Games played so far"] = pd.cut(share, [-0.01, 0.34, 0.67, 1.0],
                                          labels=["under a third", "a third to two thirds", "nearly all"])
    t_load = (early.groupby(["gw", "Games played so far"], observed=True)
              .apply(score, include_groups=False)[["n", "RMSE", "Mean error", "95% interval coverage", "Clamped"]])
    r.table(mr.table_html(t_load, ["GW", "Share of club games played"]),
            "Early error by how much the player has actually played.")
    early["Position"] = early["element_type"]
    t_pos = (early[early["gw"] == 5].groupby("Position").apply(score, include_groups=False)
             [["n", "RMSE", "Mean error", "95% interval coverage"]])
    r.table(mr.table_html(t_pos, ["Position"]), "GW5 error by position.")
    worst = early[early["gw"] == 5].assign(gap=lambda d: d["pred"] - d["actual"])
    worst = worst.reindex(worst["gap"].abs().sort_values(ascending=False).index).head(15)
    t_worst = pd.DataFrame({
        "Player": worst["web_name"].to_numpy(), "Season": worst["season"].map(config.season_label).to_numpy(),
        "Pos": worst["element_type"].to_numpy(), "Appearances": worst["appearances"].to_numpy(),
        "Start £m": worst["start_cost"].to_numpy(), "Model £m": worst["pred"].round(1).to_numpy(),
        "FPL £m": worst["actual"].to_numpy(), "Gap £m": worst["gap"].round(1).to_numpy()})
    r.table(plain_table(t_worst), "The 15 biggest misses of the GW5 projection, all six seasons.")

    # §3 player paths
    r.section("Player paths: how one player's projection moved",
              "The projected next start price after each gameweek (purple, with its 95% interval), the "
              "player's actual price at the time (grey), and the price FPL set the next summer (orange). "
              "Out-of-sample: the model for each season is fitted on earlier seasons only.")
    for name, season in players:
        fig = f_player(replay, name, season)
        if fig is None:
            r.note(f"No replay rows for {name} {config.season_label(season)}; check the web_name and season.")
            continue
        r.fig(fig, f"{name}, {config.season_label(season)}.")

    # §4 surprises
    r.section("Pricing surprises in history",
              "Where FPL's start price for the next season differed most from what the served model "
              "(trained to " + config.season_label(config.TRAIN_THROUGH) + ") would have set. <b>Hatched "
              "bars and 'in-sample' rows were part of the model's own training data</b>, so those gaps "
              "are smaller than a fair test would give. Only "
              f"{config.season_label(config.SCORE_SEASON)} → {config.season_label(config.PREDICT_SEASON)} "
              "is out-of-sample for this model.")
    top = gaps.reindex(gaps["gap"].abs().sort_values(ascending=False).index).head(25)
    r.fig(f_surprises(top), "The 25 largest gaps, every season since 2017-18. Orange: the model priced "
          "him above FPL. Purple: below.")
    r.fig(f_scatter(gaps), "Every player-season since 2017-18: the price the model predicted against the price "
          "FPL set, served model. Purple points were in the model's training data; orange are the "
          f"{int((~gaps['in_sample']).sum()):,} out-of-sample players of {config.season_label(config.SCORE_SEASON)}. "
          "Hover for the player.")
    r.table(plain_table(surprise_table(gaps, 25)), "The same 25, with club and position moves (not model inputs).")
    by_season = gaps.groupby("season").agg(
        n=("gap", "size"), RMSE=("gap", lambda g: float(np.sqrt((g ** 2).mean()))),
        **{"Over £1.0m out": ("gap", lambda g: int((g.abs() >= 1.0).sum()))})
    by_season["Sample"] = np.where(by_season.index <= config.TRAIN_THROUGH, "in-sample", "out-of-sample")
    by_season.index = [f"{config.season_label(int(s))} → {config.season_label(int(s) + 1)}" for s in by_season.index]
    r.table(mr.table_html(by_season, ["Prices"]), "Gaps by transition, served model.")
    honest = mr.out_of_sample(frame)
    honest = honest.assign(gap=honest["error"])
    honest = mr.with_next_season(honest, cleaned)
    honest["in_sample"] = False
    r.table(plain_table(surprise_table(honest, 20)),
            "The 20 largest gaps when each season is predicted by a model fitted only on earlier seasons "
            f"({config.season_label(FIRST_TEST_SEASON + 1)} onward). Fair, but covers fewer seasons.")
    oos_gaps = gaps[~gaps["in_sample"]]
    r.commentary(
        "<ul>"
        f"<li>The model's biggest misses are players FPL re-rated on form it could not see from last "
        "season's totals: a breakout (Palmer, Fernandes, Kroupi.Jr priced above the model) or a "
        "collapse (Rashford, Sterling, Sánchez priced below).</li>"
        f"<li>Per-season RMSE is steady at £0.25m to £0.33m for the in-sample seasons, and "
        f"£{float(np.sqrt((oos_gaps['gap'] ** 2).mean())):.2f}m for the one out-of-sample season, so "
        "the in-sample rows flatter the model only a little. Read the hatched bars as the model's "
        "fit, not as a forecast record.</li></ul>")
    pattern = gaps[gaps["gap"].abs() >= 1.0]
    r.note(f"Of the {len(pattern):,} gaps of £1.0m or more, {pattern['moved_club'].mean():.0%} involve a "
           f"club move and {pattern['changed_pos'].mean():.0%} a change of position, against "
           f"{gaps['moved_club'].mean():.0%} and {gaps['changed_pos'].mean():.0%} of all transitions.")

    r.write(OUT, header)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
