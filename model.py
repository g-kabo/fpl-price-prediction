"""The price model itself: an OLS fit wrapped with its own preprocessing.

Translation of the tidymodels ``workflow()`` at lines 1210-1272 of
``Price Prediction.Rmd``. A workflow bundles the recipe and the model so
that ``fit()`` and ``predict()`` cannot disagree about preprocessing;
``PriceModel`` is the same idea — it owns the ``TeamLumper`` and the fitted
column order alongside the regression.

statsmodels rather than scikit-learn because the R model's output includes
95% *prediction* intervals (``predict(type = "pred_int")``) and a
coefficient table with p-values (``tidy(conf.int = TRUE)``). Both come for
free from ``OLSResults``; neither exists in scikit-learn.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.model_selection import KFold, train_test_split

import config
import features

TARGET = "next_cost"


def rmse(truth: np.ndarray, estimate: np.ndarray) -> float:
    return float(np.sqrt(np.mean((np.asarray(truth) - np.asarray(estimate)) ** 2)))


def mae(truth: np.ndarray, estimate: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(truth) - np.asarray(estimate))))


def r_squared(truth: np.ndarray, estimate: np.ndarray) -> float:
    truth, estimate = np.asarray(truth), np.asarray(estimate)
    ss_res = np.sum((truth - estimate) ** 2)
    ss_tot = np.sum((truth - truth.mean()) ** 2)
    return float(1 - ss_res / ss_tot)


@dataclass
class PriceModel:
    """Fitted preprocessing + regression for next-season starting price."""

    lump_threshold: float = config.TEAM_LUMP_THRESHOLD
    #: Numeric predictors; None means ``features.DEFAULT_NUMERIC``.
    numeric: list[str] | None = None
    use_team: bool = True
    lumper: features.TeamLumper | None = None
    columns: list[str] = field(default_factory=list)
    result: sm.regression.linear_model.RegressionResultsWrapper | None = None
    n_dropped: int = 0

    # --- fitting -----------------------------------------------------------

    def fit(self, df: pd.DataFrame) -> "PriceModel":
        self.lumper = features.TeamLumper(self.lump_threshold).fit(df["team_name"])
        X = features.build_design_matrix(df, self.lumper, numeric=self.numeric,
                                         use_team=self.use_team)
        y = df[TARGET].astype(float)

        # R's lm() drops incomplete cases via na.action = na.omit; a handful
        # of upstream rows carry unparseable points_per_game / value_season.
        complete = X.notna().all(axis=1) & y.notna()
        self.n_dropped = int((~complete).sum())

        self.columns = list(X.columns)
        self.result = sm.OLS(y[complete], sm.add_constant(X[complete], has_constant="add")).fit()
        return self

    def _matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.result is None or self.lumper is None:
            raise RuntimeError("PriceModel.fit() must be called before predicting")
        # getattr: artifacts pickled before these fields existed lack them.
        X = features.build_design_matrix(df, self.lumper, self.columns,
                                         numeric=getattr(self, "numeric", None),
                                         use_team=getattr(self, "use_team", True))
        return sm.add_constant(X, has_constant="add")

    # --- prediction --------------------------------------------------------

    def predict(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(self.result.predict(self._matrix(df)), index=df.index, name="pred")

    def predict_with_interval(
        self, df: pd.DataFrame, alpha: float = config.PRED_INTERVAL_ALPHA
    ) -> pd.DataFrame:
        """Point prediction plus a 95% prediction interval per player.

        ``obs_ci_*`` is the interval for a *new observation* (R's
        ``pred_int``), which is much wider than the ``mean_ci_*`` interval
        for the fitted mean — the latter would badly understate how far an
        individual player's price can land from the prediction.
        """
        frame = self.result.get_prediction(self._matrix(df)).summary_frame(alpha=alpha)
        return pd.DataFrame(
            {
                "pred": frame["mean"].to_numpy(),
                "pred_lower": frame["obs_ci_lower"].to_numpy(),
                "pred_upper": frame["obs_ci_upper"].to_numpy(),
            },
            index=df.index,
        )

    # --- inspection --------------------------------------------------------

    def coefficients(self, alpha: float = config.PRED_INTERVAL_ALPHA) -> pd.DataFrame:
        """R's ``tidy(conf.int = TRUE)``."""
        conf = self.result.conf_int(alpha=alpha)
        return (
            pd.DataFrame(
                {
                    "term": self.result.params.index,
                    "estimate": self.result.params.to_numpy(),
                    "std_error": self.result.bse.to_numpy(),
                    "statistic": self.result.tvalues.to_numpy(),
                    "p_value": self.result.pvalues.to_numpy(),
                    "conf_low": conf[0].to_numpy(),
                    "conf_high": conf[1].to_numpy(),
                }
            )
            .sort_values("p_value")
            .reset_index(drop=True)
        )

    def _variable_columns(self, variable: str) -> list[str]:
        """Design-matrix columns that carry one original variable.

        ``element_type`` and ``team_name`` each span several dummy columns;
        every other variable owns exactly one.
        """
        if variable in ("element_type", "team_name"):
            return [c for c in self.columns if c.startswith(f"{variable}_")]
        return [c for c in self.columns if c == variable]

    def permutation_importance(
        self, df: pd.DataFrame, n_repeats: int = 50, seed: int = config.SEED
    ) -> pd.DataFrame:
        """Drop-out loss per variable, in the spirit of DALEX ``model_parts``.

        Variables are scored in their *original* form rather than as dummy
        columns, so ``team_name`` counts as one variable instead of
        nineteen -- which is what makes the result comparable with the R.

        The permutation is applied to the **built design matrix**, not to the
        raw frame. Permuting the raw column and re-deriving features from it --
        which is what this method used to do, and what DALEX over the R's
        ``step_mutate`` recipe still does -- rebuilds the per-minute rates from
        a shuffled denominator. ``goals_per_min`` carries a coefficient near
        -4, so a scrambled ``minutes`` yields predicted prices in the hundreds
        of millions, and the resulting "importance" measures that blow-up
        rather than the variable's contribution. It ranked ``bps`` and
        ``total_points`` top while ``start_cost`` -- which :meth:`leave_one_out`
        shows is worth ~30x either -- came sixth.

        One permutation is drawn per repeat and applied to all of a variable's
        columns together, so each row stays internally consistent (a player's
        ``goals_scored`` still matches their ``goals_per_min``).
        """
        rng = np.random.default_rng(seed)
        y = df[TARGET].astype(float).to_numpy()
        X = self._matrix(df)
        baseline = rmse(y, self.result.predict(X).to_numpy())

        rows = []
        for variable in features.MODEL_VARIABLES:
            columns = self._variable_columns(variable)
            if not columns:
                continue
            losses = []
            for _ in range(n_repeats):
                order = rng.permutation(len(X))
                shuffled = X.copy()
                shuffled[columns] = X[columns].to_numpy()[order]
                losses.append(rmse(y, self.result.predict(shuffled).to_numpy()))
            rows.append({
                "variable": variable,
                "dropout_loss": float(np.mean(losses)),
                "loss_increase": float(np.mean(losses)) - baseline,
            })

        return (pd.DataFrame(rows)
                .sort_values("dropout_loss", ascending=False)
                .reset_index(drop=True))

    def leave_one_out(self, train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
        """Refit without each variable and report the cost in holdout RMSE.

        The most interpretable statement of variable impact available for a
        linear model, and the one to trust where it disagrees with
        :meth:`permutation_importance`: heavily collinear predictors (``bps``,
        ``total_points`` and ``clean_sheets`` sat at r = 0.89-0.95 in the R's
        formula) each
        look useful in isolation but are individually redundant, which only a
        refit reveals.
        """
        y_test = test[TARGET].astype(float).to_numpy()
        baseline = rmse(y_test, self.predict(test).to_numpy())
        X_train, X_test = self._matrix(train), self._matrix(test)
        y_train = train[TARGET].astype(float)
        complete = X_train.notna().all(axis=1) & y_train.notna()

        rows = []
        for variable in features.MODEL_VARIABLES:
            columns = self._variable_columns(variable)
            if not columns:
                continue
            keep = [c for c in X_train.columns if c not in columns]
            refit = sm.OLS(y_train[complete], X_train.loc[complete, keep]).fit()
            loss = rmse(y_test, refit.predict(X_test[keep]).to_numpy())
            rows.append({
                "variable": variable,
                "holdout_rmse": float(loss),
                "rmse_increase": float(loss - baseline),
            })

        return (pd.DataFrame(rows)
                .sort_values("rmse_increase", ascending=False)
                .reset_index(drop=True))

    def standardized_effects(self, df: pd.DataFrame) -> pd.DataFrame:
        """|coefficient| x SD(predictor): each term's effect in GBPm per 1 SD.

        Raw OLS coefficients are not comparable across predictors measured on
        different scales -- ``minutes`` runs past 3,000 while
        ``points_per_game`` tops out near 8 -- so the raw table cannot be read
        as a ranking. Scaling by the predictor's own spread makes it one.
        """
        X = self._matrix(df)
        params, pvalues = self.result.params, self.result.pvalues
        rows = [{
            "term": term,
            "estimate": float(params[term]),
            "sd_predictor": float(X[term].std()),
            "std_effect": float(abs(params[term] * X[term].std())),
            "p_value": float(pvalues[term]),
        } for term in self.columns]
        return (pd.DataFrame(rows)
                .sort_values("std_effect", ascending=False)
                .reset_index(drop=True))


# --- resampling ------------------------------------------------------------


def split_train_test(
    df: pd.DataFrame, test_prop: float = config.TEST_PROP, seed: int = config.SEED
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``initial_split(strata = next_cost)`` — stratified on price quartile."""
    train_idx, test_idx = train_test_split(
        df.index,
        test_size=test_prop,
        random_state=seed,
        stratify=features.strata_bins(df[TARGET]),
    )
    return df.loc[train_idx], df.loc[test_idx]


def cross_validate(
    df: pd.DataFrame, folds: int = config.CV_FOLDS, seed: int = config.SEED,
    **model_kwargs,
) -> dict:
    """``fit_resamples(vfold_cv(v = 10))``.

    The lumper is refit inside each fold rather than once up front, because
    ``step_other`` is part of the recipe and tidymodels preps the recipe on
    each fold's analysis set. Fitting it on all the data first would leak
    the held-out fold's team distribution into training.
    """
    kfold = KFold(n_splits=folds, shuffle=True, random_state=seed)
    fold_rmse, fold_r2 = [], []

    for train_pos, test_pos in kfold.split(df):
        train, test = df.iloc[train_pos], df.iloc[test_pos]
        preds = PriceModel(**model_kwargs).fit(train).predict(test)
        truth = test[TARGET].astype(float)
        keep = preds.notna() & truth.notna()
        fold_rmse.append(rmse(truth[keep], preds[keep]))
        fold_r2.append(r_squared(truth[keep], preds[keep]))

    return {
        "rmse_mean": float(np.mean(fold_rmse)),
        "rmse_std_err": float(np.std(fold_rmse, ddof=1) / np.sqrt(folds)),
        "rsq_mean": float(np.mean(fold_r2)),
        "rsq_std_err": float(np.std(fold_r2, ddof=1) / np.sqrt(folds)),
        "folds": folds,
    }
