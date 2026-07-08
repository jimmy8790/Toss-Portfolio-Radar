from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from os import getenv

from dotenv import load_dotenv


PLACEHOLDER_VALUES = {"your_client_id_here", "your_client_secret_here", ""}


@dataclass(frozen=True)
class AppConfig:
    toss_client_id: str | None
    toss_client_secret: str | None
    base_url: str = "https://openapi.tossinvest.com"
    timeout_seconds: float = 10.0

    @property
    def is_configured(self) -> bool:
        return bool(self.toss_client_id and self.toss_client_secret)

    @property
    def missing_keys(self) -> list[str]:
        missing = []
        if not self.toss_client_id:
            missing.append("TOSS_CLIENT_ID")
        if not self.toss_client_secret:
            missing.append("TOSS_CLIENT_SECRET")
        return missing


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    load_dotenv(override=True)
    return AppConfig(
        toss_client_id=_read_secret_setting("TOSS_CLIENT_ID"),
        toss_client_secret=_read_secret_setting("TOSS_CLIENT_SECRET"),
    )


def _read_secret_setting(key: str) -> str | None:
    value = (getenv(key) or "").strip()
    if value in PLACEHOLDER_VALUES:
        return None
    return value
