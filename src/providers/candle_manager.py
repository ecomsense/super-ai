import pandas as pd
import pendulum as pdlm


class CandleManager:
    def __init__(self, timeframe_minutes=1):
        self.tf = timeframe_minutes
        self._completed = []  # Completed candles
        self._current = None
        self._tick_counter = 0
        
    def add_tick(self, price):
        """Incrementally track candles - O(1) operation."""
        self._tick_counter += 1
        now = pdlm.now("Asia/Kolkata").add(microseconds=self._tick_counter)
        current_min = now.start_of("minute")
        
        if self._current is None:
            self._current = {"open": price, "high": price, "low": price, "close": price, "minute": current_min}
            return
        
        if current_min != self._current["minute"]:
            self._completed.append(self._current)
            if len(self._completed) > 10:  # Store more for safety
                self._completed.pop(0)
            self._current = {"open": price, "high": price, "low": price, "close": price, "minute": current_min}
            return
        
        self._current["close"] = price
        self._current["high"] = max(self._current["high"], price)
        self._current["low"] = min(self._current["low"], price)
    
    def transform(self):
        """Returns candles as DataFrame (for compatibility)."""
        candles = self._completed.copy()
        if self._current:
            candles.append(self._current)
        
        if not candles:
            return pd.DataFrame()
        
        n = len(candles)
        base = pdlm.now("Asia/Kolkata").start_of("minute")
        dts = [base.subtract(minutes=n-1-i) for i in range(n)]
        
        df = pd.DataFrame(candles)
        df["dt"] = dts
        return df[["dt", "open", "high", "low", "close"]]
    
    def get_candles(self):
        """Returns list of candles as dicts - direct access without DataFrame."""
        candles = self._completed.copy()
        if self._current:
            candles.append(self._current)
        return candles
    
    def __len__(self):
        """Returns count of available candles."""
        count = len(self._completed)
        if self._current:
            count += 1
        return count