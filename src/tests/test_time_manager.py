import pendulum
from freezegun import freeze_time
from src.time_manager import (
    TimeManager,
)  # Assuming your TimeManager class is in src/time_manager.py

# A pytest fixture to provide a clean TimeManager instance for each test
# This helps ensure tests are independent
import pytest


@pytest.fixture
def time_manager_one_minute():
    tm = TimeManager(rest_min=1)
    # Set the initial market open and close times for consistency across tests
    test_date_base = pendulum.datetime(2025, 6, 18, tz="Asia/Kolkata")
    tm.market_open = test_date_base.at(9, 0, 0)
    tm.market_close = test_date_base.at(9, 5, 0)
    tm.candle_times = tm._generate_candle_times()  # Regenerate after setting open/close
    return tm


def test_can_trade_when_no_last_trade_time(time_manager_one_minute):
    """
    Test case 1: No previous trade recorded.
    """
    tm = time_manager_one_minute
    tm.last_trade_time = None  # Ensure it's explicitly None
    assert tm.can_trade is True, "Should be able to trade when last_trade_time is None"


def test_can_trade_when_rest_period_not_elapsed(time_manager_one_minute):
    """
    Test case 4: Last trade occurred, but the rest period has NOT elapsed yet.
    """
    tm = time_manager_one_minute
    trade_time = pendulum.datetime(2025, 6, 18, 9, 0, 30, tz="Asia/Kolkata")
    tm.set_last_trade_time(trade_time)

    # Current time is within the same minute as the trade, or just before the next minute close
    time_to_test = pendulum.datetime(2025, 6, 18, 9, 0, 45, tz="Asia/Kolkata")
    with freeze_time(time_to_test):
        print(
            f"\nTest: Rest period NOT elapsed. Current time: {pendulum.now('Asia/Kolkata')}"
        )
        assert (
            tm.can_trade is False
        ), "Should NOT be able to trade if rest period has not elapsed"

    # Test at the exact boundary (should still be False due to strict >)
    time_to_test_exact_boundary = pendulum.datetime(
        2025, 6, 18, 9, 1, 0, tz="Asia/Kolkata"
    )
    with freeze_time(time_to_test_exact_boundary):
        print(
            f"Test: Rest period at boundary. Current time: {pendulum.now('Asia/Kolkata')}"
        )
        assert (
            tm.can_trade is False
        ), "Should NOT be able to trade exactly at the minute close"


def test_can_trade_when_rest_period_has_elapsed(time_manager_one_minute):
    """
    Test case 3: Last trade occurred, and the rest period HAS elapsed.
    """
    tm = time_manager_one_minute
    trade_time = pendulum.datetime(2025, 6, 18, 9, 0, 30, tz="Asia/Kolkata")
    tm.set_last_trade_time(trade_time)

    # Current time is after the next minute close
    time_to_test = pendulum.datetime(2025, 6, 18, 9, 1, 1, tz="Asia/Kolkata")
    with freeze_time(time_to_test):
        print(
            f"\nTest: Rest period HAS elapsed. Current time: {pendulum.now('Asia/Kolkata')}"
        )
        assert (
            tm.can_trade is True
        ), "Should be able to trade if rest period has elapsed"


def test_can_trade_edge_case_trade_near_market_open(time_manager_one_minute):
    """
    Test an edge case where the trade happens very close to market open.
    """
    tm = time_manager_one_minute
    trade_time = pendulum.datetime(
        2025, 6, 18, 9, 0, 0, tz="Asia/Kolkata"
    )  # Trade exactly at market open
    tm.set_last_trade_time(trade_time)

    # Should not trade at 9:00:59
    with freeze_time(pendulum.datetime(2025, 6, 18, 9, 0, 59, tz="Asia/Kolkata")):
        assert not tm.can_trade, "Should not trade before 9:01:00 if trade at 9:00:00"

    # Should trade at 9:01:01
    with freeze_time(pendulum.datetime(2025, 6, 18, 9, 1, 1, tz="Asia/Kolkata")):
        assert tm.can_trade, "Should trade after 9:01:00 if trade at 9:00:00"


def test_can_trade_edge_case_trade_near_market_close(time_manager_one_minute):
    """
    Test an edge case where the trade happens very close to market close,
    and then market close is reached.
    """
    tm = time_manager_one_minute
    # Adjust market close closer for this specific test, if needed, or rely on existing setup.
    # tm.market_close = pendulum.datetime(2025, 6, 18, 9, 3, 0, tz="Asia/Kolkata")
    # tm.candle_times = tm._generate_candle_times() # Regenerate for new close

    trade_time = pendulum.datetime(
        2025, 6, 18, 9, 4, 30, tz="Asia/Kolkata"
    )  # Trade at 9:04:30
    tm.set_last_trade_time(trade_time)

    # Next candle close should be 9:05:00
    # Should not trade at 9:04:59
    with freeze_time(pendulum.datetime(2025, 6, 18, 9, 4, 59, tz="Asia/Kolkata")):
        assert not tm.can_trade, "Should not trade before 9:05:00 if trade at 9:04:30"

    # Should trade at 9:05:01 (or after market close if market_close is the last boundary)
    # Given your current `_generate_candle_times` and `can_trade` logic,
    # if `market_close` is 9:05:00, then `tm.candle_times` will end at 9:05:00.
    # A trade at 9:04:30 will target 9:05:00 as its `target_candle_close`.
    # At 9:05:01, `now > target_candle_close` will be true.
    with freeze_time(pendulum.datetime(2025, 6, 18, 9, 5, 1, tz="Asia/Kolkata")):
        assert (
            tm.can_trade
        ), "Should trade after 9:05:00 if trade at 9:04:30 and market closes at 9:05:00"


def test_can_trade_when_last_trade_time_is_future_or_out_of_bounds(
    time_manager_one_minute,
):
    """
    Test case 2: last_trade_time is somehow outside expected range (e.g., in future or very old).
    This relates to the `target_candle_close is None` branch.
    """
    tm = time_manager_one_minute

    # Simulate a trade far in the past, before market_open
    trade_time_past = pendulum.datetime(
        2025, 6, 17, 8, 0, 0, tz="Asia/Kolkata"
    )  # Before market open
    tm.set_last_trade_time(trade_time_past)
    with freeze_time(pendulum.datetime(2025, 6, 18, 9, 0, 1, tz="Asia/Kolkata")):
        # If last_trade_time is before market_open, target_candle_close might not be found or logic needs to handle.
        # Based on current `can_trade` logic, `target_candle_close` would be None for this case, leading to False.
        assert (
            not tm.can_trade
        ), "Should not trade if last_trade_time is before market open"

    # Simulate a trade far in the future (beyond market_close for our short test range)
    trade_time_future = pendulum.datetime(
        2025, 6, 18, 10, 0, 0, tz="Asia/Kolkata"
    )  # After market close
    tm.set_last_trade_time(trade_time_future)
    with freeze_time(pendulum.datetime(2025, 6, 18, 10, 0, 1, tz="Asia/Kolkata")):
        # Similarly, for trade after market_close, target_candle_close might be None or the last one.
        # This case often implies the trading day is over.
        assert (
            not tm.can_trade
        ), "Should not trade if last_trade_time is after market close"
