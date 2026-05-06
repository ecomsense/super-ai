"""
Tests for CandleManager
"""
import pytest
import pendulum as pdlm
from src.providers.candle_manager import CandleManager


class TestCandleManager:
    
    def test_consecutive_ticks_get_unique_timestamps(self):
        """Each tick should get a unique timestamp, even if added rapidly."""
        cm = CandleManager(timeframe_minutes=1)
        
        # Add multiple ticks without timestamp (like real-time trading)
        cm.add_tick(100.0)
        cm.add_tick(101.0)
        cm.add_tick(102.0)
        
        # Each should have unique timestamp
        timestamps = [t["dt"] for t in cm._ticks]
        
        assert len(set(timestamps)) == 3, "All timestamps should be unique"
        
    def test_resample_works_with_unique_timestamps(self):
        """Unique timestamps should make resample predictable."""
        cm = CandleManager(timeframe_minutes=1)
        
        base = pdlm.now("Asia/Kolkata")
        cm._ticks = [
            {"dt": base, "price": 100.0},
            {"dt": base.add(seconds=30), "price": 105.0},
            {"dt": base.add(minutes=1), "price": 101.0},
        ]
        
        df = cm.transform()
        
        assert len(df) == 2, "Should get 2 candles across 2 different minutes"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])