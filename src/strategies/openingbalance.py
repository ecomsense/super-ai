from src.constants import logging_func
from src.sdk.helper import Helper

from src.providers.trade_manager import TradeManager
from src.providers.time_manager import TimeManager
from src.providers.utils import table

from traceback import print_exc
import pendulum as pdlm
from math import ceil
from enum import IntEnum


logging = logging_func(__name__)


class BreakoutState(IntEnum):
    DEFAULT = 0  # waiting fore new candle + breakout
    ARMED = 1  # breakout detected, monitoring for Condition 2


class Openingbalance:
    def __init__(self, prefix: str, symbol_info: dict, user_settings: dict, rest):
        # initialize
        self._stopped = set()
        self._orders = []
        self._positions = []

        # from parameters
        self._rest = rest
        self._prefix = prefix
        self.option_type = symbol_info["option_type"]
        self._token = symbol_info["token"]
        self._quantity = user_settings["quantity"]
        self._symbol = symbol_info["symbol"]
        self._last_price = symbol_info["ltp"]

        self._stop = None
        self._t2 = user_settings.get("t2", user_settings["t1"])
        self._txn = user_settings["txn"]
        self._target = user_settings["t1"] * 2
        self._exchange = user_settings["option_exchange"]

        # objects and dependencies
        self._time_mgr = TimeManager(user_settings["rest_time"])
        self._state = BreakoutState.DEFAULT
        self._is_breakout = False
        self.trade_mgr = TradeManager(
            Helper.api(), symbol=self._symbol, exchange=user_settings["option_exchange"]
        )

        # state variables
        self._removable = False
        self._fn = "set_stop"

    """
    def _is_trailstopped(self, percent):
        # set max target reached
        if max(percent, self._max_target_reached) == percent:
            self._max_target_reached = percent
        trailing_target = self._max_target_reached / 2

        # if currently above stop% and below trailing target
        if self._t2 <= percent < trailing_target:
            msg = f"#TSL 50 PERC: {self._symbol} {percent=} < {trailing_target=}"
            logging.info(msg)
            return True
        elif percent < self._t2 < self._max_target_reached:
            msg = f"#TSL T2 HIT: {self._symbol} {percent=} < t2={self._t2}"
            logging.info(msg)
            return True

        msg = f"#TRAIL: {self._symbol} {percent=} vs  max target reached:{self._max_target_reached}"
        logging.info(msg)
        return False
    """

    def set_stop(self):
        try:
            self._last_idx = self._time_mgr.current_index
            if self._stop is None:
                intl = self._rest.history(
                    exchange=self._exchange,
                    token=self._token,
                    loc=pdlm.now("Asia/Kolkata").replace(hour=9, minute=16),
                    key="intl",
                )
                if intl is not None:
                    self._stop = intl
                    self._fn = "wait_for_breakout"
        except Exception as e:
            logging.error(f"set stop for next trade: {e}")
            print_exc()

    def wait_for_breakout(self):
        try:
            curr_idx = self._time_mgr.current_index

            # --- PHASE 1: ARMING (Condition 1) ---
            if self._state == BreakoutState.DEFAULT:
                if curr_idx > self._last_idx:
                    if self._last_price > self._stop:
                        self._state = BreakoutState.ARMED
                        self._last_idx = curr_idx
                return

            # --- PHASE 2: VALIDATION (Condition 2) ---
            if self._state == BreakoutState.ARMED:
                # If we are still in the same candle, check for breach
                if curr_idx == self._last_idx:
                    if self._last_price <= self._stop:
                        self._state = BreakoutState.DEFAULT  # Reset if touched
                    return

                # If index changed and we are still ARMED, it means NO BREACH happened
                self._state = BreakoutState.DEFAULT
                self._last_idx = curr_idx
                # Execute trade because the previous candle survived the test
                is_entered = self.trade_mgr.complete_entry(
                    quantity=self._quantity, price=self._last_price + 2
                )
                if is_entered:
                    self._fn = "place_exit_order"
                return

        except Exception as e:
            logging.error(f"Logic Error: {e}")
            print_exc()

    def place_exit_order(self):
        try:
            sell_order = self.trade_mgr.pending_exit(
                stop=self._stop, orders=self._orders
            )
            if sell_order.order_id:
                self._fn = "try_exiting_trade"
        except Exception as e:
            logging.error(f"{e} while place exit order")
            print_exc()

    def _set_target(self):
        try:
            # resp = self.rest.positions()
            resp = self._positions
            total_profit = sum(
                item["rpnl"] + item["urmtom"]
                for item in resp
                if item["symbol"].startswith(self._prefix)
            )
            # total_profit = total_for_this_prefix - m2m if m2m > 0 else total_for_this_prefix
            # calculate txn cost
            count = len(
                [
                    order["order_id"]
                    for order in self._orders
                    if order["symbol"].startswith(self._prefix)
                ]
            )
            count = 1 if count == 0 else count / 2
            count = ceil(count)
            txn_cost = count * self._txn
            logging.debug(f"{txn_cost=} for {count} trades * txn_rate:{self._txn}")
            """
            rate_to_be_added = abs(total_profit) / self.trade.quantity  # type: ignore
            logging.debug(
                f"{rate_to_be_added=} because of negative {total_profit=} / {self.trade.quantity}q"
            )
            """
            m2m = next(
                (
                    item["urmtom"] + item["rpnl"]
                    for item in resp
                    if item["symbol"] == self._symbol
                ),
                0,
            )
            other_instrument_m2m = total_profit - m2m
            rpnl = next(
                (item["rpnl"] for item in resp if item["symbol"] == self._symbol),
                0,
            )

            rate_to_be_added = (other_instrument_m2m + rpnl) / self._quantity  # type: ignore
            rate_to_be_added = -1 * rate_to_be_added
            logging.debug(
                f"{rate_to_be_added=}  = {other_instrument_m2m=} + {rpnl=} / {self._quantity}q"
            )

            fill_price = self.trade_mgr.position.entry.filled_price  # type: ignore
            target_buffer = self._target * fill_price / 100
            target_virtual = fill_price + target_buffer + rate_to_be_added + txn_cost
            target_progress = (
                (target_virtual - target_buffer - self._last_price)
                / fill_price
                * 100
                * -1
            )
            logging.debug(
                f"target_price {target_virtual} = fill: {fill_price} + {target_buffer=} + {rate_to_be_added=} + {txn_cost=} {target_progress=}"
            )
            """
            # trailing
            if self._is_trailstopped(target_progress):
                resp = self._modify_to_exit()
                logging.debug(f"SELL MODIFY: {self.trade.symbol} got {resp}")
                self._fn = "remove_me"
                return True
            """
            self.trade_mgr.target(round(target_virtual / 0.05) * 0.05)
        except Exception as e:
            print_exc()
            logging.error(f"{e} while set target")

    def try_exiting_trade(self):
        try:
            # TODO
            self._last_idx = self._time_mgr.current_index

            # if trail stopped return prefix
            self._set_target()

            exit_status = self.trade_mgr.is_trade_exited(
                self._last_price, self._orders, removable=False
            )

            if exit_status in [1, 2]:
                self._fn = "wait_for_breakout"
            elif exit_status == 3:
                self._stop.add(self._prefix)
                self._removable = True

            msg = f"PROGRESS: {self._symbol} target {self.trade_mgr.position.target_price} < {self._last_price} > sl {self._stop} "
            logging.info(msg)

            """ 
            if self._fn == "wait_for_breakout":
                self._time_mgr.set_last_trade_time(pdlm.now("Asia/Kolkata"))
            """

        except Exception as e:
            logging.error(f"{e} while exit order")
            print_exc()

    def remove_me(self):
        if self._fn == "place_exit_order":
            self.place_exit_order()

        if self._fn == "try_exiting_trade":
            status = self.trade_mgr.is_trade_exited(
                self._last_price, self._orders, True
            )
            assert status == 3

            self._removable = True
            logging.info(
                f"REMOVING: {self._symbol} switching from waiting for breakout"
            )

    def run(self, orders, ltps, positions):
        try:
            self._orders = orders

            if positions and any(positions):
                self._positions = positions

            ltp = ltps.get(self._symbol, None)
            if ltp is not None:
                self._last_price = float(ltp)

            if self._prefix in self._stopped:
                self.remove_me()

            result = getattr(self, self._fn)()
            table(self)
            return result
        except Exception as e:
            logging.error(f"{e} in running {self._symbol}")
            print_exc()
