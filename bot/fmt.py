"""Formato de números y fechas para los mensajes."""
from __future__ import annotations

import html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def price(p: float | None) -> str:
    if p is None:
        return "—"
    if p >= 1000:
        s = f"{p:,.0f}"
    elif p >= 100:
        s = f"{p:,.2f}"
    elif p >= 1:
        s = f"{p:.3f}"
    elif p >= 0.01:
        s = f"{p:.4f}"
    else:
        s = f"{p:.8f}"
    # Formato rioplatense: 64.230,50
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def pct(x: float, signed: bool = True) -> str:
    s = f"{x:+.2f}" if signed else f"{x:.2f}"
    return s.replace(".", ",") + "%"


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def local_time(ts: float | datetime, tz: str) -> str:
    dt = ts if isinstance(ts, datetime) else datetime.fromtimestamp(ts, timezone.utc)
    return dt.astimezone(ZoneInfo(tz)).strftime("%d/%m %H:%M")
