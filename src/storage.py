from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WATCHLIST_PATH = Path("watchlist.json")
SNAPSHOTS_PATH = Path("snapshots.json")


def load_watchlist(path: Path = WATCHLIST_PATH) -> list[str]:
    payload = _read_json(path, default=[])
    if isinstance(payload, dict):
        payload = payload.get("symbols", [])
    if not isinstance(payload, list):
        return []
    return list(dict.fromkeys(str(symbol).strip().upper() for symbol in payload if str(symbol).strip()))


def save_watchlist(symbols: list[str], path: Path = WATCHLIST_PATH) -> None:
    normalized = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
    _write_json(path, normalized)


def load_snapshots(path: Path = SNAPSHOTS_PATH) -> list[dict[str, Any]]:
    payload = _read_json(path, default=[])
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def append_snapshot(
    snapshot: dict[str, Any],
    path: Path = SNAPSHOTS_PATH,
    *,
    min_interval_seconds: int = 60,
    max_items: int = 1000,
) -> None:
    snapshots = load_snapshots(path)
    if snapshots and _seconds_since(snapshots[-1].get("timestamp")) < min_interval_seconds:
        return
    snapshots.append(snapshot)
    _write_json(path, snapshots[-max_items:])


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _seconds_since(timestamp: object) -> float:
    if not timestamp:
        return float("inf")
    try:
        previous = datetime.fromisoformat(str(timestamp))
    except ValueError:
        return float("inf")
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - previous).total_seconds()
