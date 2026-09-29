"""Running commentary for ``model_report.py``: one note per chart and table.

Each note leads with the key message in bold, then at most a few supporting
points. Every figure a note quotes is computed from the same table the chart
or table draws, so a rerun on new data cannot leave a note stating an old
number. What stays fixed is the framing: a note says which way the pattern
runs, and the numbers say how far.

Error is ``predicted - actual`` throughout: positive means priced too high.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config

POSITIONS = config.POSITIONS
TIERS = config.TIER_NAMES


# ---------------------------------------------------------------- formatting


def m(v: float, places: int = 2) -> str:
    """Signed money: +£0.03m, −£0.16m."""
    sign = "+" if v > 0 else "−" if v < 0 else "±"
    return f"{sign}£{abs(v):.{places}f}m"


def s(v: float, places: int = 2) -> str:
    return f"£{v:.{places}f}m"


def note(head: str, *points: str) -> str:
    items = "".join(f"<li>{p}</li>" for p in points if p)
    return f"<b>{head}</b>" + (f"<ul>{items}</ul>" if items else "")


def _cell(pos: str, tier: str) -> str:
    return f"{pos} {tier}"


def _outfield(t: pd.DataFrame):
    return [p for p in POSITIONS if p != "GK" and p in t.index.get_level_values(0)]


# ---------------------------------------------------------------- §1 overview


def overview(o: pd.Series, served: pd.Series | None, served_label: str) -> str:
    cover = "in line with" if o["95% range held"] >= 0.94 else "short of"
    points = [
        f"{o['Within £0.25m']:.0%} of prices land within £0.25m, {o['Within £0.1m']:.0%} "
        "within £0.1m.",
        f"The 95% range held {o['95% range held']:.0%} of actual prices, {cover} what it "
        "promises.",
    ]
    if served is not None:
        points.append(
            f"The served model's one season ({served_label}) was harder: SD "
            f"{served['SD of error']:.3f} against {o['SD of error']:.3f}, mean error "
            f"{m(served['Mean error'])}, range held {served['95% range held']:.0%}.")
    return note(f"Across {int(o['n']):,} out-of-sample predictions the model is close to "
                f"unbiased (mean error {m(o['Mean error'], 3)}) and typically misses by "
                f"{s(o['MAE'], 3)}.", *points)


def histogram(e: pd.Series) -> str:
    within = (e.abs() <= 0.5 + 1e-9).mean()
    big = int((e.abs() >= 1.0).sum())
    tails = ("heavier than a bell curve" if e.kurt() > 1 else "close to a bell curve")
    return note(
        "Errors are centred just above zero and close to symmetric; large misses are rare "
        "but real.",
        f"Median {m(e.median())}; the middle 90% run from {m(e.quantile(0.05))} to "
        f"{m(e.quantile(0.95))}.",
        f"{within:.0%} of predictions miss by £0.5m or less; {big} miss by £1m or more. "
        f"The tails are {tails}, which is why §7 looks at the extremes.")


# ---------------------------------------------------------------- §2 position


def positions(t: pd.DataFrame) -> str:
    order = t["SD of error"].sort_values()
    worst = order.index[-1]
    return note(
        "Bias is small and similar in every position; the spread is what differs.",
        f"Mean error ranges only from {m(t['Mean error'].min(), 3)} to "
        f"{m(t['Mean error'].max(), 3)}.",
        "SD: " + " &lt; ".join(f"{p} {v:.3f}" for p, v in order.items()) + ".",
        f"{worst} is the hardest position: {t.loc[worst, 'Within £0.25m']:.0%} within £0.25m "
        f"and the 95% range held {t.loc[worst, '95% range held']:.0%}.")


def position_hists(oos: pd.DataFrame) -> str:
    q = {p: oos.loc[oos["element_type"] == p, "error"].quantile([0.05, 0.95])
         for p in POSITIONS}
    width = {p: v.iloc[1] - v.iloc[0] for p, v in q.items()}
    wide, tight = max(width, key=width.get), min(width, key=width.get)
    return note(
        f"All four centre near zero; {wide} is the widest and {tight} the tightest.",
        f"Middle 90% of errors: {tight} {m(q[tight].iloc[0])} to {m(q[tight].iloc[1])}, "
        f"{wide} {m(q[wide].iloc[0])} to {m(q[wide].iloc[1])}.")


def served_positions(t: pd.DataFrame) -> str:
    low = [p for p in t.index if t.loc[p, "Mean error"] < -0.02]
    high = [p for p in t.index if t.loc[p, "Mean error"] > 0.02]
    worst = t["SD of error"].idxmax()
    parts = []
    if low:
        parts.append("priced " + ", ".join(f"{p} ({m(t.loc[p, 'Mean error'])})" for p in low)
                     + " too low")
    if high:
        parts.append(", ".join(f"{p} ({m(t.loc[p, 'Mean error'])})" for p in high)
                     + " too high")
    return note(
        "In its one real season the served model " + " and ".join(parts) + ".",
        f"{worst} was also the least predictable: SD {t.loc[worst, 'SD of error']:.3f}, "
        f"range held {t.loc[worst, '95% range held']:.0%}.",
        "One season only: §5 shows the direction of the bias changes from season to season.")


# ---------------------------------------------------------------- §3 tiers


def _tier_breaks(t: pd.DataFrame, metric: str) -> list[tuple[str, str]]:
    """Outfield (position, tier) cells where ``metric`` falls from the tier below."""
    out = []
    for p in _outfield(t):
        v = t.loc[p, metric]
        out += [(p, tier) for tier, d in v.diff().items() if d < 0]
    return out


def tiers(t: pd.DataFrame) -> str:
    budget = t.xs("Budget", level=1)["Mean error"]
    upper = t[t.index.get_level_values(1).isin(["High-Mid", "Premium"])]
    top = upper["Mean error"].nlargest(3)
    flagged = t[t["95% range held"] < 0.9]
    gk = t.loc["GK", "SD of error"]
    falls = {"mean error": _tier_breaks(t, "Mean error"), "SD": _tier_breaks(t, "SD of error")}
    breaks = sorted({k for cells in falls.values() for k in cells})
    return note(
        "Within each outfield position, bias and spread "
        + ("rise with tier." if not breaks else "mostly rise with tier."),
        ("Exception: " + "; ".join(
            f"{_cell(*k)} (n={int(t.loc[k, 'n'])}), where "
            + " and ".join(name for name, cells in falls.items() if k in cells)
            + " fall from the tier below"
            for k in breaks) + ".") if breaks else "",
        f"Budget tiers lean slightly low in every position ({m(budget.min(), 3)} to "
        f"{m(budget.max(), 3)}); the upper tiers lean high, most in "
        + ", ".join(f"{_cell(*k)} ({m(v, 3)})" for k, v in top.items()) + ".",
        "The 95% range falls below 90% in " + ", ".join(
            f"{_cell(*k)} ({v:.0%})" for k, v in flagged["95% range held"].items())
        + "." if len(flagged) else "",
        f"Goalkeepers stay tight in every tier (SD {gk.min():.2f}–{gk.max():.2f}).")


def tier_whiskers(t: pd.DataFrame) -> str:
    runs, faster = [], []
    for p in _outfield(t):
        sd, mean = t.loc[p, "SD of error"], t.loc[p, "Mean error"]
        wide = sd.idxmax()
        d_sd, d_mean = sd[wide] - sd.iloc[0], mean[wide] - mean.iloc[0]
        runs.append(f"{p} SD {sd.iloc[0]:.2f} → {sd[wide]:.2f}, mean {m(mean.iloc[0])} → "
                    f"{m(mean[wide])} ({wide})")
        if d_sd > 1.5 * abs(d_mean):
            faster.append(p)
    widest = t["SD of error"].idxmax()
    return note(
        "Up the tiers the whiskers widen and the dots rise with them"
        + (f"; only in {', '.join(faster)} does the spread grow much faster than the bias."
           if faster else "."),
        "Budget to each position's widest tier: " + "; ".join(runs) + ".",
        f"Widest: {_cell(*widest)}, ±{s(t.loc[widest, 'SD of error'])} around a mean of "
        f"{m(t.loc[widest, 'Mean error'])}.")


def heat_mean(t: pd.DataFrame) -> str:
    hot = t["Mean error"].idxmax()
    upper = t[t.index.get_level_values(1).isin(["High-Mid", "Premium"])]
    odd = upper[upper["Mean error"] < 0]
    return note(
        "Purple on the left, orange on the right: cheap tiers are priced slightly low, "
        "dearer tiers too high.",
        f"Hottest cell: {_cell(*hot)} ({m(t.loc[hot, 'Mean error'], 3)}).",
        ("Exception: " + ", ".join(f"{_cell(*k)} ({m(r['Mean error'], 3)}, n={int(r['n'])})"
                                   for k, r in odd.iterrows()) + ".") if len(odd) else "")


def heat_sd(t: pd.DataFrame) -> str:
    dark = t["SD of error"].idxmax()
    gk = t.loc["GK", "SD of error"]
    breaks = _tier_breaks(t, "SD of error")
    return note(
        f"Spread {'mostly ' if breaks else ''}darkens with tier in the outfield rows; "
        f"{_cell(*dark)} is the darkest ({s(t.loc[dark, 'SD of error'], 3)}).",
        ("Lighter than the tier below: " + ", ".join(
            f"{_cell(*k)} ({t.loc[k, 'SD of error']:.3f}, n={int(t.loc[k, 'n'])})"
            for k in breaks) + ".") if breaks else "",
        f"The GK row stays light throughout ({gk.min():.3f}–{gk.max():.3f}).")


def heat_rmse(t: pd.DataFrame) -> str:
    worst, best = t["RMSE"].nlargest(2), t["RMSE"].nsmallest(2)
    return note(
        "RMSE combines bias and spread, so it picks out the model's weakest and strongest "
        "cells.",
        "Weakest: " + ", ".join(f"{_cell(*k)} ({s(v, 3)})" for k, v in worst.items()) + ".",
        "Strongest: " + ", ".join(f"{_cell(*k)} ({s(v, 3)})" for k, v in best.items()) + ".")


def served_tiers(t: pd.DataFrame) -> str:
    thin = int((t["n"] < 15).sum())
    budget = t.xs("Budget", level=1)["Mean error"]
    worst = t[t["n"] >= 5]["Mean error"].abs().idxmax()
    return note(
        "One season with thin cells: a spot check, not a pattern.",
        f"{thin} of {len(t)} cells hold fewer than 15 players.",
        f"Budget tiers were priced too low in every position ({m(budget.min())} to "
        f"{m(budget.max())})." if (budget < 0).all() else "",
        f"Largest miss among cells of 5+: {_cell(*worst)}, mean {m(t.loc[worst, 'Mean error'])}"
        f", range held {t.loc[worst, '95% range held']:.0%} (n={int(t.loc[worst, 'n'])}).")


def served_whiskers(t: pd.DataFrame) -> str:
    wide = t[t["n"] >= 5]["SD of error"].idxmax()
    return note(
        "The same one-season picture as the table above; don't read much into any single "
        "cell.",
        f"Widest whisker among cells of 5+: {_cell(*wide)} (SD "
        f"{s(t.loc[wide, 'SD of error'])}, n={int(t.loc[wide, 'n'])}).")


# ---------------------------------------------------------------- §4 bands


def bands(t: pd.DataFrame) -> str:
    peak = t["Mean error"].idxmax()
    share = t["n"].iloc[:2].sum() / t["n"].sum()
    return note(
        f"Bias peaks in the middle ({peak}, {m(t.loc[peak, 'Mean error'], 3)}) and eases at "
        f"the top; spread rises steadily with price.",
        f"SD: {s(t['SD of error'].iloc[0])} at {t.index[0]} to {s(t['SD of error'].iloc[-1])} "
        f"at {t.index[-1]}.",
        f"{share:.0%} of rows sit in the two cheapest bands, so the headline numbers in §1 "
        "mostly describe cheap players.",
        f"The 95% range held {t['95% range held'].iloc[-1]:.0%} at {t.index[-1]}, against "
        f"{t['95% range held'].iloc[0]:.0%} at {t.index[0]}.")


def band_whiskers(t: pd.DataFrame) -> str:
    ratio = t["SD of error"].iloc[-1] / t["SD of error"].iloc[0]
    return note(
        f"From the cheapest band to the dearest the whisker grows {ratio:.1f}×; the dot "
        f"never moves more than {s(t['Mean error'].abs().max())} from zero.")


def by_predicted(t: pd.DataFrame) -> str:
    edges = [b.left for b in t.index]
    neg = [e for e, v in zip(edges, t["Mean error"]) if v < 0]
    big = [i for i, n in enumerate(t["n"]) if n >= 100]
    small = t.iloc[big[-1] + 1:] if big else t
    return note(
        "The spread rises almost steadily with the predicted price; the lean turns from "
        "negative to positive.",
        f"SD: {s(t['SD of error'].iloc[0])} for the cheapest predictions to "
        f"{s(t['SD of error'].iloc[-1])} for the dearest shown.",
        f"Mean error is negative only below £{max(neg) + 0.5:.1f}m." if neg else "",
        f"From £{small.index[0].left:.1f}m up, bins hold under 100 players, so the mean bars "
        "there are noisy." if len(small) else "")


def error_path(t: pd.DataFrame) -> str:
    sd, mean = t["SD of error"].to_numpy(), t["Mean error"].to_numpy()
    k = 0
    while k + 1 < len(t) and sd[k + 1] > sd[k] and mean[k + 1] > mean[k]:
        k += 1
    rest = t.iloc[k + 1:]
    rising = bool((np.diff(sd[k:]) > 0).all())
    return note(
        f"Up and to the right until the £{t.index[k].left:.1f}m bin: larger and more "
        "positive errors arrive together.",
        (("Beyond it the SD keeps rising" if rising else
          f"Beyond it the SD stays higher but uneven ({s(rest['SD of error'].min(), 3)}–"
          f"{s(rest['SD of error'].max(), 3)})")
         + f" and the mean jumps between {m(rest['Mean error'].min())} and "
         f"{m(rest['Mean error'].max())}; those bins hold "
         f"{int(rest['n'].min())}–{int(rest['n'].max())} players.") if len(rest) else "")


def tier_path(t: pd.DataFrame) -> str:
    points = []
    for p in POSITIONS:
        r = t.loc[p]
        points.append(f"{p}: mean {m(r['Mean error'].iloc[0])} → {m(r['Mean error'].iloc[-1])}, "
                      f"SD {r['SD of error'].iloc[0]:.2f} → {r['SD of error'].iloc[-1]:.2f} "
                      f"(Premium n={int(r['n'].iloc[-1])}).")
    return note("Moving up the tiers adds spread in every outfield position, and lean in most; "
                "goalkeepers barely move.", *points)


def residuals(oos: pd.DataFrame) -> str:
    cheap = oos.loc[oos["pred"] <= 5, "error"].std()
    dear = oos.loc[oos["pred"] > 8, "error"].std()
    within = (oos["error"].abs() <= 0.5 + 1e-9).mean()
    return note(
        f"{within:.0%} of points sit within ±£0.5m; the cloud fans out to the right.",
        f"SD {s(cheap)} for predictions up to £5m against {s(dear)} above £8m.")


# ---------------------------------------------------------------- §5 seasons


def seasons_by_position(t: pd.DataFrame) -> str:
    mean = t["Mean error"].unstack()[POSITIONS]
    sd = t["SD of error"].unstack()[POSITIONS]
    label = lambda season: config.season_label(int(season) + 1)  # noqa: E731
    # The clearest over-pricing season: every position above zero, largest average.
    positive = mean[mean.min(axis=1) > 0]
    high = positive.mean(axis=1).idxmax() if len(positive) else mean.mean(axis=1).idxmax()
    last = mean.index[-1]
    fwd_top = int((sd.idxmax(axis=1) == "FWD").sum())
    rose = bool((sd.loc[last] > sd.iloc[-2]).all())
    all_high = mean.loc[high].min() > 0
    return note(
        "The bias drifts over time: from priced too high early on to mostly too low recently.",
        (f"Prices for {label(high)}: every position too high "
         f"({m(mean.loc[high].min())} to {m(mean.loc[high].max())})." if all_high else ""),
        f"Prices for {label(last)}: " + ", ".join(f"{p} {m(mean.loc[last, p])}"
                                                   for p in POSITIONS) + ".",
        f"FWD has the widest spread in {fwd_top} of {len(sd)} seasons"
        + (f"; every position's SD rose for {label(last)}." if rose else "."))


def seasons_all(t: pd.DataFrame) -> str:
    best, worst = t["RMSE"].idxmin(), t["RMSE"].idxmax()
    return note(
        f"Best season: prices for {best} (RMSE {s(t.loc[best, 'RMSE'], 3)}); worst: {worst} "
        f"({s(t.loc[worst, 'RMSE'], 3)}).",
        f"Mean error swings from {m(t['Mean error'].min(), 3)} to {m(t['Mean error'].max(), 3)}"
        " between seasons: FPL's pricing shifts a little each year, and a model fitted to "
        "past seasons lags it.",
        f"The 95% range held {t['95% range held'].min():.0%}–{t['95% range held'].max():.0%} "
        "every season.")


# ---------------------------------------------------------------- §6 calibration


def calibration(oos: pd.DataFrame) -> str:
    bins = np.arange(3.5, oos["pred"].max() + 0.5, 0.5)
    t = (oos.assign(bin=pd.cut(oos["pred"], bins)).groupby("bin", observed=True)
         .agg(pred=("pred", "mean"), actual=("actual", "mean"), n=("pred", "size")))
    t = t[t["n"] >= 10]
    t["gap"] = t["pred"] - t["actual"]
    lowgap = t[t["pred"] < 6.5]["gap"].abs().max()
    upper = t[t["pred"] >= 6.5]
    top = t.index[-1].right
    dropped = int((oos["pred"] > top).sum())
    return note(
        "Right on average across the cheap and mid range; above about £6.5m the predictions "
        "sit above the actual prices.",
        f"Below £6.5m every bin is within {s(lowgap)} of the line.",
        (f"From £6.5m the model is {s(upper['gap'].min())}–{s(upper['gap'].max())} too high "
         "on average: the same over-pricing as §4.") if len(upper) else "",
        f"Bins with fewer than 10 players are left out, so the chart stops at £{top:.1f}m: "
        f"all {dropped} predictions above it are dropped.")


# ---------------------------------------------------------------- §8 drivers


def contributions(typical: pd.DataFrame) -> str:
    top, second = typical.index[0], typical.index[1]
    row = typical.loc[top, POSITIONS]
    ratio = typical.loc[top, "All"] / typical.loc[second, "All"]
    goals = typical.loc["Goals", POSITIONS] if "Goals" in typical.index else None
    rank2 = {pos: typical[pos].drop(top).idxmax() for pos in POSITIONS}
    if all(v == second for v in rank2.values()):
        points = [f"{second} is second in every position "
                  f"({s(typical.loc[second, POSITIONS].min())}–"
                  f"{s(typical.loc[second, POSITIONS].max())})."]
    else:
        odd = {pos: v for pos, v in rank2.items() if v != second}
        points = [f"{second} is second overall and in every position except "
                  + ", ".join(f"{pos} (where {v.lower()} is second)" for pos, v in odd.items())
                  + "."]
    if goals is not None:
        others = goals.drop(goals.idxmax())
        points.append(f"Goals matter most for {goals.idxmax()} ({s(goals.max())}, against "
                      f"{s(others.min())}–{s(others.max())} elsewhere).")
    small = typical["All"].nsmallest(3)
    points.append("Smallest: " + ", ".join(f"{k} ({s(v, 3)})" for k, v in small.items()) + ".")
    return note(f"{top} dominates in every position (typical push {s(row.min())}–"
                f"{s(row.max())}), about {ratio:.1f}× the next group.", *points)


def typical_table(typical: pd.DataFrame, value_weight: float) -> str:
    return note(
        "The ‘All’ column sets the order; a big push needs a big weight or a big spread "
        "between players.",
        f"Points per £m ranks high although its weight is small ({m(value_weight, 3)} per "
        "unit): it varies a lot from player to player.")


def worked_example(ex: pd.DataFrame) -> str:
    groups = ex.drop(index=["Average training player", "Predicted price"])
    points = []
    for player in ex.columns:
        top = groups[player].abs().nlargest(3).index
        parts = ", ".join(f"{g.lower()} {m(groups.loc[g, player])}" for g in top)
        points.append(f"{player.split(' (')[0]}: {parts} → {s(ex.loc['Predicted price', player])}.")
    return note("Each column starts at the average player's price and adds its pushes; the "
                "total is exactly the model's prediction.", *points)


def coefficients(coefs: pd.DataFrame) -> str:
    sig = coefs["p_value"] < 0.05
    clubs = coefs.index.str.startswith("team_name_")
    other = coefs[~sig & ~clubs & (coefs.index != "const")].index.tolist()
    return note(
        f"{int(sig.sum())} of {len(coefs)} terms are significant at 5%; most of the rest are "
        "club terms.",
        f"{int((~sig & clubs).sum())} of {int(clubs.sum())} club terms are not significant.",
        ("Other non-significant terms: " + ", ".join(other) + ". The price terms are tied "
         "to each other, so read them together (§9), not one by one.") if other else "",
        f"Most precise per unit: goals {m(coefs.loc['goals_scored', 'estimate'], 3)} each, "
        f"assists {m(coefs.loc['assists', 'estimate'], 3)} each.")


def clubs(t: pd.DataFrame) -> str:
    t = t.sort_values("estimate", ascending=False)
    clear = t[t["conf_low"] > 0]
    below = t[t["conf_high"] < 0]
    return note(
        f"{t.index[0]} stands out ({m(t['estimate'].iloc[0])}); {len(clear)} of {len(t)} "
        "clubs have intervals clear of zero.",
        "Clear of zero: " + ", ".join(f"{c} ({m(v)})" for c, v in clear["estimate"].items())
        + ".",
        f"The other {len(t) - len(clear) - len(below)} overlap zero: for them, the club adds "
        "little beyond the season's own numbers."
        + (f" {len(below)} sit clearly below zero." if len(below) else ""))


def positions_coef(t: pd.DataFrame) -> str:
    mid, fwd, dfn = (t.loc[p] for p in ("MID", "FWD", "DEF"))
    overlap = mid["conf_low"] <= fwd["conf_high"] and fwd["conf_low"] <= mid["conf_high"]
    return note(
        f"Midfielders and forwards cost about {s((mid['estimate'] + fwd['estimate']) / 2)} "
        "more than a goalkeeper with the same season; defenders about the same as "
        "goalkeepers.",
        f"MID {m(mid['estimate'], 3)}, FWD {m(fwd['estimate'], 3)}"
        + (": their intervals overlap, so the two are indistinguishable." if overlap else "."),
        f"DEF {m(dfn['estimate'], 3)}, interval {m(dfn['conf_low'], 3)} to "
        f"{m(dfn['conf_high'], 3)}"
        + (", which includes zero." if dfn["conf_low"] < 0 < dfn["conf_high"] else "."))


# ---------------------------------------------------------------- §9 squares


def fpl_curve(frame: pd.DataFrame) -> str:
    df = frame.assign(price=frame["start_cost"].round(1))
    t = df.groupby("price").agg(next=("next_cost", "mean"), n=("next_cost", "size"))
    t = t[t["n"] >= 8]
    t["diff"] = t["next"] - t.index
    up = t[t["diff"] > 0.05]
    down_from = next((p for p in t.index if (t.loc[p:, "diff"] < 0).all()), None)
    worst = t["diff"].idxmin()
    return note(
        "Cheap players drift up, dear players drift down.",
        (f"Below £{up.index.max() + 0.5:.1f}m prices rise on average (£{t.index[0]:.1f}m "
         f"players: {m(t['diff'].iloc[0])})." if len(up) else ""),
        (f"From £{down_from:.1f}m up every price level falls on average, by "
         f"{s(-t.loc[down_from:, 'diff'].max())} to {s(-t['diff'].min())}; the biggest drop is "
         f"at £{worst:.1f}m (n={int(t.loc[worst, 'n'])})." if down_from is not None else ""))


def slope(curve: pd.DataFrame) -> str:
    lo, hi = curve["linear"].iloc[0] - curve["linear_ci"].iloc[0], \
        curve["linear"].iloc[0] + curve["linear_ci"].iloc[0]
    band_lo = curve["carried"] - curve["carried_ci"]
    band_hi = curve["carried"] + curve["carried_ci"]
    inside = curve[(band_lo <= hi) & (band_hi >= lo)]["price"]
    ends_clear = not (inside.min() == curve["price"].iloc[0] or
                      inside.max() == curve["price"].iloc[-1]) if len(inside) else True
    return note(
        f"The bend is real: carry-over rises from £{curve['carried'].iloc[0]:.2f} to "
        f"£{curve['carried'].iloc[-1]:.2f} per £1"
        + (", and the straight line's intervals don't overlap it at either end." if ends_clear
           else "."),
        (f"The two only agree between £{inside.min():.1f}m and £{inside.max():.1f}m, where "
         f"the straight line's £{curve['linear'].iloc[0]:.2f} is about right."
         if len(inside) else ""))


def slope_split(curve: pd.DataFrame) -> str:
    diff = curve["via_end"] - curve["via_start"]
    cross = curve.loc[diff.abs().idxmin(), "price"]
    neg = curve[curve["via_start"] < 0]
    return note(
        f"Start and end price count about equally near £{cross:.1f}m; above that the end "
        "price takes over.",
        (f"The start price's own effect turns negative from £{neg['price'].iloc[0]:.1f}m, but "
         "its interval includes zero there." if len(neg) and
         (neg["via_start"] + neg["via_start_ci"] > 0).iloc[0] else ""),
        "The bands are wide because start and end price move together for most players: "
        "treat the split as indicative.")


def squares_bands(both: pd.DataFrame) -> str:
    closer = int((both["mean"].abs() < both["lin_mean"].abs()).sum())
    tighter = int((both["sd"] < both["lin_sd"]).sum())
    return note(
        f"With the squares, bias is closer to zero in {closer} of {len(both)} bands and the SD "
        f"is lower in {tighter} of {len(both)}.",
        "The whiskers barely change: the squares mostly fix the lean, not the spread.")


def squares_table(both: pd.DataFrame) -> str:
    gain = (both["lin_rmse"] - both["rmse"])
    band = gain.idxmax()
    r = both.loc[band]
    return note(
        f"The biggest gain is at {band}: mean error {m(r['lin_mean'], 3)} → "
        f"{m(r['mean'], 3)}, RMSE {s(r['lin_rmse'], 3)} → {s(r['rmse'], 3)}.",
        f"At {both.index[0]} the gain is small ({s(gain.iloc[0], 3)} RMSE) but applies to "
        f"{int(both['n'].iloc[0]):,} players.")


# ---------------------------------------------------------------- §10 moves


def moves(shares: pd.DataFrame) -> str:
    budget = shares.xs("Budget", level=1)
    sharp = shares["sharp fall"].sort_values(ascending=False)
    top = sharp[sharp >= 0.3]
    gk = shares.loc["GK", ["sharp fall", "sharp rise"]].to_numpy().max()
    rise = shares["sharp rise"].groupby(level=0).mean()
    most = rise.idxmax()
    most_range = shares.loc[most, "sharp rise"]
    upper = shares[shares.index.get_level_values(1).isin(["High-Mid", "Premium"])]
    fell = upper["sharp fall"] + upper["fall"]
    holders = sorted({p for (p, _), f in fell.items() if f < upper.loc[(p, _), "held"]},
                     key=POSITIONS.index)
    fallers = [p for p in POSITIONS if p not in holders]
    return note(
        "The floor and the top behave differently: budget tiers mostly hold; upper tiers "
        f"{'in ' + ', '.join(fallers) + ' ' if holders else ''}fall more often than they "
        "hold, often sharply.",
        (f"Except {', '.join(holders)}: upper tiers hold "
         + ", ".join(f"{upper.loc[(p, tier), 'held']:.0%} ({p} {tier})"
                     for p in holders for tier in upper.loc[p].index)
         + " of the time.") if holders else "",
        f"Budget tiers hold {budget['held'].min():.0%}–{budget['held'].max():.0%} of the time "
        f"and almost never fall sharply (at most {budget['sharp fall'].max():.0%}).",
        ("Sharp falls of £1m+: " + ", ".join(f"{_cell(*k)} {v:.0%}" for k, v in top.items())
         + ".") if len(top) else "",
        f"Goalkeepers rarely move sharply either way (at most {gk:.0%} in any tier).",
        f"Sharp rises are most common for {most} ({most_range.min():.0%}–"
        f"{most_range.max():.0%} per tier, against {rise.drop(most).max():.0%} on average for "
        "the next position).")


#: Final-price bands for the summer reset (F21): edges and labels.
RESET_EDGES = [0, 5.5, 6.5, 8, 10, 99]
RESET_LABELS = ["up to £5.5m", "£5.6–6.5m", "£6.6–8.0m", "£8.1–10.0m", "over £10m"]


def summer(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per transition with the summer change and its final-price band.

    Prices are rounded to FPL's £0.1m grid: they are recovered by
    subtraction and carry float noise.
    """
    df = frame.dropna(subset=["next_cost", "final_cost"]).copy()
    for c in ("start_cost", "final_cost", "next_cost"):
        df[c] = df[c].round(1)
    df["summer"] = (df["next_cost"] - df["final_cost"]).round(1)
    df["reset_band"] = pd.cut(df["final_cost"], RESET_EDGES, labels=RESET_LABELS)
    return df


