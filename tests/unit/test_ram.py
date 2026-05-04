"""
Tests for RAM strategy
Run with: pytest tests/unit/test_ram.py -v
"""

from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from src.strategies.ram import Ram


class TestRamOnSignal:
    """Tests for _on_signal method"""

    def test_on_signal_creates_new_position(self):
        """_on_signal should call rm.new with correct parameters"""
        mock_rm = Mock()
        mock_rm.new.return_value = 123

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            ram = Ram(
                tradingsymbol="NIFTY05MAY26C23700",
                strategy="ram",
                stop_time={"hour": 15, "minute": 30},
                rm=mock_rm,
                option_exchange="NFO",
                quantity=65,
                ltp=340.0,
                rest=mock_rest,
                option_token="123",
                low_candle_time={"hour": 9, "minute": 14, "second": 59},
            )

        ram._last_price = 350.0

        ram._on_signal(1)

        mock_rm.new.assert_called_once_with(
            symbol="NIFTY05MAY26C23700",
            exchange="NFO",
            quantity=65,
            tag="ram",
            entry_price=350.0,
            target=ram._target,
            stop_loss=0,
        )
        assert ram.pos_id == 123
        assert ram._armed_idx == 1


class TestRamWaitForBreakout:
    """Tests for wait_for_breakout method"""

    def test_wait_for_breakout_single_candle_breakout(self):
        """Should trigger signal when single candle breaks out"""
        mock_rm = Mock()
        mock_rm.new.return_value = 123

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            ram = Ram(
                tradingsymbol="NIFTY05MAY26C23700",
                strategy="ram",
                stop_time={"hour": 15, "minute": 30},
                rm=mock_rm,
                option_exchange="NFO",
                quantity=65,
                ltp=340.0,
                rest=mock_rest,
                option_token="123",
                low_candle_time={"hour": 9, "minute": 14, "second": 59},
            )

        ram._stop = 100.0
        ram._last_price = 110.0
        ram._armed_idx = 0

        mock_candle = pd.DataFrame({
            "low": [90.0],
            "open": [105.0],
            "close": [108.0],
        })
        ram._candle.transform = Mock(return_value=mock_candle)

        ram.wait_for_breakout()

        mock_rm.new.assert_called_once()
        assert ram.pos_id is not None

    def test_wait_for_breakout_no_breakout_when_last_price_below_stop(self):
        """Should NOT trigger signal when last_price is below stop"""
        mock_rm = Mock()
        mock_rm.new.return_value = 123

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            ram = Ram(
                tradingsymbol="NIFTY05MAY26C23700",
                strategy="ram",
                stop_time={"hour": 15, "minute": 30},
                rm=mock_rm,
                option_exchange="NFO",
                quantity=65,
                ltp=90.0,
                rest=mock_rest,
                option_token="123",
                low_candle_time={"hour": 9, "minute": 14, "second": 59},
            )

        ram._stop = 100.0
        ram._last_price = 90.0
        ram._armed_idx = 0

        mock_candle = pd.DataFrame({
            "low": [90.0],
            "open": [105.0],
            "close": [108.0],
        })
        ram._candle.transform = Mock(return_value=mock_candle)

        initial_pos_id = ram.pos_id
        ram.wait_for_breakout()

        mock_rm.new.assert_not_called()
        assert ram.pos_id == initial_pos_id

    def test_wait_for_breakout_two_candle_condition(self):
        """Should trigger signal on two candle condition"""
        mock_rm = Mock()
        mock_rm.new.return_value = 456

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            ram = Ram(
                tradingsymbol="NIFTY05MAY26C23700",
                strategy="ram",
                stop_time={"hour": 15, "minute": 30},
                rm=mock_rm,
                option_exchange="NFO",
                quantity=65,
                ltp=105.0,
                rest=mock_rest,
                option_token="123",
                low_candle_time={"hour": 9, "minute": 14, "second": 59},
            )

        ram._stop = 100.0
        ram._last_price = 105.0
        ram._target = 200.0
        ram._armed_idx = 1  # Set armed_idx to 1 so single candle condition fails
        ram.prev_trade_at = 100.0

        # Need at least 4 candles for two-candle condition
        mock_candle = pd.DataFrame({
            "low": [95.0, 96.0, 97.0, 101.0],  # Last low > stop to fail single candle condition
            "open": [102.0, 105.0, 104.0, 105.0],  # -3 open=105, close=101 (close<open)
            "close": [101.0, 101.0, 106.0, 107.0],  # -2 open=104, close=106 (close>open)
        })
        ram._candle.transform = Mock(return_value=mock_candle)

        ram.wait_for_breakout()

        mock_rm.new.assert_called_once()
        assert ram.pos_id == 456
        assert ram.prev_trade_at == 105.0

    def test_wait_for_breakout_skips_while_waiting_for_candles(self):
        """Should skip breakout check when not enough candles"""
        mock_rm = Mock()
        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            ram = Ram(
                tradingsymbol="NIFTY05MAY26C23700",
                strategy="ram",
                stop_time={"hour": 15, "minute": 30},
                rm=mock_rm,
                option_exchange="NFO",
                quantity=65,
                ltp=90.0,  # Set last price <= stop to fail single candle condition
                rest=mock_rest,
                option_token="123",
                low_candle_time={"hour": 9, "minute": 14, "second": 59},
            )

        ram._stop = 100.0
        ram._last_price = 90.0
        ram._target = 200.0
        ram._armed_idx = 1
        ram.prev_trade_at = 100.0

        mock_candle = pd.DataFrame({
            "low": [95.0, 96.0],
            "open": [102.0, 103.0],
            "close": [101.0, 104.0],
        })
        ram._candle.transform = Mock(return_value=mock_candle)

        ram.wait_for_breakout()

        mock_rm.new.assert_not_called()

    def test_wait_for_breakout_already_armed(self):
        """Should not trigger if already armed at current candle"""
        mock_rm = Mock()
        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            ram = Ram(
                tradingsymbol="NIFTY05MAY26C23700",
                strategy="ram",
                stop_time={"hour": 15, "minute": 30},
                rm=mock_rm,
                option_exchange="NFO",
                quantity=65,
                ltp=110.0,
                rest=mock_rest,
                option_token="123",
                low_candle_time={"hour": 9, "minute": 14, "second": 59},
            )

        ram._stop = 100.0
        ram._last_price = 110.0
        ram._armed_idx = 1

        mock_candle = pd.DataFrame({
            "low": [90.0],
            "open": [105.0],
            "close": [108.0],
        })
        ram._candle.transform = Mock(return_value=mock_candle)

        ram.wait_for_breakout()

        mock_rm.new.assert_not_called()


