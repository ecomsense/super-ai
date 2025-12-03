from src.constants import logging

from src.sdk.helper import Helper

from src.providers.time_manager import TimeManager
from src.providers.trade_manager import TradeManager

import pendulum as pdlm
from traceback import print_exc


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

        self.time_mgr = TimeManager(user_settings["rest_time"])
        self.trade_mgr = TradeManager(
            stock_broker=Helper.api(),
            symbol=self._symbol,
            last_price=self._last_price,
            exchange=user_settings["option_exchange"],
        )

        self._high = self._rest.history(
            exchange=user_settings["option_exchange"],
            token=symbol_info["token"],
            loc=0,
            key="inth",
        )

        self._low = self._rest.history(
            exchange=user_settings["option_exchange"],
            token=symbol_info["token"],
            loc=0,
            key="intl",
        )
        """
        initial trade low condition
        """
        self._init_low_condition()

    def _init_low_condition(self):
        self._below_low = False
        self._fn = "is_trading_below_low"
        self.time_mgr.set_last_trade_time(pdlm.now("Asia/Kolkata"))

    def is_trading_below_low(self):
        try:
            if self.time_mgr.can_trade:
                if self._last_price < self._low:
                    self._below_low = True
                    self._fn = "is_breakout"
        except Exception as e:
            logging.error(f"Hilo: while checking traded below {e}")
        finally:
            return self._below_low

    def is_breakout(self):
        try:
            if self.is_trading_below_low():
                if self.time_mgr.can_trade:
                    self._init_low_condition()
                    if self._last_price > self._low:
                        order_id = self.trade_mgr.complete_entry(
                            quantity=self._quantity, price=self._last_price + 2
                        )
                        if order_id is not None:
                            self._fn = "place_exit_order"
                        else:
                            logging.warning(f"{self._symbol} without order id")
        except Exception as e:
            logging.error(f"{e} while waiting for breakout")
            print_exc()

    def place_exit_order(self):
        try:
            sell_order = self.trade_mgr.pending_exit(
                stop=self._low, orders=self._orders
            )
            if sell_order.order_id is not None:
                self.trade_mgr.target(target_price=self._high)
                self._fn = "try_exiting_trade"
        except Exception as e:
            logging.error(f"{e} while place exit order")
            print_exc()

    def try_exiting_trade(self):
        try:
            if self.trade_mgr.is_trade_exited(self._last_price, self._orders):
                self._init_low_condition()
        except Exception as e:
            logging.error(f"{e} while exit order")
            print_exc()

    def run(self, orders, ltps):
        try:
            self._orders = orders

            ltp = ltps.get(self._symbol, None)
            if ltp is not None:
                self._last_price = float(ltp)
            msg = f"RUNNING {self._symbol} with {self._fn} @ ltp:{self._last_price}"
            print(msg)
            return getattr(self, self._fn)()
        except Exception as e:
            logging.error(f"{e} in running {self._symbol}")
            print_exc()
