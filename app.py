from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config import get_config
from src.formatting import format_currency, format_number, format_percent, format_score
from src.indicators import prepare_candle_dataframe
from src.portfolio import (
    add_risk_scores,
    add_warning_counts,
    calculate_summary,
    calculate_weights,
    extract_api_summary,
    holdings_to_dataframe,
    merge_prices,
)
from src.risk_model import (
    build_analysis_comment,
    calculate_downside_risk_score,
    calculate_trend_score,
    calculate_volatility_score,
)
from src.storage import (
    append_snapshot,
    load_snapshots,
    load_watchlist,
    save_watchlist,
    utc_now_iso,
)
from src.toss_client import TossInvestClient, TossInvestError


st.set_page_config(page_title="Toss Portfolio Radar", page_icon="TPR", layout="wide")

AUTO_REFRESH_MIN_SECONDS = 5
AUTO_REFRESH_DEFAULT_SECONDS = 60
AUTO_REFRESH_MAX_SECONDS = 3600
MENU_ITEMS = ["포트폴리오", "관심종목", "변화 그래프"]


@st.cache_resource(show_spinner=False)
def get_client() -> TossInvestClient:
    return TossInvestClient(get_config())


def main() -> None:
    config = get_config()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    default_auto_refresh = _query_bool("auto_refresh", False)
    default_refresh_interval = _query_int(
        "refresh_interval",
        AUTO_REFRESH_DEFAULT_SECONDS,
        AUTO_REFRESH_MIN_SECONDS,
        AUTO_REFRESH_MAX_SECONDS,
    )

    st.sidebar.title("Toss Portfolio Radar")
    st.sidebar.caption("조회 전용 포트폴리오 리스크 대시보드")
    st.sidebar.divider()
    menu = st.sidebar.selectbox("☰ 메뉴", MENU_ITEMS)
    client = get_client() if config.is_configured else None
    if client:
        show_sidebar_market_status(client)
    refresh = st.sidebar.button("새로고침", use_container_width=True)
    auto_refresh = st.sidebar.checkbox("자동 새로고침", value=default_auto_refresh)
    refresh_interval = st.sidebar.number_input(
        "새로고침 간격(초)",
        min_value=AUTO_REFRESH_MIN_SECONDS,
        max_value=AUTO_REFRESH_MAX_SECONDS,
        value=default_refresh_interval,
        step=5,
        disabled=not auto_refresh,
    )
    sync_auto_refresh_query_params(auto_refresh, int(refresh_interval))
    st.sidebar.write("마지막 갱신 시간:", now)
    if auto_refresh:
        st.sidebar.caption(f"{int(refresh_interval)}초마다 자동으로 새로고침합니다.")
    if st.sidebar.button("API 연결 진단", use_container_width=True):
        get_config.cache_clear()
        st.cache_resource.clear()
        show_api_diagnostics(get_config())

    if refresh:
        get_config.cache_clear()
        st.cache_resource.clear()
        st.rerun()

    st.title("Toss Portfolio Radar")
    st.caption("조회 전용 포트폴리오 리스크 대시보드")
    st.info("보유 종목과 관심종목의 추세, 변동성, 하락위험을 참고용 점수로 확인합니다. 실제 주문 기능이나 투자 조언은 제공하지 않습니다.")

    if not config.is_configured:
        st.info(
            ".env 파일에 TOSS_CLIENT_ID와 TOSS_CLIENT_SECRET을 설정하면 계좌와 보유 종목을 조회할 수 있습니다."
        )
        st.code("copy .env.example .env\nstreamlit run app.py", language="powershell")
        return

    client = get_client()

    if menu == "관심종목":
        render_watchlist_page(client)
        return
    if menu == "변화 그래프":
        render_snapshot_page()
        return

    try:
        accounts = client.get_accounts()
    except TossInvestError as exc:
        st.error(str(exc))
        return

    if not accounts:
        st.info("조회 가능한 계좌가 없습니다. API 설정과 토스증권 Open API 권한을 확인해 주세요.")
        st.warning(
            "인증은 진행됐지만 계좌 목록이 비어 있습니다. 토스증권 Open API에서 계좌 조회 권한이 활성화되어 있는지, "
            "해당 API 키가 실제 계좌와 연결되어 있는지 확인해 주세요."
        )
        show_summary_cards(calculate_summary(pd.DataFrame()))
        return

    account_options = {_account_label(account): account for account in accounts}
    selected_label = st.sidebar.selectbox("선택 계좌", list(account_options.keys()))
    selected_account = account_options[selected_label]
    account_seq = _account_seq(selected_account)
    if account_seq is None:
        st.error("선택한 계좌에서 accountSeq를 확인할 수 없습니다.")
        return

    if auto_refresh:
        render_auto_refresh_dashboard(client, account_seq, int(refresh_interval))
    else:
        render_dashboard(client, account_seq)


