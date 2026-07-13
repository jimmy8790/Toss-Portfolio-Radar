from __future__ import annotations

from typing import Any

import pandas as pd


def holdings_to_dataframe(holdings: list[dict[str, Any]]) -> pd.DataFrame:
    columns = [
        "symbol",
        "name",
        "marketCountry",
        "currency",
        "quantity",
        "averagePurchasePrice",
        "profitLoss.rate",
        "profitLoss.rateBeforeCost",
        "profitLoss.rateKrw",
        "dailyProfitLoss.rate",
        "evaluationAmount",
        "evaluationAmountBeforeCost",
        "purchaseAmount",
        "marketValue.amount",
        "profitLoss.amount",
        "dailyProfitLoss.amount",
        "cost.commission",
        "cost.tax",
    ]
    if not holdings:
        return pd.DataFrame(columns=columns)

    normalized = pd.json_normalize(holdings, sep=".")
    df = pd.DataFrame()
    df["symbol"] = _pick_column(normalized, ["symbol", "stock.symbol", "ticker"])
    df["name"] = _pick_column(normalized, ["name", "stock.name", "stockName", "companyName"])
    df["marketCountry"] = _pick_column(normalized, ["marketCountry", "country", "market.country"])
    df["currency"] = _pick_column(normalized, ["currency", "currencyCode"])
    df["quantity"] = _pick_column(normalized, ["quantity", "qty", "holdingQuantity"])
    df["averagePurchasePrice"] = _pick_column(
        normalized,
        ["averagePurchasePrice", "avgPurchasePrice", "averagePrice", "purchaseAveragePrice"],
    )
    df["profitLoss.rateBeforeCost"] = _pick_column(normalized, ["profitLoss.rate", "profitRate", "returnRate"])
    df["profitLoss.rate"] = _pick_column(
        normalized,
        ["profitLoss.rateAfterCost", "profitLoss.rate", "profitRate", "returnRate"],
    )
    df["profitLoss.rateKrw"] = _pick_column(
        normalized,
        [
            "profitLoss.rate.krw",
            "profitLoss.krw.rate",
            "profitLoss.rateKrw",
            "profitLossRateKrw",
            "krwProfitLoss.rate",
            "returnRateKrw",
        ],
    )
    df["dailyProfitLoss.rate"] = _pick_column(normalized, ["dailyProfitLoss.rate", "dailyProfitRate"])
    df["evaluationAmountBeforeCost"] = _pick_column(
        normalized,
        ["evaluationAmount", "marketValue.amount", "marketValue", "value"],
    )
    df["evaluationAmount"] = _pick_column(
        normalized,
        ["evaluationAmountAfterCost", "marketValue.amountAfterCost", "evaluationAmount", "marketValue.amount", "marketValue", "value"],
    )
    df["purchaseAmount"] = _pick_column(normalized, ["purchaseAmount", "marketValue.purchaseAmount", "costBasis"])
    df["marketValue.amount"] = df["evaluationAmount"]
    df["profitLoss.amount"] = _pick_column(normalized, ["profitLoss.amountAfterCost", "profitLoss.amount", "profitLossAmount"])
    df["dailyProfitLoss.amount"] = _pick_column(normalized, ["dailyProfitLoss.amount", "dailyProfitLossAmount"])
    df["cost.commission"] = _pick_column(normalized, ["cost.commission", "commission", "fee"])
    df["cost.tax"] = _pick_column(normalized, ["cost.tax", "tax"])

    for column in [
        "quantity",
        "averagePurchasePrice",
        "profitLoss.rate",
        "profitLoss.rateBeforeCost",
        "profitLoss.rateKrw",
        "dailyProfitLoss.rate",
        "evaluationAmount",
        "evaluationAmountBeforeCost",
        "purchaseAmount",
        "profitLoss.amount",
        "dailyProfitLoss.amount",
        "cost.commission",
        "cost.tax",
    ]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["symbol"] = df["symbol"].fillna("").astype(str)
    df["name"] = df["name"].fillna(df["symbol"]).astype(str)
    df["currency"] = df["currency"].fillna("KRW").astype(str)
    df["marketCountry"] = df["marketCountry"].fillna("").astype(str)
    return df


def merge_prices(holdings_df: pd.DataFrame, prices: list[dict[str, Any]]) -> pd.DataFrame:
    df = holdings_df.copy()
    if df.empty:
        df["lastPrice"] = pd.Series(dtype="float64")
        return df

    price_df = _prices_to_dataframe(prices)
    if price_df.empty:
        if "lastPrice" not in df:
            df["lastPrice"] = pd.NA
        return df

    merged = df.merge(price_df, on="symbol", how="left", suffixes=("", "_price"))
    if "lastPrice_price" in merged:
        if "lastPrice" in merged:
            merged["lastPrice"] = merged["lastPrice_price"].combine_first(merged["lastPrice"])
        else:
            merged["lastPrice"] = merged["lastPrice_price"]
        merged = merged.drop(columns=["lastPrice_price"])
    return merged


def add_warning_counts(holdings_df: pd.DataFrame, warning_counts: dict[str, int]) -> pd.DataFrame:
    df = holdings_df.copy()
    df["warning_count"] = df["symbol"].map(warning_counts).fillna(0).astype(int) if "symbol" in df else 0
    return df


def add_risk_scores(holdings_df: pd.DataFrame, risk_scores: dict[str, dict[str, int]]) -> pd.DataFrame:
    df = holdings_df.copy()
    for column in ["trend_score", "volatility_score", "downside_risk_score"]:
        df[column] = df["symbol"].map(lambda symbol: risk_scores.get(symbol, {}).get(column, 0)) if "symbol" in df else 0
    return df


