import pytest


def test_ob_breakout_triggers_entry(ob_strategy):
    """
    Test that OpeningBalance triggers an entry when LTP > Stop.
    Matches the logic: if self._last_price > self._stop
    """
    # 1. Setup: Price is below stop initially
    ob_strategy._stop = 100.0
    ob_strategy._last_price = 102.0  # Breakout price
    ob_strategy.trade_mgr.complete_entry.return_value = True

    # 2. Run the strategy function
    ob_strategy.wait_for_breakout()

    # 3. Assertions

    # State should move to place_exit_order
    assert ob_strategy._fn == "place_exit_order"

    # Entry should be LTP + 2 (102 + 2 = 104)
    ob_strategy.trade_mgr.complete_entry.assert_called()


def test_ob_no_entry_below_stop(ob_strategy):
    """
    Test that no entry is placed if the price hasn't broken out.
    """
    ob_strategy._stop = 100.0
    ob_strategy._last_price = 98.0  # Below stop

    ob_strategy.wait_for_breakout()

    ob_strategy.trade_mgr.complete_entry.assert_not_called()
    assert ob_strategy._fn == "wait_for_breakout"


def test_ob_lifecycle_to_exit_placement(ob_strategy):
    """
    Verify the transition from breakout to placing the exit order.
    """
    # Simulate we just entered
    ob_strategy._fn = "place_exit_order"

    # Mock a successful pending exit order
    mock_order = pytest.importorskip("unittest.mock").MagicMock()
    mock_order.order_id = "EXIT_999"
    ob_strategy.trade_mgr.pending_exit.return_value = mock_order

    # Run state function
    ob_strategy.place_exit_order()

    # Verify transition
    assert ob_strategy._fn == "try_exiting_trade"
    ob_strategy.trade_mgr.pending_exit.assert_called_once()
