from src.constants import logging_func

from toolkit.kokoo import is_time_past
from src.sdk.helper import Helper

from src.providers.trade_manager import TradeManager
from src.providers.time_manager import TimeManager
from src.providers.grid import Gridlines

from traceback import print_exc

logging = logging_func(__name__)


class Pivot:

    def __init__(self, **kwargs):
        # initialize
        self._trades = []

        # from parameters
        self.strategy = kwargs["strategy"]
        self.stop_time = kwargs["stop_time"]
        self._rest = kwargs["rest"]

        self.option_type = kwargs["option_type"]
        self._option_token = kwargs["option_token"]
        self._option_exchange = kwargs["option_exchange"]
        self._quantity = kwargs["quantity"]
        self._tradingsymbol = kwargs["tradingsymbol"]

        self._last_price = kwargs.get("ltp", 10000)

        prices = [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200]
        self.gridlines = Gridlines(prices=prices, reverse=False)
        self._price_idx = 100
        self._is_breakout = False
        self._stop = None

        self.time_mgr = TimeManager({"minutes": 1})
        self._time_idx = self.time_mgr.current_index
        # objects and dependencies
        self.trade_mgr = TradeManager(
            stock_broker=Helper.api(),
            symbol=self._tradingsymbol,
            exchange=self._option_exchange,
            quantity=self._quantity,
            tag=self.strategy,
        )

        # state variables
        self._removable = False
        self._fn = "is_breakout"

    def is_breakout(self):
        try:

            if self._is_breakout:
                # 3. place entry
                order_id = self.trade_mgr.complete_entry(price=self._last_price + 2)
                if order_id:
                    self._fn = "place_exit_order"
                    return

        except Exception as e:
            logging.error(f"{e} while waiting for breakout")
            print_exc()

    def place_exit_order(self):
        try:
            sell_order = self.trade_mgr.pending_exit(
                stop=self._stop, orders=self._trades, last_price=self._last_price
            )
            if sell_order.order_id:
                self.trade_mgr.target(target_price=self._target)
                self._fn = "try_exiting_trade"
        except Exception as e:
            logging.error(f"{e} while place exit order")
            print_exc()

    def try_exiting_trade(self):
        try:
            if self.trade_mgr.is_trade_exited(
                self._last_price, self._trades, self._removable
            ):
                self._fn = "is_breakout"
            else:
                logging.debug(
                    f"Progress: {self._tradingsymbol} stop:{self._stop} < ltp:{self._last_price} < target:{self._target}"
                )
        except Exception as e:
            logging.error(f"{e} while exit order")
            print_exc()

    def remove_me(self):
        if self._fn == "place_exit_order":
            self.place_exit_order()
            return

        if self._fn == "try_exiting_trade":
            status = self.trade_mgr.is_trade_exited(
                self._last_price, self._trades, True
            )
            assert status == 3
            self._fn = "wait_for_breakout"

        self._removable = True
        logging.info(
            f"REMOVING: {self._tradingsymbol} switching from waiting for breakout"
        )

    def run(self, trades, quotes, positions):
        try:

            # time
            is_removable = is_time_past(self.stop_time)
            if is_removable:
                if self.remove_me():
                    return

            curr = self.time_mgr.current_index
            if curr == self._time_idx:
                return
            self._time_idx = curr

            # price
            ltp = quotes.get(self._tradingsymbol, None)
            if ltp is not None:
                self._last_price = float(ltp)

            curr_price = self.gridlines.find_current_grid(self._last_price)
            self._is_breakout = curr_price > self._price_idx
            self._price_idx = curr_price

            self._trades = trades

            return getattr(self, self._fn)()
        except Exception as e:
            logging.error(f"{e} in running {self._tradingsymbol}")
            print_exc()
