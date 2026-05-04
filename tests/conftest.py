import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from src.providers.trade_manager import TradeManager
from src.providers.position_manager import PositionManager


@pytest.fixture
def mock_broker():
    mock = MagicMock()
    mock.order_place.return_value = "ORD_12345"
    mock.positions = []
    return mock


@pytest.fixture
def rm(mock_broker):
    """Create a RiskManager instance with mock broker."""
    from src.providers.risk_manager import RiskManager
    return RiskManager(mock_broker)


# Realistic dummy data that resembles actual broker position response
# From actual flattrade broker API response
BROKER_POSITION_DICT = {
    "stat": "Ok",
    "uid": "FZ13059",
    "actid": "FZ13059",
    "exchange": "NFO",
    "symbol": "NIFTY05MAY26C23800",
    "s_prdt_ali": "MIS",
    "prd": "I",
    "token": "74129",
    "symname": "NIFTY",
    "und_exch": "NSE",
    "und_tk": "26000",
    "instname": "OPTIDX",
    "cname": "NIFTY 05MAY26 23800 CE ",
    "dname": "NIFTY 05MAY26 23800 CE ",
    "frzqty": "1801",
    "pp": "2",
    "ls": "65",
    "ti": "0.05",
    "mult": "1",
    "prcftr": "1.000000",
    "daybuyqty": 455,
    "daysellqty": 455,
    "day_buy_value": 208058.5,
    "daybuyavgprc": 457.27,
    "day_sell_value": 214340.75,
    "daysellavgprc": 471.08,
    "cfbuyqty": 0,
    "cfsellqty": 0,
    "openbuyqty": 0,
    "opensellqty": 0,
    "dayavgprc": 0.0,
    "quantity": 0,  # net position (daybuyqty - daysellqty)
    "netavgprc": "0.00",
    "upldprc": "0.00",
    "last_price": 354.4,
    "urmtom": 0.0,
    "bep": "0.00",
    "totbuyamt": "208058.50",
    "totsellamt": "214340.75",
    "totbuyavgprc": "457.27",
    "totsellavgprc": "471.08",
    "rpnl": 6282.25,
}


@pytest.fixture
def broker_position_book():
    """Return a realistic position book as returned by the broker.
    
    This data resembles the actual response from the broker's positions API.
    Some fields may vary between brokers, but this is a realistic example.
    From actual flattrade broker API response.
    """
    return [
        {
            "stat": "Ok",
            "uid": "FZ13059",
            "actid": "FZ13059",
            "exchange": "NFO",
            "symbol": "NIFTY05MAY26C23800",
            "s_prdt_ali": "MIS",
            "prd": "I",
            "token": "74129",
            "symname": "NIFTY",
            "und_exch": "NSE",
            "und_tk": "26000",
            "instname": "OPTIDX",
            "cname": "NIFTY 05MAY26 23800 CE ",
            "dname": "NIFTY 05MAY26 23800 CE ",
            "ls": "65",
            "mult": "1",
            "daybuyqty": 455,
            "daysellqty": 455,
            "daybuyavgprc": 457.27,
            "daysellavgprc": 471.08,
            "cfbuyqty": 0,
            "cfsellqty": 0,
            "openbuyqty": 0,
            "opensellqty": 0,
            "dayavgprc": 0.0,
            "quantity": 0,
            "netavgprc": "0.00",
            "last_price": 354.4,
            "urmtom": 0.0,
            "bep": "0.00",
            "totbuyamt": "208058.50",
            "totsellamt": "214340.75",
            "rpnl": 6282.25,
        },
        {
            "stat": "Ok",
            "uid": "FZ13059",
            "actid": "FZ13059",
            "exchange": "NFO",
            "symbol": "NIFTY05MAY26P24200",
            "s_prdt_ali": "MIS",
            "prd": "I",
            "token": "74168",
            "symname": "NIFTY",
            "und_exch": "NSE",
            "und_tk": "26000",
            "instname": "OPTIDX",
            "cname": "NIFTY 05MAY26 24200 PE ",
            "dname": "NIFTY 05MAY26 24200 PE ",
            "ls": "65",
            "mult": "1",
            "daybuyqty": 780,
            "daysellqty": 780,
            "daybuyavgprc": 126.6,
            "daysellavgprc": 127.8,
            "cfbuyqty": 0,
            "cfsellqty": 0,
            "openbuyqty": 0,
            "opensellqty": 0,
            "dayavgprc": 0.0,
            "quantity": 0,
            "netavgprc": "0.00",
            "last_price": 133.65,
            "urmtom": 0.0,
            "bep": "0.00",
            "totbuyamt": "98751.25",
            "totsellamt": "99680.75",
            "rpnl": 929.5,
        },
    ]


