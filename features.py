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
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config

#: Predictors named directly in the R formula.
BASE_NUMERIC = [
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

#: Original (pre-dummy) variables, in the order permutation importance
#: reports them. DALEX permutes original variables rather than dummy
#: columns, so importance is measured over these.
MODEL_VARIABLES = BASE_NUMERIC + list(RATE_FEATURES) + [
    "no_mins", "element_type", "team_name",
]


def add_rate_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-minute rates, zeroed for players who never took the field.

    A zero-minute player is a real and common case (unused squad members),
    so the rates are defined as 0 rather than left undefined — matching
    the R's ``if_else(minutes == 0, 0, ...)``.
    """
    df = df.copy()
    played = df["minutes"] > 0

    for new_col, numerator in RATE_FEATURES.items():
        df[new_col] = (df[numerator] / df["minutes"]).where(played, 0.0)

    df["no_mins"] = ~played
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
    df: pd.DataFrame, lumper: TeamLumper, columns: list[str] | None = None
) -> pd.DataFrame:
    """Assemble the numeric matrix the OLS fit consumes.

    Passing ``columns`` (the order stored at fit time) reindexes the result
    to match, so a scoring frame missing a team simply contributes a column
    of zeros rather than shifting every coefficient along by one.
    """
    df = add_rate_features(df)

    parts = [df[BASE_NUMERIC + list(RATE_FEATURES)].astype(float)]
    parts.append(df[["no_mins"]].astype(float))
    parts.append(_dummies(df["element_type"].astype(object), config.POSITIONS, "element_type"))
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
