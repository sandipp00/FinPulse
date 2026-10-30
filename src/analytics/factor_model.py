"""Factor exposure: an ordinary least squares regression of daily excess returns on factors.

    r_asset - RF = alpha + b1 * (Mkt-RF) + b2 * SMB + b3 * HML + b4 * MOM + e

(the Fama-French three factors plus momentum, i.e. the Carhart four-factor model).
All returns are in percent per day, as the factor files publish them. Everything is
descriptive: it measures how the asset moved with the factors in the window used,
and says nothing about the future.
"""
from typing import Optional

import numpy as np
import pandas as pd

FACTORS = ("Mkt-RF", "SMB", "HML", "Mom")
TRADING_DAYS = 252
MIN_DAYS = 120


def regress(asset_returns_pct: pd.Series, factors: pd.DataFrame) -> Optional[dict]:
    """Fit the model on the dates both share. None when there are fewer than MIN_DAYS.

    `asset_returns_pct` is the asset's daily simple return in percent; `factors` has the
    FACTORS columns and RF, in percent, indexed by date.
    """
    joined = pd.concat([asset_returns_pct.rename("r"), factors[[*FACTORS, "RF"]]], axis=1, join="inner").dropna()
    n = len(joined)
    if n < MIN_DAYS:
        return None
    y = (joined["r"] - joined["RF"]).to_numpy(dtype=float)
    x = np.column_stack([np.ones(n), joined[list(FACTORS)].to_numpy(dtype=float)])
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    residuals = y - x @ coef
    dof = n - x.shape[1]
    sigma2 = float(residuals @ residuals) / dof
    cov = sigma2 * np.linalg.inv(x.T @ x)
    stderr = np.sqrt(np.diag(cov))
    total = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float(residuals @ residuals) / total if total > 0 else None

    def term(i):
        return {"value": round(float(coef[i]), 3), "t_stat": round(float(coef[i] / stderr[i]), 2) if stderr[i] > 0 else None}

    alpha_daily = float(coef[0])
    return {
        "observations": n,
        "start_date": joined.index[0].date().isoformat(),
        "end_date": joined.index[-1].date().isoformat(),
        # Daily alpha (percent) compounded over a 252-day year.
        "alpha_annual_pct": round(((1 + alpha_daily / 100) ** TRADING_DAYS - 1) * 100, 2),
        "alpha_t_stat": term(0)["t_stat"],
        "betas": {name: term(i + 1) for i, name in enumerate(FACTORS)},
        "r_squared": round(r2, 3) if r2 is not None else None,
    }
