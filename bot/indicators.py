"""Indicadores replicando la matemática de TradingView / Pine Script.

Todas las funciones reciben listas (la más vieja primero) y devuelven listas del
mismo largo, con ``None`` donde Pine devolvería ``na``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

Series = list[Optional[float]]


def _window_ok(values: Sequence[Optional[float]], i: int, n: int) -> bool:
    if i < n - 1:
        return False
    return all(v is not None for v in values[i - n + 1 : i + 1])


def sma(values: Sequence[Optional[float]], n: int) -> Series:
    """ta.sma"""
    out: Series = [None] * len(values)
    for i in range(len(values)):
        if _window_ok(values, i, n):
            out[i] = sum(values[i - n + 1 : i + 1]) / n  # type: ignore[arg-type]
    return out


def wma(values: Sequence[Optional[float]], n: int) -> Series:
    """ta.wma: pesos 1..n, el más reciente pesa n."""
    out: Series = [None] * len(values)
    denom = n * (n + 1) / 2
    for i in range(len(values)):
        if _window_ok(values, i, n):
            w = values[i - n + 1 : i + 1]
            out[i] = sum((k + 1) * w[k] for k in range(n)) / denom  # type: ignore[operator]
    return out


def _smoothed(values: Sequence[Optional[float]], n: int, alpha: float) -> Series:
    """Base común de ta.ema y ta.rma: arranca con la SMA de las primeras n velas."""
    out: Series = [None] * len(values)
    prev: Optional[float] = None
    for i, v in enumerate(values):
        if prev is None:
            if _window_ok(values, i, n):
                prev = sum(values[i - n + 1 : i + 1]) / n  # type: ignore[arg-type]
        elif v is not None:
            prev = alpha * v + (1 - alpha) * prev
        out[i] = prev
    return out


def ema(values: Sequence[Optional[float]], n: int) -> Series:
    """ta.ema (alpha = 2 / (n + 1), semilla = SMA)."""
    return _smoothed(values, n, 2 / (n + 1))


def rma(values: Sequence[Optional[float]], n: int) -> Series:
    """ta.rma (alpha = 1 / n, semilla = SMA)."""
    return _smoothed(values, n, 1 / n)


def atr(high: Sequence[float], low: Sequence[float], close: Sequence[float], n: int = 14) -> Series:
    """ta.atr = rma(true range, n)."""
    tr: list[Optional[float]] = []
    for i in range(len(close)):
        if i == 0:
            tr.append(high[i] - low[i])
        else:
            tr.append(max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])))
    return rma(tr, n)


def moving_average(kind: str, values: Sequence[Optional[float]], n: int) -> Series:
    kind = kind.upper()
    if kind == "WMA":
        return wma(values, n)
    if kind == "EMA":
        return ema(values, n)
    if kind == "SMA":
        return sma(values, n)
    if kind in ("SMMA", "RMA"):
        return rma(values, n)
    raise ValueError(f"Tipo de media no soportado para el ASH: {kind}")


def ash(close: Sequence[float], length: int = 16, smooth: int = 4, ma_type: str = "EMA") -> tuple[Series, Series]:
    """Absolute Strength Histogram v2 (jh), modo RSI (el predeterminado).

    Bulls0 = 0.5 * (|Δ| + Δ)   Bears0 = 0.5 * (|Δ| - Δ)   con Δ = close - close[1]
    SmthBulls = MA(MA(Bulls0, length), smooth)   (idem Bears)
    """
    bulls: Series = [None]
    bears: Series = [None]
    for i in range(1, len(close)):
        d = close[i] - close[i - 1]
        bulls.append(0.5 * (abs(d) + d))
        bears.append(0.5 * (abs(d) - d))
    avg_bulls = moving_average(ma_type, bulls, length)
    avg_bears = moving_average(ma_type, bears, length)
    return moving_average(ma_type, avg_bulls, smooth), moving_average(ma_type, avg_bears, smooth)


# Colores del ASH tal como los pinta el indicador (bull_trend_color / bear_trend_color).
ASH_COLORS = {
    "green": ("🟢", "alcista y ganando fuerza"),
    "lime": ("🟩", "alcista pero perdiendo fuerza"),
    "red": ("🔴", "bajista y ganando fuerza"),
    "orange": ("🟠", "bajista pero perdiendo fuerza"),
}


@dataclass(frozen=True)
class AshState:
    bullish: bool
    color: str  # green | lime | red | orange
    bulls: float
    bears: float

    @property
    def separation(self) -> float:
        return abs(self.bulls - self.bears)

    @property
    def separation_pct(self) -> float:
        total = self.bulls + self.bears
        return self.separation / total * 100 if total > 0 else 0.0

    @property
    def arrow(self) -> str:
        return "▲" if self.bullish else "▼"

    @property
    def emoji(self) -> str:
        return ASH_COLORS[self.color][0]

    @property
    def description(self) -> str:
        return ASH_COLORS[self.color][1]


def ash_state(bulls: Series, bears: Series, idx: int = -1) -> Optional[AshState]:
    """Estado del ASH en la vela ``idx``, con la misma lógica que el cuadro MTF."""
    n = len(bulls)
    i = idx if idx >= 0 else n + idx
    if i < 1 or i >= n:
        return None
    b, s, b1, s1 = bulls[i], bears[i], bulls[i - 1], bears[i - 1]
    if b is None or s is None:
        return None
    bullish = b - s >= 0
    if bullish:
        color = "lime" if (b1 is not None and b < b1) else "green"
    else:
        color = "orange" if (s1 is not None and s < s1) else "red"
    return AshState(bullish, color, b, s)