def reset(frame: pd.DataFrame) -> str:
    """F21: how the summer re-pricing moves a player from his final price."""
    df = summer(frame)
    change = df["summer"]
    up, same, down = (change > 0).mean(), (change == 0).mean(), (change < 0).mean()
    g = change.groupby(df["reset_band"], observed=True)
    med, mean = g.median(), g.mean()
    share_up, share_down = g.apply(lambda c: (c > 0).mean()), g.apply(lambda c: (c < 0).mean())
    rises = [b for b, v in med.items() if v > 0]
    falls = [b for b, v in med.items() if v < 0]
    cheap = df[df["reset_band"].isin(rises) & (df["final_cost"] < df["start_cost"])]
    below_floor = int((df["final_cost"] < 4.0).sum())
    deeper = bool((np.diff(mean[falls].to_numpy()) < 0).all()) if len(falls) > 1 else False
    cut = change.groupby(df["element_type"]).apply(lambda c: (c < 0).mean()).reindex(POSITIONS)
    split = RESET_EDGES[RESET_LABELS.index(falls[0])] if falls else None
    return note(
        "Between seasons FPL raises most cheap players' prices and cuts most dear players' "
        f"prices. Overall {up:.0%} were raised, {down:.0%} cut and {same:.0%} left alone.",
        "“Summer change” is the new season's start price minus last season's final price: "
        "positive means FPL raised the price over the summer, negative means it cut it.",
        "Median summer change, by final price (the black steps): " + ", ".join(
            f"{b} {m(v)}" for b, v in med.items()) + ".",
        (f"Final price up to £{split:.1f}m: {share_up[rises].min():.0%} were raised. "
         f"{len(cheap) / df['reset_band'].isin(rises).sum():.0%} of these players had lost "
         f"value during the season, and FPL mostly gave it back: of those {len(cheap):,}, "
         f"{(cheap['summer'] > 0).mean():.0%} were raised over the summer and "
         f"{(cheap['next_cost'] == cheap['start_cost']).mean():.0%} went back to exactly the "
         "price they had started the previous season on. "
         + (f"{below_floor} had ended the season below £4.0m, lower than any start price "
            "FPL sets." if below_floor else "")) if rises and split else "",
        (f"Final price above £{split:.1f}m: {share_down[falls].min():.0%}–"
         f"{share_down[falls].max():.0%} were cut, depending on the band. "
         + ("The cut gets bigger with price; average change " if deeper else
            f"The median cut is biggest in the {med[falls].idxmin()} band, but the average change does "
            "not get steadily bigger with price: ")
         + ", ".join(f"{b} {m(v)}" for b, v in mean[falls].items()) + ".") if falls else "",
        "Share cut over the summer, by position: " + ", ".join(
            f"{p} {v:.0%}" for p, v in cut.items()) + f"; {cut.idxmax()} is cut most often.")


