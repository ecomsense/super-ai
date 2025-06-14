from constants import logging, O_SETG
from helper import Helper
from traceback import print_exc
from time_manager import TimeManager
import pendulum as pdlm
from trade import Trade


class Grid:
    ohlc = {}

    @classmethod
    def run(
        cls,
        api,
        prefix,
        exchange,
        tradingsymbol,
    ):
        if cls.ohlc.get(prefix, None) is None:
            start = pdlm.now().subtract(days=4).timestamp()
            now = pdlm.now().timestamp()
            ret = api.broker.get_daily_price_series(
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                startdate=start,
                enddate=now,
            )
            cls.ohlc["prefix"] = ret
        return cls.ohlc[prefix]


class Pivot:

    def __init__(self, prefix: str, symbol_info: dict, user_settings: dict, pivot_grid):
        print(pivot_grid)
        self._id = symbol_info["symbol"]
        self._buy_order = {}
        self._fill_price = 0
        self._sell_order = None
        self._orders = []
        self._target_price = None
        self._removable = False
        self._trade_manager = None
        self._reduced_target_sequence = 0
        self._t1 = user_settings["t1"]
        self._t2 = user_settings["t2"]
        self._prefix = prefix
        self.trade = Trade(
            symbol=symbol_info["symbol"],
            last_price=symbol_info["ltp"],
            exchange=user_settings["option_exchange"],
            quantity=user_settings["quantity"],
        )
        self._low = float(symbol_info["low"])
        self._stop = symbol_info["low"]
        self._target = self._t1
        self._txn = user_settings["txn"]
        self._time_mgr = TimeManager(rest_min=user_settings["rest_min"])
        self._fn = "wait_for_breakout"

    def wait_for_breakout(self):
        print("waiting for breakout")

    def run(self, orders, ltps, underlying_ltp):
        try:
            self._orders = orders

            ltp = ltps.get(self.trade.symbol, None)
            if ltp is not None:
                self.trade.last_price = float(ltp)

            return getattr(self, self._fn)()
        except Exception as e:
            logging.error(f"{e} in running {self.trade.symbol}")
            print_exc()
