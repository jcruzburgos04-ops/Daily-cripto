"""Cambios del ASH (Absolute Strength Histogram v2) en semanal / mensual.

Igual que el cuadro MTF del indicador, se mira la vela EN CURSO del timeframe
superior. Como esa vela todavía se mueve, un cambio sólo se avisa si se
sostiene ``confirm_minutes`` minutos seguidos (evita avisos que se deshacen).

* Cambio de dirección (▲ alcista ↔ ▼ bajista): siempre.
* Cambio de color (ganando / perdiendo fuerza): si el grupo tiene
  ``ash_color_changes: true``.
* Al cerrar la vela semanal/mensual, el estado final queda en el resumen.
"""
from __future__ import annotations

import logging
import time

from .. import fmt
from ..config import Config
from ..indicators import AshState, ash, ash_state
from ..market import Candles, Market, tf_name
from ..state import State

log = logging.getLogger(__name__)


def compute_ash(cfg: Config, c: Candles, idx: int = -1) -> AshState | None:
    p = cfg.ash
    bulls, bears = ash(c.close, int(p["length"]), int(p["smooth"]), p["ma"])
    return ash_state(bulls, bears, idx)


def describe(st: AshState) -> str:
    return f"{st.emoji} {st.arrow} {st.description} · sep. {fmt.pct(st.separation_pct, signed=False)}"


class AshDetector:
    def __init__(self, cfg: Config, market: Market, state: State):
        self.cfg = cfg
        self.market = market
        self.state = state

    async def check(self) -> list[str]:
        out = []
        now = time.time()
        for g in self.cfg.groups:
            for asset in g.assets:
                lines = []
                for tf in g.ash_timeframes:
                    try:
                        c = await self.market.candles(asset, tf, max_age=float(self.cfg.ash["refresh_seconds"]))
                    except Exception as e:  # noqa: BLE001
                        log.warning("ASH %s %s: %s", asset, tf, e)
                        continue
                    line = self.evaluate(asset, tf, c, g.ash_color_changes, now)
                    if line:
                        lines.append(line)
                if lines:
                    out.append(f"📊 <b>{asset}</b> — ASH · precio {fmt.price(c.price)}\n" + "\n".join(lines))
        return out

    def evaluate(self, asset: str, tf: str, c: Candles, color_changes: bool, now: float) -> str | None:
        st = compute_ash(self.cfg, c)
        if st is None:
            return None
        key = f"ash:{asset}:{tf}"
        rec = dict(self.state.get(key) or {})
        ident = {"bullish": st.bullish, "color": st.color if color_changes else None}
        confirmed = rec.get("confirmed")
        if confirmed is None:
            self.state.set(key, {"confirmed": ident})
            return None
        if ident == confirmed:
            rec.pop("pending", None)
            self.state.set(key, rec)
            return None
        pend = rec.get("pending")
        if not pend or pend["ident"] != ident:
            rec["pending"] = {"ident": ident, "since": now}
            self.state.set(key, rec)
            return None
        if now - pend["since"] < float(self.cfg.ash["confirm_minutes"]) * 60:
            return None
        rec = {"confirmed": ident}
        self.state.set(key, rec)
        label = tf_name(tf).upper()
        if ident["bullish"] != confirmed["bullish"]:
            head = f"🔄 <b>ASH {label} cambió a {'ALCISTA ▲' if st.bullish else 'BAJISTA ▼'}</b>"
        else:
            head = f"🎨 ASH {label}: cambió de color"
        return f"{head}\n     {describe(st)}\n     <i>Vela {tf_name(tf)} en curso: se confirma al cierre</i>"