class TestRamTryExitingTrade:
    """Tests for try_exiting_trade method"""

    def test_try_exiting_trade_exits_when_time_past_and_no_position(self):
        """Should set removable when time is past and position is closed"""
        mock_rm = Mock()
        mock_rm.status.return_value = 0

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            with patch("src.strategies.ram.is_time_past", return_value=True):
                ram = Ram(
                    tradingsymbol="NIFTY05MAY26C23700",
                    strategy="ram",
                    stop_time={"hour": 15, "minute": 30},
                    rm=mock_rm,
                    option_exchange="NFO",
                    quantity=65,
                    ltp=340.0,
                    rest=mock_rest,
                    option_token="123",
                    low_candle_time={"hour": 9, "minute": 14, "second": 59},
                )

                ram.pos_id = 123
                ram._last_price = 350.0

                ram.try_exiting_trade()

                mock_rm.status.assert_called_once_with(pos_id=123, last_price=350.0)
                assert ram._removable is True
                assert ram.pos_id is None

    def test_try_exiting_trade_no_exit_when_position_still_open(self):
        """Should NOT set removable when position is still open"""
        mock_rm = Mock()
        mock_rm.status.return_value = 1

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            with patch("src.strategies.ram.is_time_past", return_value=True):
                ram = Ram(
                    tradingsymbol="NIFTY05MAY26C23700",
                    strategy="ram",
                    stop_time={"hour": 15, "minute": 30},
                    rm=mock_rm,
                    option_exchange="NFO",
                    quantity=65,
                    ltp=340.0,
                    rest=mock_rest,
                    option_token="123",
                    low_candle_time={"hour": 9, "minute": 14, "second": 59},
                )

                ram.pos_id = 123
                ram._last_price = 350.0
                ram._removable = False

                ram.try_exiting_trade()

                assert ram._removable is False
                assert ram.pos_id == 123

    def test_try_exiting_trade_no_exit_when_time_not_past(self):
        """Should NOT set removable when time is not past (but still calls status)"""
        mock_rm = Mock()
        mock_rm.status.return_value = 1

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            with patch("src.strategies.ram.is_time_past", return_value=False):
                ram = Ram(
                    tradingsymbol="NIFTY05MAY26C23700",
                    strategy="ram",
                    stop_time={"hour": 15, "minute": 30},
                    rm=mock_rm,
                    option_exchange="NFO",
                    quantity=65,
                    ltp=340.0,
                    rest=mock_rest,
                    option_token="123",
                    low_candle_time={"hour": 9, "minute": 14, "second": 59},
                )

                ram.pos_id = 123
                ram._last_price = 350.0

                ram.try_exiting_trade()

                # status IS called but removable is NOT set because time is not past
                mock_rm.status.assert_called_once_with(pos_id=123, last_price=350.0)
                assert ram._removable is False


