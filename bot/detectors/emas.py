"""EMAs: toques de la EMA 100/200, la nube entre ambas y cruces de la EMA 21/34.

* Toque: la vela en curso contiene la EMA (low <= EMA <= high). Un aviso por
  vela, con enfriamiento de N velas para no repetir mientras sigue pegado.
* Nube (EMA100–EMA200): avisa cuando entra, sale, se acerca (a menos de
  ``near_atr`` ATRs) o se aleja. Mientras siga adentro o cerca, manda un
  recordatorio periódico con cuánto está oscilando.
* Cruces 21/34 y 100/200: sólo con velas CERRADAS, para no avisar cruces que
  después se deshacen dentro de la misma vela.
"""
from __future__ import annotations

import logging
import time

from .. import fmt
from ..config import Config, Group
from ..indicators import atr, ema
from ..market import Candles, Market, tf_name
from ..state import State

log = logging.getLogger(__name__)

ZONE_TEXT = {
    "above": "arriba de la nube",
    "near_above": "apenas arriba de la nube",
    "inside": "DENTRO de la nube",
    "near_below": "apenas debajo de la nube",
    "below": "debajo de la nube",
}


def classify(price: float, e100: float, e200: float, atr_v: float, near_atr: float, prev: str | None = None) -> str:
    top, bot = max(e100, e200), min(e100, e200)
    if bot <= price <= top:
        return "inside"
    above = price > top
    dist = price - top if above else bot - price
    near = near_atr * atr_v
    # Histéresis: para dejar de estar "cerca" tiene que alejarse un 50% más.
    if prev == ("near_above" if above else "near_below"):
        near *= 1.5
    if dist <= near:
        return "near_above" if above else "near_below"
    return "above" if above else "below"


def cloud_bounds(e100: float, e200: float) -> tuple[float, float]:
    return max(e100, e200), min(e100, e200)


def oscillation(c: Candles, e100: list, e200: list, lookback: int) -> tuple[int, int, int]:
    """Sobre las últimas ``lookback`` velas cerradas: (velas que tocaron la nube,
    cierres dentro, cambios de lado de la nube)."""
    touched = inside = flips = 0
    last_side = None
    n = len(c)
    for i in range(max(0, n - 1 - lookback), n - 1):
        if e100[i] is None or e200[i] is None:
            continue
        top, bot = cloud_bounds(e100[i], e200[i])
        if c.low[i] <= top and c.high[i] >= bot:
            touched += 1
        side = "in" if bot <= c.close[i] <= top else ("up" if c.close[i] > top else "down")
        inside += side == "in"
        if last_side is not None and side != last_side:
            flips += 1
        last_side = side
    return touched, inside, flips


