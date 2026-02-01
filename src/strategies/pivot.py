from src.constants import logging_func

from toolkit.kokoo import is_time_past
from src.sdk.helper import Helper
from src.sdk.utils import round_down_to_tick

from src.providers.trade_manager import TradeManager
from src.providers.time_manager import TimeManager
from src.providers.grid import Gridlines
from src.providers.utils import table

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
        self._target = None

        self.time_mgr = TimeManager({"minutes": 1})
        self._time_idx = 0
        # objects and dependencies
        self.trade_mgr = TradeManager(
            stock_broker=Helper.api(),
            symbol=self._tradingsymbol,
            exchange=self._option_exchange,
            quantity=self._quantity,
            tag=self.strategy,
        )
        self._count = 1
        # state variables
        self._removable = False
        self._fn = "is_breakout"

    def is_breakout(self):
        try:

            if self._is_breakout:

                self._count += 1

                if self._count % 2 == 0:
                    # 3. place entry
                    order_id = self.trade_mgr.complete_entry(price=self._last_price)
                    if order_id:
                        self._fn = "place_exit_order"
                        return
                else:
                    logging.debug(
                        f"SKIPPING TRADE# {self._count-2}: ltp:{self._last_price} pivot:{self._stop}"
                    )

        except Exception as e:
            logging.error(f"{e} while waiting for breakout")
            print_exc()

    def _set_new_stop(self):
        stop = self._stop
        fill = self.trade_mgr.position.average_price
        buffer = (fill - stop) / 2
        new_stop = fill + buffer
        rounded_ltp = round_down_to_tick(last_price=new_stop)
        self.trade_mgr.stop(stop_price=rounded_ltp)

    def place_exit_order(self):
        try:
            sell_order = self.trade_mgr.pending_exit(
                stop=self._stop, orders=self._trades, last_price=self._last_price
            )

            if sell_order and sell_order.order_id:

                self.trade_mgr.target(target_price=self._target)

                self._set_new_stop()

                self._fn = "try_exiting_trade"
        except Exception as e:
            logging.error(f"{e} while place exit order")
            print_exc()

    def try_exiting_trade(self):
        try:
            if self.trade_mgr.is_trade_exited(self._last_price, self._trades):
                self._fn = "is_breakout"
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
            if status > 0:
                self._fn = "remove_me"
            return

        self._removable = True

    def run(self, trades, quotes, positions):
        try:

            """needed for removing the object"""

            self._trades = trades

            ltp = quotes.get(self._tradingsymbol, None)
            if ltp is not None:
                self._last_price = float(ltp)

            if is_time_past(self.stop_time):
                logging.info(f"REMOVING: {self._tradingsymbol} .. ")
                self.remove_me()
                return

            curr = self.time_mgr.current_index
            if self._fn == "is_breakout":
                if curr == self._time_idx:
                    return
                else:
                    logging.debug(f"New Candle: {ltp}")
            self._time_idx = curr

            """ update truth of indices if there is a breakout """
            price_idx, stop, target = self.gridlines.find_current_grid(self._last_price)

            self._is_breakout = price_idx > self._price_idx
            if self._is_breakout:
                self._stop = stop
                self._target = target
                logging.debug(f"Breakout: temp {stop=} < {ltp=} < {target=} ")
            self._price_idx = price_idx

            table(self)
            return getattr(self, self._fn)()
        except Exception as e:
            logging.error(f"{e} in running {self._tradingsymbol}")
            print_exc()
