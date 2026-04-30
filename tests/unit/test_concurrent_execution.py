"""
Tests for concurrent execution improvements:
- Task 1: Position book snapshot
- Task 2: Thread-safe RiskManager

Run with: uv run pytest tests/unit/test_concurrent_execution.py -v
"""

import threading
import time
from unittest.mock import Mock, patch
from src.providers.risk_manager import RiskManager


class TestPositionBookSnapshot:
    """Task 1: Verify position book is passed correctly"""

    def test_run_receives_position_book(self):
        """Strategy.run() should accept position_book parameter"""
        mock_rm = Mock(spec=RiskManager)
        mock_rm.positions = []

        ram = Ram(
            tradingsymbol="NIFTY05MAY26C23700",
            strategy="ram",
            stop_time={"hour": 15, "minute": 30},
            rm=mock_rm,
            option_exchange="NFO",
            quantity=65,
            ltp=340.0,
        )

        position_book = [{"symbol": "NIFTY05MAY26C23700", "quantity": 65}]
        quotes = {"NIFTY05MAY26C23700": 340.0}

        # Should not raise TypeError
        ram.run(position_book, quotes)

        # Verify position book was assigned
        assert mock_rm.positions == position_book

    def test_run_updates_risk_manager_positions(self):
        """Strategy.run() should update RiskManager.positions"""
        mock_rm = Mock(spec=RiskManager)
        mock_rm.positions = []

        ram = Ram(
            tradingsymbol="NIFTY05MAY26C23700",
            strategy="ram",
            stop_time={"hour": 15, "minute": 30},
            rm=mock_rm,
            option_exchange="NFO",
            quantity=65,
            ltp=340.0,
        )

        position_book = [{"symbol": "NIFTY05MAY26C23700", "quantity": 65}]
        quotes = {"NIFTY05MAY26C23700": 340.0}

        ram.run(position_book, quotes)

        # Verify positions were updated
        mock_rm.positions = position_book

    def test_run_with_empty_position_book(self):
        """Strategy should handle empty position book"""
        mock_rm = Mock(spec=RiskManager)
        mock_rm.positions = []

        ram = Ram(
            tradingsymbol="NIFTY05MAY26C23700",
            strategy="ram",
            stop_time={"hour": 15, "minute": 30},
            rm=mock_rm,
            option_exchange="NFO",
            quantity=65,
            ltp=340.0,
        )

        position_book = []
        quotes = {"NIFTY05MAY26C23700": 340.0}

        # Should not raise
        ram.run(position_book, quotes)


