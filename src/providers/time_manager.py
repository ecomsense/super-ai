import pendulum

class TimeManager:
    def __init__(self, rest_min: int):
        self.last_trade_time = None
        self.market_open = pendulum.today("Asia/Kolkata").at(9, 0, 0)
        self.market_close = pendulum.today("Asia/Kolkata").at(23, 55, 0)
        self.rest_min = rest_min
        self.candle_times = self._generate_candle_times()

    def _generate_candle_times(self):
        """
        Generate a list of 1-minute candle close times from market open to close.
        e.g., if rest_min=1, market_open=9:00, market_close=9:05
        times = [9:01, 9:02, 9:03, 9:04, 9:05]
        """
        times = []
        current_time = self.market_open
        while current_time < self.market_close:
            next_close_time = current_time.add(minutes=self.rest_min)
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

        now = pendulum.now("Asia/Kolkata")

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
