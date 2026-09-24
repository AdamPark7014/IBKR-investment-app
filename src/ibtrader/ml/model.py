from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import r2_score
from sklearn.preprocessing import StandardScaler

from .cv import PurgedTimeSeriesSplit


@dataclass
class MLConfig:
    lookahead: int = 5  # predict forward return over N days
    enable: bool = False
    min_oos_r2: float = 0.0


class MLModel:
    def __init__(self, cfg: MLConfig | None = None) -> None:
        self.cfg = cfg or MLConfig()
        self.model = GradientBoostingRegressor(random_state=42)
        self.scaler = StandardScaler(with_mean=True, with_std=True)

    def build_dataset(
        self, features: Dict[str, pd.DataFrame], prices: Dict[str, pd.DataFrame]
    ) -> Tuple[pd.DataFrame, pd.Series]:
        # Stack symbols with symbol as column prefix
        # For simplicity, we model each symbol independently and concatenate, sharing model
        frames = []
        ys = []
        for sym, feat in features.items():
            f = feat.copy()
            close = prices[sym]["close"].astype(float).reindex(f.index)
            y = close.pct_change(self.cfg.lookahead).shift(-self.cfg.lookahead)
            # Drop rows with NaNs
            data = f.join(y.rename("y")).dropna()
            if data.empty:
                continue
            # Add symbol dummy if multiple symbols
            data = data.copy()
            data["sym_" + sym] = 1.0
            frames.append(data.drop(columns=["y"]))
            ys.append(data["y"])
        if not frames:
            raise ValueError("No ML dataset could be built (insufficient data).")
        X = pd.concat(frames, axis=0).fillna(0.0)
        y = pd.concat(ys, axis=0).reindex(X.index)
        return X, y

    def cross_validate(self, X: pd.DataFrame, y: pd.Series) -> float:
        splitter = PurgedTimeSeriesSplit(n_splits=5, embargo=5)
        oos_preds = []
        oos_true = []
        X_values = X.values
        y_values = y.values
        for train_idx, test_idx in splitter.split(X):
            X_train, y_train = X_values[train_idx], y_values[train_idx]
            X_test, y_test = X_values[test_idx], y_values[test_idx]
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            self.model.fit(X_train_scaled, y_train)
            preds = self.model.predict(X_test_scaled)
            oos_preds.append(preds)
            oos_true.append(y_test)
        preds_all = np.concatenate(oos_preds)
        true_all = np.concatenate(oos_true)
        return float(r2_score(true_all, preds_all))

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        Xs = self.scaler.fit_transform(X.values)
        self.model.fit(Xs, y.values)

    def predict_score(self, X: pd.DataFrame) -> pd.Series:
        Xs = self.scaler.transform(X.values)
        preds = self.model.predict(Xs)
        # Map forward return prediction to score [-1,1] via tanh
        score = np.tanh(preds / (np.std(preds) + 1e-9))
        return pd.Series(score, index=X.index)

