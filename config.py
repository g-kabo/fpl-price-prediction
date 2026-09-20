"""Central configuration for the FPL price-prediction pipeline.

Rolling the model forward a season is a one-line change here: bump
``TRAIN_THROUGH``, ``SCORE_SEASON`` and ``PREDICT_SEASON`` by one. Every
script also accepts CLI overrides for the same three values, which is how
the R-reproduction check in the README is run.

Seasons are identified by their *start year* throughout: 2025 means the
2025-26 season, whose data lives in the ``2025-26`` folder upstream.
"""

from pathlib import Path

# --- Paths -----------------------------------------------------------------

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_DIR = PROJECT_DIR / "output"
PLOT_DIR = OUTPUT_DIR / "plots"

# --- Upstream data ---------------------------------------------------------

GITHUB_BASE = (
    "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/"
)

# --- Season configuration --------------------------------------------------

#: Earliest season with usable ``players_raw.csv`` for this model.
FIRST_SEASON = 2017

#: Last season used for *training*. Each training row's target is the start
#: price of the following season, so TRAIN_THROUGH=2024 means the newest
#: training transition is 2024-25 -> 2025-26.
TRAIN_THROUGH = 2024

#: End-of-season stats fed to the fitted model to produce predictions.
SCORE_SEASON = 2025

#: The season whose starting prices we are predicting.
PREDICT_SEASON = 2026


def training_seasons(train_through: int = TRAIN_THROUGH) -> list[int]:
    return list(range(FIRST_SEASON, train_through + 1))


def required_seasons(
    train_through: int = TRAIN_THROUGH,
    score_season: int = SCORE_SEASON,
    predict_season: int = PREDICT_SEASON,
) -> list[int]:
    """Every season that must be downloaded.

    Note the ``+ 1``: the newest training season needs the *following*
    season's start price as its target, so that season must be loaded too
    even when it is not itself a training season.
    """
    seasons = set(training_seasons(train_through))
    seasons.add(train_through + 1)
    seasons.add(score_season)
    seasons.add(predict_season)
    return sorted(seasons)


def season_folder(season: int) -> str:
    """2025 -> '2025-26' (the upstream repo's folder naming)."""
    return f"{season}-{(season + 1) % 100:02d}"


def season_label(season: int) -> str:
    """Human-facing season name, same format as the folder."""
    return season_folder(season)


# --- Model hyperparameters (mirroring the R) -------------------------------

SEED = 2021
TEST_PROP = 0.25          # tidymodels initial_split() default prop = 3/4
STRATA_BREAKS = 4         # tidymodels strata default breaks = 4
CV_FOLDS = 10             # vfold_cv(v = 10)
TEAM_LUMP_THRESHOLD = 0.03  # step_other(team_name, threshold = 0.03)
PRED_INTERVAL_ALPHA = 0.05  # 95% prediction intervals

#: Positions in the order R declared the factor levels. The first entry is
#: the dummy-encoding reference level (step_dummy drops the first level).
POSITIONS = ["GK", "DEF", "MID", "FWD"]

#: Set1, ordered to match the R's ``direction = -1`` (FWD first). Lives here
#: rather than in ``plots.py`` so the app's Plotly charts and the pipeline's
#: matplotlib PNGs colour a position identically without the app having to
#: import matplotlib for four hex values.
POSITION_COLOURS = {
    "GK": "#984EA3",
    "DEF": "#4DAF4A",
    "MID": "#377EB8",
    "FWD": "#E41A1C",
}

#: A second, non-colour channel for the same four categories.
#:
#: Set1's blue and purple are 3.5 apart in OKLab Delta E under a simulated
#: deuteranope -- well inside the range where MID and GK are the same dot.
#: The palette is the R's and stays the R's, so identity rides on shape as
#: well as hue wherever the marks are intermixed, which on a scatter of 667
#: overlapping players is everywhere.
POSITION_SYMBOLS = {
    "GK": "diamond",
    "DEF": "square",
    "MID": "triangle-up",
    "FWD": "circle",
}

#: Level that lumped/unseen teams collapse into, and the team reference
#: level (R: step_relevel(team_name, ref_level = "other")).
OTHER_TEAM = "other"
