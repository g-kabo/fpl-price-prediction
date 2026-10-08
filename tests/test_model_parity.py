"""The saved model and the batch pipeline must price every player identically.

The site is built from a saved artifact while ``run_pipeline.py`` refits from
scratch, so the two can silently diverge: a change to ``features.py`` or
``clean.py`` leaves an old pickle that still loads and still predicts, just
wrongly. Nothing in either code path would complain. This test is what
complains.

    python -m pytest tests/ -q

Run ``python train_and_save.py --force`` if this fails after an
intentional model change -- a failure here means the artifact is stale, not
that the model is wrong.
"""

from __future__ import annotations

import sys
from pathlib import Path

import joblib
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import train_and_save  # noqa: E402

PUBLISHED = config.OUTPUT_DIR / f"pred_price_{config.PREDICT_SEASON}.csv"

#: Predictions are exported rounded to 2dp, so equality is to that grid.
TOLERANCE = 0.005


@pytest.fixture(scope="module")
def artifacts():
    if not train_and_save.MODEL_PATH.exists():
        pytest.skip("run train_and_save.py first")
    return (
        joblib.load(train_and_save.MODEL_PATH),
        pd.read_csv(train_and_save.SCORES_PATH, encoding="utf-8"),
    )


@pytest.fixture(scope="module")
def published():
    if not PUBLISHED.exists():
        pytest.skip("run run_pipeline.py first")
    return pd.read_csv(PUBLISHED, encoding="utf-8").set_index("code")


def test_artifacts_are_not_stale():
    assert not train_and_save.is_stale(), (
        "models/ is older than the code or data it was built from -- "
        "run: python train_and_save.py --force"
    )


@pytest.mark.parametrize("column", ["pred", "pred_lower", "pred_upper"])
def test_matches_pipeline(artifacts, published, column):
    """Every player, point estimate and both interval bounds."""
    fitted, scores = artifacts

    predicted = fitted.predict_with_interval(scores).round(2)
    predicted.index = scores["code"]

    joined = predicted.join(published[[column]], rsuffix="_published", how="inner")
    assert len(joined) > 500, "too few players matched to be a meaningful check"

    difference = (joined[column] - joined[f"{column}_published"]).abs()
    worst = difference.max()
    assert worst < TOLERANCE, (
        f"{column} differs from the pipeline by up to {worst:.4f} "
        f"for {int((difference >= TOLERANCE).sum())} players"
    )


def test_intervals_survived_serialisation(artifacts):
    """``remove_data()`` on the results object would silently break these.

    A model pickled without its design matrix still returns point
    predictions, so this is the only cheap way to catch that regression.
    """
    fitted, scores = artifacts
    interval = fitted.predict_with_interval(scores.head(50))

    width = interval["pred_upper"] - interval["pred_lower"]
    assert (width > 0).all(), "prediction intervals collapsed to zero width"
    assert width.mean() == pytest.approx(1.177, abs=0.05)


def test_form_row_assembly_matches_cleaned_frame(artifacts):
    """A row built from form values must score like the cleaned row it came from.

    This is the join between What if's hand-assembled input and the
    pipeline's frame: if ``schema.MODEL_INPUT_COLUMNS`` ever drifts from
    what ``build_design_matrix`` reads, the two diverge here first.
    """
    import form
    import schema

    fitted, scores = artifacts
    sample = scores.nlargest(25, "total_points")

    from_frame = fitted.predict(sample).to_numpy()

    for position, (_, player) in enumerate(sample.iterrows()):
        # As the What if page does it: games played in, FPL's ratios derived.
        values = schema.form_values(player)
        values[schema.POSITION_FIELD] = player[schema.POSITION_FIELD]
        values[schema.TEAM_FIELD] = player[schema.TEAM_FIELD]
        interval, _ = form.predict(schema.with_ratios(values))
        assert float(interval["pred"].iloc[0]) == pytest.approx(
            from_frame[position], abs=1e-6
        ), f"{player['web_name']} scored differently through the form"
