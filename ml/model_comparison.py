"""
project_QLE/ml/model_comparison.py
──────────────────────────────────
Machine learning model training and comparison.

Algorithms: Linear Regression, Random Forest, XGBoost
Metrics: MAE, RMSE, R² Score
"""
from __future__ import annotations
import base64
import pickle
from typing import Dict, Tuple, List
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import logging

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logger.warning("XGBoost not installed. Install with: pip install xgboost")


class ModelComparer:
    """
    Train and compare multiple models on petrophysical data.

    Example:
        comparer = ModelComparer(df, target='porosity', features=['GR', 'RHOB', 'NPHI'])
        results = comparer.train_all_models()
        best = results.best_model
    """

    def __init__(self, df: pd.DataFrame, target: str, features: List[str],
                 test_size: float = 0.2, random_state: int = 42):
        """
        Parameters
        ----------
        df : pd.DataFrame
            Dataframe with well log data
        target : str
            Column name to predict (e.g., 'PHIE', 'PERM_mD', 'SW')
        features : List[str]
            Column names to use as input features
        test_size : float
            Fraction of data to use for testing
        random_state : int
            Random seed for reproducibility
        """
        self.df = df.copy()
        self.target = target
        self.features = [f for f in features if f in df.columns]
        self.test_size = test_size
        self.random_state = random_state

        # Clean data: remove rows with NaN in target or features
        self.df = self.df.dropna(subset=[target] + self.features)

        if len(self.df) < 10:
            raise ValueError(f"Not enough data: {len(self.df)} samples (need ≥10)")

        self.X = self.df[self.features].values
        self.y = self.df[target].values

        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(
            self.X, self.y, test_size=test_size, random_state=random_state
        )

        self.models = {}
        self.results = {}

    # ── Training methods ────────────────────────────────────

    def train_linear_regression(self) -> Dict:
        """Train Linear Regression model."""
        logger.info("Training Linear Regression...")
        model = LinearRegression()
        model.fit(self.X_train, self.y_train)

        y_pred = model.predict(self.X_test)
        mae = mean_absolute_error(self.y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(self.y_test, y_pred))
        r2 = r2_score(self.y_test, y_pred)

        self.models["linear_regression"] = model
        result = {
            "model": model,
            "mae": mae,
            "rmse": rmse,
            "r2": r2,
            "n_samples": len(self.X_train),
        }
        self.results["linear_regression"] = result
        logger.info(f"  MAE: {mae:.4f}, RMSE: {rmse:.4f}, R²: {r2:.4f}")
        return result

    def train_random_forest(self, n_estimators: int = 100) -> Dict:
        """Train Random Forest model."""
        logger.info("Training Random Forest...")
        model = RandomForestRegressor(
            n_estimators=n_estimators,
            random_state=self.random_state,
            n_jobs=-1,
        )
        model.fit(self.X_train, self.y_train)

        y_pred = model.predict(self.X_test)
        mae = mean_absolute_error(self.y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(self.y_test, y_pred))
        r2 = r2_score(self.y_test, y_pred)

        self.models["random_forest"] = model
        result = {
            "model": model,
            "mae": mae,
            "rmse": rmse,
            "r2": r2,
            "n_samples": len(self.X_train),
        }
        self.results["random_forest"] = result
        logger.info(f"  MAE: {mae:.4f}, RMSE: {rmse:.4f}, R²: {r2:.4f}")
        return result

    def train_xgboost(self, n_estimators: int = 100) -> Dict:
        """Train XGBoost model."""
        if not XGBOOST_AVAILABLE:
            logger.warning("XGBoost not available - skipping")
            return None

        logger.info("Training XGBoost...")
        model = xgb.XGBRegressor(
            n_estimators=n_estimators,
            random_state=self.random_state,
            n_jobs=-1,
            verbosity=0,
        )
        model.fit(self.X_train, self.y_train)

        y_pred = model.predict(self.X_test)
        mae = mean_absolute_error(self.y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(self.y_test, y_pred))
        r2 = r2_score(self.y_test, y_pred)

        self.models["xgboost"] = model
        result = {
            "model": model,
            "mae": mae,
            "rmse": rmse,
            "r2": r2,
            "n_samples": len(self.X_train),
        }
        self.results["xgboost"] = result
        logger.info(f"  MAE: {mae:.4f}, RMSE: {rmse:.4f}, R²: {r2:.4f}")
        return result

    def train_all_models(self) -> ComparisonResults:
        """Train all available models and return comparison."""
        self.train_linear_regression()
        self.train_random_forest()
        if XGBOOST_AVAILABLE:
            self.train_xgboost()

        return ComparisonResults(self.results, self.models)

    def get_best_model(self) -> Tuple[str, Dict]:
        """Return the best-performing model by R² score."""
        if not self.results:
            raise ValueError("No models trained yet. Call train_all_models() first.")
        best_name = max(self.results.keys(), key=lambda k: self.results[k]["r2"])
        return best_name, self.results[best_name]


class ComparisonResults:
    """Container for model comparison results."""

    def __init__(self, results: Dict, models: Dict):
        self.results = results
        self.models = models

    @property
    def best_model_name(self) -> str:
        """Return the name of the best model."""
        if not self.results:
            return None
        return max(self.results.keys(), key=lambda k: self.results[k]["r2"])

    @property
    def best_model(self):
        """Return the best-performing model object."""
        name = self.best_model_name
        return self.models[name] if name else None

    @property
    def best_result(self) -> Dict:
        """Return the result dict of the best model."""
        name = self.best_model_name
        return self.results[name] if name else None

    def summary_df(self) -> pd.DataFrame:
        """Return a comparison DataFrame."""
        rows = []
        for name, result in self.results.items():
            rows.append({
                "Model": name,
                "MAE": f"{result['mae']:.4f}",
                "RMSE": f"{result['rmse']:.4f}",
                "R²": f"{result['r2']:.4f}",
                "Samples": result['n_samples'],
            })
        return pd.DataFrame(rows).sort_values("R²", ascending=False)

    def __repr__(self):
        return (
            f"<ComparisonResults best={self.best_model_name} "
            f"r2={self.best_result['r2']:.3f}>"
        )


# ── Model serialization ─────────────────────────────────────

def serialize_model(model) -> str:
    """Serialize a model to base64 string for storage."""
    pickled = pickle.dumps(model)
    return base64.b64encode(pickled).decode("utf-8")


def deserialize_model(model_bytes: str):
    """Deserialize a model from base64 string."""
    pickled = base64.b64decode(model_bytes.encode("utf-8"))
    return pickle.loads(pickled)


# ── Prediction helper ───────────────────────────────────────

def predict_with_model(model, feature_values: Dict) -> float:
    """
    Make a prediction with a trained model.

    Parameters
    ----------
    model : fitted sklearn/xgboost model
    feature_values : dict
        Feature name → value mapping

    Returns
    -------
    float : predicted value
    """
    feature_names = list(feature_values.keys())
    X = np.array([list(feature_values.values())])
    return float(model.predict(X)[0])