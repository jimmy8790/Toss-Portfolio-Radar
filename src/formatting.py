from __future__ import annotations

import math


def format_currency(value: object, currency: str = "KRW") -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    if currency.upper() == "USD":
        return f"${number:,.2f}"
    return f"{number:,.0f}원"


def format_percent(value: object) -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    return f"{number * 100:+.2f}%"


def format_number(value: object, digits: int = 2) -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    return f"{number:,.{digits}f}"


def risk_level(score: object) -> str:
    number = _to_float(score)
    if number is None:
        return "-"
    if number >= 70:
        return "높음"
    if number >= 40:
        return "보통"
    return "낮음"


def format_score(score: object) -> str:
    number = _to_float(score)
    if number is None:
        return "-"
    return f"{number:.0f} ({risk_level(number)})"


def _to_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number
