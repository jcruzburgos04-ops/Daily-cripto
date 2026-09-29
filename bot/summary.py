"""Resumen al cierre diario (y semanal / mensual cuando corresponde) + /estado."""
from __future__ import annotations

import logging
import time

from . import fmt
from .config import Config
from .detectors.ash import compute_ash
from .detectors.emas import ZONE_TEXT, classify
from .indicators import atr, ema
from .market import Market, tf_name

log = logging.getLogger(__name__)

SHORT_TF = {"1d": "D", "1w": "S", "1M": "M"}


async def asset_block(cfg: Config, market: Market, asset: str, closing: bool, detailed: bool) -> str:
    """``closing``: usa la última vela cerrada (resumen de cierre). Si no, la vela en curso (/estado)."""
    s = cfg.summary
    now_ms = time.time() * 1000
    try:
        d = await market.candles(asset, "1d", max_age=60)
    except Exception as e:  # noqa: BLE001
        return f"<b>{asset}</b>: sin datos ({fmt.esc(str(e))})"
    i = -2 if closing else -1
    chg = (d.close[i] / d.close[i - 1] - 1) * 100 if len(d) >= 3 else 0.0
    head = f"<b>{asset}</b> {fmt.price(d.close[i])} ({fmt.pct(chg)} {'el día' if closing else 'hoy'})"

    ema_parts = []
    for tf in s["ema_timeframes"]:
        try:
            c = await market.candles(asset, tf, max_age=60)
        except Exception:  # noqa: BLE001
            continue
        e21, e34, e100, e200 = (ema(c.close, n)[i] for n in (21, 34, 100, 200))
        a = atr(c.high, c.low, c.close, 14)[i]
        px = c.close[i]
        bits = []
        if e100 is not None and e200 is not None and a is not None:
            zone = classify(px, e100, e200, a, float(cfg.emas["near_atr"]))
            top, bot = max(e100, e200), min(e100, e200)
            if zone == "inside":
                bits.append("☁️ dentro de la nube")
            else:
                edge = top if px > top else bot
                arrow = "⬆️" if px > top else "⬇️"
                bits.append(f"{arrow} {ZONE_TEXT[zone]} ({fmt.pct((px - edge) / edge * 100)})")
        elif e100 is not None:
            bits.append(("⬆️ sobre" if px > e100 else "⬇️ bajo") + " EMA100")
        if e21 is not None and e34 is not None:
            bits.append("21>34 ✅" if e21 > e34 else "21<34 ❌")
        if bits:
            ema_parts.append(f"{tf_name(tf)}: " + ", ".join(bits))

    ash_parts = []
    for tf in s["ash_timeframes"]:
        try:
            c = await market.candles(asset, tf, max_age=60)
        except Exception:  # noqa: BLE001
            continue
        # Semanal/mensual: si la vela acaba de cerrar (cierre de semana/mes), mostramos la cerrada.
        just_closed = closing and (tf == "1d" or now_ms - c.ts[-1] < 86400 * 1000)
        idx = -2 if just_closed else -1
        st = compute_ash(cfg, c, idx)
        if st is None:
            continue
        txt = f"{tf_name(tf)} {st.emoji}{st.arrow}"
        if detailed:
            txt += f" {fmt.pct(st.separation_pct, signed=False)}"
        if just_closed and tf != "1d":
            prev = compute_ash(cfg, c, idx - 1)
            changed = prev is not None and prev.bullish != st.bullish
            txt += " <b>(CERRÓ, cambió)</b>" if changed else " (cerró)"
        ash_parts.append(txt)

    lines = [head]
    if detailed:
        lines += [f"   EMAs {p}" for p in ema_parts]
        if ash_parts:
            lines.append("   ASH " + " · ".join(ash_parts))
    else:
        tail = []
        if ash_parts:
            tail.append("ASH " + " ".join(ash_parts))
        tail += ema_parts
        lines.append("   " + "\n   ".join(tail))
    return "\n".join(lines)


def title_for_close(ts: float) -> str:
    t = time.gmtime(ts)
    parts = ["Cierre diario"]
    if t.tm_wday == 0:
        parts.append("semanal")
    if t.tm_mday == 1:
        parts.append("mensual")
    return " + ".join(parts) if len(parts) > 1 else parts[0]


async def build(cfg: Config, market: Market, closing: bool, only: list[str] | None = None) -> str:
    now = time.time()
    tz = cfg.general["timezone"]
    title = f"🌙 <b>{title_for_close(now)}</b>" if closing else "📋 <b>Estado actual</b>"
    out = [f"{title} — {fmt.local_time(now, tz)}"]
    for g in cfg.groups:
        assets = [a for a in g.assets if not only or a in only]
        if not assets:
            continue
        detailed = g.moves or g.ema_cloud  # los principales van con más detalle
        out.append(f"\n━━ <b>{g.name.upper()}</b> ━━")
        for a in assets:
            out.append(await asset_block(cfg, market, a, closing, detailed))
    legend = "ASH: 🟢 alcista fuerte · 🟩 alcista debilitándose · 🔴 bajista fuerte · 🟠 bajista debilitándose"
    out.append(f"\n<i>{legend}</i>")
    return "\n".join(out)
