import pandas as pd

from src.indicators import prepare_candle_dataframe
from src.risk_model import (
    FORBIDDEN_PHRASES,
    build_analysis_comment,
    calculate_downside_risk_score,
    calculate_trend_score,
    calculate_volatility_score,
)


def sample_df() -> pd.DataFrame:
    candles = [
        {"date": f"2026-01-{day:02d}", "close": 100 + day, "open": 99 + day, "high": 101 + day, "low": 98 + day}
        for day in range(1, 26)
    ]
    return prepare_candle_dataframe(candles)


def test_trend_score_is_between_zero_and_one_hundred():
    score = calculate_trend_score(sample_df())

    assert 0 <= score <= 100


def test_volatility_score_is_between_zero_and_one_hundred():
    score = calculate_volatility_score(sample_df())

    assert 0 <= score <= 100


def test_downside_risk_score_is_between_zero_and_one_hundred():
    score = calculate_downside_risk_score(sample_df())

    assert 0 <= score <= 100


def test_warning_count_increases_downside_risk():
    df = sample_df()

    without_warning = calculate_downside_risk_score(df, warning_count=0)
    with_warning = calculate_downside_risk_score(df, warning_count=1)

    assert with_warning >= without_warning


def test_analysis_comment_is_not_empty_and_has_no_forbidden_phrases():
    comment = build_analysis_comment(50, 40, 30, rsi=55)

    assert comment
    assert all(phrase not in comment for phrase in FORBIDDEN_PHRASES)
