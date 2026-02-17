from unittest.mock import MagicMock, PropertyMock, patch

import pendulum as pdlm
import pytest


@pytest.fixture(autouse=True)
def global_mocks():
    """
    Patches dependencies where they are IMPORTED in the strategy files.
    """
    # Create a single PropertyMock instance to control the time index
    time_idx_mock = PropertyMock(return_value=9)

    with (
        # dummies
        patch("src.sdk.helper.Helper.api"),
        patch("toolkit.kokoo.timer"),
        patch("src.providers.ui.clear_screen"),
        patch("src.providers.ui.pingpong"),
        patch("src.providers.ui.table"),
        # patch with return value
        patch("toolkit.kokoo.is_time_past", return_value=False),
        # opening balance
        patch("src.strategies.openingbalance.TradeManager") as mock_ob_tm,
        patch("src.strategies.openingbalance.TimeManager") as mock_ob_time,
        # hilo
        patch("src.strategies.hilo.TradeManager") as mock_hilo_tm,
        patch("src.strategies.hilo.TimeManager") as mock_hilo_time,
    ):
        # Attach the PropertyMock to the return_value (the instance) of the mocked classes
        type(mock_hilo_time.return_value).current_index = time_idx_mock
        type(mock_ob_time.return_value).current_index = time_idx_mock

        yield {
            "time_idx": time_idx_mock,  # Access this to change the index in tests
            "tm_hilo": mock_hilo_tm,
            "tm_ob": mock_ob_tm,
        }


@pytest.fixture
def mock_rest():
    """
    Mocks the SDK/Rest provider with distinct High and Low values.
    """
    mock = MagicMock()

    def history_side_effect(*args, **kwargs):
        # Check the 'key' argument to decide what to return
        key = kwargs.get("key")
        if key == "intl":
            return 100.0  # Previous Period Low
        elif key == "inth":
            return 150.0  # Previous Period High

    mock.history.side_effect = history_side_effect
    # mock.ltp.return_value = 105.0
    return mock


@pytest.fixture
def common_symbol_info():
    """
    Common keys found in symbol_info that both strategies use.
    """
    return {
        "symbol": "BANKNIFTY",  # Used by Openingbalance as prefix
        "tradingsymbol": "BANKNIFTY-OPT",  # Used by both
        "option_token": "12345",
        "option_exchange": "NFO",
        "option_type": "CE",
        # "quantity": 15,
        # "ltp": 100.0,
    }


@pytest.fixture
def strategy_factory(mock_rest, common_symbol_info):
    """
    Instantiates a strategy by merging common info with specific settings.
    """

    def _create(strategy_class, user_settings):
        # Merge all data into one kwargs dict
        kwargs = {
            **common_symbol_info,
            **user_settings,
            "rest": mock_rest,
            "stop_time": "15:30:00",
        }
        return strategy_class(**kwargs)

    return _create
