from __future__ import annotations

import time
from typing import Any

import httpx

from src.config import AppConfig


class TossInvestError(RuntimeError):
    """User-safe API error. Never include secrets in this message."""


class TossInvestClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self._access_token: str | None = None
        self._token_expires_at = 0.0
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.timeout_seconds),
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TossInvestClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def issue_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        if not self.config.is_configured:
            raise TossInvestError(".env에 TOSS_CLIENT_ID와 TOSS_CLIENT_SECRET을 설정해 주세요.")

        try:
            response = self._client.post(
                "/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.config.toss_client_id,
                    "client_secret": self.config.toss_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            self._raise_for_status(response)
            payload = self._safe_json(response)
        except TossInvestError:
            raise
        except httpx.TimeoutException as exc:
            raise TossInvestError("API 응답 시간이 초과되었습니다.") from exc
        except httpx.NetworkError as exc:
            raise TossInvestError("네트워크 연결을 확인하세요.") from exc
        except httpx.HTTPError as exc:
            raise TossInvestError("토스증권 API 호출 중 오류가 발생했습니다.") from exc

        token_payload = self._first_dict(payload, "result", "data")
        token = self._pick(token_payload, "access_token", "accessToken")
        expires_in = self._pick(token_payload, "expires_in", "expiresIn", default=3600)
        if not token:
            raise TossInvestError("인증 응답에서 access token을 확인할 수 없습니다.")

        self._access_token = str(token)
        self._token_expires_at = time.time() + max(int(expires_in or 3600), 1)
        return self._access_token

    def get_accounts(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/v1/accounts", default={})
        accounts = self._extract_list(
            payload,
            "accounts",
            "accountList",
            "items",
            "result.accounts",
            "result.accountList",
            "result.items",
            "data.accounts",
            "data.accountList",
            "data.items",
            "data",
            "result",
        )
        return accounts

    def get_holdings(self, account_seq: int, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else None
        payload = self._request(
            "GET",
            "/api/v1/holdings",
            headers={"X-Tossinvest-Account": str(account_seq)},
            params=params,
            default={},
        )
        return self._extract_list(
            payload,
            "holdings",
            "holdingList",
            "items",
            "result.holdings",
            "result.holdingList",
            "result.items",
            "data.holdings",
            "data.holdingList",
            "data.items",
            "data",
            "result",
        )

    def get_prices(self, symbols: list[str]) -> list[dict[str, Any]]:
        unique_symbols = list(dict.fromkeys([symbol for symbol in symbols if symbol]))
        if not unique_symbols:
            return []

        prices: list[dict[str, Any]] = []
        for start in range(0, len(unique_symbols), 200):
            batch = unique_symbols[start : start + 200]
            payload = self._request(
                "GET",
                "/api/v1/prices",
                params={"symbols": ",".join(batch)},
                default={},
                suppress_errors=True,
            )
            prices.extend(
                self._extract_list(
                    payload,
                    "prices",
                    "priceList",
                    "items",
                    "result.prices",
                    "result.priceList",
                    "result.items",
                    "data.prices",
                    "data.priceList",
                    "data.items",
                    "data",
                    "result",
                )
            )
        return prices

    def get_candles(
        self,
        symbol: str,
        interval: str = "1d",
        count: int = 100,
        adjusted: bool = True,
    ) -> list[dict[str, Any]]:
        if interval not in {"1d", "1m"}:
            raise ValueError('interval은 "1d" 또는 "1m"만 허용됩니다.')

        bounded_count = min(max(int(count), 1), 200)
        payload = self._request(
            "GET",
            "/api/v1/candles",
            params={
                "symbol": symbol,
                "interval": interval,
                "count": bounded_count,
                "adjusted": str(adjusted).lower(),
            },
            default={},
            suppress_errors=True,
        )
        return self._extract_list(
            payload,
            "result.candles",
            "result.items",
            "data.candles",
            "data.items",
            "candles",
            "items",
            "data",
            "result",
        )

    def get_exchange_rate(self, base: str = "USD", quote: str = "KRW") -> dict[str, Any] | None:
        payload = self._request(
            "GET",
            "/api/v1/exchange-rate",
            params={"baseCurrency": base, "quoteCurrency": quote},
            default=None,
            suppress_errors=True,
        )
        if not isinstance(payload, dict):
            return None
        result = payload.get("result", payload)
        return result if isinstance(result, dict) else None

    def get_stock_warnings(self, symbol: str) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"/api/v1/stocks/{symbol}/warnings",
            default={},
            suppress_errors=True,
        )
        return self._extract_list(
            payload,
            "warnings",
            "warningList",
            "items",
            "result.warnings",
            "result.warningList",
            "result.items",
            "data.warnings",
            "data.warningList",
            "data.items",
            "data",
            "result",
        )

    def get_market_calendar(self, market: str, date: str | None = None) -> dict[str, Any] | None:
        market_code = market.upper()
        if market_code not in {"KR", "US"}:
            raise ValueError('market은 "KR" 또는 "US"만 허용됩니다.')
        params = {"date": date} if date else None
        payload = self._request(
            "GET",
            f"/api/v1/market-calendar/{market_code}",
            params=params,
            default=None,
            suppress_errors=True,
        )
        if not isinstance(payload, dict):
            return None
        result = payload.get("result", payload)
        return result if isinstance(result, dict) else None

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        default: Any = None,
        suppress_errors: bool = False,
    ) -> Any:
        try:
            token = self.issue_token()
            merged_headers = {"Authorization": f"Bearer {token}"}
            if headers:
                merged_headers.update(headers)
            response = self._client.request(method, path, headers=merged_headers, params=params)
            self._raise_for_status(response)
            return self._safe_json(response)
        except TossInvestError:
            if suppress_errors:
                return default
            raise
        except httpx.TimeoutException:
            if suppress_errors:
                return default
            raise TossInvestError("API 응답 시간이 초과되었습니다.")
        except httpx.NetworkError:
            if suppress_errors:
                return default
            raise TossInvestError("네트워크 연결을 확인하세요.")
        except httpx.HTTPError:
            if suppress_errors:
                return default
            raise TossInvestError("토스증권 API 호출 중 오류가 발생했습니다.")

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return

        messages = {
            400: "요청 형식이 올바르지 않습니다.",
            401: "인증에 실패했습니다. API 키와 시크릿을 확인하세요.",
            403: "API 접근 권한이 없습니다.",
            404: "요청한 데이터를 찾을 수 없습니다.",
            429: "API 호출 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
        }
        if response.status_code >= 500:
            raise TossInvestError("토스증권 API 서버 오류가 발생했습니다.")
        raise TossInvestError(messages.get(response.status_code, "토스증권 API 호출 중 오류가 발생했습니다."))

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {}

    @staticmethod
    def _pick(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in payload:
                return payload[key]
        return default

    @staticmethod
    def _first_dict(payload: Any, *keys: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        return payload

    @classmethod
    def _extract_list(cls, payload: Any, *paths: str) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []

        for path in paths:
            value: Any = payload
            for part in path.split("."):
                if not isinstance(value, dict):
                    value = None
                    break
                value = value.get(part)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []
