import pytest
from unittest.mock import PropertyMock
from src.strategies.openingbalance import BreakoutState


def test_ob_successful_sequential_entry(ob_strategy):
    """
    Verifies the full 3-step sequence:
    1. Condition 1: New index starts, LTP > Stop -> ARMED.
    2. Condition 2: Same index, LTP stays > Stop -> Stays ARMED.
    3. Condition 3: Next index starts -> EXECUTE at current LTP + 2.
    """
    # Force strategy past 'set_stop' into the breakout logic
    ob_strategy._stop = 100.0
    ob_strategy._fn = "wait_for_breakout"

    # --- STEP 1: ARMING (Condition 1) ---
    # Move from index 10 to 11
    type(ob_strategy._time_mgr).current_index = PropertyMock(return_value=11)
    ob_strategy._last_price = 105.0
    ob_strategy.wait_for_breakout()

    assert ob_strategy._state == BreakoutState.ARMED
    assert ob_strategy._last_idx == 11

    # --- STEP 2: VALIDATION (Condition 2 - Same Index) ---
    ob_strategy._last_price = 103.0  # Price dips but safe
    ob_strategy.wait_for_breakout()
    assert ob_strategy._state == BreakoutState.ARMED

    # --- STEP 3: EXECUTION (Condition 3 - Next Index pulse) ---
    # Trigger the 'Rising Edge' by moving to index 12
    type(ob_strategy._time_mgr).current_index = PropertyMock(return_value=12)

    # We set the price at which we want to execute
    execution_price = 105.0
    ob_strategy._last_price = execution_price
    ob_strategy.trade_mgr.complete_entry.return_value = True

    ob_strategy.wait_for_breakout()

    # Assertions
    assert ob_strategy._fn == "place_exit_order"
    assert ob_strategy._state == BreakoutState.DEFAULT

    # Expected price is execution_price (105) + 2 = 107
    expected_entry_price = execution_price + 2
    ob_strategy.trade_mgr.complete_entry.assert_called_once_with(
        quantity=15, price=expected_entry_price
    )
