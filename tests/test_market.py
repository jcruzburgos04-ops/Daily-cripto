import asyncio
import time

from bot.market import Market


class FakeExchange:
    id = "fake"

    def __init__(self, n, step):
        now = int(time.time() * 1000) // step * step
        self.rows = [[now - (n - 1 - i) * step, 1, 2, 0.5, float(i), 1] for i in range(n)]
        self.calls = []
        self.markets = {"BTC/USDT": {}}

    async def fetch_ohlcv(self, symbol, tf, since=None, limit=None):
        self.calls.append((since, limit))
        rows = [r for r in self.rows if since is None or r[0] >= since]
        return rows[:limit] if since is not None else rows[-limit:]


def make_market(ex):
    m = Market(["fake"], history=1000)
    m.exchanges["fake"] = ex
    return m


def test_paginates_when_more_than_1000_candles_are_needed():
    step = 4 * 3600_000
    ex = FakeExchange(6000, step)
    m = make_market(ex)
    c = asyncio.run(m.candles("BTC", "4h", min_candles=4800))
    assert len(c) == 4800
    assert c.ts == sorted(set(c.ts)) and c.close[-1] == 5999.0
    assert len(ex.calls) >= 5


def test_incremental_update_merges_new_candles():
    step = 4 * 3600_000
    ex = FakeExchange(3000, step)
    m = make_market(ex)
    asyncio.run(m.candles("BTC", "4h", min_candles=2400))
    ex.rows[-1][4] = 12345.0                                     # la vela en curso cambia
    ex.rows.append([ex.rows[-1][0] + step, 1, 2, 0.5, 777.0, 1])  # y abre una nueva
    ex.calls.clear()
    c = asyncio.run(m.candles("BTC", "4h", min_candles=2400))
    assert ex.calls == [(None, 10)]                              # sólo pidió las últimas
    assert c.close[-2:] == [12345.0, 777.0] and len(c) == 2400


def test_young_coin_with_short_history_is_not_refetched_forever():
    ex = FakeExchange(300, 86400_000)
    m = make_market(ex)
    asyncio.run(m.candles("BTC", "1d", min_candles=800))
    ex.calls.clear()
    asyncio.run(m.candles("BTC", "1d", min_candles=800))
    assert ex.calls == [(None, 10)]
