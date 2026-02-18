import pytest
from src.providers.trade_manager import TradeManager
from src.strategies.hilo import Hilo


@pytest.mark.integration
def test_hilo_real_trade_flow(strategy_factory, mock_broker, global_mocks):
    """
    Test the actual interaction between Hilo and TradeManager.
    """
    # 1. Setup Strategy with REAL TradeManager
    # Because of the 'integration' marker, TradeManager is NOT a mock here.
    settings = {"symbol": "BANKNIFTY", "quantity": 15}
    strat = strategy_factory(Hilo, settings)

    # Inject real TM with the mock_broker from conftest
    strat.trade_mgr = TradeManager(
        stock_broker=mock_broker, symbol="BANKNIFTY", exchange="NFO", quantity=15
    )

    # 2. Simulate Market Movement
    strat._state = "ARMED"
    strat._last_price = 155.0  # Breakout!
    global_mocks["time_idx"].return_value = 10  # New candle

    # 3. Trigger Strategy Breakout
    strat.wait_for_breakout()

    # 4. Assertions
    # Verify the real TradeManager logic correctly called the mock broker
    mock_broker.order_place.assert_called_once()
    assert strat.trade_mgr.position.state == "entry_pending"