def render_auto_refresh_dashboard(client: TossInvestClient, account_seq: int, interval_seconds: int) -> None:
    bounded_seconds = min(max(interval_seconds, AUTO_REFRESH_MIN_SECONDS), AUTO_REFRESH_MAX_SECONDS)

    @st.fragment(run_every=f"{bounded_seconds}s")
    def dashboard_fragment() -> None:
        render_dashboard(client, account_seq)

    dashboard_fragment()


def render_dashboard(client: TossInvestClient, account_seq: int) -> None:
    with st.spinner("포트폴리오 데이터를 조회하는 중입니다."):
        data = load_dashboard_data(client, account_seq)

    if data["error"]:
        st.error(data["error"])

    holdings_df = data["holdings_df"]
    summary = calculate_summary(holdings_df, data["usd_krw"], data["api_summary"])
    save_portfolio_snapshot(summary, holdings_df)
    show_summary_cards(summary)

    st.caption("USD/KRW 환율은 참고용 표시 환율이며 실제 주문 환율이 아닙니다.")

    if holdings_df.empty:
        st.info("현재 표시할 보유 종목이 없습니다.")
        return

    st.markdown("### 종목별 현황")
    table_df = build_display_table(holdings_df)
    st.dataframe(table_df, use_container_width=True, hide_index=True)
    show_exchange_impact(holdings_df, data["usd_krw"])

    symbols = holdings_df["symbol"].dropna().astype(str).tolist()
    selected_symbol = st.selectbox(
        "종목 상세",
        symbols,
        format_func=lambda symbol: _symbol_label(holdings_df, symbol),
        key="selected_symbol",
    )
    show_symbol_detail(selected_symbol, holdings_df, data["candles"], data["warnings"])


def render_watchlist_page(client: TossInvestClient) -> None:
    st.markdown("### 관심종목")
    st.caption("관심종목은 보유 종목과 별도로 `watchlist.json`에 저장됩니다.")

    symbols = load_watchlist()
    with st.form("watchlist_controls"):
        c1, c2, c3 = st.columns([2, 2, 1])
        new_symbol = c1.text_input("관심종목 심볼 추가", placeholder="예: 005930 또는 AAPL").strip().upper()
        delete_options = [""] + symbols
        delete_symbol = c2.selectbox("관심종목 삭제", delete_options, format_func=lambda value: value or "선택 안 함")
        submitted = c3.form_submit_button("적용", use_container_width=True)
        if submitted:
            updated_symbols = symbols
            if new_symbol:
                updated_symbols = updated_symbols + [new_symbol]
            if delete_symbol:
                updated_symbols = [symbol for symbol in updated_symbols if symbol != delete_symbol]
            save_watchlist(updated_symbols)
            st.rerun()

    symbols = load_watchlist()
    if not symbols:
        st.info("관심종목이 없습니다. 위 입력칸에서 심볼을 추가해 주세요.")
        return

    with st.spinner("관심종목 데이터를 조회하는 중입니다."):
        watchlist_df, candles_by_symbol, warnings_by_symbol = load_watchlist_data(client, symbols)

    st.dataframe(build_watchlist_display_table(watchlist_df), use_container_width=True, hide_index=True)

    selected_symbol = st.selectbox("관심종목 상세", symbols, key="selected_watchlist_symbol")
    selected_row = watchlist_df.loc[watchlist_df["symbol"] == selected_symbol]
    if selected_row.empty:
        return
    show_watchlist_detail(selected_row.iloc[0], candles_by_symbol.get(selected_symbol, pd.DataFrame()), warnings_by_symbol.get(selected_symbol, []))


def render_snapshot_page() -> None:
    st.markdown("### 포트폴리오 변화 그래프")
    snapshots = load_snapshots()
    if not snapshots:
        st.info("저장된 snapshot이 아직 없습니다. 포트폴리오 화면을 한 번 조회하면 자동으로 저장됩니다.")
        return

    df = pd.DataFrame(snapshots)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    if df.empty:
        st.info("표시할 수 있는 snapshot 데이터가 없습니다.")
        return

    st.plotly_chart(build_snapshot_chart(df, "total_value_krw", "총 평가금액 KRW", "총 평가금액 변화"), use_container_width=True)
    st.plotly_chart(build_snapshot_chart(df, "total_profit_rate", "총수익률", "총수익률 변화", percent=True), use_container_width=True)
    st.plotly_chart(
        build_snapshot_chart(df, "average_downside_risk_score", "평균 하락위험점수", "하락위험 점수 평균 변화"),
        use_container_width=True,
    )


