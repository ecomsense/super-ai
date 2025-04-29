import pendulum


class TimeManager:
    def __init__(self, rest_min: int):
        self.last_trade_time = None
        self.market_open = pendulum.today().at(9, 0, 0)  # Market starts at 9:00 AM
        self.market_close = pendulum.today().at(23, 55, 0)  # Market closes at 3:30 PM
        self.rest_min = rest_min
        self.candle_times = self._generate_candle_times()

    def _generate_candle_times(self):
        """Generate a list of 1-minute candle close times from market open to close."""
        times = []
        time = self.market_open
        while time < self.market_close:
            time = time.add(minutes=self.rest_min)
            times.append(time)
        return times

    def set_last_trade_time(self, trade_time):
        self.last_trade_time = trade_time

    @property
    def can_trade(self):
        """Finds the index of the candle where the trade happened."""
        if self.last_trade_time is None:
            return True

        index = None
        for i, candle_close in enumerate(self.candle_times):
            if self.candle_times[i - 1] <= self.last_trade_time < candle_close:
                index = i
                break

        now = pendulum.now("Asia/Kolkata")
        if index is None:
            return False
        elif now > self.candle_times[index]:
            print(now, "is greater than", self.candle_times[index])
            return True
        return False


if __name__ == "__main__":
    import time

    mgr = TimeManager()

    while True:
        time.sleep(1)
        print(mgr.can_trade)
