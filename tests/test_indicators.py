import math

from bot.indicators import ash, ash_state, atr, ema, rma, sma, wma


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-9)


def test_sma_wma():
    v = [1, 2, 3, 4, 5]
    assert sma(v, 3) == [None, None, 2, 3, 4]
    # wma(3) de [3,4,5] = (1*3 + 2*4 + 3*5) / 6
    assert close(wma(v, 3)[-1], 26 / 6)


def test_ema_seeded_with_sma_like_pine():
    v = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = ema(v, 3)
    assert out[:2] == [None, None]
    assert close(out[2], 2.0)             # semilla = SMA(1,2,3)
    assert close(out[3], 0.5 * 4 + 0.5 * 2.0)
    assert close(out[4], 0.5 * 5 + 0.5 * 3.0)


def test_rma_and_atr():
    assert close(rma([2.0, 4.0, 6.0], 2)[2], 0.5 * 6 + 0.5 * 3)
    h, l, c = [10, 12, 11], [9, 10, 9], [9.5, 11, 10]
    # TR = [1, max(2, 2.5, 0.5)=2.5, max(2, 1, 2)=2]
    a = atr(h, l, c, 2)
    assert close(a[1], 1.75) and close(a[2], 0.5 * 2 + 0.5 * 1.75)


def test_ash_direction_and_colors():
    up = [100 + i for i in range(30)]
    bulls, bears = ash(up)
    st = ash_state(bulls, bears)
    assert st.bullish and st.bears == 0 and st.separation_pct == 100

    # Sube fuerte y después se frena: sigue alcista pero perdiendo fuerza (lime)
    slowing = [100 + 5 * i for i in range(20)] + [200 + 0.1 * i for i in range(4)]
    st = ash_state(*ash(slowing))
    assert st.bullish and st.color == "lime"

    down = [200 - 2 * i for i in range(30)]
    st = ash_state(*ash(down))
    assert not st.bullish and st.color == "red"


def test_ash_needs_history():
    bulls, bears = ash([1.0, 2.0, 3.0])
    assert ash_state(bulls, bears) is None