def show_sidebar_market_status(client: TossInvestClient) -> None:
    with st.sidebar.expander("장 운영 상태", expanded=True):
        st.caption("토스증권 Open API 시장 캘린더 기준")
        for market, label in [("KR", "국내"), ("US", "미국")]:
            calendar = client.get_market_calendar(market)
            status = summarize_market_status(calendar)
            st.write(f"**{label}**: {status['status']}")
            st.caption(f"{status['session']} · {status['detail']}")


def render_market_status_page(client: TossInvestClient) -> None:
    st.markdown("### 장 운영 상태")
    st.caption("장 운영 시간은 토스증권 Open API의 시장 캘린더 기준입니다.")
    cols = st.columns(2)
    for column, market, label in [(cols[0], "KR", "국내 시장"), (cols[1], "US", "미국 시장")]:
        calendar = client.get_market_calendar(market)
        status = summarize_market_status(calendar)
        with column:
            st.metric(label, status["status"])
            st.write("기준일:", status["date"])
            st.write("현재 세션:", status["session"])
            st.caption(status["detail"])


def load_watchlist_data(
    client: TossInvestClient,
    symbols: list[str],
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, list[dict[str, Any]]]]:
    prices = client.get_prices(symbols)
    price_map = {str(item.get("symbol", "")).upper(): item for item in prices}
    rows = []
    candles_by_symbol: dict[str, pd.DataFrame] = {}
    warnings_by_symbol: dict[str, list[dict[str, Any]]] = {}

    for symbol in symbols:
        price = price_map.get(symbol, {})
        warnings = client.get_stock_warnings(symbol)
        candle_df = prepare_candle_dataframe(client.get_candles(symbol))
        candles_by_symbol[symbol] = candle_df
        warnings_by_symbol[symbol] = warnings
        rows.append(
            {
                "symbol": symbol,
                "category": "관심종목",
                "currency": price.get("currency"),
                "lastPrice": price.get("lastPrice"),
                "trend_score": calculate_trend_score(candle_df),
                "volatility_score": calculate_volatility_score(candle_df),
                "downside_risk_score": calculate_downside_risk_score(candle_df, len(warnings)),
                "warning_count": len(warnings),
            }
        )
    return pd.DataFrame(rows), candles_by_symbol, warnings_by_symbol


def show_api_diagnostics(config: Any) -> None:
    if not config.is_configured:
        st.sidebar.error(".env의 TOSS_CLIENT_ID와 TOSS_CLIENT_SECRET을 먼저 입력해 주세요.")
        return

    try:
        with TossInvestClient(config) as client:
            client.issue_token()
            accounts = client.get_accounts()
    except TossInvestError as exc:
        st.sidebar.error(f"진단 실패: {exc}")
        return

    st.sidebar.success("토큰 발급 성공")
    if accounts:
        st.sidebar.success(f"계좌 API 성공: {len(accounts)}개 계좌 확인")
    else:
        st.sidebar.warning("계좌 API 성공, 하지만 반환된 계좌가 0개입니다.")


def sync_auto_refresh_query_params(enabled: bool, interval_seconds: int) -> None:
    desired_auto_refresh = "1" if enabled else "0"
    desired_interval = str(min(max(interval_seconds, AUTO_REFRESH_MIN_SECONDS), AUTO_REFRESH_MAX_SECONDS))
    if st.query_params.get("auto_refresh") != desired_auto_refresh:
        st.query_params["auto_refresh"] = desired_auto_refresh
    if st.query_params.get("refresh_interval") != desired_interval:
        st.query_params["refresh_interval"] = desired_interval


def _query_bool(key: str, default: bool) -> bool:
    value = st.query_params.get(key)
    if value is None:
        return default
    return str(value).lower() in {"1", "true", "yes", "on"}


def _query_int(key: str, default: int, minimum: int, maximum: int) -> int:
    value = st.query_params.get(key)
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


