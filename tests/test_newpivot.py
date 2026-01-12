import pytest


def test_breakout_and_entry_logic(strategy):
    """
    Test that an entry is triggered when LTP crosses the stop level.
    """
    # 1. Setup Initial State
    strategy._last_price = 99.0
    strategy._prev_price = 98.0
    strategy._fn = "is_breakout"

    # Mock Buckets to allow trade
    strategy._small_bucket.can_allow.return_value = True
    strategy._big_bucket.can_allow.return_value = True

    # 2. Simulate Price Tick: LTP jumps to 102 (Crosses Stop of 100)
    # Price + 2 is used in your code for entry
    strategy.trade_mgr.complete_entry.return_value = "ORDER_ID_123"

    ltps = {strategy._symbol: 102.0}
    strategy.run(orders=[], ltps=ltps)

    # 3. Assertions
    # Verify TradeManager was called with expected price (LTP + 2)
    strategy.trade_mgr.complete_entry.assert_called_with(quantity=15, price=104.0)

    # Verify state transitioned to exit placement
    assert strategy._fn == "place_exit_order"


def test_no_entry_if_bucket_full(strategy):
    """
    Test that if the time bucket is full, no trade is placed even if price breakouts.
    """
    strategy._last_price = 99.0
    strategy._small_bucket.can_allow.return_value = False  # Bucket Full!

    ltps = {strategy._symbol: 102.0}
    strategy.run(orders=[], ltps=ltps)

    strategy.trade_mgr.complete_entry.assert_not_called()
    assert strategy._fn == "is_breakout"


def test_skip_if_already_above_target(strategy):
    """
    If the stock opens or jumps beyond target, we should not trade.
    """
    # Level is (100, 110). If LTP is 115, it should skip.
    strategy._last_price = 115.0

    strategy.is_breakout()

    strategy.trade_mgr.complete_entry.assert_not_called()
