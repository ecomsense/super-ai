import pytest
from unittest.mock import patch


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
