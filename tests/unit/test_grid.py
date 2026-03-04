from src.providers.grid import Gridlines, StopAndTarget


def test_beg_with_zero():
    prices = [0, 100, 200, 200]
    gl = Gridlines(prices=prices, reverse=False)
    curr, lowest, highest = gl.find_current_grid(24)
    assert curr == 0, "index not zero"
    assert lowest == 0, "low is not zero"
    assert highest == 100, "high is not 100"

def test_stop_and_target():
    prices = [(0, 100), (100, 200), (200,300), (300, 300)]
    gl = StopAndTarget(prices)
    curr, lowest, highest = gl.find_current_grid(101)
    assert curr == 1, "index is not one"
    assert lowest == 100, "low is not 100"
    assert highest == 200, "high is not 200"

