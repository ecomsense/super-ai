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
