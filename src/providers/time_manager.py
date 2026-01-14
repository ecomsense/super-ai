import pendulum as pdlm


class TimeManager:
    def __init__(self, rest_time: dict):
        self.last_trade_time = None
        self.market_open = pdlm.today("Asia/Kolkata").at(9, 0, 0)
        self.market_close = pdlm.today("Asia/Kolkata").at(23, 55, 0)
        self.candle_times = self._generate_candle_times(rest_time)

    def _generate_candle_times(self, rest_time):
        """
        Generate a list of 1-minute candle close times from market open to close.
        e.g., if rest_min=1, market_open=9:00, market_close=9:05
        times = [9:01, 9:02, 9:03, 9:04, 9:05]
        """
        times = []
        current_time = self.market_open
        while current_time < self.market_close:
            next_close_time = current_time.add(**rest_time)
            # Ensure we don't go past market close if the last interval overlaps
            if next_close_time <= self.market_close:
                times.append(next_close_time)
            else:
                # If the next interval would cross market_close, include market_close itself as the last point
                if (
                    current_time < self.market_close
                ):  # Only if there's still time left in the market
                    times.append(self.market_close)
                break  # Stop generating beyond market close
            current_time = next_close_time
        return times

    def set_last_trade_time(self, trade_time):
        self.last_trade_time = trade_time

    @property
    def can_trade(self):
        """
        Determines if a trade can be made based on the last trade time
        and the defined rest period.
        """
        if self.last_trade_time is None:
            return True  # No previous trade, so a trade can be made

        # Find the candle close time corresponding to the last_trade_time
        target_candle_close = None

        # Check if last_trade_time is within the first interval [market_open, self.candle_times[0])
        if (
            self.last_trade_time >= self.market_open
            and self.last_trade_time < self.candle_times[0]
        ):
            target_candle_close = self.candle_times[0]
        else:
            # Iterate through the candle_times to find which interval last_trade_time falls into
            # For subsequent intervals [self.candle_times[i-1], self.candle_times[i])
            for i in range(1, len(self.candle_times)):
                if (
                    self.candle_times[i - 1]
                    <= self.last_trade_time
                    < self.candle_times[i]
                ):
                    target_candle_close = self.candle_times[i]
                    break
            # Handle the case where last_trade_time is exactly the last candle close (e.g., market close itself)
            if (
                target_candle_close is None
                and len(self.candle_times) > 0
                and self.last_trade_time == self.candle_times[-1]
            ):
                target_candle_close = self.candle_times[-1]

        now = pdlm.now("Asia/Kolkata")

        if target_candle_close is None:
            # This means last_trade_time was outside any defined valid interval,
            # either before market_open or after the market_close.
            # In such cases, no trade should be allowed based on this last_trade_time,
            # or it indicates the trading day is over relative to that last trade.
            return False
        elif now > target_candle_close:
            # The "rest_min" period for that trade has elapsed
            return True
        else:
            # The "rest_min" period has not yet elapsed
            return False

    @property
    def current_index(self):
        """
        Returns the index of the last completed candle.
        Returns -1 if the market hasn't reached the first candle close.
        """
        now = pdlm.now("Asia/Kolkata")
        # Find the highest index where candle_time <= now
        idx = -1
        for i, candle_time in enumerate(self.candle_times):
            if now >= candle_time:
                idx = i
            else:
                break
        return idx


class Gate:
    """Allows action only if 'interval' seconds have passed since last allow()."""

    def __init__(self, interval: dict):
        self.interval = interval
        self._next_time = pdlm.now("Asia/Kolkata")

    def allow(self) -> bool:
        now = pdlm.now()
        if now >= self._next_time:
            self._next_time = now.add(**self.interval)
            return True
        return False


class Bucket:
    """Limit N events every M seconds — never earlier.
    Uses Fixed Window Counter approach.
    """

    def __init__(self, period: dict, max_trades: int):
        self.period = period
        self.max_trades = max_trades
        self.reset()

    def reset(self):
        now = pdlm.now("Asia/Kolkata")
        # Ensure the bucket_end calculation handles the 'period' dict correctly
        self.bucket_end = now.add(**self.period)
        self.count = 0

    def can_allow(self) -> bool:
        """Checks if a trade can occur WITHOUT consuming a count."""
        now = pdlm.now("Asia/Kolkata")

        # Check for expiry first and reset if necessary
        if now >= self.bucket_end:
            self.reset()

        # Check if we are below the trade limit
        return self.count < self.max_trades

    def allow(self) -> bool:
        """Consumes a trade count ONLY if allowed."""

        # Check if the trade is allowed using the safe check
        if self.can_allow():
            self.count += 1
            return True

        return False


class SimpleBucket:
    def __init__(self, bucket_time: dict):
        self._bucket_time = bucket_time
        self._next_bucket = None

    def set_bucket(self):
        """
        set next time of trade
        """
        now = pdlm.now("Asia/Kolkata")
        self._next_bucket = now.add(**self._bucket_time)

    def is_bucket(self):
        if self._next_bucket and pdlm.now("Asia/Kolkata") > self._next_bucket:
            return True
        return False
