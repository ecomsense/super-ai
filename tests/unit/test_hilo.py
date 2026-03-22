from src.strategies.hilo import BreakoutState, Hilo
from tests.factory_settings import Factory


def test_init(strategy_factory):
    settings = Factory.settings(strategy_name="hilo")
    strat = strategy_factory(Hilo, settings)
    # verify initialization
    assert strat._state == BreakoutState.DEFAULT, "initial state is not DEFAULT"
    assert strat._last_idx == 10, "not initialized to 9 + 1 in config + strategy"

    # 1. Verify the 'prices' grid calculation
    # We assume low=100, high=110 from your mock data
    prices = [
        (0, 100.0),  # (0, low)
        (100.0, 150),  # (low, low + 10%)
        (150.0, 200),  # (high, high + 10%)
        (200, 200),  # (highest, highest)
    ]

    if settings.get("reentry"):
        assert strat._is_reentry == strat._is_entry
        assert strat._count == 1
    else:
        assert strat._is_reentry.__name__ == "always_true"


def test_breakout_fails_if_stop_is_none(strategy_factory, global_mocks):
    # Instance creation uses the mocked TimeManager automatically
    strat = strategy_factory(Hilo, Factory.settings("hilo"))

    # 1. attach values that may be set at Hilo.run()
    strat._prev_period_low = 90
    strat._last_price = 90
    strat._stop = None
    strat._target = None
    global_mocks["time_idx"].return_value = 11

    is_new_candle = True
    # run the method
    strat.wait_for_breakout(is_new_candle)

    # verify the state of properties after running
    assert strat._state == BreakoutState.DEFAULT, (
        "breakout state cannot change if stop is None"
    )


def test_hilo_armed(strategy_factory, global_mocks):
    # Instance creation uses the mocked TimeManager automatically
    strat = strategy_factory(Hilo, Factory.settings("hilo"))

    # 1. attach values that may be set at Hilo.run()
    strat._prev_period_low = 90
    strat._last_price = 110
    global_mocks["time_idx"].return_value = 11

    # run the method
    strat.wait_for_breakout(True)

    # stop == 100
    assert strat._prev_period_low <= strat._stop, "prev period low > stop"

    assert strat._last_price > strat._stop, "last_price < stop"
    # verify the state of properties after running
    assert strat._state == BreakoutState.ARMED, (
        "not curr idx > stored or prev_low < stop < last_price"
    )
    assert strat._target == 150, "Should be locked at high 100"


def test_hilo_disarmed_of_period_low_breach(strategy_factory, global_mocks):
    # Instance creation uses the mocked TimeManager automatically
    strat = strategy_factory(Hilo, Factory.settings("hilo"))

    strat._state = BreakoutState.ARMED

    strat._armed_idx = global_mocks["time_idx"].return_value = 11

    # 1. attach values that may be set at Hilo.run()
    strat._period_low = 90

    strat._last_price = 110

    # stop is not set in init for this stratergy
    strat._stop = 100

    # run the method
    strat.wait_for_breakout(True)

    # verify the state of properties after running
    assert strat._state == BreakoutState.DEFAULT, "Still ARMED"


def test_hilo_breakout_fails_on_target_breach(strategy_factory, global_mocks):
    """
    Verifies that if price drops back below the breakout line
    during the arming candle, it returns to DEFAULT.
    """
    strat = strategy_factory(Hilo, Factory.settings("hilo"))

    strat._state = BreakoutState.ARMED

    strat._armed_idx = global_mocks["time_idx"].return_value = 11

    # 1. attach values that may be set at Hilo.run()
    strat._period_low = 110

    strat._last_price = 151

    # stop is not set in init for this stratergy
    strat._stop = 100

    strat._target = 150

    # run the method
    strat.wait_for_breakout(True)

    # verify the state of properties after running
    assert strat._state == BreakoutState.DEFAULT, "Still ARMED"


def test_hilo_try_exit(strategy_factory, global_mocks):
    strat = strategy_factory(Hilo, Factory.settings("hilo"))

    # 1. Setup specific values for this test
    strat.pos_id = 1
    strat._last_price = 110
    strat._trades = ["trade1"]
    strat._removable = True
    # 2. Just run it! The TradeManager is already primed in conftest.
    strat.try_exiting_trade()

    strat.pm.status.assert_called_once_with(
        pos_id=1, last_price=110, orders=strat._trades, removable=True
    )


def test_hilo_execution_success(strategy_factory, global_mocks):
    strat = strategy_factory(Hilo, Factory.settings("hilo"))

    # Force the strategy into the ARMED state
    strat._state = BreakoutState.ARMED
    strat._armed_idx = global_mocks["time_idx"].return_value = 11

    # Set levels so it passes the execution checks
    strat._stop = 100
    strat._target = 150
    strat._period_low = 105  # Held above stop
    strat._last_price = 110  # Hasn't hit target yet

    # Mock the position manager to return a valid position ID
    strat.pm.new.return_value = "POS_777"

    # Run the breakout logic (not a new candle, evaluating current armed state)
    strat.wait_for_breakout(is_new_candle=False)

    # Verify execution
    strat.pm.new.assert_called_once()
    assert strat.pos_id == "POS_777", "Position ID was not set from pm.new()"
    assert strat._state == BreakoutState.DEFAULT, (
        "State did not reset to DEFAULT after execution"
    )


def test_hilo_run_candle_tracking(strategy_factory, global_mocks):
    strat = strategy_factory(Hilo, Factory.settings("hilo"))

    # Setup initial state
    strat._last_idx = 10
    strat._period_low = 150
    strat.pos_id = None  # Ensure it routes to wait_for_breakout

    # Scenario A: Same candle, price drops
    global_mocks["time_idx"].return_value = 10
    quotes = {strat._tradingsymbol: 140}
    strat.run(trades=[], quotes=quotes, positions={})

    assert strat._period_low == 140, (
        "Period low should update to the new minimum during the same candle"
    )

    # Scenario B: New candle begins
    global_mocks["time_idx"].return_value = 11
    quotes = {strat._tradingsymbol: 145}
    strat.run(trades=[], quotes=quotes, positions={})

    assert strat._prev_period_low == 140, (
        "Previous period low was not stored correctly on candle flip"
    )
    assert strat._period_low == 145, (
        "Period low did not reset to the first tick of the new candle"
    )
    assert strat._last_idx == 11, "Last index did not update to the new candle index"


def test_hilo_is_entry_toggle(strategy_factory):
    # Test Odd
    settings_odd = Factory.settings("hilo")
    settings_odd["reentry"] = "odd"
    strat_odd = strategy_factory(Hilo, settings_odd)

    assert strat_odd._is_entry() is True  # 1st try: odd (1 % 2 != 0) -> True
    assert strat_odd._is_entry() is False  # 2nd try: even -> False
    assert strat_odd._is_entry() is True  # 3rd try: odd -> True

    # Test Even
    settings_even = Factory.settings("hilo")
    settings_even["reentry"] = "even"
    strat_even = strategy_factory(Hilo, settings_even)

    assert strat_even._is_entry() is False  # 1st try: odd -> False
    assert strat_even._is_entry() is True  # 2nd try: even -> True
