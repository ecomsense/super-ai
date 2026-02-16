import pytest

from src.strategies.openingbalance import BreakoutState, Openingbalance


def test_ob_initialization(strategy_factory):
    ob_settings = {
        "strategy": "ob_test",
        "txn": 20,
        "t1": 10,
        "rest_time": {"minutes": 1},
    }

    strat = strategy_factory(Openingbalance, ob_settings)

    assert strat._stop == 100.0  # From mock_rest.history
    assert strat._fn == "wait_for_breakout"
