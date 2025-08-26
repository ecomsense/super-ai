# src/tests/test_one_trade.py

import pytest
from src.one_trade import OneTrade


@pytest.fixture(autouse=True)
def reset_state():
    """
    Ensures each test starts with a clean slate.
    """
    OneTrade._state = {"traded_once": []}
    yield
    OneTrade._state = {"traded_once": []}


def test_add_first_trade():
    OneTrade.add("NIFTY", "24JUN25CE26000")

    state = OneTrade.get_state()
    assert "24JUN25CE26000" in state["traded_once"]
    assert "24JUN25CE26000" in state["NIFTY"]
    assert OneTrade.is_traded_once("24JUN25CE26000")
    assert OneTrade.is_prefix_in_trade("NIFTY")


def test_add_duplicate_trade():
    OneTrade.add("NIFTY", "24JUN25CE26000")
    OneTrade.add("NIFTY", "24JUN25CE26000")  # duplicate

    state = OneTrade.get_state()
    # Still only one occurrence
    assert state["NIFTY"].count("24JUN25CE26000") == 1
    assert state["traded_once"].count("24JUN25CE26000") == 1


def test_add_multiple_trades_same_prefix():
    OneTrade.add("NIFTY", "24JUN25CE26000")
    OneTrade.add("NIFTY", "24JUN25PE25000")

    state = OneTrade.get_state()
    assert "24JUN25CE26000" in state["NIFTY"]
    assert "24JUN25PE25000" in state["NIFTY"]
    assert OneTrade.is_prefix_in_trade("NIFTY")


def test_add_trades_different_prefixes():
    OneTrade.add("NIFTY", "24JUN25CE26000")
    OneTrade.add("SENSEX", "24JUN25PE75000")

    state = OneTrade.get_state()
    assert "24JUN25CE26000" in state["NIFTY"]
    assert "24JUN25PE75000" in state["SENSEX"]
    assert OneTrade.is_prefix_in_trade("NIFTY")
    assert OneTrade.is_prefix_in_trade("SENSEX")


def test_remove_trade():
    OneTrade.add("NIFTY", "24JUN25PE25000")
    OneTrade.remove("NIFTY", "24JUN25PE25000")

    state = OneTrade.get_state()
    assert "24JUN25PE25000" not in state["NIFTY"]
    assert not OneTrade.is_prefix_in_trade("NIFTY")
    # but it should remain in traded_once history
    assert OneTrade.is_traded_once("24JUN25PE25000")


def test_remove_non_existent_trade():
    OneTrade.add("NIFTY", "24JUN25CE26000")
    OneTrade.remove("NIFTY", "24JUN25PE25000")  # does not exist

    state = OneTrade.get_state()
    # CE still exists, PE was never added
    assert "24JUN25CE26000" in state["NIFTY"]
    assert "24JUN25PE25000" not in state["NIFTY"]
