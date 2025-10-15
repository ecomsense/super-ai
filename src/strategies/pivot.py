from src.constants import logging, S_SETG, yml_to_obj

from src.config.interface import Trade
from src.sdk.helper import Helper

from src.providers.time_manager import TimeManager
from src.providers.trade_manager import TradeManager
from src.providers.state_manager import StateManager
from src.providers.grid import Gridlines

import pendulum as pdlm
from traceback import print_exc


"""
Rentry, if stop hits
Rentry conditions
Note close of each candle when stop hits
Reentry at if the price crosses above previous open.
Re entry previous open should be updated only if lesser than previous open candle
Rentry should happen only for certain time frame ( Say, 5 minutes or 10 minutes)
Reentry should happen only if it ltp crosses from below to above close price of these candle
Reentry should happen again at Pivot price if the re entry is missed at (previous open)
Reentry should happen irrespective of price post sleep time in case of Pivot PRICE reentry
Do one minute per trade.
Exit when index crosses from lower pivot line to higher pivot line
Do not trade at a particular pivot line if the target is met. There is no second chance for a particular pivot.
Rentry stop time at a particular pivot (Say, 10 min, 15 min or 30 min)
"""
from dataclasses import dataclass


@dataclass
class IndexBreakout:
    idx: int = 100
    time: pdlm.DateTime = pdlm.now("Asia/Kolkata")
    # breakout | target | waiting
    _status: str = "waiting"

    def status(self, curr_idx):
        if curr_idx is None:
            return self._status

        if curr_idx > self.idx:
            if self._status == "waiting":
                self._status = "breakout"
            elif self._status == "breakout":
                self._status = "target"
        if curr_idx < self.idx:
            if self._status == "target":
                self._status = "exit"
            elif self._status == "breakout":
                self._status = "waiting"


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
        self.minutes = 10
        self.differance = 10

        # 1. Core Attributes (directly from parameters)
        self.rest = rest
        self._prefix = prefix
        self.option_type = symbol_info["option_type"]
        self._token = symbol_info["token"]

        # 2. Derived Attributes (calculated from core attributes)
        # self._other_option = "CE" if self.option_type == "PE" else "PE"
        # self._condition = condition[self.option_type]

        # 3. Dependencies and Helper Objects
        self.quantity = user_settings["quantity"]
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
            self._fn = "is_index_breakout"
        else:
            logging.error(f"Pivot: last price is None {self.trade.symbol}")

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
                self._first_trade_at = pdlm.now("Asia/Kolkata")
                logging.info(
                    f"INDEX BREAKOUT: {self.trade.symbol} curr:{curr_idx}  prev:{prev_idx} ltp:{self.trade.last_price}"
                )
                self.pivot_price = self.trade.last_price
                self._low = self.trade.last_price - self.differance

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
        self.trade.tag = "entry_pivot"
        self._reset_trade()

        buy_order = self.trade_mgr.complete_entry(self.trade)
        if buy_order.order_id is not None:
            logging.info(
                f"BREAKOUT: {self.trade.symbol} ltp: {self.trade.last_price} > stop:{self.trade_mgr.stop()}"
            )
            self._fn = "find_fill_price"
            return True

        logging.warning(
            f"got {buy_order} without buy order order id {self.trade.symbol}"
        )
        return False

    def is_time_to_trade(self):
        try:
            now = pdlm.now("Asia/Kolkata")
            before = self._first_trade_at.add(minutes=self.minutes)
            flag = now < before
            logging.info(f"is time to trade? {now} < {before} = {flag}")
            return flag
        except Exception as e:
            logging.error(f"Pivot: while checking time to trade {e}")
            print_exc()

    def is_traded_below(self):
        """
        sets to true only if it is false
        """
        try:
            if not self._is_traded_below:
                self._is_traded_below = self.trade.last_price < self._low

            return self._is_traded_below
        except Exception as e:
            logging.error(f"Pivot: while checking traded below {e}")
            print_exc()

    def wait_for_breakout(self):
        try:
            if self.is_time_to_trade:
                flag = 0
                if self._time_mgr.can_trade:
                    if self.trade.last_price >= self.pivot_price:
                        logging.info("PIVOT BREAK: {self.trade.symbol} > pivot_price")
                        self.trade_mgr.stop(stop_price=self.pivot_price)
                        flag = 1
                    elif self.is_traded_below and (self.trade.last_price > self._low):
                        logging.info(
                            f"TRADED BELOW LOW: {self.trade.symbol} < {self._low}"
                        )
                        self.trade_mgr.stop(stop_price=self._low)
                        flag = 2
                if flag > 0:
                    if self._entry(flag):
                        StateManager.start_trade(self._prefix, self.option_type)
                        self._is_traded_below = False
            else:
                # todo: start again
                ...

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
            self.trade.tag = "sl_pivot"
            self._reset_trade()
            sell_order = self.trade_mgr.pending_exit(self.trade)
            # dont delay exit while logging
            logging.info(f"FILLED: {self.trade.symbol} @ {self.trade_mgr.fill_price()}")
            if sell_order.order_id is not None:
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

    def _target_reached(self, curr_idx, prev_idx):
        if curr_idx < prev_idx and curr_idx > self.index_broke_on:
            return True
        print(f"curr:{curr_idx} prev:{prev_idx} index_broke_on:{self.index_broke_on}")
        return False

    """
            TODO
    """

    def try_exiting_trade(self):
        try:
            # evaluate the condition
            curr, prev = self.lines.find_current_grid(
                self.trade.last_price
            ), StateManager.get_idx(self._prefix, self.option_type)

            if self._target_reached(curr, prev):
                logging.info(
                    f"TARGET: {self.trade.symbol} curr:{curr} BROKE prev:{prev}"
                )
                self._modify_to_exit()
            elif self._is_stoploss_hit():
                logging.info(
                    f"STOP HIT: {self.trade.symbol} with buy fill price {self.trade_mgr.fill_price()} hit stop {self.trade_mgr.stop()}"
                )
                self._fn = "wait_for_breakout"
            elif self.trade.last_price <= self.trade_mgr.stop():  # type: ignore
                resp = self._modify_to_kill()
                logging.info(f"KILLING STOP: returned {resp}")
                self._fn = "wait_for_breakout"

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