class TestRamRun:
    """Tests for run method"""

    def test_run_updates_last_price_and_candle(self):
        """Should update last_price and add tick to candle"""
        mock_rm = Mock()
        mock_rm.positions = []

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            ram = Ram(
                tradingsymbol="NIFTY05MAY26C23700",
                strategy="ram",
                stop_time={"hour": 15, "minute": 30},
                rm=mock_rm,
                option_exchange="NFO",
                quantity=65,
                ltp=340.0,
                rest=mock_rest,
                option_token="123",
                low_candle_time={"hour": 9, "minute": 14, "second": 59},
            )

        quotes = {"NIFTY05MAY26C23700": "350.0"}
        position_book = []

        ram.run(position_book, quotes)

        assert ram._last_price == 350.0

    def test_run_returns_when_symbol_not_in_quotes(self):
        """Should return early when symbol not in quotes"""
        mock_rm = Mock()
        mock_rm.positions = []

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            ram = Ram(
                tradingsymbol="NIFTY05MAY26C23700",
                strategy="ram",
                stop_time={"hour": 15, "minute": 30},
                rm=mock_rm,
                option_exchange="NFO",
                quantity=65,
                ltp=340.0,
                rest=mock_rest,
                option_token="123",
                low_candle_time={"hour": 9, "minute": 14, "second": 59},
            )

            quotes = {}
            position_book = []

            initial_last_price = ram._last_price
            ram.run(position_book, quotes)

            assert ram._last_price == initial_last_price

    def test_run_calls_wait_for_breakout_when_not_past_stop_time(self):
        """Should call wait_for_breakout when time not past stop_time"""
        mock_rm = Mock()
        mock_rm.positions = []

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            with patch("src.strategies.ram.is_time_past", return_value=False):
                ram = Ram(
                    tradingsymbol="NIFTY05MAY26C23700",
                    strategy="ram",
                    stop_time={"hour": 15, "minute": 30},
                    rm=mock_rm,
                    option_exchange="NFO",
                    quantity=65,
                    ltp=340.0,
                    rest=mock_rest,
                    option_token="123",
                    low_candle_time={"hour": 9, "minute": 14, "second": 59},
                )

                ram.wait_for_breakout = Mock()
                ram._removable = False

                quotes = {"NIFTY05MAY26C23700": "350.0"}
                position_book = []

                ram.run(position_book, quotes)

                ram.wait_for_breakout.assert_called_once()

    def test_run_skips_wait_for_breakout_when_past_stop_time(self):
        """Should skip wait_for_breakout when time is past stop_time"""
        mock_rm = Mock()
        mock_rm.positions = []

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            with patch("src.strategies.ram.is_time_past", return_value=True):
                ram = Ram(
                    tradingsymbol="NIFTY05MAY26C23700",
                    strategy="ram",
                    stop_time={"hour": 15, "minute": 30},
                    rm=mock_rm,
                    option_exchange="NFO",
                    quantity=65,
                    ltp=340.0,
                    rest=mock_rest,
                    option_token="123",
                    low_candle_time={"hour": 9, "minute": 14, "second": 59},
                )

                ram.wait_for_breakout = Mock()
                ram.try_exiting_trade = Mock()

                quotes = {"NIFTY05MAY26C23700": "350.0"}
                position_book = []

                ram.run(position_book, quotes)

                ram.wait_for_breakout.assert_not_called()

    def test_run_calls_try_exiting_trade_when_position_exists_and_target_reached(self):
        """Should call try_exiting_trade when pos_id exists and price > target"""
        mock_rm = Mock()
        mock_rm.positions = []

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            with patch("src.strategies.ram.is_time_past", return_value=False):
                ram = Ram(
                    tradingsymbol="NIFTY05MAY26C23700",
                    strategy="ram",
                    stop_time={"hour": 15, "minute": 30},
                    rm=mock_rm,
                    option_exchange="NFO",
                    quantity=65,
                    ltp=340.0,
                    rest=mock_rest,
                    option_token="123",
                    low_candle_time={"hour": 9, "minute": 14, "second": 59},
                )

                ram.pos_id = 123
                ram._target = 300.0
                ram.wait_for_breakout = Mock()
                ram.try_exiting_trade = Mock()

                quotes = {"NIFTY05MAY26C23700": "350.0"}
                position_book = []

                ram.run(position_book, quotes)

                ram.try_exiting_trade.assert_called_once()

    def test_run_skips_try_exiting_trade_when_no_position(self):
        """Should not call try_exiting_trade when pos_id is None"""
        mock_rm = Mock()
        mock_rm.positions = []

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            with patch("src.strategies.ram.is_time_past", return_value=False):
                ram = Ram(
                    tradingsymbol="NIFTY05MAY26C23700",
                    strategy="ram",
                    stop_time={"hour": 15, "minute": 30},
                    rm=mock_rm,
                    option_exchange="NFO",
                    quantity=65,
                    ltp=340.0,
                    rest=mock_rest,
                    option_token="123",
                    low_candle_time={"hour": 9, "minute": 14, "second": 59},
                )

                ram.pos_id = None
                ram._target = 300.0
                ram.wait_for_breakout = Mock()
                ram.try_exiting_trade = Mock()

                quotes = {"NIFTY05MAY26C23700": "350.0"}
                position_book = []

                ram.run(position_book, quotes)

                ram.try_exiting_trade.assert_not_called()


