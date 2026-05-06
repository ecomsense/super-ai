import pandas as pd
import pendulum as pdlm


class CandleManager:
    def __init__(self, timeframe_minutes=1):
        self.tf = timeframe_minutes
        self._ticks = []  # List of (timestamp, price)

    def add_tick(self, price, timestamp=None):
        """Accepts ticks with an optional timestamp.

        Args:
            price: The tick price
            timestamp: pendulum DateTime (optional). If not provided, uses current time.
        """
        if timestamp is None:
            timestamp = pdlm.now("Asia/Kolkata")
        self._ticks.append({"dt": timestamp, "price": price})

    def transform(self):
        """Compresses ticks into OHLC and enforces the 5-candle window."""
        if not self._ticks:
            return pd.DataFrame()

        df_ticks = pd.DataFrame(self._ticks)

        # Resample ticks into OHLC based on the timeframe
        # '1T' = 1 minute, '5T' = 5 minutes
        df_ohlc = df_ticks.set_index("dt")["price"].resample(f"{self.tf}min").ohlc()

        # Remove empty rows (intervals with no ticks)
        df_ohlc = df_ohlc.dropna()

        return df_ohlc.reset_index()  # Returns [dt, open, high, low, close]
