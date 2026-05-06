"""
Tests for optimized CandleManager
"""
import pytest
import pendulum as pdlm
from src.providers.candle_manager import CandleManager


class TestCandleManager:
    
    def test_first_tick_creates_current(self):
        """First tick should create current candle."""
        cm = CandleManager()
        cm.add_tick(100.0)
        
        assert cm._current is not None
        assert cm._current["open"] == 100.0
        assert cm._current["close"] == 100.0
    
    def test_tick_updates_current(self):
        """Subsequent ticks update current candle OHLC."""
        cm = CandleManager()
        cm.add_tick(100.0)
        cm.add_tick(105.0)
        cm.add_tick(98.0)
        
        assert cm._current["open"] == 100.0
        assert cm._current["high"] == 105.0
        assert cm._current["low"] == 98.0
        assert cm._current["close"] == 98.0
    
    def test_new_minute_closes_current(self):
        """New minute should close current and move to completed."""
        cm = CandleManager()
        
        # Add tick at minute X
        cm._current = {"open": 100, "high": 100, "low": 100, "close": 100, 
                      "minute": pdlm.now("Asia/Kolkata").start_of("minute")}
        
        # Simulate tick in next minute (by manually setting)
        next_min = cm._current["minute"].add(minutes=1)
        cm._current["minute"] = next_min
        cm.add_tick(101.0)  # This closes and starts new
        
        # Current should be new, completed should have previous
        assert len(cm._completed) == 1
    
    def test_transform_returns_dataframe(self):
        """transform() should return DataFrame for compatibility."""
        cm = CandleManager()
        cm.add_tick(100.0)
        cm.add_tick(101.0)
        
        df = cm.transform()
        
        assert not df.empty
        assert "open" in df.columns
        assert "high" in df.columns
        assert "low" in df.columns
        assert "close" in df.columns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])