from src.constants import logging

from src.sdk.helper import Helper

from src.providers.time_manager import Gate, Bucket
from src.providers.trade_manager import TradeManager

from traceback import print_exc


def calc_highest_target(high, target):
    """
    calculate the target price from percentage or fixed value
    """
    if isinstance(target, str) and target.endswith("%"):
        target = target.split("%")[0].strip()
        return high + (high * float(target) / 100)
    return high + float(target)


class Hilo:

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
        self._check_gate = Gate(user_settings["rest_time"])
        self._trade_bucket = Bucket(
            period=user_settings["time_bucket"],
            max_trades=user_settings["max_trade_in_bucket"],
        )

        self.trade_mgr = TradeManager(
            stock_broker=Helper.api(),
            symbol=self._symbol,
            last_price=self._last_price,
            exchange=user_settings["option_exchange"],
        )
        loc = user_settings.get("candle_number", -1)
        self._high = self._rest.history(
            exchange=user_settings["option_exchange"],
            token=symbol_info["token"],
            loc=loc,
            key="inth",
        )

        self._low = self._rest.history(
            exchange=user_settings["option_exchange"],
            token=symbol_info["token"],
            loc=loc,
            key="intl",
        )
        self._stop = self._low

        self._target = self._high

        self._target_set_by_user = user_settings.get("target", "50%")
        """
        initial trade low condition
        """
        self._fn = "is_breakout"

    def is_breakout(self):
        try:
            # 1. Check other conditions every check_every (30 seconds)
            if not self._check_gate.allow():
                return

            for stop in [self._low, self._high]:
                # 2. check actual breakout condition
                logging.debug(f"Gate Opened: {self._symbol} checking breakout@ {stop}")
                if self._last_price > stop and self._prev_price <= stop:

                    # 3. are we with the trade limits in this bucket
                    if not self._trade_bucket.allow():
                        logging.debug(f"{self._symbol} bucket full, skipping trading")
                        return

                    self._target = (
                        self._high
                        if stop == self._low
                        else calc_highest_target(self._high, self._target_set_by_user)
                    )
                    # 4. place entry
                    order_id = self.trade_mgr.complete_entry(
                        quantity=self._quantity, price=self._last_price + 2
                    )
                    if order_id:
                        self._fn = "place_exit_order"
                    else:
                        logging.warning(f"{self._symbol} without order id")

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

            msg = f"RUNNING {self._symbol} with {self._fn} @ ltp:{self._last_price} low:{self._low}  high:{self._high}"
            print(msg)
            return getattr(self, self._fn)()
        except Exception as e:
            logging.error(f"{e} in running {self._symbol}")
            print_exc()


if __name__ == "__main__":
    assert calc_highest_target(100, "50%") == 150  # 50% of 100
    assert calc_highest_target(100, "50") == 150  # 50 fixed
