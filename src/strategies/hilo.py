from src.constants import logging, S_SETG, yml_to_obj

from src.config.interface import Trade
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
        self.trade = Trade(
            symbol=symbol_info["symbol"],
            last_price=symbol_info["ltp"],
            exchange=user_settings["option_exchange"],
        )
        self.time_mgr = TimeManager(user_settings["rest_time"])
        self.trade_mgr = TradeManager(Helper.api())

        self._high = self._rest.history(
            exchange=user_settings["option_exchange"],
            token=user_settings["option_token"],
            loc=0,
            key="inth",
        )

        low = self._rest.history(
            exchange=user_settings["option_exchange"],
            token=user_settings["option_token"],
            loc=0,
            key="intl",
        )
        self.trade_mgr.stop(stop_price=low)
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
                if self.trade.last_price < self.trade_mgr.stop():
                    self._below_low = True
                    self._fn = "is_breakout"
        except Exception as e:
            logging.error(f"Hilo: while checking traded below {e}")
        finally:
            return self._below_low

    def _reset_trade(self):
        self.trade.filled_price = None
        self.trade.status = None
        self.trade.order_id = None

    def _entry(self):
        self.trade.side = "B"
        self.trade.quantity = self.quantity
        self.trade.disclosed_quantity = None
        self.trade.price = self.trade.last_price + 2  # type: ignore
        self.trade.trigger_price = 0.0
        self.trade.order_type = "LMT"
        self.trade.tag = "entry"
        self._reset_trade()

        buy_order = self.trade_mgr.complete_entry(self.trade)
        if buy_order.order_id is not None:
            return True

        logging.warning(
            f"got {buy_order} without buy order order id {self.trade.symbol}"
        )
        return False

    def find_fill_price(self):
        order = self.trade_mgr.find_order_if_exists(
            self.trade_mgr.position.entry.order_id, self._orders
        )
        if isinstance(order, dict):
            self.trade_mgr.fill_price(float(order["fill_price"]))

            # place sell order only if buy order is filled
            self.trade.side = "S"
            self.trade.disclosed_quantity = 0
            self.trade.price = self.trade_mgr.stop() - 2
            self.trade.trigger_price = self.trade_mgr.stop()
            self.trade.order_type = "SL-LMT"
            self._reset_trade()
            sell_order = self.trade_mgr.pending_exit(self.trade)
            # dont delay exit while logging
            logging.info(f"FILLED: {self.trade.symbol} @ {self.trade_mgr.fill_price()}")
            if sell_order.order_id is not None:
                # switch the next function here
                # TODO
                self._fn = "try_exiting_trade"
            else:
                logging.error(f"id is not found for sell {sell_order}")
        else:
            logging.error(
                f"{self.trade.symbol} buy order {self.trade_mgr.position.entry.order_id} not complete, to find fill price"
            )

    def _is_stoploss_hit(self):
        try:
            O_SETG = yml_to_obj(S_SETG)
            if O_SETG.get("live", 1) == 1:
                order = self.trade_mgr.find_order_if_exists(
                    self.trade_mgr.position.exit.order_id, self._orders
                )
                if isinstance(order, dict):
                    return True
            else:
                logging.debug("CHECKING STOP IN PAPER MODE")
                return self._rest.can_move_order_to_trade(
                    self.trade_mgr.position.exit.order_id, self.trade.last_price
                )
        except Exception as e:
            logging.error(f"{e} is stoploss hit {self.trade.symbol}")
            print_exc()

    def _modify_to_exit(self):
        try:
            kwargs = dict(
                trigger_price=0.0,
                order_type="LIMIT",
                last_price=self.trade.last_price,
            )
            return self.trade_mgr.complete_exit(**kwargs)
        except Exception as e:
            logging.error(f"{e} while modify to exit {self.trade.symbol}")
            print_exc()

    def _modify_to_kill(self):
        try:
            kwargs = dict(
                price=0.0,
                order_type="MARKET",
                last_price=self.trade.last_price,
            )
            return self.trade_mgr.complete_exit(**kwargs)
        except Exception as e:
            logging.error(f"{e} while modify to exit {self.trade.symbol}")
            print_exc()

    def is_breakout(self):
        try:
            if self.is_trading_below_low():
                if self.time_mgr.can_trade:
                    self._init_low_condition()
                    if self.trade.last_price > self.trade_mgr.stop():
                        if self._entry():
                            self._fn = "find_fill_price"

        except Exception as e:
            logging.error(f"{e} while waiting for breakout")
            print_exc()

    def try_exiting_trade(self):
        try:
            FLAG_NEW_TRADE = False

            if self._is_stoploss_hit():
                logging.info(
                    f"STOP HIT: {self.trade.symbol} buy fill: {self.trade_mgr.fill_price()}  stop: {self.trade_mgr.stop()}"
                )
                FLAG_NEW_TRADE = True

            elif self.trade.last_price <= self.trade_mgr.stop():  # type: ignore
                resp = self._modify_to_kill()
                logging.info(f"KILLING STOP: returned {resp}")
                FLAG_NEW_TRADE = True

            elif self.trade.last_price > self._high:
                self._modify_to_exit()
                FLAG_NEW_TRADE = True

            if FLAG_NEW_TRADE:
                self._init_low_condition()

        except Exception as e:
            logging.error(f"{e} while exit order")
            print_exc()

    def run(self, orders, ltps):
        try:
            self._orders = orders

            ltp = ltps.get(self.trade.symbol, None)
            if ltp is not None:
                self.trade.last_price = float(ltp)
            msg = f"RUNNING {self.trade.symbol} with {self._fn} @ ltp:{self.trade.last_price} stop:{self.trade_mgr.stop()}"
            print(msg)
            return getattr(self, self._fn)()
        except Exception as e:
            logging.error(f"{e} in running {self.trade.symbol}")
            print_exc()