@pytest.fixture
def broker_position_book_with_exit():
    """Return a position book where some positions are ready to exit (profit target hit)."""
    return [
        {
            "stat": "Ok",
            "uid": "FZ13059",
            "actid": "FZ13059",
            "exchange": "NFO",
            "symbol": "NIFTY05MAY26C23800",
            "s_prdt_ali": "MIS",
            "prd": "I",
            "token": "74129",
            "symname": "NIFTY",
            "ls": "65",
            "mult": "1",
            "daybuyqty": 100,
            "daysellqty": 0,
            "daybuyavgprc": 440.00,
            "daysellavgprc": 0.0,
            "quantity": 100,
            "last_price": 470.00,  # Target hit - price above target
            "rpnl": 3000.00,  # Profit
        },
    ]


@pytest.fixture
def broker_position_book_empty():
    """Return an empty position book."""
    return []


@pytest.fixture(autouse=True)
def global_mocks(request):
    """
    Patches dependencies. If a test is marked @pytest.mark.integration,
    it skips patching TradeManager to allow real award interaction.
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
            patch("src.deprecated.openingbalance.TimeManager") as mock_ob_time,
            patch("src.deprecated.hilo.TimeManager") as mock_hilo_time,
        ):
            type(mock_hilo_time.return_value).current_index = time_idx_mock
            type(mock_ob_time.return_value).current_index = time_idx_mock

            yield {"time_idx": time_idx_mock}
    else:
        # Standard Unit Test Mode: Patch everything
        with (
            patch("src.deprecated.openingbalance.TradeManager") as mock_ob_tm,
            patch("src.deprecated.openingbalance.TimeManager") as mock_ob_time,
            patch("src.deprecated.hilo.TimeManager") as mock_hilo_time,
            patch("src.providers.position_manager.NFOManager") as nfo_manager,
            patch("src.providers.position_manager.Position") as pm_position,
        ):
            type(mock_hilo_time.return_value).current_index = time_idx_mock
            type(mock_ob_time.return_value).current_index = time_idx_mock

            mock_order = MagicMock()
            mock_order.order_id = "ORD_12345"

            mock_position = MagicMock()
            mock_position.average_price = 110  # Fixed typo from 'averge_price'

            mock_instance = MagicMock()
            mock_pos = MagicMock()

            yield {
                "time_idx": time_idx_mock,
                "tm_hilo": mock_instance,
                "tm_ob": mock_ob_tm,
                "order": mock_order,
                "position": mock_position,
                "nfo_manager": nfo_manager,
                "pm_position": pm_position,
                "mock": mock_pos,
            }

    # Stop all common patches after the test is done
    for p in dummies:
        p.stop()


@pytest.fixture
def strategy_factory(mock_broker):
    def _create_strategy(strategy_class, settings):
        # ensure common keys are present
        if "tradingsymbol" not in settings and "symbol" in settings:
            settings["tradingsymbol"] = settings["symbol"]
        if "strategy" not in settings:
            settings["strategy"] = strategy_class.__name__.lower()
        if "stop_time" not in settings:
            settings["stop_time"] = {"hour": 15, "minute": 20}
        if "option_type" not in settings:
            settings["option_type"] = "CE"
        if "pm" not in settings:
            settings["pm"] = MagicMock()
        if "option_token" not in settings:
            settings["option_token"] = "123"
        if "option_exchange" not in settings:
            settings["option_exchange"] = "NFO"

        mock_rest = MagicMock()
        mock_rest.history.return_value = 100.0

        return strategy_class(
            trade_settings=settings,
            user_settings={},
            quote=MagicMock(),
            rest=mock_rest,
            rm=MagicMock(),
            **settings
        )

    return _create_strategy
