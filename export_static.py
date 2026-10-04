"""Export what the static site needs: the fitted model and today's projection.

    python export_static.py            ->  web/data/*.json
    python export_static.py --parity   ->  also web/tests/parity.json

The site in ``web/`` is plain HTML and JavaScript, so everything Python
used to work out per request is computed here, once, and shipped as JSON:

    model.json    the fitted weights, the covariance behind the prediction
                  interval, ranges, teams and the form's field definitions
    board.json    every current player, projected to 38 gameweeks and priced
    seasons.json  every player-season What if can load, as form values
    history.json  start and finishing prices per season for today's players

The browser re-does the model's one line of arithmetic itself (``web/js/
model.js``), because What if needs it on every keystroke. ``--parity`` writes
the Python answers for a spread of inputs, and ``web/tests/parity.mjs``
checks the JavaScript against them.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

import config

APP_DIR = config.PROJECT_DIR / "app"
sys.path.insert(0, str(APP_DIR))

import charts  # noqa: E402
import form  # noqa: E402
import live  # noqa: E402
import model_store  # noqa: E402
import projection  # noqa: E402
import schema  # noqa: E402
import theme  # noqa: E402

WEB_DIR = config.PROJECT_DIR / "web"
DATA_DIR = WEB_DIR / "data"
TESTS_DIR = WEB_DIR / "tests"

#: Columns Price Watch keeps per player; the same list ``board.py`` used.
BOARD_KEEP = list(dict.fromkeys(
    schema.NUMERIC_NAMES
    + ["code", "web_name", "team_name", "element_type", "pred", "price_now",
       "points_now", "minutes_now", "selected_by_percent", "games_played"]))

#: Per-row fields of ``seasons.json``, in order.
SEASON_FIELDS = (["season", "code", "web_name", "team_name", "element_type", "form_team"]
                 + schema.FORM_NAMES + ["next_cost", "games_played", "pred"])


def _clean(value):
    """A JSON-safe scalar: numpy types unwrapped, NaN and inf as null."""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        value = float(value)
        return None if not math.isfinite(value) else value
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if value is pd.NA or value is None:
        return None
    return value


def _write(name: str, payload, directory: Path = DATA_DIR) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False),
                    encoding="utf-8")
    print(f"  {path.relative_to(config.PROJECT_DIR)}  {path.stat().st_size / 1024:,.0f} KB")


# ---------------------------------------------------------------- model


def model_payload() -> dict:
    fitted = model_store.get_model()
    meta = model_store.get_meta()
    result = fitted.result

    order = ["const"] + list(fitted.columns)
    params = result.params.reindex(order)
    cov = result.cov_params().reindex(index=order, columns=order)
    if params.isna().any() or cov.isna().any().any():
        raise RuntimeError("model parameters do not line up with the design columns")

    tcrit = float(stats.t.ppf(1 - config.PRED_INTERVAL_ALPHA / 2, result.df_resid))
    return {
        "columns": list(fitted.columns),
        "params": {name: float(value) for name, value in params.items()},
        "cov": [[float(v) for v in row] for row in cov.to_numpy()],
        "scale": float(result.scale),
        "tcrit": tcrit,
        "teams_retained": meta["teams_retained"],
        "other_team": config.OTHER_TEAM,
        "positions": schema.POSITIONS,
        "ranges": meta["ranges"],
        "medians": {k: _clean(v) for k, v in schema.field_defaults(meta["ranges"]).items()},
        "meta": {k: meta[k] for k in ("score_season", "predict_season", "train_through",
                                      "training_rows", "n_predictors", "rsquared_adj")},
        "first_season": config.FIRST_SEASON,
        "team_lump_threshold": config.TEAM_LUMP_THRESHOLD,
        "price_grid": form.PRICE_GRID,
        "material_contribution": form.MATERIAL_CONTRIBUTION,
        "term_labels": {c: charts.term_label(c) for c in fitted.columns},
        "kits": {team: list(kit) for team, kit in theme.KITS.items()},
        "neutral_kit": list(theme.NEUTRAL_KIT),
        "form": {
            "fields": [list(f) for f in schema.FORM_FIELDS],
            "numeric_fields": [list(f) for f in schema.NUMERIC_FIELDS],
            "numeric_names": schema.NUMERIC_NAMES,
            "form_names": schema.FORM_NAMES,
            "help": schema.FIELD_HELP,
            "steps": form.STEPS,
            "groups": form.FIELD_GROUPS,
            "appearances_field": schema.APPEARANCES_FIELD,
            "max_appearances": schema.MAX_APPEARANCES,
            "position_field": schema.POSITION_FIELD,
            "team_field": schema.TEAM_FIELD,
        },
    }


# ---------------------------------------------------------------- Price Watch


def _project(season: live.LiveSeason, meta: dict) -> pd.DataFrame:
    """Every current player, projected and priced, as Price Watch did it."""
    current = season.players
    projected = projection.project_frame(
        current, season.player_games, meta["ranges"], league_games=season.progress.league_games)
    raw = model_store.get_model().predict(projected[schema.MODEL_INPUT_COLUMNS])
    projected["pred_raw"] = raw
    projected["pred"] = raw.round(3)

    lookup = current.set_index("code")
    for column, source in (("team_name", "team_name"), ("element_type", "element_type"),
                           ("points_now", "total_points"), ("minutes_now", "minutes"),
                           ("price_now", "final_cost"),
                           ("selected_by_percent", "selected_by_percent")):
        projected[column] = projected["code"].map(lookup[source])
    projected["element_type"] = projected["element_type"].astype(str)
    return projected


def board_payload(season: live.LiveSeason, projected: pd.DataFrame) -> dict:
    keep = [c for c in BOARD_KEEP if c in projected.columns]
    records = [{k: _clean(v) for k, v in row.items()}
               for row in projected[keep].to_dict("records")]
    return {
        "fetched_at": season.fetched_at.isoformat() if season.fetched_at else None,
        "as_of_label": season.as_of_label,
        "is_live": bool(season.is_live),
        "error": season.error,
        "gameweek_label": season.gameweek_label,
        "stale_after_hours": live.STALE_AFTER_HOURS,
        "players": records,
    }


def history_payload(codes: set[int], predict_season: int) -> dict:
    history = model_store.get_price_history().reset_index()
    history = history[history["code"].isin(codes) & (history["season"] < predict_season)]
    out: dict[str, list] = {}
    for row in history.itertuples():
        out.setdefault(str(int(row.code)), []).append(
            [int(row.season), _clean(row.start_cost), _clean(row.final_cost)])
    return out


# ---------------------------------------------------------------- What if


def seasons_payload(projected: pd.DataFrame, meta: dict) -> dict:
    """Every season What if can load, as the form holds it.

    Completed seasons come from ``seasons.csv``; the season in progress is
    the projection above, which is what ``lab.py`` loaded it from.
    """
    retained = set(meta["teams_retained"])

    def form_team(team):
        return team if team in retained else config.OTHER_TEAM

    rows = []
    seasons = model_store.get_seasons()
    for player in seasons.itertuples(index=False):
        record = pd.Series(player._asdict())
        values = schema.form_values(record)
        rows.append({
            "season": int(record["season"]), "code": int(record["code"]),
            "web_name": record["web_name"], "team_name": record["team_name"],
            "element_type": record["element_type"], "form_team": form_team(record["team_name"]),
            **values, "next_cost": record["next_cost"], "games_played": None, "pred": None,
        })

    for _, player in projected.iterrows():
        values = schema.form_values(player)
        values[schema.APPEARANCES_FIELD] = float(player[schema.APPEARANCES_FIELD])
        rows.append({
            "season": int(meta["predict_season"]), "code": int(player["code"]),
            "web_name": player["web_name"], "team_name": player["team_name"],
            "element_type": player["element_type"], "form_team": form_team(player["team_name"]),
            **values, "next_cost": None, "games_played": float(player["games_played"]),
            "pred": float(player["pred_raw"]),
        })

    return {
        "fields": SEASON_FIELDS,
        "rows": [[_clean(row[f]) for f in SEASON_FIELDS] for row in rows],
    }


# ---------------------------------------------------------------- parity


def parity_payload(projected: pd.DataFrame, meta: dict, count: int = 400) -> dict:
    """Python's own answers for the JavaScript to match.

    Inputs are real player-seasons, plus a few deliberately awkward ones
    (a never-played player, a club the model lumps, values past the training
    range) because those are where a reimplementation would drift.
    """
    fitted = model_store.get_model()
    rng = np.random.default_rng(config.SEED)

    seasons = model_store.get_seasons()
    sample = seasons.sample(min(count, len(seasons)), random_state=config.SEED)
    cases = []
    for _, player in sample.iterrows():
        values = {name: float(player[name]) for name in schema.NUMERIC_NAMES}
        values[schema.POSITION_FIELD] = player["element_type"]
        values[schema.TEAM_FIELD] = player["team_name"]
        cases.append(values)

    base = dict(cases[0])
    for tweak in (
        {"minutes": 0, "total_points": 0, "goals_scored": 0, "assists": 0,
         "points_per_game": 0, "value_season": 0},
        {schema.TEAM_FIELD: "Hull City"},
        {schema.TEAM_FIELD: config.OTHER_TEAM, schema.POSITION_FIELD: "GK"},
        {"start_cost": 16.5, "final_cost": 17.2, "total_points": 500},
        {"total_points": -4, "value_season": -1.0},
    ):
        cases.append({**base, **tweak})

    out = []
    for values in cases:
        row = form.row_from_values(values)
        interval = fitted.predict_with_interval(row)
        parts = form.contributions(values)
        out.append({
            "values": values,
            "pred": float(interval["pred"].iloc[0]),
            "lower": float(interval["pred_lower"].iloc[0]),
            "upper": float(interval["pred_upper"].iloc[0]),
            "total": float(parts["total"]),
            "intercept": float(parts["intercept"]),
            "rest": float(parts["rest"]),
            "n_rest": int(parts["n_rest"]),
            "shown": [[t[0], float(t[3])] for t in parts["shown"]],
        })

    # What Price Watch showed, for the page's own list to match.
    board = [{"code": int(r.code), "pred": float(r.pred),
              "values": {k: _clean(getattr(r, k)) for k in
                         schema.NUMERIC_NAMES + [schema.POSITION_FIELD, schema.TEAM_FIELD]}}
             for r in projected.itertuples()]
    del rng
    return {"cases": out, "board": board}


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--parity", action="store_true",
                        help="also write web/tests/parity.json for web/tests/parity.mjs")
    args = parser.parse_args(argv)

    meta = model_store.get_meta()
    season = live.get_live_season()
    projected = _project(season, meta)

    print("Writing the static site's data:")
    _write("model.json", model_payload())
    _write("board.json", board_payload(season, projected))
    _write("seasons.json", seasons_payload(projected, meta))
    _write("history.json", history_payload(set(projected["code"].astype(int)),
                                           meta["predict_season"]))
    if args.parity:
        _write("parity.json", parity_payload(projected, meta), TESTS_DIR)


if __name__ == "__main__":
    main()
