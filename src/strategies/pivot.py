from constants import logging, O_SETG
from helper import Helper
from traceback import print_exc
from time_manager import TimeManager
import pendulum as pdlm
from trade import Trade
from json import loads


def compute(ohlc_prefix):
    try:
        high, low, close = (
            float(ohlc_prefix["inth"]),
            float(ohlc_prefix["intl"]),
            float(ohlc_prefix["intc"]),
        )
        pivot = (high + low + close) / 3.0
        """
        bc = (high + low) / 2.0
        tc = (pivot - bc) + pivot
        """
        R3 = high + (2 * (pivot - low))
        R2 = pivot + (high - low)
        R1 = (2 * pivot) - low
        S1 = (2 * pivot) - high
        S2 = pivot - (high - low)
        S3 = low - (2 * (high - pivot))
        R4 = R3 + R2 + R1 + pivot + S1 + S2 + S3
        lst = [R4, R3, R2, R1, pivot, S1, S2, S3, 0]
        lst = [int(item) for item in lst]
        print("compute", lst)
        return lst
    except Exception as e:
        logging.error(f"{e} while computing grid")
        print_exc()


class Grid:
    grid = {}

    @classmethod
    def run(cls, api, prefix, symbol_constant):
        try:
            if cls.grid.get(prefix, None) is None:
                start = pdlm.now().subtract(days=4).timestamp()
                now = pdlm.now().timestamp()
                ret = api.broker.get_daily_price_series(
                    exchange=symbol_constant[prefix]["exchange"],
                    tradingsymbol=symbol_constant[prefix]["index"],
                    startdate=start,
                    enddate=now,
                )
                ohlc = loads(ret[0])
                cls.grid[prefix] = compute(ohlc)
            return cls.grid[prefix]
        except Exception as e:
            logging.error(f"{e} while computing grid")
            print_exc()


class Gridlines:
    def __init__(self, prices: list, reverse: bool):
        print("prices", prices)
        levels = sorted(prices, reverse=reverse)
        self.lines = list(zip(levels[:-1], levels[1:]))
        print("gridlines", self.lines)

    def find_current_grid(self, ltp: float):
        for idx, (a, b) in enumerate(self.lines):
            low, high = min(a, b), max(a, b)
            if low <= ltp < high:
                return idx


class Pivot:
    def __init__(
        self, prefix: str, symbol_info: dict, user_settings: dict, pivot_grids
    ):
        self._removable = False
        self._prefix = prefix
        self._id = symbol_info["symbol"]
        self.trade = Trade(
            symbol=symbol_info["symbol"],
            last_price=symbol_info["ltp"],
            exchange=user_settings["option_exchange"],
            quantity=user_settings["quantity"],
        )
        self._time_mgr = TimeManager(rest_min=user_settings["rest_min"])
        option_type = "PE"
        reverse = True if option_type == "PE" else False
        self.lines = Gridlines(prices=pivot_grids, reverse=reverse)
        self.curr_idx = 100
        self._fn = "wait_for_breakout"

    @property
    def curr_idx(self):
        return self._curr_idx

    @curr_idx.setter
    def curr_idx(self, idx):
        self._curr_idx = idx

    def wait_for_breakout(self):
        try:
            idx = self.lines.find_current_grid(self.underlying_ltp)
            if idx > self.curr_idx:
                pass
            print("breakout")
            self.curr_idx = idx
        except Exception as e:
            logging.error(f"{e} in wait_for_breakout")
            print_exc()

    def run(self, orders, ltps, underlying_ltp):
        try:
            print("underlying_ltp", underlying_ltp)
            self._orders = orders

            ltp = ltps.get(self.trade.symbol, None)
            if ltp is not None:
                self.trade.last_price = float(ltp)

            self.underlying_ltp = underlying_ltp

            return getattr(self, self._fn)()
        except Exception as e:
            logging.error(f"{e} in running {self.trade.symbol}")
            print_exc()


"""
into = history(
    api=api,
    exchange=symbol_constant[prefix]["exchange"],
    token=symbol_constant[prefix]["token"],
    loc=-1,
    key="into",
)
cls.grid[prefix]["into"] = into
"""
