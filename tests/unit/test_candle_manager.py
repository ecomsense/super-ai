"""
Tests for CandleManager
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
    
    def test_tick_updates_ohlc(self):
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
        
        # Set first minute
        cm._current = {"open": 100, "high": 100, "low": 100, "close": 100, 
                      "minute": pdlm.now("Asia/Kolkata").start_of("minute")}
        
        # Change to next minute
        cm._current["minute"] = cm._current["minute"].add(minutes=1)
        cm.add_tick(101.0)
        
        assert len(cm._completed) == 1
        assert cm._current is not None
    
    def test_get_candles_returns_list(self):
        """get_candles() should return list of dicts."""
        cm = CandleManager()
        cm.add_tick(100.0)
        cm.add_tick(101.0)
        
        candles = cm.get_candles()
        
        assert isinstance(candles, list)
        assert len(candles) > 0
        assert "open" in candles[0]
        assert "high" in candles[0]
        assert "low" in candles[0]
        assert "close" in candles[0]
    
    def test_len_returns_candle_count(self):
        """len() should return candle count."""
        cm = CandleManager()
        cm.add_tick(100.0)
        
        assert len(cm) == 1
    
    def test_two_candle_pattern_access(self):
        """Can access -1, -2, -3 indices like ram.py does."""
        cm = CandleManager()
        
        # Add ticks for 3 different minutes
        base = pdlm.now("Asia/Kolkata").start_of("minute")
        
        # Minute 0
        cm._current = {"open": 100, "high": 105, "low": 98, "close": 103, "minute": base}
        cm._completed.append(cm._current)
        
        # Minute 1
        cm._current = {"open": 103, "high": 108, "low": 101, "close": 105, "minute": base.add(minutes=1)}
        cm._completed.append(cm._current)
        
        # Current (minute 2)
        cm._current = {"open": 105, "high": 110, "low": 103, "close": 107, "minute": base.add(minutes=2)}
        
        candles = cm.get_candles()
        
        # Direct access like ram.py now uses
        assert candles[-1]["close"] == 107
        assert candles[-2]["close"] == 105
        assert candles[-3]["close"] == 103


if __name__ == "__main__":
    pytest.main([__file__, "-v"])