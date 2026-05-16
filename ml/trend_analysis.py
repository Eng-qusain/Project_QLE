"""
project_QLE/ml/trend_analysis.py
────────────────────────────────
Depth-based trend analysis using Linear Regression and XGBoost.

Analyzes how petrophysical properties change with depth.
"""
from __future__ import annotations
from typing import Dict, Tuple, Optional
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
import logging

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False


class TrendAnalyzer:
    """
    Analyze depth-based trends in petrophysical properties.

    Fits Linear Regression and XGBoost models to predict property values
    as a function of depth.

    Example:
        analyzer = TrendAnalyzer(df, depth_col='DEPTH', target_col='PHIE')
        results = analyzer.analyze()
        print(results.summary())
    """

    def __init__(self, df: pd.DataFrame, depth_col: str = "DEPTH",
                 target_col: str = "PHIE", test_size: float = 0.2):
        """
        Parameters
        ----------
        df : pd.DataFrame
            Well log data
        depth_col : str
            Depth column name
        target_col : str
            Property column to analyze (e.g., 'PHIE', 'PERM_mD', 'SW')
        test_size : float
            Fraction for testing
        """
        self.df = df.copy()
        self.depth_col = depth_col
        self.target_col = target_col
        self.test_size = test_size

        # Clean data
        self.df = self.df.dropna(subset=[depth_col, target_col])

        if len(self.df) < 10:
            raise ValueError(f"Not enough data: {len(self.df)} samples")

        self.X = self.df[[depth_col]].values
        self.y = self.df[target_col].values

        # Split
        split_idx = int(len(self.X) * (1 - test_size))
        self.X_train = self.X[:split_idx]
        self.X_test = self.X[split_idx:]
        self.y_train = self.y[:split_idx]
        self.y_test = self.y[split_idx:]

        self.lr_model = None
        self.xgb_model = None
        self.results = {}

    def fit_linear_regression(self) -> Dict:
        """Fit a linear trend model."""
        logger.info("Fitting Linear Regression trend...")
        self.lr_model = LinearRegression()
        self.lr_model.fit(self.X_train, self.y_train)

        y_pred_train = self.lr_model.predict(self.X_train)
        y_pred_test = self.lr_model.predict(self.X_test)

        r2_train = r2_score(self.y_train, y_pred_train)
        r2_test = r2_score(self.y_test, y_pred_test)
        mae_test = mean_absolute_error(self.y_test, y_pred_test)
        rmse_test = np.sqrt(mean_squared_error(self.y_test, y_pred_test))

        slope = float(self.lr_model.coef_[0])
        intercept = float(self.lr_model.intercept_)

        result = {
            "model": self.lr_model,
            "slope": slope,
            "intercept": intercept,
            "r2_train": r2_train,
            "r2_test": r2_test,
            "mae": mae_test,
            "rmse": rmse_test,
            "equation": f"y = {slope:.6f}*depth + {intercept:.2f}",
        }
        self.results["linear_regression"] = result
        logger.info(
            f"  Slope: {slope:.6f}, R²(test): {r2_test:.4f}, MAE: {mae_test:.4f}"
        )
        return result

    def fit_xgboost(self, n_estimators: int = 50) -> Optional[Dict]:
        """Fit an XGBoost trend model."""
        if not XGBOOST_AVAILABLE:
            logger.warning("XGBoost not available")
            return None

        logger.info("Fitting XGBoost trend...")
        self.xgb_model = xgb.XGBRegressor(
            n_estimators=n_estimators,
            random_state=42,
            verbosity=0,
        )
        self.xgb_model.fit(self.X_train, self.y_train)

        y_pred_train = self.xgb_model.predict(self.X_train)
        y_pred_test = self.xgb_model.predict(self.X_test)

        r2_train = r2_score(self.y_train, y_pred_train)
        r2_test = r2_score(self.y_test, y_pred_test)
        mae_test = mean_absolute_error(self.y_test, y_pred_test)
        rmse_test = np.sqrt(mean_squared_error(self.y_test, y_pred_test))

        result = {
            "model": self.xgb_model,
            "r2_train": r2_train,
            "r2_test": r2_test,
            "mae": mae_test,
            "rmse": rmse_test,
        }
        self.results["xgboost"] = result
        logger.info(f"  R²(test): {r2_test:.4f}, MAE: {mae_test:.4f}")
        return result

    def analyze(self) -> TrendAnalysisResults:
        """Run both models and return comparison."""
        self.fit_linear_regression()
        if XGBOOST_AVAILABLE:
            self.fit_xgboost()
        return TrendAnalysisResults(self.results, self.X_test, self.y_test)

    def predict_at_depth(self, depth: float) -> Dict[str, float]:
        """Predict property value at a specific depth."""
        X_pred = np.array([[depth]])
        predictions = {}

        if self.lr_model:
            predictions["linear_regression"] = float(self.lr_model.predict(X_pred)[0])
        if self.xgb_model:
            predictions["xgboost"] = float(self.xgb_model.predict(X_pred)[0])

        return predictions


class TrendAnalysisResults:
    """Container for trend analysis results."""

    def __init__(self, results: Dict, X_test: np.ndarray, y_test: np.ndarray):
        self.results = results
        self.X_test = X_test
        self.y_test = y_test

    @property
    def best_model_name(self) -> str:
        """Return the best model by R² score."""
        if not self.results:
            return None
        return max(self.results.keys(), key=lambda k: self.results[k]["r2_test"])

    @property
    def best_result(self) -> Dict:
        """Return the best result dict."""
        name = self.best_model_name
        return self.results[name] if name else None

    def summary(self) -> str:
        """Return a text summary of trend analysis."""
        lines = [
            "=" * 60,
            "TREND ANALYSIS SUMMARY",
            "=" * 60,
        ]

        for name, result in self.results.items():
            lines.append("")
            lines.append(f"{name.upper()}")
            lines.append("─" * 60)

            if "equation" in result:
                lines.append(f"  Equation: {result['equation']}")
            if "slope" in result:
                slope = result["slope"]
                direction = "increasing" if slope > 0 else "decreasing"
                lines.append(f"  Trend: {direction} with depth (slope: {slope:.6f})")

            lines.append(f"  R² (train): {result['r2_train']:.4f}")
            lines.append(f"  R² (test):  {result['r2_test']:.4f}")
            lines.append(f"  MAE:        {result['mae']:.4f}")
            lines.append(f"  RMSE:       {result['rmse']:.4f}")

        lines.append("")
        lines.append("=" * 60)
        best = self.best_model_name
        if best:
            lines.append(f"BEST MODEL: {best.upper()}")
            lines.append(f"  R²: {self.best_result['r2_test']:.4f}")
        lines.append("=" * 60)

        return "\n".join(lines)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert results to DataFrame for display."""
        rows = []
        for name, result in self.results.items():
            rows.append({
                "Model": name,
                "R² (test)": f"{result['r2_test']:.4f}",
                "MAE": f"{result['mae']:.4f}",
                "RMSE": f"{result['rmse']:.4f}",
            })
        return pd.DataFrame(rows).sort_values("R² (test)", ascending=False)