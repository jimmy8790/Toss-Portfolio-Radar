import pandas as pd

from src.indicators import (
    calculate_max_drawdown,
    calculate_returns,
    calculate_rsi,
    calculate_volatility,
    moving_average,
    prepare_candle_dataframe,
)


def test_moving_average_returns_expected_length_and_values():
    series = pd.Series([1, 2, 3, 4, 5])

    result = moving_average(series, 3)

    assert len(result) == len(series)
    assert result.iloc[0] == 1
    assert result.iloc[-1] == 4


def test_rsi_is_between_zero_and_one_hundred():
    series = pd.Series([10, 11, 10, 12, 13, 12, 14, 15])

    result = calculate_rsi(series)

    assert result.between(0, 100).all()


def test_volatility_is_not_negative():
    returns = pd.Series([0.01, -0.02, 0.03, 0.0])

    result = calculate_volatility(returns)

    assert (result >= 0).all()


def test_max_drawdown_is_zero_or_negative():
    prices = pd.Series([100, 90, 95, 80, 120])

    result = calculate_max_drawdown(prices)

    assert (result <= 0).all()


def test_indicator_functions_handle_short_data_without_error():
    candles = [{"date": "2026-01-01", "close": "100", "open": "99", "high": "101", "low": "98"}]

    df = prepare_candle_dataframe(candles)
    returns = calculate_returns(df)

    assert len(df) == 1
    assert len(returns) == 1
    assert "ma5" in df
    assert "rsi" in df
