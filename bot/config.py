"""Carga de config.yaml + variables de entorno (.env)."""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "general": {
        "timezone": "America/Argentina/Buenos_Aires",
        "poll_seconds": 15,
        "exchanges": ["binance", "bybit", "okx"],
        "quote": "USDT",
        "history": 1000,
        "state_file": "data/state.json",
        "startup_message": True,
    },
    "symbols": {},
    "groups": {},
    "moves": {
        "reference": "BTC",
        "windows": [
            {"minutes": 5, "pct": 1.0},
            {"minutes": 30, "pct": 3.0},
            {"minutes": 60, "pct": 5.0},
        ],
        "scale": {
            "mode": "atr",
            "atr_timeframe": "1d",
            "atr_length": 14,
            "min": 1.0,
            "max": 3.0,
            "fixed": {},
        },
        "rearm": 0.5,
    },
    "emas": {
        "base_timeframe": "1d",
        "refresh_seconds": 60,
        "touch_cooldown_candles": 1,
        "near_atr": 0.5,
        "confirm_seconds": 60,
        "oscillation_lookback": 20,
        "reminder_hours": {"default": 6},
    },
    "ash": {
        "length": 16,
        "smooth": 4,
        "ma": "EMA",
        "refresh_seconds": 300,
        "confirm_minutes": 15,
    },
    "summary": {
        "enabled": True,
        "time_utc": "00:05",
        "ema_timeframes": ["1d"],
        "ash_timeframes": ["1d", "1w", "1M"],
    },
}

GROUP_DEFAULTS: dict[str, Any] = {
    "assets": [],
    "moves": False,
    "ema_timeframes": [],
    "ema_touch": True,
    "ema_cloud": False,
    "ema_cross": False,
    "ash_timeframes": [],
    "ash_color_changes": False,
}


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_dotenv(path: str | Path = ".env") -> None:
    """Parser mínimo de .env (KEY=VALUE). No pisa variables ya definidas."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Group:
    name: str
    assets: list[str]
    moves: bool
    ema_timeframes: list[str]
    ema_touch: bool
    ema_cloud: bool
    ema_cross: bool
    ash_timeframes: list[str]
    ash_color_changes: bool


@dataclass
class Config:
    raw: dict[str, Any]
    telegram_token: str = ""
    telegram_chat_id: str = ""
    groups: list[Group] = field(default_factory=list)

    @property
    def general(self) -> dict:
        return self.raw["general"]

    @property
    def moves(self) -> dict:
        return self.raw["moves"]

    @property
    def emas(self) -> dict:
        return self.raw["emas"]

    @property
    def ash(self) -> dict:
        return self.raw["ash"]

    @property
    def summary(self) -> dict:
        return self.raw["summary"]

    @property
    def symbols(self) -> dict:
        return self.raw.get("symbols") or {}

    @property
    def all_assets(self) -> list[str]:
        seen: list[str] = []
        for g in self.groups:
            for a in g.assets:
                if a not in seen:
                    seen.append(a)
        return seen

    def group_of(self, asset: str) -> Group | None:
        for g in self.groups:
            if asset in g.assets:
                return g
        return None


def load_config(path: str | Path = "config.yaml") -> Config:
    load_dotenv()
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    raw = _merge(DEFAULTS, data)
    groups = []
    for name, g in (raw.get("groups") or {}).items():
        merged = _merge(GROUP_DEFAULTS, g or {})
        merged["assets"] = [str(a).upper() for a in merged["assets"]]
        groups.append(Group(name=name, **{k: merged[k] for k in GROUP_DEFAULTS}))
    if not groups:
        raise ValueError("config.yaml no define ningún grupo de activos en 'groups'")
    return Config(
        raw=raw,
        telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        groups=groups,
    )