class TestRamExceptionHandlers:
    """Tests for exception handlers in RAM strategy"""

    def test_wait_for_breakout_exception_handler(self):
        """Should handle exceptions in wait_for_breakout"""
        mock_rm = Mock()
        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            ram = Ram(
                tradingsymbol="NIFTY05MAY26C23700",
                strategy="ram",
                stop_time={"hour": 15, "minute": 30},
                rm=mock_rm,
                option_exchange="NFO",
                quantity=65,
                ltp=340.0,
                rest=mock_rest,
                option_token="123",
                low_candle_time={"hour": 9, "minute": 14, "second": 59},
            )

            # Make transform raise an exception
            ram._candle.transform = Mock(side_effect=Exception("Transform error"))

            # Should not raise
            ram.wait_for_breakout()

    def test_try_exiting_trade_exception_handler(self):
        """Should handle exceptions in try_exiting_trade"""
        mock_rm = Mock()
        mock_rm.status.side_effect = Exception("Status error")

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            ram = Ram(
                tradingsymbol="NIFTY05MAY26C23700",
                strategy="ram",
                stop_time={"hour": 15, "minute": 30},
                rm=mock_rm,
                option_exchange="NFO",
                quantity=65,
                ltp=340.0,
                rest=mock_rest,
                option_token="123",
                low_candle_time={"hour": 9, "minute": 14, "second": 59},
            )

            ram.pos_id = 123
            ram._last_price = 350.0

            # Should not raise
            ram.try_exiting_trade()

    def test_run_exception_handler(self):
        """Should handle exceptions in run method"""
        mock_rm = Mock()
        mock_rm.positions = []

        mock_rest = Mock()
        mock_rest.history.return_value = 100.0

        with patch("src.strategies.ram.timer"):
            ram = Ram(
                tradingsymbol="NIFTY05MAY26C23700",
                strategy="ram",
                stop_time={"hour": 15, "minute": 30},
                rm=mock_rm,
                option_exchange="NFO",
                quantity=65,
                ltp=340.0,
                rest=mock_rest,
                option_token="123",
                low_candle_time={"hour": 9, "minute": 14, "second": 59},
            )

            # Make add_tick raise an exception
            ram._candle.add_tick = Mock(side_effect=Exception("Add tick error"))

            quotes = {"NIFTY05MAY26C23700": "350.0"}
            position_book = []

            # Should not raise
            ram.run(position_book, quotes)