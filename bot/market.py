"""Datos de mercado vía ccxt (APIs públicas, no hace falta cuenta en el exchange)."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import ccxt.async_support as ccxt

log = logging.getLogger(__name__)

TF_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "12h": 43200,
    "1d": 86400, "3d": 259200, "1w": 604800, "1M": 2592000,
}

TF_NAMES = {
    "1m": "1 min", "5m": "5 min", "15m": "15 min", "30m": "30 min",
    "1h": "1H", "2h": "2H", "4h": "4H", "6h": "6H", "12h": "12H",
    "1d": "diario", "3d": "3 días", "1w": "semanal", "1M": "mensual",
}


def tf_name(tf: str) -> str:
    return TF_NAMES.get(tf, tf)


@dataclass
class Candles:
    """Velas OHLCV, la más vieja primero. La última es la vela EN CURSO (sin cerrar)."""

    ts: list[int]
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[float]

    @classmethod
    def from_rows(cls, rows: list[list]) -> "Candles":
        rows = [r for r in rows if r[4] is not None]
        return cls(
            ts=[int(r[0]) for r in rows],
            open=[float(r[1]) for r in rows],
            high=[float(r[2]) for r in rows],
            low=[float(r[3]) for r in rows],
            close=[float(r[4]) for r in rows],
            volume=[float(r[5] or 0) for r in rows],
        )

    def __len__(self) -> int:
        return len(self.ts)

    @property
    def price(self) -> float:
        return self.close[-1]


class Market:
    def __init__(self, exchange_ids: list[str], quote: str = "USDT", overrides: dict | None = None, history: int = 1000):
        self.exchange_ids = exchange_ids
        self.quote = quote
        self.overrides = overrides or {}
        self.history = history
        self.exchanges: dict[str, ccxt.Exchange] = {}
        self.routes: dict[str, tuple[ccxt.Exchange, str]] = {}
        self._cache: dict[tuple[str, str], tuple[float, Candles]] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def start(self) -> None:
        wanted = list(self.exchange_ids)
        for ov in self.overrides.values():
            if isinstance(ov, dict) and ov.get("exchange") and ov["exchange"] not in wanted:
                wanted.append(ov["exchange"])
        for eid in wanted:
            ex = getattr(ccxt, eid)({"enableRateLimit": True, "options": {"defaultType": "spot"}})
            try:
                await ex.load_markets()
                self.exchanges[eid] = ex
                log.info("Exchange %s conectado (%d mercados)", eid, len(ex.markets))
            except Exception as e:  # noqa: BLE001 - un exchange caído no debe tirar el bot
                log.warning("No se pudo conectar a %s: %s", eid, e)
                await ex.close()
        if not self.exchanges:
            raise RuntimeError("No se pudo conectar a ningún exchange. Revisá la red / región del servidor.")

    async def close(self) -> None:
        for ex in self.exchanges.values():
            await ex.close()

    def resolve(self, asset: str) -> tuple[ccxt.Exchange, str]:
        if asset in self.routes:
            return self.routes[asset]
        ov = self.overrides.get(asset) or {}
        symbol = ov.get("symbol") or f"{asset}/{self.quote}"
        candidates = [ov["exchange"]] if ov.get("exchange") else self.exchange_ids
        for eid in candidates:
            ex = self.exchanges.get(eid)
            if ex is not None and symbol in ex.markets:
                self.routes[asset] = (ex, symbol)
                log.info("%s -> %s en %s", asset, symbol, eid)
                return self.routes[asset]
        raise LookupError(f"{symbol} no está listado en {', '.join(candidates)}")

    def source(self, asset: str) -> str:
        ex, symbol = self.resolve(asset)
        return f"{symbol} @ {ex.id}"

    async def candles(self, asset: str, tf: str, max_age: float = 0, limit: int | None = None) -> Candles:
        """Velas de ``asset`` en ``tf``. Reutiliza la última descarga si tiene menos de ``max_age`` segundos."""
        key = (asset, tf)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._cache.get(key)
            if cached and time.time() - cached[0] < max_age:
                return cached[1]
            ex, symbol = self.resolve(asset)
            rows = await ex.fetch_ohlcv(symbol, tf, limit=limit or self.history)
            c = Candles.from_rows(rows)
            if len(c) == 0:
                raise RuntimeError(f"{symbol} {tf}: el exchange no devolvió velas")
            self._cache[key] = (time.time(), c)
            return c