class EmaDetector:
    def __init__(self, cfg: Config, market: Market, state: State):
        self.cfg = cfg
        self.market = market
        self.state = state
        self.p = cfg.emas

    def reminder_seconds(self, tf: str) -> float:
        rh = self.p["reminder_hours"]
        hours = rh.get(tf, rh.get("default", 6)) if isinstance(rh, dict) else rh
        return float(hours) * 3600

    async def check(self) -> list[str]:
        out = []
        for g in self.cfg.groups:
            if not g.ema_timeframes:
                continue
            for asset in g.assets:
                events: list[str] = []
                price = None
                for tf in g.ema_timeframes:
                    try:
                        c = await self.market.candles(asset, tf, max_age=float(self.p["refresh_seconds"]))
                    except Exception as e:  # noqa: BLE001
                        log.warning("EMAs %s %s: %s", asset, tf, e)
                        continue
                    price = c.price
                    events += self.evaluate(asset, tf, c, g, now=time.time())
                if events:
                    out.append(f"📈 <b>{asset}</b> — EMAs · precio {fmt.price(price)}\n" + "\n".join(events))
        return out

    def evaluate(self, asset: str, tf: str, c: Candles, g: Group, now: float) -> list[str]:
        closes = c.close
        e = {n: ema(closes, n) for n in (21, 34, 100, 200)}
        a = atr(c.high, c.low, c.close, 14)
        events: list[str] = []
        label = f"[{tf_name(tf)}]"

        # ── Velas cerradas nuevas (para cruces) ──────────────────────────────
        ckey = f"closed:{asset}:{tf}"
        last_closed = self.state.get(ckey)
        new_close = len(c) >= 3 and last_closed is not None and c.ts[-2] != last_closed
        if len(c) >= 2:
            self.state.set(ckey, c.ts[-2])

        if g.ema_touch:
            events += self._touches(asset, tf, label, c, e)
        if g.ema_cloud:
            events += self._cloud(asset, tf, label, c, e, a, now)
            if new_close:
                events += self._cross(label, e[100], e[200], "EMA 100", "EMA 200", "la nube se vuelve alcista", "la nube se vuelve bajista")
        if g.ema_cross and new_close:
            events += self._cross(label, e[21], e[34], "EMA 21", "EMA 34", "cruce alcista", "cruce bajista")
        return events

    # ── Toques de la EMA 100 / 200 ───────────────────────────────────────────
    def _touches(self, asset: str, tf: str, label: str, c: Candles, e: dict) -> list[str]:
        out = []
        cooldown = int(self.p["touch_cooldown_candles"])
        for n in (100, 200):
            v = e[n][-1]
            if v is None or not (c.low[-1] <= v <= c.high[-1]):
                continue
            key = f"touch:{asset}:{tf}:{n}"
            last = self.state.get(key)
            if last is not None and last in c.ts[-(cooldown + 1):]:
                continue
            self.state.set(key, c.ts[-1])
            prev_close = c.close[-2] if len(c) >= 2 else c.open[-1]
            side = "desde arriba (testeando soporte)" if prev_close >= v else "desde abajo (testeando resistencia)"
            out.append(f"🎯 {label} tocó la <b>EMA {n}</b> ({fmt.price(v)}) {side}")
        return out

    # ── Nube EMA100–EMA200 ───────────────────────────────────────────────────
    def _cloud(self, asset: str, tf: str, label: str, c: Candles, e: dict, a: list, now: float) -> list[str]:
        e100, e200, atr_v = e[100][-1], e[200][-1], a[-1]
        if e100 is None or e200 is None or atr_v is None:
            return []
        key = f"cloud:{asset}:{tf}"
        st = dict(self.state.get(key) or {})
        zone = classify(c.price, e100, e200, atr_v, float(self.p["near_atr"]), st.get("zone"))
        top, bot = cloud_bounds(e100, e200)
        out: list[str] = []

        if "zone" not in st:  # primera vez: memorizar sin avisar
            st.update(zone=zone, since=now, last_msg=now)
            self.state.set(key, st)
            return []

        if zone != st["zone"]:
            pend = st.get("pending")
            if not pend or pend["zone"] != zone:
                st["pending"] = {"zone": zone, "since": now}
            elif now - pend["since"] >= float(self.p["confirm_seconds"]):
                out.append(self._transition_text(label, st["zone"], zone, c.price, top, bot, e100 > e200))
                st.update(zone=zone, since=now, last_msg=now)
                st.pop("pending", None)
        else:
            st.pop("pending", None)
            if zone in ("inside", "near_above", "near_below") and now - st.get("last_msg", 0) >= self.reminder_seconds(tf):
                touched, inside, flips = oscillation(c, e[100], e[200], int(self.p["oscillation_lookback"]))
                hours = (now - st.get("since", now)) / 3600
                out.append(
                    f"🔁 {label} sigue <b>{ZONE_TEXT[zone]}</b> hace {hours:.0f} h "
                    f"({fmt.price(bot)} – {fmt.price(top)}). "
                    f"Últimas {self.p['oscillation_lookback']} velas: {touched} tocaron la nube, "
                    f"{inside} cerraron adentro, {flips} cambios de lado"
                )
                st["last_msg"] = now
        self.state.set(key, st)
        return out

    @staticmethod
    def _transition_text(label: str, old: str, new: str, price: float, top: float, bot: float, bullish: bool) -> str:
        kind = "alcista (EMA100 > EMA200)" if bullish else "bajista (EMA100 < EMA200)"
        rng = f"nube {fmt.price(bot)} – {fmt.price(top)}, {kind}"
        if new == "inside":
            icon, txt = "☁️", "entró a la nube"
        elif old == "inside":
            icon = "⬆️" if new.endswith("above") else "⬇️"
            txt = "salió de la nube por " + ("arriba" if new.endswith("above") else "abajo")
            if new.startswith("near"):
                txt += ", todavía cerca"
        elif new.startswith("near"):
            icon, txt = "👀", "se acerca a la nube desde " + ("arriba" if new == "near_above" else "abajo")
        elif (old, new) in (("near_below", "above"), ("below", "above"), ("below", "near_above")):
            icon, txt = "⬆️", "cruzó la nube hacia arriba"
        elif (old, new) in (("near_above", "below"), ("above", "below"), ("above", "near_below")):
            icon, txt = "⬇️", "cruzó la nube hacia abajo"
        else:
            icon, txt = "↔️", "se alejó de la nube por " + ("arriba" if new == "above" else "abajo")
        edge = top if price > top else bot
        dist = (price - edge) / edge * 100 if new != "inside" else None
        tail = f" ({fmt.pct(dist)} del borde)" if dist is not None else ""
        return f"{icon} {label} {txt}{tail} · {rng}"

    # ── Cruces (velas cerradas) ──────────────────────────────────────────────
    @staticmethod
    def _cross(label: str, fast: list, slow: list, fname: str, sname: str, up_txt: str, down_txt: str) -> list[str]:
        if len(fast) < 3 or None in (fast[-2], slow[-2], fast[-3], slow[-3]):
            return []
        d_prev, d_now = fast[-3] - slow[-3], fast[-2] - slow[-2]
        if d_prev <= 0 < d_now:
            return [f"✅ {label} <b>{fname} cruzó ARRIBA de la {sname}</b> — {up_txt} (vela cerrada)"]
        if d_prev >= 0 > d_now:
            return [f"❌ {label} <b>{fname} cruzó ABAJO de la {sname}</b> — {down_txt} (vela cerrada)"]
        return []
