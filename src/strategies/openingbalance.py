from src.constants import logging_func
from src.sdk.helper import Helper

from src.providers.trade_manager import TradeManager
from src.providers.time_manager import TimeManager
from src.providers.utils import table
from toolkit.kokoo import is_time_past

from traceback import print_exc
import pendulum as pdlm
from math import ceil
from enum import IntEnum

logging = logging_func(__name__)


class BreakoutState(IntEnum):
    DEFAULT = 0  # waiting fore new candle + breakout
    ARMED = 1  # breakout detected, monitoring for Condition 2


class Openingbalance:
    def __init__(self, **kwargs):
        # initialize
        self._STOPPED = set()
        self._trades = []
        self._positions = []

        # from parameters
        self.strategy = kwargs["strategy"]
        self.stop_time = kwargs["stop_time"]
        self._rest = kwargs["rest"]

        self._prefix = kwargs["symbol"]
        self.option_type = kwargs["option_type"]
        self._option_token = kwargs["option_token"]
        self._quantity = kwargs["quantity"]
        self._tradingsymbol = kwargs["tradingsymbol"]
        self._last_price = kwargs.get("ltp", 0)

        self._stop = None
        self._txn = kwargs["txn"]
        self._target = kwargs["t1"]
        self._option_exchange = kwargs["option_exchange"]

        # objects and dependencies
        self._time_mgr = TimeManager(kwargs["rest_time"])
        self._state = BreakoutState.DEFAULT
        self.trade_mgr = TradeManager(
            Helper.api(), symbol=self._tradingsymbol, exchange=self._option_exchange
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
            msg = f"#TSL 50 PERC: {self._tradingsymbol} {percent=} < {trailing_target=}"
            logging.info(msg)
            return True
        elif percent < self._t2 < self._max_target_reached:
            msg = f"#TSL T2 HIT: {self._tradingsymbol} {percent=} < t2={self._t2}"
            logging.info(msg)
            return True

        msg = f"#TRAIL: {self._tradingsymbol} {percent=} vs  max target reached:{self._max_target_reached}"
        logging.info(msg)
        return False
    """

    def set_stop(self):
        try:
            self._last_idx = self._time_mgr.current_index
            if self._stop is None:
                intl = self._rest.history(
                    exchange=self._option_exchange,
                    token=self._option_token,
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
                    # Mark this candle as "seen" regardless of price action
                    self._last_idx = curr_idx

                    if self._last_price > self._stop:
                        self._state = BreakoutState.ARMED
                        logging.info(
                            f"ARMED: {self._tradingsymbol} at index {curr_idx}"
                        )
                return  # Exit Phase 1

            # --- PHASE 2: VALIDATION & EXECUTION ---
            if self._state == BreakoutState.ARMED:
                # 1. Monitoring Phase (Same Candle)
                if curr_idx == self._last_idx:
                    if self._last_price <= self._stop:
                        self._state = BreakoutState.DEFAULT
                        logging.info(
                            f"DISARMED: {self._tradingsymbol} - Stop breached mid-candle"
                        )
                    return

                # 2. Execution Phase (Index has incremented)
                # Since we are still ARMED and the index changed, Step 2 was successful.
                is_entered = self.trade_mgr.complete_entry(
                    quantity=self._quantity, price=self._last_price + 2
                )

                # Reset state before moving to the next phase
                self._state = BreakoutState.DEFAULT
                self._last_idx = curr_idx

                if is_entered:
                    self._fn = "place_exit_order"
                return

        except Exception as e:
            logging.error(f"Logic Error: {e}")

    def place_exit_order(self):
        try:
            sell_order = self.trade_mgr.pending_exit(
                stop=self._stop, orders=self._trades
            )
            if sell_order and sell_order.order_id:
                self._fn = "try_exiting_trade"
            else:
                self._STOPPED.add(self._prefix)
                self._removable = True
        except Exception as e:
            logging.error(f"{e} while place exit order")
            print_exc()

    def _set_target(self):
        try:
            # resp = self.rest.positions()
            if (self._positions and any(self._positions)) and (
                self._trades and any(self._trades)
            ):
                total_profit = sum(
                    item["rpnl"] + item["urmtom"]
                    for item in self._positions
                    if item["symbol"].startswith(self._prefix)
                )
                # total_profit = total_for_this_prefix - m2m if m2m > 0 else total_for_this_prefix
                # calculate txn cost
                count = len(
                    [
                        order["order_id"]
                        for order in self._trades
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
                        for item in self._positions
                        if item["symbol"] == self._tradingsymbol
                    ),
                    0,
                )
                other_instrument_m2m = total_profit - m2m
                rpnl = next(
                    (
                        item["rpnl"]
                        for item in self._positions
                        if item["symbol"] == self._tradingsymbol
                    ),
                    0,
                )

                rate_to_be_added = (other_instrument_m2m + rpnl) / self._quantity  # type: ignore
                rate_to_be_added = -1 * rate_to_be_added
                logging.debug(
                    f"{rate_to_be_added=}  = {other_instrument_m2m=} + {rpnl=} / {self._quantity}q"
                )

                fill_price = self.trade_mgr.position.average_price  # type: ignore
                if fill_price is not None:
                    target_buffer = self._target * fill_price / 100
                    target_virtual = (
                        fill_price + target_buffer + rate_to_be_added + txn_cost
                    )
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
                    return

                else:
                    logging.warning(f"trade manager fill price is {fill_price}")

            else:
                logging.warning("no trades or positions yet detected")

            self.trade_mgr.target(
                10000
            )  # very high target if no positions/trades found

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
                self._last_price, self._trades, removable=False
            )

            if exit_status in [1, 2]:
                self._fn = "wait_for_breakout"
            elif exit_status == 3:
                self._STOPPED.add(self._prefix)
                self._removable = True

            msg = f"PROGRESS: {self._tradingsymbol} target {self.trade_mgr.position.target_price} < {self._last_price} > sl {self._stop} "
            logging.info(msg)

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
            self._trades = trades

            self._positions = positions

            ltp = quotes.get(self._tradingsymbol, None)
            if ltp is not None:
                self._last_price = float(ltp)

            is_removable = is_time_past(self.stop_time)
            if is_removable or self._prefix in self._STOPPED:
                if self.remove_me():
                    return

            result = getattr(self, self._fn)()
            table(self)
            return result
        except Exception as e:
            logging.error(f"{e} in running {self._tradingsymbol}")
            print_exc()
