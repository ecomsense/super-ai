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


from unittest.mock import patch, MagicMock, PropertyMock
from enum import IntEnum


# Define the Enum here or import it from your strategy file
class BreakoutState(IntEnum):
    DEFAULT = 0
    ARMED = 1


@pytest.fixture
def mock_ob_settings():
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
    from src.strategies.openingbalance import Openingbalance, BreakoutState

    mock_rest = MagicMock()
    mock_rest.ltp.return_value = 100.0
    mock_rest.history.return_value = 95.0

    with patch("src.strategies.openingbalance.TimeManager") as mock_time_class, patch(
        "src.strategies.openingbalance.TradeManager"
    ) as mock_tm_class, patch("src.strategies.openingbalance.Helper.api"), patch(
        "src.strategies.openingbalance.table"
    ):

        # Setup TimeManager with a mockable current_index property
        mock_time_instance = mock_time_class.return_value
        type(mock_time_instance).current_index = PropertyMock(return_value=10)

        strat = Openingbalance(
            prefix="OB_TEST",
            symbol_info=mock_symbol_info,
            user_settings=mock_ob_settings,
            rest=mock_rest,
        )

        # Injected dependencies
        strat.trade_mgr = mock_tm_class.return_value
        strat._time_mgr = mock_time_instance

        # Power-On Reset State
        strat._state = BreakoutState.DEFAULT
        strat._last_idx = 10

        return strat
