from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ibtrader.regime.gmm import build_regime_features, fit_gmm_regime


def _series(len_days: int = 400) -> pd.Series:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    idx = pd.bdate_range(end=today, periods=len_days)
    px = pd.Series(100.0 + (idx - idx[0]).days * 0.05, index=idx).astype(float)
    px.name = "close"
    return px


def test_regime_default_training_excludes_future() -> None:
    px = _series(400)
    model, rep = fit_gmm_regime(px, n_components=2)
    # Last feature index should not be part of training index
    feats = build_regime_features(px)
    assert len(model.train_index) < len(feats)
    assert feats.index[-1] not in set(model.train_index)
    # Perturb future; past labels must remain unchanged
    px2 = px.copy()
    px2.iloc[-1] = px2.iloc[-1] * 2.0
    model2, rep2 = fit_gmm_regime(px2, n_components=2)
    past = rep["regime"].iloc[:-1].values
    past2 = rep2["regime"].iloc[:-1].values
    assert (past == past2).all()

