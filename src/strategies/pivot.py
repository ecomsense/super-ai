from src.constants import logging, S_SETG, yml_to_obj

from src.config.interface import Trade
from src.sdk.helper import Helper

from src.providers.time_manager import TimeManager
from src.providers.trade_manager import TradeManager
from src.providers.state_manager import StateManager
from src.providers.grid import Gridlines

import pendulum as pdlm
from traceback import print_exc

from enum import IntEnum


class LowExit(IntEnum):
    ENTRY = 1
    TARGET = 2
    EXIT = 0


class Pivot:

    def __init__(
        self,
        prefix: str,
        symbol_info: dict,
        user_settings: dict,
        pivot_grids,
        rest,
    ):
        # A hard coded
        self._removable = False
        self.low_exit = LowExit.EXIT

        # 1. Core Attributes (directly from parameters)
        self.rest = rest
        self._prefix = prefix
        self.option_type = symbol_info["option_type"]
        self._token = symbol_info["token"]
        self.differance = user_settings["differance"]
        self.quantity = user_settings["quantity"]

        # 2. Derived Attributes (calculated from core attributes)
        # self._other_option = "CE" if self.option_type == "PE" else "PE"
        # self._condition = condition[self.option_type]

        # 3. Dependencies and Helper Objects
        self.trade = Trade(
            symbol=symbol_info["symbol"],
            last_price=symbol_info["ltp"],
            exchange=user_settings["option_exchange"],
        )
        self.lines = Gridlines(prices=pivot_grids, reverse=False)
        self._time_mgr = TimeManager(rest_min=user_settings["rest_min"])
        self.trade_mgr = TradeManager(Helper.api())

        # class level state management
        if self.trade.last_price is not None:
            StateManager.initialize_prefix(prefix=self._prefix)
            # wait for index breakout (or fresh breakout)
            logging.info(f"RELAX: {self.trade.symbol} waiting for index breakout")
            self._fn = "is_index_breakout"
        else:
            logging.error(f"Pivot: last price is None {self.trade.symbol} ... exiting")
            __import__("sys").exit(1)

        """ end of initialization """

    def is_index_breakout(self):
        """
        Options ltp -crosses below to above
        Buy and keep stop loss first stop loss as pivot price ie.(P,R1,R2,S1,S2)
        """
        try:
            Flag = False
            # where is the current grid 5
            curr_idx = self.lines.find_current_grid(self.trade.last_price)
            # prev idx is 4
            prev_idx = StateManager.get_idx(self._prefix, self.option_type)

            if curr_idx > prev_idx:
                Flag = True
                logging.info(
                    f"INDEX BREAKOUT: {self.trade.symbol} curr: {curr_idx}  prev: {prev_idx} ltp:{self.trade.last_price}"
                )
                self.pivot_price = self.trade.last_price - 0.05
                self._low = self.pivot_price - self.differance

            StateManager.set_idx(
                prefix=self._prefix, option_type=self.option_type, idx=curr_idx
            )

            if Flag:
                self._fn = "wait_for_breakout"
                self.wait_for_breakout()

        except Exception as e:
            logging.error(f"{e} while checking index breakout")
            print_exc()

    def _reset_trade(self):
        self.trade.filled_price = None
        self.trade.status = None
        self.trade.order_id = None

    def _entry(self, flag):
        self.trade.side = "B"
        self.trade.quantity = self.quantity * flag
        self.trade.disclosed_quantity = None
        self.trade.price = self.trade.last_price + 2  # type: ignore
        self.trade.trigger_price = 0.0
        self.trade.order_type = "LMT"
        tag = "pivot_break" if flag == 1 else "low_break"
        self.trade.tag = tag
        self._reset_trade()

        buy_order = self.trade_mgr.complete_entry(self.trade)
        if buy_order.order_id is not None:
            self._fn = "find_fill_price"
            return True

        logging.warning(
            f"got {buy_order} without buy order order id {self.trade.symbol}"
        )
        return False

    def is_traded_below(self):
        """
        sets to true only if it is false
        """
        try:
            if not self._is_traded_below:
                self._is_traded_below = self.trade.last_price < self._low
                logging.debug(
                    f"TRADING BELOW LOW: changed from False to {self._is_traded_below}!"
                )

            return self._is_traded_below
        except Exception as e:
            logging.error(f"Pivot: while checking traded below {e}")
            print_exc()

    def removable(self):
        logging.info(f"REMOVING: {self.trade.symbol} because we went below pivot")

    def wait_for_breakout(self):
        try:
            # evaluate the condition
            curr, prev = self.lines.find_current_grid(
                self.trade.last_price
            ), StateManager.get_idx(self._prefix, self.option_type)
            if curr < (prev - 1):
                logging.warning(
                    f"TRYING ANOTHER PIVOT: {self.trade.symbol} because we went below current pivot"
                )
                StateManager.set_idx(
                    prefix=self._prefix, option_type=self.option_type, idx=curr
                )
                self._fn = "is_index_breakout"
                return

            if self._time_mgr.can_trade:
                flag = 0
                if self.trade.last_price > self.pivot_price:
                    logging.info(
                        f"PIVOT BREAK: {self.trade.symbol} ltp: {self.trade.last_price} > pivot: {self.pivot_price}"
                    )
                    self.trade_mgr.stop(stop_price=self.pivot_price)
                    flag = 1
                elif self.is_traded_below and (self.trade.last_price > self._low):
                    logging.info(
                        f"LOW BREAK: {self.trade.symbol} {self.trade.last_price} > {self._low}"
                    )
                    self.trade_mgr.stop(stop_price=self._low)
                    self.low_exit = LowExit.ENTRY
                    flag = 2

                if flag > 0:
                    is_traded = self._entry(flag=flag)
                    if not is_traded:
                        logging.error(
                            f"EXCEPTION: {self.trade.symbol} is unable to get buy order id"
                        )

        except Exception as e:
            logging.error(f"{e} while waiting for breakout")
            print_exc()

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
                self._fn = self.trade.tag
                # if sell order is placed, reset the traded below flag
                self._is_traded_below = False
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
                return self.rest.can_move_order_to_trade(
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

    def pivot_break(self):
        try:
            curr, prev = self.lines.find_current_grid(
                self.trade.last_price
            ), StateManager.get_idx(self._prefix, self.option_type)
            if curr > prev:
                logging.info(
                    f"TARGET: {self.trade.symbol} curr:{curr} BROKE prev:{prev}"
                )
                self._modify_to_exit()
                self._removable = True
                self._fn = "removable"
                return True

            self.try_exiting_trade()
            return False

        except Exception as e:
            logging.error(f"{e} while pivot break")
            print_exc()

    def _low_target_reached(self):
        try:
            if self.low_exit == LowExit.ENTRY and (
                self.trade.last_price > self.pivot_price
            ):
                self.low_exit = LowExit.TARGET
                logging.debug(
                    f"GOING TO TRAIL: {self.trade.symbol} pivot: {self.pivot_price} < ltp: {self.trade.last_price}"
                )
            elif self.low_exit == LowExit.TARGET and (
                self.trade.last_price < self.pivot_price
            ):
                logging.info(
                    f"LOW TARGET: {self.trade.symbol}  pivot: {self.pivot_price} > ltp: {self.trade.last_price}"
                )
                self.low_exit = LowExit.EXIT
                return True

            return False
        except Exception as e:
            logging.error(f"{e} while low target")
            print_exc()

    def low_break(self):
        try:
            # if target reached return true target
            if self.pivot_break():
                return

            # try secondary target
            if self._low_target_reached:
                self._modify_to_exit()
                self._fn = "wait_for_breakout"
                self._time_mgr.set_last_trade_time(pdlm.now("Asia/Kolkata"))
                return

            self.try_exiting_trade()

        except Exception as e:
            logging.error(f"{e} while low break")
            print_exc()

    def try_exiting_trade(self):
        try:
            if self._is_stoploss_hit():
                logging.info(
                    f"STOP HIT: {self.trade.symbol} buy fill: {self.trade_mgr.fill_price()}  stop: {self.trade_mgr.stop()}"
                )
                self._fn = "wait_for_breakout"

            elif self.trade.last_price <= self.trade_mgr.stop():  # type: ignore
                resp = self._modify_to_kill()
                logging.info(f"KILLING STOP: returned {resp}")
                self._fn = "wait_for_breakout"

            if self._fn == "wait_for_breakout":
                self._time_mgr.set_last_trade_time(pdlm.now("Asia/Kolkata"))

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
