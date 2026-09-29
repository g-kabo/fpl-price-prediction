"""Feature engineering and design-matrix construction.

Translation of the ``recipe()`` at lines 1224-1241 of ``Price Prediction.Rmd``:

    step_mutate(...)  -> add_rate_features()
    step_other(0.03)  -> TeamLumper
    step_relevel      -> OTHER_TEAM as the dropped reference level
    step_dummy        -> build_design_matrix()

The recipe is stateful — the set of teams that survive lumping and the
resulting dummy columns are learned at fit time and must be replayed
identically at predict time. ``TeamLumper`` plus the stored column order in
``PriceModel`` is what carries that state; rebuilding the columns from the
scoring data instead would silently misalign coefficients whenever the
league's composition changes.

The default feature set is no longer the R's. ``feature_experiments.py``
scored the alternatives on a rolling-origin temporal backtest (fit on every
season before ``s``, predict ``s -> s+1``, for 2020-21 to 2025-26) and the
default below cut its RMSE from 0.3288 to 0.3054. The R formula survives as
:data:`R_NUMERIC`, used by ``run_pipeline.py --r-compat``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config

#: Predictors named directly in the R formula.
R_BASE_NUMERIC = [
    "start_cost", "cost_change_start", "total_points", "minutes",
    "transfers_in", "transfers_out", "goals_scored", "assists", "bps",
    "clean_sheets", "points_per_game", "value_season",
]

#: ``step_mutate`` per-minute rates: new column -> numerator column.
RATE_FEATURES = {
    "goals_per_min": "goals_scored",
    "assists_per_min": "assists",
    "bps_per_min": "bps",
    "points_per_mins": "total_points",
    "cleansheets_per_min": "clean_sheets",
}

#: The numeric predictors the R model used.
R_NUMERIC = R_BASE_NUMERIC + list(RATE_FEATURES)

#: ``PriceModel``'s default numeric predictors. Against the R formula:
#:
#: * ``transfers_in``/``transfers_out`` are replaced by ``selected_by_percent``.
#:   Raw transfer counts drift with the size of the game (FPL roughly doubled
#:   its manager count between 2017-18 and 2025-26); ownership is a share, so
#:   it means the same thing every season.
#: * The five per-minute rates, ``bps`` and ``clean_sheets`` are dropped:
#:   each is near-collinear with ``total_points``/``minutes`` and removing
#:   them cost nothing out of sample.
#: * ``final_cost`` replaces ``cost_change_start``. The two span the same
#:   space alongside ``start_cost`` (final = start + change), so predictions
#:   are identical; the end price simply reads more naturally.
#: * Both prices enter squared as well. FPL's pricing is not linear: cheap
#:   players sit against a 4.0-4.5m floor and carry only about half their
#:   price into next season, premiums keep ~85% of theirs. The squares let
#:   that slope bend; splines and per-tier adjustments did no better.
DEFAULT_NUMERIC = [
    "start_cost", "final_cost", "total_points", "minutes", "goals_scored",
    "assists", "points_per_game", "value_season", "selected_by_percent",
    "start_cost_sq", "final_cost_sq",
]

#: Engineered features, derivable from a single season's frame. Most are
#: candidates ``feature_experiments.py`` scored and rejected; the squared
#: prices are in the default.
#:
#: The ``*_share`` variants exist because raw transfer counts drift with the
#: size of the game: FPL had ~6m managers in 2017-18 and over 11m by 2025-26,
#: so a given ``transfers_in`` means far less interest now than it used to.
#: Dividing by the season total puts every season on the same footing.
ENGINEERED_FEATURES = [
    "net_transfers", "log_transfers_in", "log_transfers_out", "log_net_transfers",
    "transfers_in_share", "transfers_out_share", "net_transfers_share",
    "selected_by_percent", "bonus", "ict_index", "influence", "creativity",
    "threat", "minutes_share", "start_cost_sq", "final_cost_sq",
    # From the gameweek files, merged on in clean.clean_season.
    "start_selected_by_percent", "final_selected_by_percent",
    "min_selected_by_percent", "max_selected_by_percent",
]

#: Original (pre-dummy) variables, in the order permutation importance
#: reports them. DALEX permutes original variables rather than dummy
#: columns, so importance is measured over these.
MODEL_VARIABLES = list(dict.fromkeys(DEFAULT_NUMERIC + R_NUMERIC + ENGINEERED_FEATURES + [
    "no_mins", "element_type", "team_name",
]))


def add_rate_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-minute rates, zeroed for players who never took the field.

    A zero-minute player is a real and common case (unused squad members),
    so the rates are defined as 0 rather than left undefined — matching
    the R's ``if_else(minutes == 0, 0, ...)``.

    A rate whose numerator the frame lacks is skipped: the default model uses
    none of them, and the app's form no longer collects ``bps`` or
    ``clean_sheets``.
    """
    df = df.copy()
    played = df["minutes"] > 0

    for new_col, numerator in RATE_FEATURES.items():
        if numerator in df:
            df[new_col] = (df[numerator] / df["minutes"]).where(played, 0.0)

    df["no_mins"] = ~played
    return df


def _signed_log1p(x: pd.Series) -> pd.Series:
    return np.sign(x) * np.log1p(x.abs())