def load_dashboard_data(client: TossInvestClient, account_seq: int) -> dict[str, Any]:
    error = None
    try:
        holdings_payload = client.get_holdings_payload(account_seq)
        holdings = TossInvestClient.extract_holdings_items(holdings_payload)
    except TossInvestError as exc:
        holdings_payload = {}
        holdings = []
        error = str(exc)

    api_summary = extract_api_summary(holdings_payload)
    holdings_df = holdings_to_dataframe(holdings)
    prices = client.get_prices(holdings_df["symbol"].dropna().astype(str).tolist()) if not holdings_df.empty else []
    holdings_df = merge_prices(holdings_df, prices)

    exchange_rate = client.get_exchange_rate()
    usd_krw = _extract_rate(exchange_rate)
    holdings_df = calculate_weights(holdings_df, usd_krw)

    warnings_by_symbol: dict[str, list[dict[str, Any]]] = {}
    candles_by_symbol: dict[str, pd.DataFrame] = {}
    risk_scores: dict[str, dict[str, int]] = {}

    for symbol in holdings_df["symbol"].dropna().astype(str).tolist():
        warnings = client.get_stock_warnings(symbol)
        warnings_by_symbol[symbol] = warnings
        candle_df = prepare_candle_dataframe(client.get_candles(symbol))
        candles_by_symbol[symbol] = candle_df
        risk_scores[symbol] = {
            "trend_score": calculate_trend_score(candle_df),
            "volatility_score": calculate_volatility_score(candle_df),
            "downside_risk_score": calculate_downside_risk_score(candle_df, len(warnings)),
        }

    holdings_df = add_warning_counts(holdings_df, {symbol: len(items) for symbol, items in warnings_by_symbol.items()})
    holdings_df = add_risk_scores(holdings_df, risk_scores)

    return {
        "holdings_df": holdings_df,
        "api_summary": api_summary,
        "usd_krw": usd_krw,
        "warnings": warnings_by_symbol,
        "candles": candles_by_symbol,
        "error": error,
    }


def show_summary_cards(summary: dict[str, float | int | None]) -> None:
    st.markdown("### 포트폴리오 요약")
    cols = st.columns(4)
    holding_count = summary.get("holding_count")
    cols[0].metric("총 보유 종목 수", "-" if holding_count is None else holding_count)
    cols[1].metric("총 평가금액 KRW", format_currency(summary.get("total_value_krw"), "KRW"))
    cols[2].metric("총 평가금액 USD", format_currency(summary.get("total_value_usd"), "USD"))
    cols[3].metric("당일 손익", format_currency(summary.get("daily_profit_loss"), "KRW"))

    cols = st.columns(4)
    cols[0].metric("총수익률", format_percent(summary.get("total_profit_rate")))
    cols[1].metric("국내 주식 비중", format_percent(summary.get("korea_stock_weight")))
    cols[2].metric("미국 주식 비중", format_percent(summary.get("us_stock_weight")))
    cols[3].metric("달러 자산 비중", format_percent(summary.get("usd_asset_weight")))


def build_display_table(holdings_df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "symbol",
        "name",
        "marketCountry",
        "currency",
        "quantity",
        "lastPrice",
        "averagePurchasePrice",
        "profitLoss.rate",
        "cost.commission",
        "cost.tax",
        "dailyProfitLoss.rate",
        "trend_score",
        "volatility_score",
        "downside_risk_score",
        "warning_count",
    ]
    table = holdings_df.reindex(columns=columns).copy()

    table["quantity"] = table["quantity"].map(lambda value: format_number(value, 4))
    table["lastPrice"] = table.apply(
        lambda row: format_currency(row.get("lastPrice"), str(row.get("currency") or "KRW")),
        axis=1,
    )
    table["averagePurchasePrice"] = table.apply(
        lambda row: format_currency(row.get("averagePurchasePrice"), str(row.get("currency") or "KRW")),
        axis=1,
    )
    for column in ["cost.commission", "cost.tax"]:
        table[column] = table.apply(
            lambda row: format_currency(row.get(column), str(row.get("currency") or "KRW")),
            axis=1,
        )
    for column in ["trend_score", "volatility_score", "downside_risk_score"]:
        table[column] = table[column].map(format_score)
    table["profitLoss.rate"] = table["profitLoss.rate"].map(format_percent)
    table["dailyProfitLoss.rate"] = table["dailyProfitLoss.rate"].map(format_percent)
    table = table.fillna("-")
    return table.rename(
        columns={
            "symbol": "심볼",
            "name": "종목명",
            "marketCountry": "시장",
            "currency": "통화",
            "quantity": "보유수량",
            "lastPrice": "현재가",
            "averagePurchasePrice": "평균매입가",
            "profitLoss.rate": "총수익률",
            "cost.commission": "수수료",
            "cost.tax": "세금",
            "dailyProfitLoss.rate": "당일손익률",
            "trend_score": "추세점수",
            "volatility_score": "변동성점수",
            "downside_risk_score": "하락위험점수",
            "warning_count": "유의사항수",
        }
    )


def build_watchlist_display_table(watchlist_df: pd.DataFrame) -> pd.DataFrame:
    if watchlist_df.empty:
        return pd.DataFrame()
    table = watchlist_df.copy()
    table["lastPrice"] = table.apply(
        lambda row: format_currency(row.get("lastPrice"), str(row.get("currency") or "KRW")),
        axis=1,
    )
    for column in ["trend_score", "volatility_score", "downside_risk_score"]:
        table[column] = table[column].map(format_score)
    return table.fillna("-").rename(
        columns={
            "symbol": "심볼",
            "category": "구분",
            "currency": "통화",
            "lastPrice": "현재가",
            "trend_score": "추세점수",
            "volatility_score": "변동성점수",
            "downside_risk_score": "하락위험점수",
            "warning_count": "유의사항수",
        }
    )


