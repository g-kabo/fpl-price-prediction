"""How it works: the method in plain words, and how right it has been.

Every figure on this page is read from the pipeline's own outputs --
``models/meta.json`` and ``output/backtest_metrics_<season>.json`` -- so it
cannot drift from the model it describes. If the backtest file is missing,
its section is left out rather than filled with a remembered number.
"""

from __future__ import annotations

import json

import dash
from dash import html

import config
import model_store
import theme
import ui

dash.register_page(__name__, path="/how-it-works", name="How it works", order=2,
                   title="How it works · FPL Price Prediction")

_meta = model_store.get_meta()


def _backtest() -> dict | None:
    path = config.OUTPUT_DIR / f"backtest_metrics_{_meta['predict_season']}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _step(title: str, *body) -> html.Div:
    return html.Div([html.H3(title, className="step-title"), *body], className="step")


def _accuracy(bt: dict) -> html.Section:
    overall = bt["overall"]
    rows = [
        html.Tr([
            html.Td(ui.position_pill(position)),
            html.Td(str(stats["n"]), className="num"),
            html.Td(theme.money(stats["mae"], places=2), className="num"),
            html.Td(f"{stats['within_0_25m']:.0%}", className="num"),
            html.Td(f"{stats['interval_coverage']:.0%}", className="num"),
        ])
        for position, stats in bt["by_position"].items()
    ]
    rows.append(html.Tr([
        html.Td("All positions"),
        html.Td(str(overall["n"]), className="num"),
        html.Td(theme.money(overall["mae"], places=2), className="num"),
        html.Td(f"{overall['within_0_25m']:.0%}", className="num"),
        html.Td(f"{overall['interval_coverage']:.0%}", className="num"),
    ], className="total-row"))

    weakest = max(bt["by_position"].items(), key=lambda kv: kv[1]["rmse"])
    return ui.section(
        "How right has it been?",
        html.P(
            [
                f"The model was trained only on seasons up to {config.season_label(_meta['train_through'])}, "
                f"then asked to price the {bt['matched_players']} players who carried over "
                f"into {bt['predict_season']} without ever seeing the prices FPL gave "
                "them. Then its answers were checked against FPL's.",
            ],
            className="prose",
        ),
        html.P(
            [
                "Its typical miss was ", html.Strong(theme.money(overall["mae"], places=2)),
                " a player. ", html.Strong(f"{overall['within_0_25m']:.0%}"),
                " of its prices landed within £0.25m of FPL's, ",
                html.Strong(f"{overall['interval_coverage']:.0%}"),
                " fell inside the 95% likely range, and its errors were ",
                html.Strong(f"{bt['improvement_over_naive']:.0%} smaller"),
                " than simply assuming every price stays put.",
            ],
            className="prose lead-figures",
        ),
        html.Table(
            [html.Thead(html.Tr([html.Th("Position"), html.Th("Players", className="num"),
                                 html.Th("Typical miss", className="num"),
                                 html.Th("Within £0.25m", className="num"),
                                 html.Th("Inside range", className="num")])),
             html.Tbody(rows)],
            className="terms accuracy",
        ),
        html.P(
            [
                html.Strong("Where it struggles. "),
                f"{weakest[0]}s are the weak spot: the likely range caught only "
                f"{weakest[1]['interval_coverage']:.0%} of them, short of the 95% it promises, "
                "and the model tends to overprice them. The best guess is transfer activity "
                "the season's stats cannot see. Across all positions the range covers "
                f"{overall['interval_coverage']:.0%}, a little under 95%, so read it as "
                "slightly optimistic.",
            ],
            className="prose note",
        ),
        class_name="how-block",
    )


def layout() -> html.Div:
    bt = _backtest()
    return html.Div(
        [
            html.Section(
                html.Div(
                    [
                        html.H1("How it works"),
                        html.P("A transparent model, not a black box: every price on this site "
                               "can be taken apart into the pieces that made it.",
                               className="lede"),
                    ],
                    className="wrap",
                ),
                className="hero hero-compact",
            ),
            html.Div(
                [
                    ui.section(
                        "The idea",
                        html.Div(
                            [
                                _step("1. Learn from history",
                                      html.P(f"The model studied {_meta['training_rows']:,} "
                                             "player-seasons: how each one played, and the price "
                                             "FPL gave him the following August.", className="prose")),
                                _step("2. Weigh each ingredient",
                                      html.P(f"It settles on a fixed weight for each of "
                                             f"{_meta['n_predictors']} ingredients: this season's "
                                             "price, points, minutes, goals, ownership, position, "
                                             "club and more.", className="prose")),
                                _step("3. Add them up",
                                      html.P("A player's predicted price is just those weights "
                                             "times his numbers, summed. That is why every player "
                                             "card can show exactly where its price comes from.",
                                             className="prose")),
                            ],
                            className="steps",
                        ),
                        html.P(
                            [html.Strong("The biggest ingredient is the price he already has. "),
                             "FPL rarely moves a player far between seasons, so most of any "
                             "prediction is this season's price, with performance nudging it up "
                             "or down. The interesting part is the nudge."],
                            className="prose note",
                        ),
                        class_name="how-block",
                    ),
                    _accuracy(bt) if bt else None,
                    ui.section(
                        "Predicting from a season still being played",
                        html.P(
                            "Price Watch has to turn a few gameweeks into a full season. By "
                            "default it scales each player's totals so far up to 38 gameweeks. "
                            "That is simple and uses only this season, but early on it is "
                            "jumpy: three good games scale into a record-breaking season.",
                            className="prose",
                        ),
                        html.P(
                            "Projection settings offer a steadier alternative, which blends "
                            "each player's form this season with his last one, trusting this "
                            "season more with every gameweek. At six gameweeks the two count "
                            "equally; by gameweek 30 it is 83% this season. Players new to the "
                            "league then borrow a typical season for their position and price.",
                            className="prose",
                        ),
                        html.P(
                            "Either way, each player is scaled by his own club's fixtures, so a "
                            "club with a game in hand is not treated as a week behind. Anything "
                            "that ends up beyond what the model has ever seen is held at the "
                            "edge of its experience rather than extrapolated.",
                            className="prose",
                        ),
                        class_name="how-block",
                    ),
                    ui.section(
                        "Checked, not assumed",
                        html.Ul(
                            [
                                html.Li("Every breakdown adds up exactly to its price. The model "
                                        "is linear, so nothing is approximated."),
                                html.Li("This site and the batch pipeline behind it are tested to "
                                        "give identical prices for every player."),
                                html.Li("If the code or data change, the model retrains before it "
                                        "answers, so a stale model never serves a price."),
                                html.Li("Price enters twice, as itself and squared, so budget "
                                        "and premium players can be priced on different "
                                        "slopes. FPL keeps stars expensive and props cheap "
                                        "players against a floor, and a straight line cannot "
                                        "do both."),
                            ],
                            className="prose checks",
                        ),
                        class_name="how-block",
                    ),
                ],
                className="wrap how",
            ),
        ],
    )