def calculate_weights(holdings_df: pd.DataFrame, usd_krw: float | None = None) -> pd.DataFrame:
    df = holdings_df.copy()
    if df.empty:
        df["weight"] = pd.Series(dtype="float64")
        return df

    df["evaluationAmountKrw"] = df.apply(
        lambda row: _to_krw(row.get("evaluationAmount"), row.get("currency"), usd_krw),
        axis=1,
    )
    total = pd.to_numeric(df["evaluationAmountKrw"], errors="coerce").fillna(0).sum()
    df["weight"] = df["evaluationAmountKrw"] / total if total else 0.0
    return df


def calculate_summary(
    holdings_df: pd.DataFrame,
    usd_krw: float | None = None,
    api_summary: dict[str, Any] | None = None,
) -> dict[str, float | int | None]:
    if holdings_df.empty:
        empty_summary: dict[str, float | int | None] = {
            "holding_count": 0,
            "total_value_krw": None,
            "total_value_usd": None,
            "daily_profit_loss": None,
            "total_profit_rate": None,
            "korea_stock_weight": None,
            "us_stock_weight": None,
            "usd_asset_weight": None,
        }
        return _apply_api_summary(empty_summary, api_summary)

    df = calculate_weights(holdings_df, usd_krw)
    total_value_krw = pd.to_numeric(df["evaluationAmountKrw"], errors="coerce").fillna(0).sum()
    total_value_usd = total_value_krw / usd_krw if usd_krw else None
    daily_profit_loss = pd.to_numeric(df.get("dailyProfitLoss.amount"), errors="coerce").fillna(0).sum()
    total_profit_amount = pd.to_numeric(df.get("profitLoss.amount"), errors="coerce").fillna(0).sum()
    cost_basis = total_value_krw - total_profit_amount
    total_profit_rate = total_profit_amount / cost_basis if cost_basis else None

    market_country = df["marketCountry"].astype(str).str.upper()
    currency = df["currency"].astype(str).str.upper()
    summary: dict[str, float | int | None] = {
        "holding_count": int(df["symbol"].replace("", pd.NA).dropna().nunique()),
        "total_value_krw": float(total_value_krw) if total_value_krw else None,
        "total_value_usd": float(total_value_usd) if total_value_usd else None,
        "daily_profit_loss": float(daily_profit_loss) if daily_profit_loss else None,
        "total_profit_rate": float(total_profit_rate) if total_profit_rate is not None else None,
        "korea_stock_weight": _weighted_sum(df, market_country.isin(["KR", "KOR", "KOREA", "KRW"])),
        "us_stock_weight": _weighted_sum(df, market_country.isin(["US", "USA", "UNITED STATES"])),
        "usd_asset_weight": _weighted_sum(df, currency.eq("USD")),
    }
    return _apply_api_summary(summary, api_summary)


def extract_api_summary(holdings_payload: dict[str, Any] | None) -> dict[str, float | None]:
    if not isinstance(holdings_payload, dict):
        return {}
    result = holdings_payload.get("result")
    source = result if isinstance(result, dict) else holdings_payload
    return {
        "total_value_krw": _first_nested_float(source, ["marketValue.amountAfterCost.krw", "marketValue.amount.krw"]),
        "total_value_usd": _first_nested_float(source, ["marketValue.amountAfterCost.usd", "marketValue.amount.usd"]),
        "daily_profit_loss": _nested_float(source, "dailyProfitLoss.amount.krw"),
        "total_profit_rate": _first_nested_float(source, ["profitLoss.rateAfterCost", "profitLoss.rate"]),
    }


def _apply_api_summary(
    summary: dict[str, float | int | None],
    api_summary: dict[str, Any] | None,
) -> dict[str, float | int | None]:
    if not api_summary:
        return summary
    merged = summary.copy()
    for key in ["total_value_krw", "total_value_usd", "daily_profit_loss", "total_profit_rate"]:
        value = _coerce_float(api_summary.get(key))
        if value is not None:
            merged[key] = value
    return merged


def _prices_to_dataframe(prices: list[dict[str, Any]]) -> pd.DataFrame:
    if not prices:
        return pd.DataFrame(columns=["symbol", "lastPrice"])
    normalized = pd.json_normalize(prices, sep=".")
    df = pd.DataFrame()
    df["symbol"] = _pick_column(normalized, ["symbol", "ticker"])
    df["lastPrice"] = _pick_column(normalized, ["lastPrice", "price", "close", "tradePrice"])
    df["lastPrice"] = pd.to_numeric(df["lastPrice"], errors="coerce")
    return df.dropna(subset=["symbol"]).drop_duplicates("symbol")


def _pick_column(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    for candidate in candidates:
        if candidate in df:
            return df[candidate]
    return pd.Series([pd.NA] * len(df), index=df.index)


def _to_krw(value: object, currency: object, usd_krw: float | None) -> float:
    amount = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(amount):
        return 0.0
    if str(currency).upper() == "USD" and usd_krw:
        return float(amount) * usd_krw
    return float(amount)


def _nested_float(payload: dict[str, Any], path: str) -> float | None:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return _coerce_float(value)


def _first_nested_float(payload: dict[str, Any], paths: list[str]) -> float | None:
    for path in paths:
        value = _nested_float(payload, path)
        if value is not None:
            return value
    return None


def _coerce_float(value: object) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return None
    return float(number)


def _weighted_sum(df: pd.DataFrame, mask: pd.Series) -> float | None:
    if df.empty or "weight" not in df:
        return None
    return float(pd.to_numeric(df.loc[mask, "weight"], errors="coerce").fillna(0).sum())
