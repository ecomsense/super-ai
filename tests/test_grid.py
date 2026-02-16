from src.providers.grid import Gridlines


def test_beg_with_zero():
    prices = [0, 100, 200, 200]
    gl = Gridlines(prices=prices, reverse=False)
    curr, lowest, highest = gl.find_current_grid(24)
    assert curr == 0, "index not zero"
    assert lowest == 0, "low is not zero"
    assert highest == 100, "high is not 100"
