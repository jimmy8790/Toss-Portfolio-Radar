from __future__ import annotations

import pandas as pd

from src.indicators import calculate_recent_return


FORBIDDEN_PHRASES = ("매수 추천", "매도 추천", "상승 확정", "하락 확정", "반드시 오른다", "반드시 내린다", "목표가", "적정가")


def calculate_trend_score(df: pd.DataFrame) -> int:
    if df.empty or "close" not in df:
        return 0

    latest = df.iloc[-1]
    score = 0
    close = _to_float(latest.get("close"))
    ma5 = _to_float(latest.get("ma5"))
    ma20 = _to_float(latest.get("ma20"))

    if close is not None and ma5 is not None and close > ma5:
        score += 25
    if ma5 is not None and ma20 is not None and ma5 > ma20:
        score += 25

    recent_5 = calculate_recent_return(df["close"], 5)
    recent_20 = calculate_recent_return(df["close"], 20)
    if recent_5 is not None and recent_5 > 0:
        score += 25
    if recent_20 is not None and recent_20 > 0:
        score += 25
    return _clamp(score)


def calculate_volatility_score(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    if "volatility20" in df:
        volatility = _to_float(df["volatility20"].iloc[-1])
    elif "return" in df:
        volatility = _to_float(df["return"].tail(20).std(ddof=0))
    else:
        volatility = None
    if volatility is None:
        return 0
    return _clamp((volatility / 0.05) * 100)


def calculate_downside_risk_score(df: pd.DataFrame, warning_count: int = 0) -> int:
    if df.empty:
        return _clamp(20 if warning_count > 0 else 0)

    latest = df.iloc[-1]
    drawdown = _to_float(latest.get("max_drawdown20"))
    rsi = _to_float(latest.get("rsi"))
    recent_5 = calculate_recent_return(df["close"], 5) if "close" in df else None

    score = 0
    if drawdown is not None:
        if drawdown <= -0.10:
            score += 40
        elif drawdown <= -0.05:
            score += 20
    if rsi is not None and rsi >= 70:
        score += 20
    if recent_5 is not None and recent_5 >= 0.10:
        score += 20
    if warning_count >= 1:
        score += 20
    return _clamp(score)


def build_analysis_comment(
    trend_score: int,
    volatility_score: int,
    downside_risk_score: int,
    rsi: float | None = None,
) -> str:
    comments = []
    if trend_score >= 75:
        comments.append("단기 추세 신호는 비교적 양호하게 나타납니다.")
    elif trend_score <= 25:
        comments.append("최근 데이터 기준으로 뚜렷한 방향성은 약합니다.")
    else:
        comments.append("단기 추세는 중립적인 범위에 있습니다.")

    if volatility_score >= 70:
        comments.append("변동성이 커지고 있어 가격 움직임을 보수적으로 확인할 필요가 있습니다.")
    elif volatility_score <= 30:
        comments.append("최근 변동성은 낮은 편입니다.")
    else:
        comments.append("최근 변동성은 보통 수준으로 보입니다.")

    if downside_risk_score >= 60:
        comments.append("하락위험 점수가 높아 추가 확인이 필요합니다.")
    elif downside_risk_score >= 30:
        comments.append("일부 하락위험 요인이 관찰됩니다.")
    else:
        comments.append("현재 계산 기준의 하락위험 점수는 낮은 편입니다.")

    if rsi is not None and rsi >= 70:
        comments.append("RSI가 과열권에 가까워 단기 변동에 주의가 필요합니다.")

    result = " ".join(comments)
    for phrase in FORBIDDEN_PHRASES:
        result = result.replace(phrase, "")
    return result.strip()


def _to_float(value: object) -> float | None:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return parsed


def _clamp(value: float) -> int:
    return int(max(0, min(100, round(value))))
