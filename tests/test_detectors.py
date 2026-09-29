from bot.detectors.ash import AshDetector
from bot.detectors.emas import EmaDetector, classify
from bot.detectors.moves import MoveDetector
from helpers import candles_from_closes, make_cfg, mem_state


class NoMarket:
    pass


def test_move_levels_and_rearm():
    cfg = make_cfg()
    d = MoveDetector(cfg, NoMarket(), mem_state())
    flat = [100.0] * 60
    assert d.evaluate("BTC", flat, flat, 100.0, 1.0) is None

    lows = [100.0] * 60
    highs = [100.0] * 59 + [101.2]
    msg = d.evaluate("BTC", highs, lows, 101.2, 1.0)
    assert "≤5 min" in msg and "+1,20%" in msg
    # mismo movimiento: no repite
    assert d.evaluate("BTC", highs, lows, 101.2, 1.0) is None
    # sigue subiendo hasta +2,1%: avisa nivel x2
    msg = d.evaluate("BTC", [100.0] * 59 + [102.1], lows, 102.1, 1.0)
    assert "x2" in msg
    # se desinfla (+0,3%) → se re-arma y vuelve a avisar al pasar 1%
    d.evaluate("BTC", [100.0] * 59 + [100.3], lows, 100.3, 1.0)
    assert d.evaluate("BTC", [100.0] * 59 + [101.1], lows, 101.1, 1.0) is not None


def test_move_scaled_threshold_for_eth():
    cfg = make_cfg()
    d = MoveDetector(cfg, NoMarket(), mem_state())
    lows = [100.0] * 60
    # +1,2% no alcanza si el umbral de ETH es 1,5%
    assert d.evaluate("ETH", [100.0] * 59 + [101.2], lows, 101.2, 1.5) is None
    msg = d.evaluate("ETH", [100.0] * 59 + [101.6], lows, 101.6, 1.5)
    assert "ajustados ×1.50" in msg


def test_move_drop():
    d = MoveDetector(make_cfg(), NoMarket(), mem_state())
    highs = [100.0] * 60
    msg = d.evaluate("BTC", highs, [100.0] * 59 + [96.5], 96.5, 1.0)
    assert "cae -3,50%" in msg and "≤30 min" in msg and "≤5 min" in msg and "x3" in msg


def test_classify_zones():
    assert classify(105, 100, 110, 2, 0.5) == "inside"
    assert classify(110.5, 100, 110, 2, 0.5) == "near_above"
    assert classify(115, 100, 110, 2, 0.5) == "above"
    assert classify(99.2, 100, 110, 2, 0.5) == "near_below"
    # histéresis: a 1,4 del borde sigue "cerca" si ya lo estaba
    assert classify(111.4, 100, 110, 2, 0.5, prev="near_above") == "near_above"
    assert classify(111.4, 100, 110, 2, 0.5) == "above"


def _uptrend_then(closes_after):
    base = [100 + i * 0.5 for i in range(300)]
    return base + closes_after


def test_cloud_touch_and_entry():
    cfg = make_cfg()
    st = mem_state()
    det = EmaDetector(cfg, NoMarket(), st)
    g = cfg.groups[0]
    closes = _uptrend_then([])
    c = candles_from_closes(closes, step=4 * 3600_000)
    assert det.evaluate("BTC", "4h", c, g, now=0) == []   # primera pasada: memoriza
    # caída fuerte hasta dentro de la nube
    c2 = candles_from_closes(closes + [210.0], step=4 * 3600_000)
    ev = det.evaluate("BTC", "4h", c2, g, now=10)
    assert any("EMA 100" in e for e in ev)                 # la vela atravesó la EMA 100
    assert not any("entró" in e for e in ev)               # todavía sin confirmar
    ev = det.evaluate("BTC", "4h", c2, g, now=100)
    assert any("entró a la nube" in e for e in ev)
    # recordatorio pasado el tiempo configurado
    ev = det.evaluate("BTC", "4h", c2, g, now=100 + 7 * 3600)
    assert any("sigue" in e and "DENTRO" in e for e in ev)


def test_ema_21_34_cross_on_closed_candle():
    cfg = make_cfg()
    st = mem_state()
    det = EmaDetector(cfg, NoMarket(), st)
    g = cfg.groups[1]
    closes = [200 - i * 0.5 for i in range(100)]   # bajista: 21 < 34
    c = candles_from_closes(closes + [150], step=3600_000)
    det.evaluate("UNI", "4h", c, g, now=0)
    ev = []
    for k in range(1, 40):
        closes.append(closes[-1] + 3)                 # rebote fuerte
        ev += det.evaluate("UNI", "4h", candles_from_closes(closes + [closes[-1]], step=3600_000), g, now=k)
    crosses = [e for e in ev if "EMA 21 cruzó ARRIBA" in e]
    assert len(crosses) == 1


def test_ash_flip_needs_confirmation():
    cfg = make_cfg()
    st = mem_state()
    det = AshDetector(cfg, NoMarket(), st)
    down = [200 - 2 * i for i in range(30)]
    assert det.evaluate("BTC", "1w", candles_from_closes(down), True, now=0) is None
    up = down + [down[-1] + 30]
    c = candles_from_closes(up)
    assert det.evaluate("BTC", "1w", c, True, now=10) is None          # pendiente
    assert det.evaluate("BTC", "1w", c, True, now=60) is None          # < 15 min
    msg = det.evaluate("BTC", "1w", c, True, now=10 + 15 * 60)
    assert "ALCISTA" in msg and "SEMANAL" in msg
    assert det.evaluate("BTC", "1w", c, True, now=10 + 30 * 60) is None


def test_ash_flip_that_reverts_is_not_sent():
    cfg = make_cfg()
    det = AshDetector(cfg, NoMarket(), mem_state())
    down = [200 - 2 * i for i in range(30)]
    det.evaluate("BTC", "1w", candles_from_closes(down), False, now=0)
    det.evaluate("BTC", "1w", candles_from_closes(down + [down[-1] + 30]), False, now=10)
    det.evaluate("BTC", "1w", candles_from_closes(down + [down[-1] - 5]), False, now=300)
    assert det.evaluate("BTC", "1w", candles_from_closes(down + [down[-1] - 5]), False, now=2000) is None