def show_exchange_impact(holdings_df: pd.DataFrame, usd_krw: float | None) -> None:
    if holdings_df.empty:
        return
    usd_holdings = holdings_df[holdings_df["currency"].astype(str).str.upper().eq("USD")].copy()
    if usd_holdings.empty:
        return

    st.markdown("### 해외주식 환율 참고")
    st.caption(
        "USD/KRW 환율은 참고용 표시 환율이며 실제 주문 환율과 다를 수 있습니다. "
        "해외주식 총수익률은 토스 앱의 수수료·세금 포함 기준과 맞추기 위해 OpenAPI의 비용 포함 필드를 우선 사용합니다. "
        "원화 총수익률을 입력하면 달러 총수익률과 비교해 추정 매수환율과 환율 효과를 계산합니다."
    )

    manual_krw_returns = collect_manual_krw_returns(usd_holdings)
    rows = []
    for _, row in usd_holdings.iterrows():
        symbol = str(row.get("symbol", "")).upper()
        usd_value = _to_float(row.get("evaluationAmount"))
        purchase_amount = _to_float(row.get("purchaseAmount"))
        last_price = _to_float(row.get("lastPrice"))
        average_price = _to_float(row.get("averagePurchasePrice"))
        api_krw_return = _to_float(row.get("profitLoss.rateKrw"))
        krw_return = api_krw_return if api_krw_return is not None else manual_krw_returns.get(symbol)
        krw_value = usd_value * usd_krw if usd_krw and usd_value is not None else None
        usd_return = _calculate_usd_return(last_price, average_price, usd_value, purchase_amount)
        fx_effect = krw_return - usd_return if krw_return is not None and usd_return is not None else None
        estimated_purchase_fx = _estimate_purchase_fx(usd_krw, usd_return, krw_return)
        rows.append(
            {
                "심볼": symbol,
                "종목명": row.get("name"),
                "USD 평가금액": format_currency(usd_value, "USD"),
                "KRW 환산 평가금액": format_currency(krw_value, "KRW"),
                "현재 환율": "-" if usd_krw is None else f"{usd_krw:,.2f}",
                "USD 총수익률": format_percent(usd_return),
                "원화 총수익률": format_percent(krw_return),
                "추정 매수환율": "-" if estimated_purchase_fx is None else f"{estimated_purchase_fx:,.2f}",
                "환율 효과": _format_percentage_point(fx_effect),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("추정 매수환율 = 현재 환율 × (1 + USD 총수익률) ÷ (1 + 원화 총수익률). 원화 총수익률이 없으면 계산하지 않습니다.")


def collect_manual_krw_returns(usd_holdings: pd.DataFrame) -> dict[str, float]:
    values: dict[str, float] = {}
    with st.expander("원화 총수익률 직접 입력", expanded=False):
        st.caption("토스 앱을 원화(₩) 기준으로 바꾼 뒤 종목별 총 수익률 숫자만 입력하세요. 예: -11.94")
        for symbol in usd_holdings["symbol"].dropna().astype(str).str.upper().tolist():
            raw_value = st.text_input(
                f"{symbol} 원화 총수익률(%)",
                key=f"krw_return_override_{symbol}",
                placeholder="예: -11.94",
            )
            parsed = _parse_percent_text(raw_value)
            if parsed is not None:
                values[symbol] = parsed
    return values


def _calculate_usd_return(
    last_price: float | None,
    average_price: float | None,
    current_amount: float | None,
    purchase_amount: float | None,
) -> float | None:
    if purchase_amount and current_amount is not None:
        return current_amount / purchase_amount - 1
    if average_price and last_price is not None:
        return last_price / average_price - 1
    return None


def _estimate_purchase_fx(
    current_fx: float | None,
    usd_return: float | None,
    krw_return: float | None,
) -> float | None:
    if current_fx is None or usd_return is None or krw_return is None:
        return None
    denominator = 1 + krw_return
    if denominator == 0:
        return None
    estimated = current_fx * (1 + usd_return) / denominator
    return estimated if estimated > 0 else None


def _format_percentage_point(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:+.2f}%p"


def save_portfolio_snapshot(summary: dict[str, float | int | None], holdings_df: pd.DataFrame) -> None:
    if holdings_df.empty:
        return
    downside = pd.to_numeric(holdings_df.get("downside_risk_score"), errors="coerce")
    snapshot = {
        "timestamp": utc_now_iso(),
        "total_value_krw": summary.get("total_value_krw"),
        "total_profit_rate": summary.get("total_profit_rate"),
        "average_downside_risk_score": None if downside.empty else float(downside.fillna(0).mean()),
    }
    append_snapshot(snapshot)


def build_snapshot_chart(df: pd.DataFrame, y_column: str, y_label: str, title: str, percent: bool = False) -> go.Figure:
    fig = go.Figure()
    values = pd.to_numeric(df.get(y_column), errors="coerce")
    y = values * 100 if percent else values
    fig.add_trace(go.Scatter(x=df["timestamp"], y=y, mode="lines+markers", name=y_label))
    fig.update_layout(
        title=title,
        height=320,
        margin=dict(l=20, r=20, t=50, b=20),
        yaxis_title=f"{y_label} (%)" if percent else y_label,
        hovermode="x unified",
    )
    return fig


def summarize_market_status(calendar: dict[str, Any] | None) -> dict[str, str]:
    if not calendar:
        return {
            "status": "확인 불가",
            "date": "-",
            "session": "-",
            "detail": "시장 캘린더 정보를 가져오지 못했습니다.",
        }

    today = calendar.get("today") if isinstance(calendar.get("today"), dict) else {}
    sessions = flatten_market_sessions(today)
    now = datetime.now().astimezone()
    for name, start, end in sessions:
        if start <= now <= end:
            return {
                "status": "열림",
                "date": str(today.get("date", "-")),
                "session": name,
                "detail": f"{_format_time(start)} ~ {_format_time(end)}",
            }

    upcoming = [(name, start, end) for name, start, end in sessions if now < start]
    if upcoming:
        name, start, end = upcoming[0]
        detail = f"다음 세션: {name} {_format_time(start)} ~ {_format_time(end)}"
    else:
        next_day = calendar.get("nextBusinessDay") if isinstance(calendar.get("nextBusinessDay"), dict) else {}
        detail = f"다음 영업일: {next_day.get('date', '-')}"

    return {
        "status": "닫힘",
        "date": str(today.get("date", "-")),
        "session": "-",
        "detail": detail,
    }


def flatten_market_sessions(day: dict[str, Any]) -> list[tuple[str, datetime, datetime]]:
    session_labels = {
        "dayMarket": "데이마켓",
        "preMarket": "프리마켓",
        "regularMarket": "정규장",
        "afterMarket": "애프터마켓",
    }
    source = day.get("integrated") if isinstance(day.get("integrated"), dict) else day
    sessions: list[tuple[str, datetime, datetime]] = []
    for key in ["dayMarket", "preMarket", "regularMarket", "afterMarket"]:
        item = source.get(key) if isinstance(source, dict) else None
        if not isinstance(item, dict):
            continue
        start = _parse_datetime(item.get("startTime"))
        end = _parse_datetime(item.get("endTime"))
        if start and end:
            sessions.append((session_labels[key], start, end))
    return sorted(sessions, key=lambda item: item[1])


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).astimezone()
    except ValueError:
        return None


def _format_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def show_watchlist_detail(row: pd.Series, candle_df: pd.DataFrame, warning_items: list[dict[str, Any]]) -> None:
    symbol = str(row.get("symbol"))
    st.markdown("### 관심종목 상세")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("심볼", symbol)
    c2.metric("현재가", format_currency(row.get("lastPrice"), str(row.get("currency") or "KRW")))
    c3.metric("추세점수", format_score(row.get("trend_score")))
    c4.metric("하락위험점수", format_score(row.get("downside_risk_score")))

    if candle_df.empty:
        st.info("표시할 캔들 데이터가 없습니다.")
    else:
        st.plotly_chart(build_price_chart(candle_df, symbol), use_container_width=True)
        st.plotly_chart(build_rsi_chart(candle_df, symbol), use_container_width=True)

    if warning_items:
        st.markdown("#### 매수 유의사항")
        for item in warning_items:
            st.write(f"- {_warning_text(item)}")


def show_symbol_detail(
    symbol: str,
    holdings_df: pd.DataFrame,
    candles: dict[str, pd.DataFrame],
    warnings: dict[str, list[dict[str, Any]]],
) -> None:
    row = holdings_df.loc[holdings_df["symbol"] == symbol].iloc[0]
    candle_df = candles.get(symbol, pd.DataFrame())
    warning_items = warnings.get(symbol, [])
    rsi = _latest(candle_df, "rsi")
    volatility = _latest(candle_df, "volatility20")
    max_drawdown = _latest(candle_df, "max_drawdown20")

    st.markdown("### 종목 상세")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("종목명", _safe_text(row.get("name")))
    c2.metric("심볼", symbol)
    c3.metric("현재가", format_currency(row.get("lastPrice"), str(row.get("currency") or "KRW")))
    c4.metric("평균 매입가", format_currency(row.get("averagePurchasePrice"), str(row.get("currency") or "KRW")))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총수익률(비용포함)", format_percent(row.get("profitLoss.rate")))
    c2.metric("RSI", "-" if rsi is None else f"{rsi:.2f}", help="상대강도지수. 0~100 범위에서 최근 상승/하락 압력을 보여주는 참고 지표입니다.")
    c3.metric("최근 20일 변동성", format_percent(volatility), help="최근 20일 일간 수익률의 흔들림 정도입니다.")
    c4.metric("최근 20일 최대낙폭", format_percent(max_drawdown), help="최근 20일 고점 대비 가장 크게 밀린 폭입니다.")

    c1, c2, c3 = st.columns(3)
    currency = str(row.get("currency") or "KRW")
    total_cost = _sum_optional(row.get("cost.commission"), row.get("cost.tax"))
    c1.metric("수수료", format_currency(row.get("cost.commission"), currency))
    c2.metric("세금", format_currency(row.get("cost.tax"), currency))
    c3.metric("비용 합계", format_currency(total_cost, currency))

    show_indicator_glossary()

    if candle_df.empty:
        st.info("표시할 캔들 데이터가 없습니다.")
    else:
        st.plotly_chart(build_price_chart(candle_df, symbol), use_container_width=True)
        st.plotly_chart(build_rsi_chart(candle_df, symbol), use_container_width=True)
        st.plotly_chart(build_short_term_scenario_chart(candle_df, symbol), use_container_width=True)
        st.caption(
            "단기 시나리오는 최근 흐름과 변동성을 단순 반영한 참고용 범위입니다. "
            "특정 가격 도달이나 방향을 보장하는 투자 조언이 아닙니다."
        )

    c1, c2, c3 = st.columns(3)
    c1.metric("추세점수", format_score(row.get("trend_score")), help="이동평균과 최근 수익률을 종합한 단기 흐름 점수입니다.")
    c2.metric("변동성점수", format_score(row.get("volatility_score")), help="최근 20일 가격 흔들림을 0~100으로 환산한 점수입니다.")
    c3.metric("하락위험점수", format_score(row.get("downside_risk_score")), help="최대낙폭, RSI, 단기 급등, 유의사항을 함께 본 참고용 위험 점수입니다.")

    if warning_items:
        st.markdown("#### 매수 유의사항")
        for item in warning_items:
            st.write(f"- {_warning_text(item)}")
    else:
        st.caption("현재 표시할 매수 유의사항이 없습니다.")

    comment = build_analysis_comment(
        int(row.get("trend_score") or 0),
        int(row.get("volatility_score") or 0),
        int(row.get("downside_risk_score") or 0),
        rsi,
    )
    st.info(comment)


def show_indicator_glossary() -> None:
    with st.expander("지표 용어 간단 설명", expanded=False):
        st.markdown(
            """
            - **RSI**: 최근 상승과 하락의 힘을 0~100으로 나타낸 참고 지표입니다. 70 이상은 과열권, 30 이하는 침체권에 가까운 상태로 봅니다.
            - **변동성**: 가격이 얼마나 크게 흔들렸는지 보는 지표입니다. 높을수록 단기 움직임이 거칠 수 있습니다.
            - **최대낙폭**: 최근 고점 대비 얼마나 깊게 내려왔는지 보는 지표입니다.
            - **추세점수**: 이동평균과 최근 수익률이 단기 흐름에 얼마나 우호적인지 0~100으로 나타낸 값입니다.
            - **하락위험점수**: 최대낙폭, RSI, 단기 급등, 유의사항을 함께 본 참고용 위험 점수입니다.
            """
        )


def build_price_chart(df: pd.DataFrame, symbol: str) -> go.Figure:
    fig = go.Figure()
    x = df["date"] if "date" in df else df.index
    fig.add_trace(go.Scatter(x=x, y=df["close"], mode="lines", name="종가"))
    fig.add_trace(go.Scatter(x=x, y=df["ma5"], mode="lines", name="5일 이동평균"))
    fig.add_trace(go.Scatter(x=x, y=df["ma20"], mode="lines", name="20일 이동평균"))
    fig.update_layout(title=f"{symbol} 가격", height=420, margin=dict(l=20, r=20, t=50, b=20))
    return fig


def build_rsi_chart(df: pd.DataFrame, symbol: str) -> go.Figure:
    fig = go.Figure()
    x = df["date"] if "date" in df else df.index
    fig.add_trace(go.Scatter(x=x, y=df["rsi"], mode="lines", name="RSI"))
    fig.add_hline(y=70, line_dash="dash", line_color="red")
    fig.add_hline(y=30, line_dash="dash", line_color="green")
    fig.update_layout(title=f"{symbol} RSI", height=260, margin=dict(l=20, r=20, t=50, b=20), yaxis_range=[0, 100])
    return fig


def build_short_term_scenario_chart(df: pd.DataFrame, symbol: str, days: int = 3) -> go.Figure:
    fig = go.Figure()
    if df.empty or "close" not in df:
        fig.update_layout(title=f"{symbol} 단기 시나리오", height=360, margin=dict(l=20, r=20, t=50, b=20))
        fig.add_annotation(text="시나리오를 만들 캔들 데이터가 부족합니다.", showarrow=False)
        return fig

    recent = df.tail(30).copy()
    close = pd.to_numeric(recent["close"], errors="coerce").dropna()
    if len(close) < 5:
        fig.update_layout(title=f"{symbol} 단기 시나리오", height=360, margin=dict(l=20, r=20, t=50, b=20))
        fig.add_annotation(text="최근 데이터가 더 쌓이면 단기 시나리오를 표시합니다.", showarrow=False)
        return fig

    x_history = recent.loc[close.index, "date"] if "date" in recent else close.index
    returns = close.pct_change(fill_method=None).dropna()
    drift = float(returns.tail(5).mean()) if not returns.empty else 0.0
    volatility = float(returns.tail(20).std(ddof=0)) if len(returns) >= 2 else 0.0
    drift = max(min(drift, 0.05), -0.05)
    volatility = max(min(volatility, 0.08), 0.0)

    last_price = float(close.iloc[-1])
    last_x = list(x_history)[-1]
    future_x = _future_x_values(last_x, days)
    scenario_x = [last_x] + future_x

    center = [last_price]
    upper = [last_price]
    lower = [last_price]
    for step in range(1, days + 1):
        center_price = last_price * ((1 + drift) ** step)
        band = volatility * (step**0.5)
        center.append(center_price)
        upper.append(center_price * (1 + band))
        lower.append(max(center_price * (1 - band), 0))

    fig.add_trace(go.Scatter(x=x_history, y=close, mode="lines", name="최근 종가"))
    fig.add_trace(
        go.Scatter(
            x=scenario_x,
            y=lower,
            mode="lines",
            line=dict(width=0),
            name="시나리오 하단",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=scenario_x,
            y=upper,
            mode="lines",
            fill="tonexty",
            line=dict(width=0),
            name="변동성 범위",
            fillcolor="rgba(31, 119, 180, 0.16)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=scenario_x,
            y=center,
            mode="lines+markers",
            line=dict(dash="dash"),
            name="중립 시나리오",
        )
    )
    fig.update_layout(
        title=f"{symbol} 2~3거래일 참고 시나리오",
        height=380,
        margin=dict(l=20, r=20, t=50, b=20),
        hovermode="x unified",
    )
    return fig


def _future_x_values(last_x: Any, days: int) -> list[Any]:
    last_timestamp = pd.to_datetime(last_x, errors="coerce")
    if pd.isna(last_timestamp):
        return [f"D+{step}" for step in range(1, days + 1)]
    return [last_timestamp + pd.offsets.BDay(step) for step in range(1, days + 1)]


def _account_seq(account: dict[str, Any]) -> int | None:
    for key in ["accountSeq", "account_seq", "seq", "id"]:
        value = account.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _account_label(account: dict[str, Any]) -> str:
    seq = _account_seq(account)
    name = account.get("accountName") or account.get("name") or "계좌"
    return f"{name} ({seq})" if seq is not None else str(name)


def _symbol_label(holdings_df: pd.DataFrame, symbol: str) -> str:
    row = holdings_df.loc[holdings_df["symbol"] == symbol]
    if row.empty:
        return symbol
    name = row.iloc[0].get("name") or symbol
    return f"{name} ({symbol})"


def _extract_rate(exchange_rate: dict[str, Any] | None) -> float | None:
    if not exchange_rate:
        return None
    for key in ["rate", "exchangeRate", "basePrice", "price"]:
        value = exchange_rate.get(key)
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _latest(df: pd.DataFrame, column: str) -> float | None:
    if df.empty or column not in df:
        return None
    value = pd.to_numeric(pd.Series([df[column].iloc[-1]]), errors="coerce").iloc[0]
    return None if pd.isna(value) else float(value)


def _to_float(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def _sum_optional(*values: object) -> float | None:
    numbers = [_to_float(value) for value in values]
    present = [number for number in numbers if number is not None]
    if not present:
        return None
    return sum(present)


def _parse_percent_text(value: str) -> float | None:
    cleaned = value.strip().replace("%", "").replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned) / 100
    except ValueError:
        return None


def _warning_text(item: dict[str, Any]) -> str:
    for key in ["name", "type", "warningType", "message", "description"]:
        value = item.get(key)
        if value:
            return str(value)
    return "추가 확인 필요"


def _safe_text(value: object) -> str:
    if value is None or pd.isna(value):
        return "-"
    return str(value)


if __name__ == "__main__":
    main()
