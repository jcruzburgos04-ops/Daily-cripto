from bot.config import Config, DEFAULTS, GROUP_DEFAULTS, Group, _merge
from bot.market import Candles
from bot.state import State


def make_cfg(**overrides) -> Config:
    raw = _merge(DEFAULTS, overrides)
    g1 = Group(**{**GROUP_DEFAULTS, "name": "principales", "assets": ["BTC", "ETH"], "moves": True,
                  "ema_timeframes": ["1d"], "ema_cloud": True, "ash_timeframes": ["1w"], "ash_color_changes": True})
    g2 = Group(**{**GROUP_DEFAULTS, "name": "alts", "assets": ["UNI"], "ema_timeframes": ["1d"],
                  "ema_cross": True, "ash_timeframes": ["1w"]})
    return Config(raw=raw, groups=[g1, g2])


def candles_from_closes(closes, start=0, step=60_000, wick=0.0):
    rows = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        rows.append([start + i * step, o, max(o, c) * (1 + wick), min(o, c) * (1 - wick), c, 1.0])
        prev = c
    return Candles.from_rows(rows)


def mem_state() -> State:
    return State(None)