def equation(b: pd.Series, numeric: list[str], names: dict) -> str:
    """§11: how to read the fitted weights, in a manager's units."""
    per90 = b["minutes"] * 90
    negative = [names.get(c, c) for c in numeric if b[c] < 0]
    bend = b["start_cost_sq"] + b["final_cost_sq"]
    return note(
        "Read the weights in FPL units, and read the four price terms together.",
        f"Each goal adds {m(b['goals_scored'], 3)} and each assist {m(b['assists'], 3)} to next "
        f"season's price; each 1% of ownership adds {m(b['selected_by_percent'], 3)}.",
        f"Minutes carry {m(per90, 4)} per 90 played: with points, goals and ppg held fixed, "
        "more minutes means those returns came less efficiently.",
        f"start² and end² together add {bend:+.4f} × price²: that is the bend in §9, which "
        f"makes a £1 price difference carry about £{b['start_cost'] + b['final_cost'] + 2 * bend * 4:.2f} "
        f"at £4m and £{b['start_cost'] + b['final_cost'] + 2 * bend * 12:.2f} at £12m.",
        (f"Negative weights ({', '.join(negative)}) look odd alone because the inputs overlap "
         "heavily; their combined effect is what the model means. The waterfall on every player "
         "card in the app shows those combined effects for one player.") if negative else "")