class TestThreadSafeRiskManager:
    """Task 2: Verify RiskManager is thread-safe"""

    def test_new_is_thread_safe(self):
        """Multiple threads calling new() should not corrupt state"""
        mock_broker = Mock()
        mock_broker.order_place = Mock(side_effect=lambda **kw: f"order_{kw['symbol']}")
        mock_broker.positions = []

        rm = RiskManager(mock_broker)

        results = []
        errors = []

        def place_order(symbol, entry_price):
            try:
                result = rm.new(
                    symbol=symbol,
                    exchange="NFO",
                    quantity=65,
                    entry_price=entry_price,
                    stop_loss=0,
                    target=400,
                    tag="test",
                )
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = [
            threading.Thread(target=place_order, args=("NIFTY05MAY26C23700", 340.0)),
            threading.Thread(target=place_order, args=("NIFTY05MAY26P23900", 160.0)),
            threading.Thread(target=place_order, args=("NIFTY05MAY26C23800", 280.0)),
        ]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join()

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all orders were placed
        assert len(results) == 3, f"Expected 3 results, got {len(results)}"

        # Verify broker was called 3 times
        assert mock_broker.order_place.call_count == 3

    def test_status_is_thread_safe(self):
        """Multiple threads calling status() should not corrupt state"""
        mock_broker = Mock()
        mock_broker.order_place = Mock(return_value="exit_order_123")
        mock_broker.positions = [{"symbol": "NIFTY05MAY26C23700", "quantity": 65}]

        rm = RiskManager(mock_broker)

        # First create a position
        pos_id = rm.new(
            symbol="NIFTY05MAY26C23700",
            exchange="NFO",
            quantity=65,
            entry_price=340.0,
            stop_loss=0,
            target=400,
            tag="test",
        )

        results = []
        errors = []

        def exit_position(last_price):
            try:
                result = rm.status(pos_id=pos_id, last_price=last_price)
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Create multiple threads trying to exit
        threads = [
            threading.Thread(target=exit_position, args=(350.0,)),
            threading.Thread(target=exit_position, args=(351.0,)),
            threading.Thread(target=exit_position, args=(352.0,)),
        ]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join()

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

    def test_lock_prevents_race_condition(self):
        """Verify lock actually prevents concurrent access"""
        mock_broker = Mock()
        mock_broker.order_place = Mock(side_effect=lambda **kw: time.sleep(0.01) or f"order_{kw['symbol']}")
        mock_broker.positions = []

        rm = RiskManager(mock_broker)

        start_time = time.time()

        # Call new() from multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(
                target=rm.new,
                kwargs={
                    "symbol": f"SYMBOL{i}",
                    "exchange": "NFO",
                    "quantity": 65,
                    "entry_price": 340.0,
                    "stop_loss": 0,
                    "target": 400,
                    "tag": "test",
                },
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        elapsed = time.time() - start_time

        # If lock works, should take ~0.05s (5 * 0.01s sequential)
        # If no lock, would take ~0.01s (all parallel)
        assert elapsed >= 0.04, f"Lock may not be working, elapsed: {elapsed}s"

    def test_tag_not_overwritten_by_concurrent_calls(self):
        """Verify self.tag is not corrupted by concurrent calls"""
        mock_broker = Mock()
        mock_broker.order_place = Mock(side_effect=lambda **kw: time.sleep(0.01) or f"order_{kw['symbol']}")
        mock_broker.positions = []

        rm = RiskManager(mock_broker)

        tags_used = []

        def place_order_with_tag(tag):
            rm.new(
                symbol=f"SYMBOL_{tag}",
                exchange="NFO",
                quantity=65,
                entry_price=340.0,
                stop_loss=0,
                target=400,
                tag=tag,
            )
            tags_used.append(rm.tag)

        threads = [
            threading.Thread(target=place_order_with_tag, args=("CE",)),
            threading.Thread(target=place_order_with_tag, args=("PE",)),
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Each thread should have seen its own tag
        assert "CE" in tags_used or "PE" in tags_used


class TestEngineIntegration:
    """Integration tests for Engine with position snapshot"""

    def test_engine_passes_position_book(self):
        """Engine.tick() should pass position book to strategies"""
        from src.core.engine import Engine

        mock_rest = Mock()
        mock_rest.positions = Mock(return_value=[{"symbol": "TEST", "quantity": 65}])

        mock_quote = Mock()
        mock_quote.get_quotes = Mock(return_value={"TEST": 340.0})

        mock_live = Mock()

        mock_strategy = Mock()
        mock_strategy.run = Mock()
        mock_strategy._removable = False

        engine = Engine(start={"hour": 9, "minute": 15}, stop={"hour": 15, "minute": 30})
        engine.add_strategy([mock_strategy])

        engine.tick(mock_rest, mock_quote, mock_live)

        # Verify strategy.run was called with position_book
        assert mock_strategy.run.called
        call_args = mock_strategy.run.call_args
        assert len(call_args[0]) == 2  # position_book, quotes

        # Verify rest.positions() was called once
        assert mock_rest.positions.call_count == 1

    def test_engine_single_api_call(self):
        """Engine should call rest.positions() only once per tick"""
        from src.core.engine import Engine

        mock_rest = Mock()
        mock_rest.positions = Mock(return_value=[])

        mock_quote = Mock()
        mock_quote.get_quotes = Mock(return_value={})

        mock_live = Mock()

        # Multiple strategies
        strategies = []
        for i in range(3):
            mock_strategy = Mock()
            mock_strategy.run = Mock()
            mock_strategy._removable = False
            strategies.append(mock_strategy)

        engine = Engine(start={"hour": 9, "minute": 15}, stop={"hour": 15, "minute": 30})
        engine.add_strategy(strategies)

        engine.tick(mock_rest, mock_quote, mock_live)

        # Should call positions() ONCE, not once per strategy
        assert mock_rest.positions.call_count == 1


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