def add_engineered_features(df: pd.DataFrame, wanted: list[str]) -> pd.DataFrame:
    """Compute whichever of :data:`ENGINEERED_FEATURES` appear in ``wanted``.

    Lazy on purpose: the app builds one-row frames from a form that only
    carries the default inputs, so computing every candidate unconditionally
    would fail on columns it never collects.

    The ``*_share`` columns are not derived here: a share needs the whole
    season as its denominator, and this function often sees a slice of one
    (a CV fold, a single form row). ``clean.clean_season`` computes them.
    """
    wanted = [c for c in wanted if c in ENGINEERED_FEATURES]
    if not wanted:
        return df
    df = df.copy()
    if {"net_transfers", "log_net_transfers"} & set(wanted):
        df["net_transfers"] = df["transfers_in"] - df["transfers_out"]
    derived = {
        "log_transfers_in": lambda: np.log1p(df["transfers_in"]),
        "log_transfers_out": lambda: np.log1p(df["transfers_out"]),
        "log_net_transfers": lambda: _signed_log1p(df["net_transfers"]),
        "minutes_share": lambda: df["minutes"] / (38 * 90),
        "start_cost_sq": lambda: df["start_cost"] ** 2,
        "final_cost_sq": lambda: df["final_cost"] ** 2,
    }
    for name in wanted:
        if name in derived:
            df[name] = derived[name]()
        elif name not in df:
            raise KeyError(f"engineered feature {name!r} needs a raw column the frame lacks")
    return df


class TeamLumper:
    """``step_other(team_name, threshold = 0.03)`` as a fitted transform.

    Teams making up less than ``threshold`` of the training rows are pooled
    into a single ``"other"`` level, as are any teams never seen during
    training. That second case is what keeps newly promoted sides from
    breaking prediction: in 2026-27 that is Coventry City, Hull City and
    Ipswich Town, none of which appear in the training seasons.
    """

    def __init__(self, threshold: float = config.TEAM_LUMP_THRESHOLD):
        self.threshold = threshold
        self.keep_: list[str] = []

    def fit(self, teams: pd.Series) -> "TeamLumper":
        freq = teams.value_counts(normalize=True, dropna=True)
        self.keep_ = sorted(freq[freq >= self.threshold].index.tolist())
        return self

    def transform(self, teams: pd.Series) -> pd.Series:
        kept = teams.where(teams.isin(self.keep_), config.OTHER_TEAM)
        return kept.fillna(config.OTHER_TEAM)

    @property
    def levels(self) -> list[str]:
        """All levels after lumping, reference level ("other") first."""
        return [config.OTHER_TEAM] + self.keep_


def _dummies(values: pd.Series, levels: list[str], prefix: str) -> pd.DataFrame:
    """One-hot encode against a fixed level list, dropping the first level.

    Dropping the first level is ``step_dummy``'s behaviour; the level order
    is fixed by the caller so the reference category ("other" for teams,
    "GK" for positions) is stable regardless of what the data contains.
    """
    categorical = pd.Categorical(values, categories=levels)
    out = pd.get_dummies(categorical, prefix=prefix, prefix_sep="_", dtype=float)
    return out.drop(columns=[f"{prefix}_{levels[0]}"]).set_axis(values.index)


def build_design_matrix(
    df: pd.DataFrame,
    lumper: TeamLumper | None,
    columns: list[str] | None = None,
    numeric: list[str] | None = None,
    use_team: bool = True,
    use_position: bool = True,
) -> pd.DataFrame:
    """Assemble the numeric matrix the OLS fit consumes.

    Passing ``columns`` (the order stored at fit time) reindexes the result
    to match, so a scoring frame missing a team simply contributes a column
    of zeros rather than shifting every coefficient along by one.

    ``numeric`` picks the numeric predictors (default :data:`DEFAULT_NUMERIC`)
    and ``use_team=False``/``use_position=False`` leave out the team or
    position dummies; all three exist for feature-selection experiments and
    leave the default model untouched.
    """
    numeric = DEFAULT_NUMERIC if numeric is None else numeric
    df = add_engineered_features(add_rate_features(df), numeric)

    parts = [df[numeric].astype(float)]
    parts.append(df[["no_mins"]].astype(float))
    if use_position:
        parts.append(_dummies(df["element_type"].astype(object), config.POSITIONS, "element_type"))
    if use_team:
        parts.append(_dummies(lumper.transform(df["team_name"]), lumper.levels, "team_name"))

    X = pd.concat(parts, axis=1)
    X.columns = [c.replace(" ", "_").replace("'", "") for c in X.columns]

    if columns is not None:
        X = X.reindex(columns=columns, fill_value=0.0)

    return X.astype(float)


def strata_bins(y: pd.Series, breaks: int = config.STRATA_BREAKS) -> np.ndarray:
    """Quantile bins for a stratified split, mirroring tidymodels' ``strata``.

    ``initial_split(strata = next_cost)`` cuts a numeric outcome into four
    quantile groups and splits within each, so the price distribution of
    the test set tracks the training set.
    """
    return pd.qcut(y, q=breaks, labels=False, duplicates="drop").to_numpy()
