from src.constants import logging_func

from src.sdk.helper import Helper
from src.providers.grid import Grid, pivot_to_stop_and_target

from src.providers.time_manager import Bucket, SimpleBucket
from src.providers.trade_manager import TradeManager

from traceback import print_exc

logging = logging_func(__name__)


class Newpivot:

    def __init__(
        self,
        prefix: str,
        symbol_info: dict,
        user_settings: dict,
        rest,
    ):
        # A hard coded
        self._removable = False

        # 1. Core Attributes (directly from parameters)
        self._rest = rest
        self._prefix = prefix
        self._option_type = symbol_info["option_type"]
        self._token = symbol_info["token"]
        self._quantity = user_settings["quantity"]

        # 3. Dependencies and Helper Objects
        self._symbol = symbol_info["symbol"]
        self._last_price = symbol_info["ltp"]

        # new
        self._prev_price = self._last_price
        self._small_bucket = Bucket(user_settings["small_bucket"], 1)
        self._big_bucket = Bucket(
            period=user_settings["big_bucket"],
            max_trades=user_settings["max_trade_in_bucket"],
        )
        self._simple = SimpleBucket(user_settings["big_bucket"])

        self.trade_mgr = TradeManager(
            stock_broker=Helper.api(),
            symbol=self._symbol,
            exchange=user_settings["option_exchange"],
        )

        rst = Helper._rest
        resp = Grid().get(
            rst=rst,
            exchange=user_settings["option_exchange"],
            tradingsymbol=self._symbol,
            token=self._token,
        )
        self._levels = pivot_to_stop_and_target(pivots=resp)
        logging.info(f"pivot levels: {self._levels}")
        """
        initial trade low condition
        """
        self._fn = "is_breakout"

    def _is_tradeable(self, stop, ltp, target):
        half = target / stop
        max = stop + half
        return ltp < max

    def is_breakout(self):
        try:

            # 1. are we with the trade limits of time buckets
            if not self._small_bucket.can_allow():
                print(f"small BUCKET full: {self._symbol} skipping trading")
                return
            if not self._big_bucket.can_allow():
                print(f"BIG BUCKET FULL: {self._symbol} skipping trading")
                return

            # 2 check actual breakout condition
            for self._stop, self._target in self._levels:
                if self._last_price > self._target:
                    print(
                        f"{self._symbol} ltp:{self._last_price} > target:{self._target} returning"
                    )
                    continue

                if self._last_price > self._stop:
                    logging.info(
                        f"ltp:{self._last_price} > stop:{self._stop} when prev_price={self._prev_price}"
                    )
                    if self._prev_price <= self._stop or (
                        self._simple.is_bucket()
                        and self._is_tradeable(
                            stop=self._stop, ltp=self._last_price, target=self._target
                        )
                    ):
                        # 3. place entry
                        order_id = self.trade_mgr.complete_entry(
                            quantity=self._quantity, price=self._last_price + 2
                        )
                        if order_id:
                            self._simple._next_bucket = None
                            # 4. consume tokens
                            self._small_bucket.allow()
                            self._big_bucket.allow()
                            self._fn = "place_exit_order"
                            return
                        else:
                            logging.warning(f"{self._symbol} without order id")
                            return

            # 1.2. check actual breakout condition
            logging.debug(
                f"No Breakout: {self._symbol}  {self._prev_price} > {self._levels} or < {self._last_price} "
            )

        except Exception as e:
            logging.error(f"{e} while waiting for breakout")
            print_exc()

    def place_exit_order(self):
        try:
            sell_order = self.trade_mgr.pending_exit(
                stop=self._stop, orders=self._orders
            )
            if sell_order.order_id:
                self.trade_mgr.target(target_price=self._target)
                self._fn = "try_exiting_trade"
        except Exception as e:
            logging.error(f"{e} while place exit order")
            print_exc()

    def try_exiting_trade(self):
        try:
            if self.trade_mgr.is_trade_exited(self._last_price, self._orders):
                self._simple.set_bucket()
                self._fn = "is_breakout"
            else:
                logging.debug(
                    f"Progress: {self._symbol} stop:{self._stop} < ltp:{self._last_price} < target:{self._target}"
                )
        except Exception as e:
            logging.error(f"{e} while exit order")
            print_exc()

    def run(self, orders, ltps):
        try:
            self._orders = orders

            ltp = ltps.get(self._symbol, None)
            if ltp is not None:
                self._prev_price = self._last_price
                self._last_price = float(ltp)
            """
            msg = f"RUNNING {self._symbol} with {self._fn} @ ltp:{self._last_price}"
            print(msg)
                """
            return getattr(self, self._fn)()
        except Exception as e:
            logging.error(f"{e} in running {self._symbol}")
            print_exc()
