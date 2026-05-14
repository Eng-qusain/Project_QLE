"""
project_QLE/analysis/facies.py
─────────────────────────
Facies classification from well-log data.

Strategies
──────────
1. Rule-based  – fast, deterministic, geologist-interpretable
2. KMeans      – unsupervised clustering
3. RandomForest– supervised (requires labelled training data)
4. Neural Net  – simple MLP for more complex log patterns
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

from project_QLE.core.models import Facies, WellLog, ZoneInterval

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Input features helper
# ─────────────────────────────────────────────

FEATURE_COLS = ["GR", "RHOB", "NPHI", "RT", "DT", "VSHALE", "PHIE", "SW"]


def _build_feature_matrix(df: pd.DataFrame, features: Optional[List[str]] = None) -> Tuple[np.ndarray, List[str]]:
    cols = features or FEATURE_COLS
    available = [c for c in cols if c in df.columns]
    if not available:
        raise ValueError(f"None of the feature columns {cols} found in DataFrame.")
    X = df[available].values.astype(float)
    # Replace NaN with column median
    col_medians = np.nanmedian(X, axis=0)
    inds = np.where(np.isnan(X))
    X[inds] = np.take(col_medians, inds[1])
    return X, available


# ─────────────────────────────────────────────
#  Rule-based classifier
# ─────────────────────────────────────────────

class RuleBasedFacies:
    """
    Simple deterministic facies from GR + RHOB + NPHI crossplots.

    Adjust thresholds to match your basin's log responses.
    """

    def __init__(
        self,
        gr_sand_max  : float = 50,
        gr_shale_min : float = 90,
        rho_lim_sand : float = 2.55,
        rho_lim_carb : float = 2.70,
        rho_lim_evap : float = 2.80,
        nphi_gas_max : float = 0.10,
    ):
        self.gr_sand_max   = gr_sand_max
        self.gr_shale_min  = gr_shale_min
        self.rho_lim_sand  = rho_lim_sand
        self.rho_lim_carb  = rho_lim_carb
        self.rho_lim_evap  = rho_lim_evap
        self.nphi_gas_max  = nphi_gas_max

    def classify(self, df: pd.DataFrame) -> np.ndarray:
        gr   = df.get("GR",   pd.Series(np.nan, index=df.index)).values
        rhob = df.get("RHOB", pd.Series(np.nan, index=df.index)).values
        nphi = df.get("NPHI", pd.Series(np.nan, index=df.index)).values

        n = len(df)
        labels = np.array([Facies.UNKNOWN.value] * n, dtype=object)

        for i in range(n):
            g = gr[i]
            r = rhob[i]
            p = nphi[i]

            if np.isnan(g):
                continue

            if g >= self.gr_shale_min:
                labels[i] = Facies.SHALE.value

            elif g <= self.gr_sand_max:
                if not np.isnan(r):
                    if r >= self.rho_lim_evap:
                        labels[i] = Facies.ANHYDRITE.value
                    elif r >= self.rho_lim_carb:
                        labels[i] = Facies.DOLOMITE.value
                    elif r >= self.rho_lim_sand:
                        labels[i] = Facies.LIMESTONE.value
                    else:
                        labels[i] = Facies.SANDSTONE.value
                else:
                    labels[i] = Facies.SANDSTONE.value
            else:
                # Mixed – use RHOB to differentiate
                if not np.isnan(r) and r >= self.rho_lim_carb:
                    labels[i] = Facies.LIMESTONE.value
                else:
                    labels[i] = Facies.SHALE.value   # transitional shale

        return labels


# ─────────────────────────────────────────────
#  Unsupervised KMeans
# ─────────────────────────────────────────────

_CLUSTER_FACIES_MAP: Dict[int, Facies] = {
    0: Facies.SANDSTONE,
    1: Facies.SHALE,
    2: Facies.LIMESTONE,
    3: Facies.DOLOMITE,
    4: Facies.ANHYDRITE,
}


class KMeansFacies:
    """Cluster logs into facies groups automatically."""

    def __init__(self, n_clusters: int = 5, random_state: int = 42):
        self.n_clusters   = n_clusters
        self.random_state = random_state
        self.scaler   = StandardScaler()
        self.model    = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
        self._trained = False

    def fit_predict(self, df: pd.DataFrame, features: Optional[List[str]] = None) -> np.ndarray:
        X, used = _build_feature_matrix(df, features)
        Xs = self.scaler.fit_transform(X)
        labels_int = self.model.fit_predict(Xs)
        self._trained = True
        # Map cluster id → Facies name
        facies_labels = np.array(
            [_CLUSTER_FACIES_MAP.get(l, Facies.UNKNOWN).value for l in labels_int],
            dtype=object,
        )
        logger.info("KMeans facies: cluster sizes %s", np.unique(labels_int, return_counts=True)[1])
        return facies_labels

    def predict(self, df: pd.DataFrame, features: Optional[List[str]] = None) -> np.ndarray:
        if not self._trained:
            raise RuntimeError("Call fit_predict first.")
        X, _ = _build_feature_matrix(df, features)
        Xs = self.scaler.transform(X)
        labels_int = self.model.predict(Xs)
        return np.array([_CLUSTER_FACIES_MAP.get(l, Facies.UNKNOWN).value for l in labels_int], dtype=object)


# ─────────────────────────────────────────────
#  Supervised Random Forest
# ─────────────────────────────────────────────

class RFFaciesClassifier:
    """Train a Random Forest on labelled depth intervals."""

    def __init__(self, n_estimators: int = 200, random_state: int = 42):
        self.scaler = StandardScaler()
        self.model  = RandomForestClassifier(
            n_estimators = n_estimators,
            random_state = random_state,
            class_weight = "balanced",
            n_jobs       = -1,
        )
        self._trained    = False
        self._features   : List[str] = []

    def train(
        self,
        df: pd.DataFrame,
        labels: np.ndarray,
        features: Optional[List[str]] = None,
        test_size: float = 0.2,
    ) -> Dict:
        X, self._features = _build_feature_matrix(df, features)
        Xs = self.scaler.fit_transform(X)
        X_tr, X_te, y_tr, y_te = train_test_split(Xs, labels, test_size=test_size, random_state=42)
        self.model.fit(X_tr, y_tr)
        self._trained = True
        report = classification_report(y_te, self.model.predict(X_te), output_dict=True)
        logger.info("RF Facies classifier trained – accuracy %.3f", report.get("accuracy", 0))
        return report

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        if not self._trained:
            raise RuntimeError("Model not trained.")
        X, _ = _build_feature_matrix(df, self._features)
        Xs   = self.scaler.transform(X)
        return self.model.predict(Xs)

    def feature_importances(self) -> pd.Series:
        return pd.Series(self.model.feature_importances_, index=self._features).sort_values(ascending=False)


# ─────────────────────────────────────────────
#  MLP Neural Network classifier
# ─────────────────────────────────────────────

class MLPFaciesClassifier:
    def __init__(self, hidden: Tuple[int, ...] = (128, 64, 32)):
        self.scaler   = StandardScaler()
        self.model    = MLPClassifier(
            hidden_layer_sizes = hidden,
            activation         = "relu",
            max_iter           = 500,
            random_state       = 42,
            early_stopping     = True,
            validation_fraction= 0.1,
        )
        self._trained  = False
        self._features : List[str] = []

    def train(self, df: pd.DataFrame, labels: np.ndarray, features: Optional[List[str]] = None) -> None:
        X, self._features = _build_feature_matrix(df, features)
        Xs = self.scaler.fit_transform(X)
        self.model.fit(Xs, labels)
        self._trained = True
        logger.info("MLP facies classifier trained (%d iterations)", self.model.n_iter_)

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        if not self._trained:
            raise RuntimeError("Model not trained.")
        X, _ = _build_feature_matrix(df, self._features)
        return self.model.predict(self.scaler.transform(X))


# ─────────────────────────────────────────────
#  Convert depth labels → ZoneInterval list
# ─────────────────────────────────────────────

def labels_to_zones(
    depth: np.ndarray,
    facies_labels: np.ndarray,
    min_thickness_m: float = 0.5,
) -> List[ZoneInterval]:
    """
    Merge consecutive equal-facies depth points into ZoneInterval objects.
    """
    if len(depth) == 0:
        return []

    zones: List[ZoneInterval] = []
    current_facies = facies_labels[0]
    current_top    = float(depth[0])

    for i in range(1, len(depth)):
        if facies_labels[i] != current_facies:
            base = float(depth[i - 1])
            if (base - current_top) >= min_thickness_m:
                try:
                    f = Facies(current_facies)
                except ValueError:
                    f = Facies.UNKNOWN
                zones.append(ZoneInterval(top=current_top, base=base, facies=f))
            current_facies = facies_labels[i]
            current_top    = float(depth[i])

    # Close last zone
    base = float(depth[-1])
    if (base - current_top) >= min_thickness_m:
        try:
            f = Facies(current_facies)
        except ValueError:
            f = Facies.UNKNOWN
        zones.append(ZoneInterval(top=current_top, base=base, facies=f))

    logger.info("Identified %d facies zones", len(zones))
    return zones