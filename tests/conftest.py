import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_symbol_info():
    return {
        "option_type": "CE",
        "token": "12345",
        "symbol": "BANKNIFTY-OPT",
        "ltp": 100.0,
    }


@pytest.fixture
def mock_user_settings():
    return {
        "quantity": 15,
        "small_bucket": 60,
        "big_bucket": 300,
        "max_trade_in_bucket": 2,
        "option_exchange": "NFO",
    }


@pytest.fixture
def mock_env():
    """
    Patches external dependencies globally for any test using this fixture.
    """
    with patch("src.sdk.helper.Helper.api") as mock_api, patch(
        "src.providers.grid.Grid.get"
    ) as mock_grid_get, patch(
        "src.providers.grid.pivot_to_stop_and_target"
    ) as mock_pivot:

        # Default behavior: Return a single pivot level
        mock_grid_get.return_value = {"status": "success"}
        mock_pivot.return_value = [(100, 110)]  # stop=100, target=110

        yield {"api": mock_api, "grid": mock_grid_get, "pivot": mock_pivot}


@pytest.fixture
def strategy(mock_env, mock_symbol_info, mock_user_settings):
    """
    Returns an instance of Newpivot with mocked Managers and Buckets.
    """
    from src.strategies.newpivot import Newpivot

    # We patch the dependent classes inside the strategy module
    with patch("src.strategies.newpivot.TradeManager"), patch(
        "src.strategies.newpivot.Bucket"
    ), patch("src.strategies.newpivot.SimpleBucket"), patch(
        "src.strategies.newpivot.is_time_past", return_value=False
    ):

        strat = Newpivot(
            prefix="TEST",
            symbol_info=mock_symbol_info,
            user_settings=mock_user_settings,
            rest="dummy_rest_data",
        )
        # Mocking specific state variables
        strat.stop_time = "15:20:00"
        return strat


@pytest.fixture
def mock_ob_settings():
    """Specific settings for the Opening Balance strategy."""
    return {
        "quantity": 15,
        "t1": 10,
        "t2": 5,
        "txn": 20,
        "rest_time": {"minutes": 5},
        "option_exchange": "NFO",
    }


@pytest.fixture
def ob_strategy(mock_symbol_info, mock_ob_settings):
    """
    Returns an instance of Openingbalance with mocked Managers,
    Buckets, and StateManager.
    """
    from src.strategies.openingbalance import Openingbalance

    # 1. Create the 'rest' mock for history and ltp calls
    mock_rest = MagicMock()
    mock_rest.ltp.return_value = 100.0
    mock_rest.history.return_value = 95.0

    # 2. Patch dependencies inside the strategy module
    with patch("src.strategies.openingbalance.TimeManager") as mock_time_class, patch(
        "src.strategies.openingbalance.StateManager"
    ) as mock_state, patch(
        "src.strategies.openingbalance.TradeManager"
    ) as mock_tm_class, patch(
        "src.strategies.openingbalance.Helper.api"
    ), patch(
        "src.strategies.openingbalance.table"
    ):

        # Capture the instance of TradeManager
        mock_tm_instance = mock_tm_class.return_value

        # Default StateManager behavior
        mock_state.get_trade_count.return_value = 0

        strat = Openingbalance(
            prefix="OB_TEST",
            symbol_info=mock_symbol_info,
            user_settings=mock_ob_settings,
            rest=mock_rest,
        )

        # Ensure TradeManager mock is accessible
        strat.trade_mgr = mock_tm_instance
        # Force time manager to allow trading for tests
        strat._time_mgr.can_trade = True

        return strat
