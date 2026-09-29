"""Score non-linear learners against the default OLS model.

    python model_experiments.py [--refresh] [--tag NAME] [--quick]

Same protocol as ``feature_experiments.py``: rolling-origin temporal CV, fit
on every transition starting before season ``s`` and predict ``s -> s+1``
for 2020-21 .. 2025-26. The OLS default is the baseline every row is measured
against, so ``temporal_rmse_delta < 0`` means the learner beat it.

Two things are varied besides the learner:

* **Target.** ``level`` predicts ``next_cost`` directly. ``delta`` predicts
  ``next_cost - start_cost`` and adds ``start_cost`` back. Trees cannot
  extrapolate past the range of their leaves, and most of a player's next
  price is simply his current one, so asking a tree to learn the *change*
  leaves it the part it is good at. ``ols_resid`` fits the OLS default first
  and a booster on its residuals -- a stacked hybrid that keeps the linear
  model's extrapolation and lets the trees mop up interactions.
* **Features.** ``default`` is ``features.DEFAULT_NUMERIC`` (what OLS uses).
  ``wide`` adds the candidates OLS rejected -- lags, the gameweek ownership
  path, ICT and bonus. Collinearity that hurt OLS costs a tree much less, so
  a rejection there is not a rejection here.

Writes ``output/model_experiments{_tag}.csv`` and
``output/model_experiments_folds{_tag}.csv``.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import (ExtraTreesRegressor, HistGradientBoostingRegressor,
                              RandomForestRegressor)

import config
import feature_experiments as fe
import features
import model

WIDE_NUMERIC = list(dict.fromkeys(features.DEFAULT_NUMERIC + [
    "cost_change_start", "bonus", "bps", "ict_index", "influence", "creativity", "threat",
    "start_selected_by_percent", "final_selected_by_percent",
    "min_selected_by_percent", "max_selected_by_percent",
    *fe.LAG_FEATURES, *fe.CUMUL_FEATURES,
]))

FEATURE_SETS = {"default": features.DEFAULT_NUMERIC, "wide": WIDE_NUMERIC}

#: Premium tier cut for the fold-level premium RMSE -- where a tree's
#: inability to extrapolate would show first.
PREMIUM_FROM = 9.5


@dataclass
class SklearnPriceModel:
    """``PriceModel``'s preprocessing in front of any scikit-learn regressor."""

    estimator: object
    numeric: list[str] | None = None
    target: str = "level"  # "level" | "delta" | "ols_resid"
    lumper: features.TeamLumper | None = None
    columns: list[str] = field(default_factory=list)
    base: model.PriceModel | None = None

    def _offset(self, df: pd.DataFrame) -> np.ndarray:
        if self.target == "delta":
            return df["start_cost"].to_numpy(float)
        if self.target == "ols_resid":
            return self.base.predict(df).to_numpy(float)
        return np.zeros(len(df))

    def fit(self, df: pd.DataFrame) -> "SklearnPriceModel":
        self.lumper = features.TeamLumper().fit(df["team_name"])
        if self.target == "ols_resid":
            self.base = model.PriceModel().fit(df)
        X = features.build_design_matrix(df, self.lumper, numeric=self.numeric)
        y = df[model.TARGET].to_numpy(float) - self._offset(df)
        complete = (X.notna().all(axis=1) & np.isfinite(y)).to_numpy()
        self.columns = list(X.columns)
        self.estimator = clone(self.estimator).fit(X[complete].to_numpy(), y[complete])
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        X = features.build_design_matrix(df, self.lumper, self.columns, numeric=self.numeric)
        pred = self.estimator.predict(X.fillna(0).to_numpy()) + self._offset(df)
        # Match OLS: no prediction for a row with a missing input.
        pred = np.where(X.notna().all(axis=1), pred, np.nan)
        return pd.Series(pred, index=df.index, name="pred")


def rf(**kw):
    return RandomForestRegressor(n_estimators=500, n_jobs=-1, random_state=config.SEED, **kw)


def hgb(**kw):
    base = dict(max_iter=2000, learning_rate=0.03, early_stopping=False, random_state=config.SEED)
    return HistGradientBoostingRegressor(**{**base, **kw})


#: name -> (estimator, target, feature set). A small, deliberate grid: six
#: temporal folds cannot carry a big search without the winner being luck.
LEARNERS: dict[str, tuple] = {
    "rf  level  default  (mf=1/3, leaf=3)": (rf(max_features=1 / 3, min_samples_leaf=3), "level", "default"),
    "rf  delta  default  (mf=1/3, leaf=3)": (rf(max_features=1 / 3, min_samples_leaf=3), "delta", "default"),
    "rf  delta  default  (mf=0.6, leaf=5)": (rf(max_features=0.6, min_samples_leaf=5), "delta", "default"),
    "rf  delta  wide     (mf=1/3, leaf=3)": (rf(max_features=1 / 3, min_samples_leaf=3), "delta", "wide"),
    "et  delta  default  (mf=0.6, leaf=3)": (
        ExtraTreesRegressor(n_estimators=500, max_features=0.6, min_samples_leaf=3,
                            n_jobs=-1, random_state=config.SEED), "delta", "default"),

    "hgb level  default  (d=4, 600 it)": (hgb(max_depth=4, max_iter=600), "level", "default"),
    "hgb delta  default  (d=4, 600 it)": (hgb(max_depth=4, max_iter=600), "delta", "default"),
    "hgb delta  default  (d=3, 400 it, l2=1)": (hgb(max_depth=3, max_iter=400, l2_regularization=1.0), "delta", "default"),
    "hgb delta  default  (d=6, 300 it, leaf=30)": (hgb(max_depth=6, max_iter=300, min_samples_leaf=30), "delta", "default"),
    "hgb delta  wide     (d=4, 600 it)": (hgb(max_depth=4, max_iter=600), "delta", "wide"),
    "hgb delta  default  L1    (d=4, 600 it)": (hgb(max_depth=4, max_iter=600, loss="absolute_error"), "delta", "default"),

    "hgb ols_resid default (d=3, 200 it)": (hgb(max_depth=3, max_iter=200, learning_rate=0.02), "ols_resid", "default"),
    "hgb ols_resid wide    (d=3, 200 it)": (hgb(max_depth=3, max_iter=200, learning_rate=0.02), "ols_resid", "wide"),
    "rf  ols_resid wide    (mf=1/3, leaf=10)": (rf(max_features=1 / 3, min_samples_leaf=10), "ols_resid", "wide"),
}

