from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, cast

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler


@dataclass
class RegimeModel:
    scaler: StandardScaler
    gmm: GaussianMixture
    feature_names: Tuple[str, str] = ("ret_1d", "vol_20")
    risk_on_label: int = 0
    train_index: Tuple[pd.Timestamp, ...] = ()

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        Z = self.scaler.transform(X[list(self.feature_names)].values)
        return cast(np.ndarray, self.gmm.predict_proba(Z))

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        Z = self.scaler.transform(X[list(self.feature_names)].values)
        return cast(np.ndarray, self.gmm.predict(Z))


def build_regime_features(benchmark_px: pd.Series) -> pd.DataFrame:
    px = benchmark_px.astype(float).dropna()
    rets = px.pct_change().fillna(0.0)
    vol20 = rets.rolling(20).std(ddof=0)
    feats = pd.DataFrame({"ret_1d": rets, "vol_20": vol20}).dropna()
    return feats


def fit_gmm_regime(
    benchmark_px: pd.Series,
    n_components: int = 2,
    train_slice: slice | None = None,
) -> Tuple[RegimeModel, pd.DataFrame]:
    feats = build_regime_features(benchmark_px)
    if train_slice is None:
        # Default: first 60% of data for training
        n = len(feats)
        train_end = int(n * 0.6)
        train_idx = feats.index[:train_end]
    else:
        train_idx = feats.index[train_slice]
    X_train = feats.loc[train_idx, :]
    scaler = StandardScaler()
    Z = scaler.fit_transform(X_train.values)
    gmm = GaussianMixture(n_components=n_components, covariance_type="full", random_state=42)
    gmm.fit(Z)
    # Identify risk-on by higher mean return on training data
    probs_train = gmm.predict_proba(Z)
    labels_train = probs_train.argmax(axis=1)
    df_train = X_train.copy()
    df_train["regime"] = labels_train
    means_train = df_train.groupby("regime")["ret_1d"].mean()
    risk_on_label = int(means_train.idxmax()) if len(means_train) else 0
    model = RegimeModel(scaler=scaler, gmm=gmm, risk_on_label=risk_on_label, train_index=tuple(train_idx))
    # Full prediction for reporting
    probs = model.predict_proba(feats)
    labels = probs.argmax(axis=1)
    report = feats.copy()
    report["regime"] = labels
    for k in range(n_components):
        report[f"p_{k}"] = probs[:, k]
    return model, report
