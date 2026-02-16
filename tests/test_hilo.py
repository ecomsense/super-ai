from src.strategies.hilo import BreakoutState, Hilo
from toolkit.fileutils import Fileutils


def flatten_no_rename(d, result=None):
    if result is None:
        result = {}

    for k, v in d.items():
        if isinstance(v, dict):
            # Recurse into the dictionary
            flatten_no_rename(v, result)
        else:
            # Assign the value to the flat result
            result[k] = v
    return result


def get_settings(strategy_name):
    return flatten_no_rename(
        Fileutils().read_file("./factory/" + strategy_name + ".yml")
    )


def test_hilo_arming_logic(strategy_factory, global_mocks):
    # Instance creation uses the mocked TimeManager automatically
    strat = strategy_factory(Hilo, get_settings("hilo"))

    # verify initialization
    assert strat._state == BreakoutState.DEFAULT, "initial state is not DEFAULT"

    # 1. override initial settings
    strat._last_idx = 10
    strat._prev_period_low = 90
    strat._last_price = 110
    global_mocks["time_idx"].return_value = 11

    # run the method
    strat.wait_for_breakout()

    # verify the state of properties after running
    assert strat._state == BreakoutState.ARMED, (
        "not curr idx > stored or prev_low < stop < last_price"
    )
    assert strat._last_idx == 11, "stored time idx is not 11"
    assert strat._stop == 100, "Should be locked at low 100"
    assert strat._target == 150, "Should be locked at high 100"

    # --- PHASE 2: PIVOT LOCKING (The fix for Stop > Entry) ---
    # Simulate price jumping to a much higher grid (e.g., 210) within the SAME candle
    # If the logic isn't 'locked', _set_stop() would move strat._stop to 200 here.
    strat._last_price = 149
    strat.wait_for_breakout()

    assert strat._state == BreakoutState.ARMED, "Should stay ARMED"
    assert strat._stop == 100, (
        "CRITICAL: Stop drifted! stop must stay locked during ARMED state."
    )

    # --- PHASE 3: EXECUTION ---
    # Move to the next candle index to trigger entry
    global_mocks["time_idx"].return_value = 12
    strat.wait_for_breakout()

    # Verify transition to order placement
    assert strat._state == BreakoutState.DEFAULT
    assert strat._fn == "place_exit_order"
    # Ensure complete_entry was called with the price at the time of the new candle
    strat.trade_mgr.complete_entry.assert_called_once_with(price=149)


def test_hilo_disarm_on_price_fail(strategy_factory, global_mocks):
    """
    Verifies that if price drops back below the breakout line
    during the arming candle, it returns to DEFAULT.
    """
    strat = strategy_factory(Hilo, get_settings("hilo"))

    # Manually force ARMED state
    strat._state = BreakoutState.ARMED
    strat._stop = 100
    strat._last_idx = 11
    global_mocks["time_idx"].return_value = 11

    # Price drops to 99 (below the 100 breakout line)
    strat._last_price = 99
    strat.wait_for_breakout()

    assert strat._state == BreakoutState.DEFAULT
    assert strat._fn == "wait_for_breakout"
