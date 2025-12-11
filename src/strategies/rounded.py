from src.constants import logging_func

from src.sdk.helper import Helper

from src.providers.time_manager import Bucket
from src.providers.trade_manager import TradeManager

from traceback import print_exc

logging = logging_func(__name__)


class Rounded:

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

        self.trade_mgr = TradeManager(
            stock_broker=Helper.api(),
            symbol=self._symbol,
            exchange=user_settings["option_exchange"],
        )

        low = user_settings.get("low", 150)
        levels = user_settings.get("no_of_levels", 3)
        self._distance = user_settings.get("distance", 50)

        self._stops = []
        start = 1
        while start <= levels:
            self._stops.append(low + self._distance * start)
            start += 1

        """
        initial trade low condition
        """
        self._fn = "is_breakout"

    def is_breakout(self):
        try:

            for self._stop in self._stops:
                # 1.1 check actual breakout condition
                if self._last_price > self._stop and self._prev_price <= self._stop:
                    # 2. are we with the trade limits of time buckets
                    if not self._small_bucket.can_allow():
                        logging.debug(
                            f"small BUCKET full: {self._symbol} skipping trading"
                        )
                        return
                    if not self._big_bucket.can_allow():
                        logging.debug(
                            f"BIG BUCKET FULL: {self._symbol} skipping trading"
                        )
                        return

                    # 3. calculate target price
                    self._target = self._stop + self._distance
                    # 4. place entry
                    order_id = self.trade_mgr.complete_entry(
                        quantity=self._quantity, price=self._last_price + 2
                    )
                    if order_id:
                        # 5. consume tokens
                        self._small_bucket.allow()
                        self._big_bucket.allow()
                        self._fn = "place_exit_order"
                        return
                    else:
                        logging.warning(f"{self._symbol} without order id")
                        return

            # 1.2. check actual breakout condition
            logging.debug(
                f"No Breakout: {self._symbol}  {self._prev_price} is not less than {self._stops} and not less than {self._last_price} "
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
            msg = f"RUNNING {self._symbol} with {self._fn} @ ltp:{self._last_price} low:{self._low}  high:{self._high}"
            print(msg)
            """
            return getattr(self, self._fn)()
        except Exception as e:
            logging.error(f"{e} in running {self._symbol}")
            print_exc()
