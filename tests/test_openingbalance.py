from src.strategies.openingbalance import BreakoutState, Openingbalance
from tests.factory_settings import Factory


def test_ob_initialization(strategy_factory):
    strat = strategy_factory(Openingbalance, Factory.settings("openingbalance"))

    assert strat._stop == 100.0  # From mock_rest.history
    assert strat._fn == "wait_for_breakout"
