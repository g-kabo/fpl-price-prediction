"""Matplotlib translations of the ggplot figures in the R.

Each function saves a PNG into ``output/plots/`` and returns its path.
Colours follow the R's ``scale_colour_brewer(palette = "Set1")`` so the
figures stay recognisable next to the originals.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display on this box; write straight to file

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config

#: Set1, ordered to match the R's direction = -1 (FWD first). Defined in
#: :mod:`config` so the app's charts colour positions the same way.
POSITION_COLOURS = config.POSITION_COLOURS

_MONEY = "£{:.0f}m"


def _save(fig, name: str) -> Path:
    config.PLOT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.PLOT_DIR / name
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return path


def _grid(n: int, ncols: int, size: tuple[float, float]):
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(size[0] * ncols, size[1] * nrows))
    return fig, np.atleast_1d(axes).ravel(), nrows


def _money_axes(ax) -> None:
    fmt = matplotlib.ticker.FuncFormatter(lambda v, _: _MONEY.format(v))
    ax.xaxis.set_major_formatter(fmt)
    ax.yaxis.set_major_formatter(fmt)


def predicted_vs_actual_by_season(df: pd.DataFrame, name: str = "predicted_vs_actual_by_season.png") -> Path:
    """R lines 1274-1292: test-set fit, one panel per season.

    The dashed 45-degree line is where a perfect prediction would sit;
    systematic drift away from it in a particular season is the thing worth
    looking for, since that is what a model fitted across eight seasons of
    changing price inflation would show.
    """
    seasons = sorted(df["season"].unique())
    fig, axes, _ = _grid(len(seasons), 4, (3.4, 3.2))

    for ax, season in zip(axes, seasons):
        panel = df[df["season"] == season]
        for position, colour in POSITION_COLOURS.items():
            sub = panel[panel["element_type"] == position]
            ax.scatter(sub["pred"], sub["next_cost"], s=9, color=colour, alpha=0.7, label=position)
        lims = [df["pred"].min() - 0.5, df["pred"].max() + 0.5]
        ax.plot(lims, lims, ls="--", color="#2166AC", lw=1)
        ax.set_title(config.season_label(season), fontsize=10)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Actual")
        _money_axes(ax)
        ax.grid(alpha=0.25)

    for ax in axes[len(seasons):]:
        ax.axis("off")

    handles = [plt.Line2D([], [], marker="o", ls="", color=c, label=p) for p, c in POSITION_COLOURS.items()]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False)
    fig.suptitle("Predicted vs actual next-season starting price (held-out test set)", fontsize=13)
    fig.tight_layout(rect=[0, 0.04, 1, 0.97])
    return _save(fig, name)


def previous_vs_predicted_by_position(
    df: pd.DataFrame, predict_season: int, name: str = "previous_vs_predicted_by_position.png"
) -> Path:
    """R lines 1397-1414: last season's price against next season's prediction.

    Points above the diagonal are players the model expects to be priced up.
    """
    fig, axes, _ = _grid(len(config.POSITIONS), 2, (5.0, 4.4))

    for ax, position in zip(axes, config.POSITIONS):
        panel = df[df["element_type"] == position]
        ax.scatter(panel["start_cost"], panel["pred"], s=16, color=POSITION_COLOURS[position])
        lims = [
            min(panel["start_cost"].min(), panel["pred"].min()) - 0.3,
            max(panel["start_cost"].max(), panel["pred"].max()) + 0.3,
        ]
        ax.plot(lims, lims, ls="--", color="black", lw=1)
        for _, row in panel.nlargest(12, "pred").iterrows():
            ax.annotate(row["web_name"], (row["start_cost"], row["pred"]),
                        fontsize=7, xytext=(0, 5), textcoords="offset points", ha="center")
        ax.set_title(position, fontsize=11)
        ax.set_xlabel(f"{config.season_label(predict_season - 1)} starting price")
        ax.set_ylabel(f"Predicted {config.season_label(predict_season)} price")
        _money_axes(ax)
        ax.grid(alpha=0.25)

    fig.suptitle(
        f"Previous starting price vs predicted {config.season_label(predict_season)} price",
        fontsize=13,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    return _save(fig, name)


def team_prediction_intervals(
    df: pd.DataFrame, predict_season: int, top_n: int = 15,
    name: str = "team_prediction_intervals.png"
) -> Path:
    """R lines 1416-1438: per-team dot-and-interval plot.

    Grey dot is last season's starting price, coloured dot the prediction,
    and the bar the 95% prediction interval. Limited to each club's ``top_n``
    players by minutes, since the long tail of unused squad players carries
    no signal and would swamp the panel.
    """
    teams = sorted(df["team"].dropna().unique())
    fig, axes, _ = _grid(len(teams), 4, (4.0, 4.2))

    for ax, team in zip(axes, teams):
        panel = (
            df[df["team"] == team]
            .nlargest(top_n, "minutes")
            .sort_values(["element_type", "pred"])
            .reset_index(drop=True)
        )
        y = np.arange(len(panel))
        for i, row in panel.iterrows():
            colour = POSITION_COLOURS.get(row["element_type"], "grey")
            ax.plot([row["pred_lower"], row["pred_upper"]], [i, i], color=colour, lw=1.4, alpha=0.8)
            ax.scatter(row["start_cost"], i, color="#404040", s=14, zorder=3)
            ax.scatter(row["pred"], i, color=colour, s=26, zorder=4)
        ax.set_yticks(y)
        ax.set_yticklabels(panel["web_name"], fontsize=7)
        ax.set_title(team, fontsize=10)
        ax.set_xlabel("Price (£m)")
        ax.grid(axis="x", alpha=0.3)
        ax.set_axisbelow(True)

    for ax in axes[len(teams):]:
        ax.axis("off")

    handles = [plt.Line2D([], [], marker="o", ls="", color=c, label=p) for p, c in POSITION_COLOURS.items()]
    handles.append(plt.Line2D([], [], marker="o", ls="", color="#404040", label="last season's price"))
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False)
    fig.suptitle(
        f"Predicted {config.season_label(predict_season)} starting prices — "
        f"95% prediction interval, top {top_n} players per club by minutes",
        fontsize=13,
    )
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])
    return _save(fig, name)


def coefficients(coefs: pd.DataFrame, name: str = "coefficients.png") -> Path:
    """R lines 1300-1317: coefficient estimates, teams split from the rest.

    Team effects are shown separately because they are on a different scale
    and would otherwise compress every performance term into a single line.
    """
    is_team = coefs["term"].str.startswith("team_name")
    panels = [("Performance and price terms", coefs[~is_team]), ("Team effects", coefs[is_team])]

    fig, axes = plt.subplots(1, 2, figsize=(14, 8))
    for ax, (title, panel) in zip(axes, panels):
        panel = panel.sort_values("estimate")
        y = np.arange(len(panel))
        ax.errorbar(
            panel["estimate"], y,
            xerr=[panel["estimate"] - panel["conf_low"], panel["conf_high"] - panel["estimate"]],
            fmt="o", ms=4, lw=1, color="#377EB8", ecolor="#999999",
        )
        ax.axvline(0, ls="--", color="black", lw=1)
        ax.set_yticks(y)
        ax.set_yticklabels(panel["term"], fontsize=8)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Coefficient (£m)")
        ax.grid(axis="x", alpha=0.3)

    fig.suptitle("Model coefficients with 95% confidence intervals", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    return _save(fig, name)


def backtest_scatter(df: pd.DataFrame, predict_season: int, name: str = "backtest.png") -> Path:
    """Predicted against the starting prices FPL actually set."""
    fig, ax = plt.subplots(figsize=(8.5, 8))
    covered = (df["actual_start_cost"] >= df["pred_lower"]) & (df["actual_start_cost"] <= df["pred_upper"])

    ax.scatter(df.loc[covered, "pred"], df.loc[covered, "actual_start_cost"],
               s=18, color="#377EB8", alpha=0.65, label="inside 95% interval")
    ax.scatter(df.loc[~covered, "pred"], df.loc[~covered, "actual_start_cost"],
               s=26, color="#E41A1C", alpha=0.85, label="outside 95% interval")

    lims = [df[["pred", "actual_start_cost"]].min().min() - 0.4,
            df[["pred", "actual_start_cost"]].max().max() + 0.4]
    ax.plot(lims, lims, ls="--", color="black", lw=1)

    for _, row in df.assign(err=(df["pred"] - df["actual_start_cost"]).abs()).nlargest(15, "err").iterrows():
        ax.annotate(row["web_name"], (row["pred"], row["actual_start_cost"]),
                    fontsize=8, xytext=(0, 6), textcoords="offset points", ha="center")

    ax.set_xlabel(f"Predicted {config.season_label(predict_season)} starting price")
    ax.set_ylabel(f"Actual {config.season_label(predict_season)} starting price")
    ax.set_title(
        f"Backtest: predicted vs actual {config.season_label(predict_season)} starting prices\n"
        f"returning players only (n = {len(df)})",
        fontsize=12,
    )
    _money_axes(ax)
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    return _save(fig, name)
