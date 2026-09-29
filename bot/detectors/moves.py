"""Movimientos bruscos: ±1% en ≤5 min, ±3% en ≤30 min, ±5% en ≤1 h (BTC).

Para cada ventana se mide el precio actual contra el mínimo (subida) y el máximo
(bajada) de las velas de 1 minuto de esa ventana. Los umbrales son escalones: si
avisó al 1% y el movimiento llega al 2%, vuelve a avisar ("x2"), y así.

Otros activos (ETH) usan el umbral de BTC multiplicado por la relación de ATR%
(ETH se mueve más, entonces necesita moverse más para que sea "igual de raro").
"""
from __future__ import annotations

import logging
import time

from .. import fmt
from ..config import Config
from ..indicators import atr
from ..market import Market
from ..state import State

log = logging.getLogger(__name__)


class MoveDetector:
    def __init__(self, cfg: Config, market: Market, state: State):
        self.cfg = cfg
        self.market = market
        self.state = state
        self.assets = [a for g in cfg.groups if g.moves for a in g.assets]
        self._scale_cache: dict[str, tuple[float, float]] = {}

    async def atr_pct(self, asset: str) -> float:
        sc = self.cfg.moves["scale"]
        c = await self.market.candles(asset, sc["atr_timeframe"], max_age=3600)
        a = atr(c.high, c.low, c.close, int(sc["atr_length"]))
        # ATR de la última vela cerrada, en % del precio
        return a[-2] / c.close[-2] * 100

    async def scale(self, asset: str) -> float:
        mv = self.cfg.moves
        sc = mv["scale"]
        ref = mv["reference"]
        if asset == ref:
            return 1.0
        if sc["mode"] == "fixed":
            return float((sc.get("fixed") or {}).get(asset, 1.0))
        cached = self._scale_cache.get(asset)
        if cached and time.time() - cached[0] < 3600:
            return cached[1]
        try:
            ratio = await self.atr_pct(asset) / await self.atr_pct(ref)
            ratio = min(max(ratio, float(sc["min"])), float(sc["max"]))
        except Exception as e:  # noqa: BLE001
            log.warning("No pude calcular el ATR de %s (%s); uso el último factor conocido", asset, e)
            ratio = cached[1] if cached else float((sc.get("fixed") or {}).get(asset, 1.0))
        self._scale_cache[asset] = (time.time(), ratio)
        return ratio

    async def check(self) -> list[str]:
        windows = self.cfg.moves["windows"]
        longest = max(int(w["minutes"]) for w in windows)
        out = []
        for asset in self.assets:
            try:
                c = await self.market.candles(asset, "1m", limit=longest + 5)
                scale = await self.scale(asset)
            except Exception as e:  # noqa: BLE001
                log.warning("Movimientos %s: %s", asset, e)
                continue
            msg = self.evaluate(asset, c.high, c.low, c.close[-1], scale)
            if msg:
                out.append(msg)
        return out

    def evaluate(self, asset: str, highs: list[float], lows: list[float], price: float, scale: float) -> str | None:
        rearm = float(self.cfg.moves["rearm"])
        lines = []
        for w in self.cfg.moves["windows"]:
            n = int(w["minutes"])
            thr = float(w["pct"]) * scale
            lo, hi = min(lows[-n:]), max(highs[-n:])
            for direction, ref, chg in (("up", lo, (price - lo) / lo * 100), ("down", hi, (price - hi) / hi * 100)):
                key = f"move:{asset}:{n}:{direction}"
                prev = int(self.state.get(key, 0))
                level = int(abs(chg) // thr)
                if level > prev:
                    self.state.set(key, level)
                    icon = "🚀" if direction == "up" else "🩸"
                    word = "sube" if direction == "up" else "cae"
                    since = "desde el mínimo" if direction == "up" else "desde el máximo"
                    extra = f"  <b>(nivel x{level})</b>" if level > 1 else ""
                    lines.append(
                        f"{icon} <b>{word} {fmt.pct(chg)}</b> en ≤{n} min{extra}\n"
                        f"     {since} {fmt.price(ref)} · umbral {fmt.pct(thr, signed=False)}"
                    )
                elif prev and abs(chg) < (prev - 1 + rearm) * thr:
                    # El movimiento se desinfló: re-armamos para poder avisar de nuevo.
                    self.state.set(key, level)
        if not lines:
            return None
        head = f"⚡ <b>{asset}</b> — movimiento fuerte · precio {fmt.price(price)}"
        if scale != 1.0:
            head += f"\n<i>Umbrales de {asset} ajustados ×{scale:.2f} por su ATR vs {self.cfg.moves['reference']}</i>"
        return head + "\n" + "\n".join(lines)
