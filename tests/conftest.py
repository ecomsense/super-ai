from unittest.mock import MagicMock, PropertyMock, patch

import pendulum as pdlm
import pytest


# 1. Added mock_broker (kept from previous discussion)
@pytest.fixture
def mock_broker():
    """Mocks the low-level stock broker API (e.g., Finvasia)."""
    broker = MagicMock()
    broker.order_place.return_value = "ORD_12345"
    broker.order_modify.return_value = "MOD_12345"
    return broker


@pytest.fixture
def tm(mock_broker, common_symbol_info):
    """Provides a pre-configured REAL TradeManager instance for integration tests."""
    from src.providers.trade_manager import TradeManager

    return TradeManager(
        stock_broker=mock_broker,
        symbol=common_symbol_info["symbol"],
        exchange=common_symbol_info["option_exchange"],
        quantity=15,
        tag="test_tag",
    )


@pytest.fixture(autouse=True)
def global_mocks(request):
    """
    Patches dependencies. If a test is marked @pytest.mark.integration,
    it skips patching TradeManager to allow real component interaction.
    """
    # Check if 'integration' marker is present on the test
    is_integration = request.node.get_closest_marker("integration") is not None

    time_idx_mock = PropertyMock(return_value=9)

    # Define common dummies that are always patched
    dummies = [
        patch("src.sdk.helper.Helper.api"),
        patch("toolkit.kokoo.timer"),
        patch("src.providers.ui.clear_screen"),
        patch("src.providers.ui.pingpong"),
        patch("src.providers.ui.table"),
        patch("toolkit.kokoo.is_time_past", return_value=False),
    ]

    # Start the common patches
    for p in dummies:
        p.start()

    # Conditional Patching Logic
    if is_integration:
        # In integration mode, we only patch TimeManager, NOT TradeManager
        with (
            patch("src.strategies.openingbalance.TimeManager") as mock_ob_time,
            patch("src.strategies.hilo.TimeManager") as mock_hilo_time,
        ):
            type(mock_hilo_time.return_value).current_index = time_idx_mock
            type(mock_ob_time.return_value).current_index = time_idx_mock

            yield {"time_idx": time_idx_mock}
    else:
        # Standard Unit Test Mode: Patch everything
        with (
            patch("src.strategies.openingbalance.TradeManager") as mock_ob_tm,
            patch("src.strategies.openingbalance.TimeManager") as mock_ob_time,
            patch("src.strategies.hilo.TradeManager") as mock_hilo_tm,
            patch("src.strategies.hilo.TimeManager") as mock_hilo_time,
        ):
            type(mock_hilo_time.return_value).current_index = time_idx_mock
            type(mock_ob_time.return_value).current_index = time_idx_mock

            mock_order = MagicMock()
            mock_order.order_id = "ORD_12345"
            mock_hilo_tm.return_value.pending_exit.return_value = mock_order

            mock_position = MagicMock()
            mock_position.average_price = 110  # Fixed typo from 'averge_price'
            mock_hilo_tm.return_value.position = mock_position

            mock_instance = MagicMock()

            yield {
                "time_idx": time_idx_mock,
                "tm_hilo": mock_hilo_tm,
                "tm_ob": mock_ob_tm,
                "order": mock_order,
                "position": mock_position,
                "mock": mock_instance,
            }

    patch.stopall()


@pytest.fixture
def mock_rest():
    mock = MagicMock()

    def history_side_effect(*args, **kwargs):
        key = kwargs.get("key")
        if key == "intl":
            return 100.0
        elif key == "inth":
            return 150.0

    mock.history.side_effect = history_side_effect
    return mock


@pytest.fixture
def common_symbol_info():
    return {
        "symbol": "BANKNIFTY",
        "tradingsymbol": "BANKNIFTY-OPT",
        "option_token": "12345",
        "option_exchange": "NFO",
        "option_type": "CE",
    }


@pytest.fixture
def strategy_factory(mock_rest, common_symbol_info):
    def _create(strategy_class, user_settings):
        kwargs = {
            **common_symbol_info,
            **user_settings,
            "rest": mock_rest,
            "stop_time": "15:30:00",
        }
        return strategy_class(**kwargs)

    return _create
