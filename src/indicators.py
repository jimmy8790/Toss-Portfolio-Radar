from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def calculate_returns(df: pd.DataFrame) -> pd.Series:
    if df.empty or "close" not in df:
        return pd.Series(dtype="float64")
    close = pd.to_numeric(df["close"], errors="coerce")
    return close.pct_change(fill_method=None).fillna(0.0)


def moving_average(series: pd.Series, window: int) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if window <= 0:
        return pd.Series(np.nan, index=series.index, dtype="float64")
    return numeric.rolling(window=window, min_periods=1).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.empty:
        return pd.Series(dtype="float64")

    delta = numeric.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    fallback = pd.Series(np.where(avg_gain > 0, 100.0, 50.0), index=numeric.index)
    rsi = rsi.fillna(fallback)
    return rsi.clip(0, 100)


def calculate_volatility(returns: pd.Series, window: int = 20) -> pd.Series:
    numeric = pd.to_numeric(returns, errors="coerce")
    if numeric.empty:
        return pd.Series(dtype="float64")
    return numeric.rolling(window=window, min_periods=1).std(ddof=0).fillna(0.0).clip(lower=0)


def calculate_max_drawdown(series: pd.Series, window: int = 20) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.empty:
        return pd.Series(dtype="float64")
    rolling_peak = numeric.rolling(window=window, min_periods=1).max()
    drawdown = numeric / rolling_peak - 1
    return drawdown.fillna(0.0).clip(upper=0)


def calculate_recent_return(series: pd.Series, days: int) -> float | None:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if days <= 0 or len(numeric) < 2:
        return None
    offset = min(days, len(numeric) - 1)
    previous = numeric.iloc[-offset - 1]
    current = numeric.iloc[-1]
    if previous == 0 or pd.isna(previous) or pd.isna(current):
        return None
    return float(current / previous - 1)


def prepare_candle_dataframe(candles: list[dict[str, Any]]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    rows = []
    for candle in candles:
        rows.append(
            {
                "date": _first_present(candle, "date", "time", "datetime", "timestamp", "baseDate"),
                "open": _first_present(candle, "open", "openPrice"),
                "high": _first_present(candle, "high", "highPrice"),
                "low": _first_present(candle, "low", "lowPrice"),
                "close": _first_present(candle, "close", "closePrice", "tradePrice"),
                "volume": _first_present(candle, "volume", "accumulatedTradingVolume"),
            }
        )

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["close"]).sort_values("date", na_position="first").reset_index(drop=True)
    if not df.empty:
        df["return"] = calculate_returns(df)
        df["ma5"] = moving_average(df["close"], 5)
        df["ma20"] = moving_average(df["close"], 20)
        df["rsi"] = calculate_rsi(df["close"])
        df["volatility20"] = calculate_volatility(df["return"], 20)
        df["max_drawdown20"] = calculate_max_drawdown(df["close"], 20)
    return df


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None
