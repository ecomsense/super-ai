from src.strategies.hilo import BreakoutState, Hilo
from tests.factory_settings import Factory


def test_hilo_breakout_succeeds(strategy_factory, global_mocks):
    # Instance creation uses the mocked TimeManager automatically
    strat = strategy_factory(Hilo, Factory.settings("hilo"))
    # verify initialization
    assert strat._state == BreakoutState.DEFAULT, "initial state is not DEFAULT"
    assert strat._last_idx == 10, "not initialized to 9 + 1 in config + strategy"

    # 1. attach values that may be set at Hilo.run()
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


def test_hilo_breakout_fails_on_low_breach(strategy_factory, global_mocks):
    """
    Verifies that if price drops back below the breakout line
    during the arming candle, it returns to DEFAULT.
    """
    strat = strategy_factory(Hilo, Factory.settings("hilo"))

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


def test_hilo_breakout_fails_on_target_breach(strategy_factory, global_mocks):
    """
    Verifies that if price drops back below the breakout line
    during the arming candle, it returns to DEFAULT.
    """
    strat = strategy_factory(Hilo, Factory.settings("hilo"))

    # Manually force ARMED state
    strat._state = BreakoutState.ARMED
    strat._target = 150
    strat._stop = 100
    strat._last_idx = 11
    global_mocks["time_idx"].return_value = 11

    # Price breaches target
    strat._last_price = 151
    strat.wait_for_breakout()

    assert strat._state == BreakoutState.DEFAULT
    assert strat._fn == "wait_for_breakout"


def test_hilo_place_exit_order_flow(strategy_factory, global_mocks):
    strat = strategy_factory(Hilo, Factory.settings("hilo"))

    # 1. Setup specific values for this test
    strat._stop = 100
    strat._target = 150
    strat._last_price = 110
    strat._trades = ["trade1"]
    strat.set_new_stop = global_mocks["mock"]

    # 2. Just run it! The TradeManager is already primed in conftest.
    strat.place_exit_order()

    # 3. Verify the result
    # We check if the strategy correctly moved to the next function
    assert strat._fn == "try_exiting_trade"

    # We can still verify the math was correct
    strat.trade_mgr.pending_exit.assert_called_once_with(
        stop=50, orders=strat._trades, last_price=110
    )

    strat.trade_mgr.target.assert_called_once_with(target_price=strat._target)


def test_hilo_set_new_stop(strategy_factory, global_mocks):
    strat = strategy_factory(Hilo, Factory.settings("hilo"))
    strat._stop = 100
    strat.trade_mgr.position = global_mocks["position"]
    # average_price or fill price is 110
    strat._set_new_stop()
    strat.trade_mgr.stop.asset_called_once_with(stop_price=105)