QUICK = [
    "rf  level  default  (mf=1/3, leaf=3)", "rf  delta  default  (mf=1/3, leaf=3)",
    "hgb level  default  (d=4, 600 it)", "hgb delta  default  (d=4, 600 it)",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--refresh", action="store_true", help="re-download instead of using data/ cache")
    p.add_argument("--tag", default="", help="suffix for output filenames")
    p.add_argument("--quick", action="store_true", help="only the four headline learners")
    return p.parse_args()


def temporal_cv(frame: pd.DataFrame, make) -> list[dict]:
    rows = []
    for season in range(fe.FIRST_TEST_SEASON, int(frame["season"].max()) + 1):
        train, test = frame[frame["season"] < season], frame[frame["season"] == season]
        pred = make().fit(train).predict(test)
        truth = test[model.TARGET]
        rmse, mae, n = fe._score(truth, pred)
        prem = test["start_cost"] >= PREMIUM_FROM
        keep = pred.notna()
        err = (pred - truth)[keep]
        rows.append({
            "test_season": config.season_label(season), "rmse": rmse, "mae": mae, "n": n,
            "bias": float(err.mean()),
            "within_0_1m": float((err.abs() <= 0.1 + 1e-9).mean()),
            "premium_rmse": fe._score(truth[prem], pred[prem])[0],
            "naive_rmse": fe._score(truth, test["start_cost"])[0],
        })
    return rows


def main() -> None:
    args = parse_args()
    tag = f"_{args.tag}" if args.tag else ""
    frame = fe.load_frame(args.refresh)
    print(f"{len(frame)} transitions; temporal folds "
          f"{config.season_label(fe.FIRST_TEST_SEASON)} .. {config.season_label(frame['season'].max())}\n")

    learners = {k: LEARNERS[k] for k in QUICK} if args.quick else LEARNERS
    makers = {"ols default (baseline)": lambda: model.PriceModel()}
    for name, (est, target, fset) in learners.items():
        makers[name] = (lambda est=est, target=target, fset=fset:
                        SklearnPriceModel(est, numeric=FEATURE_SETS[fset], target=target))

    summary, folds = [], []
    for name, make in makers.items():
        t0 = time.perf_counter()
        fold_rows = temporal_cv(frame, make)
        fd = pd.DataFrame(fold_rows)
        folds += [{"learner": name, **r} for r in fold_rows]
        summary.append({
            "learner": name,
            "temporal_rmse": fd["rmse"].mean(), "temporal_mae": fd["mae"].mean(),
            "premium_rmse": fd["premium_rmse"].mean(), "within_0_1m": fd["within_0_1m"].mean(),
            "bias": fd["bias"].mean(), "rmse_2026": fd["rmse"].iloc[-1],
            "seconds": time.perf_counter() - t0,
        })
        print(f"  {name:<45} temporal RMSE {summary[-1]['temporal_rmse']:.4f}  "
              f"({summary[-1]['seconds']:.0f}s)")

    out = pd.DataFrame(summary)
    fold_df = pd.DataFrame(folds)
    base = out.iloc[0]
    base_folds = fold_df[fold_df["learner"] == base["learner"]].set_index("test_season")["rmse"]
    for col in ("temporal_rmse", "premium_rmse", "rmse_2026"):
        out[f"{col}_delta"] = out[col] - base[col]
    out["folds_won"] = [
        int((fold_df[fold_df["learner"] == v].set_index("test_season")["rmse"] < base_folds).sum())
        for v in out["learner"]
    ]

    pd.set_option("display.width", 220)
    n_folds = fold_df["test_season"].nunique()
    print(f"\nSorted by temporal RMSE (deltas vs OLS; folds won of {n_folds}):")
    cols = ["learner", "temporal_rmse", "temporal_rmse_delta", "temporal_mae", "premium_rmse",
            "premium_rmse_delta", "within_0_1m", "bias", "rmse_2026", "folds_won", "seconds"]
    print(out.sort_values("temporal_rmse")[cols].round(4).to_string(index=False))

    print("\nPer-fold RMSE:")
    print(fold_df.pivot(index="learner", columns="test_season", values="rmse")
          .loc[out.sort_values("temporal_rmse")["learner"]].round(4).to_string())
    print("\nCarry-forward (naive) RMSE per fold:")
    print(fold_df[fold_df["learner"] == base["learner"]][["test_season", "naive_rmse"]]
          .round(4).to_string(index=False))

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(config.OUTPUT_DIR / f"model_experiments{tag}.csv", index=False, encoding="utf-8")
    fold_df.to_csv(config.OUTPUT_DIR / f"model_experiments_folds{tag}.csv", index=False, encoding="utf-8")
    print(f"\nWrote model_experiments{tag}.csv, model_experiments_folds{tag}.csv")


if __name__ == "__main__":
    main()
