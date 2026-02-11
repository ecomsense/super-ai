from collections import deque
from enum import IntEnum
from traceback import print_exc

import pendulum as pdlm
from toolkit.kokoo import is_time_past

from src.constants import logging_func
from src.providers.grid import Gridlines
from src.providers.time_manager import TimeManager
from src.providers.trade_manager import TradeManager
from src.providers.ui import clear_screen, pingpong
from src.sdk.helper import Helper
from src.sdk.utils import calc_highest_target, round_down_to_tick

logging = logging_func(__name__)


class BreakoutState(IntEnum):
    DEFAULT = 0  # waiting fore new candle + breakout
    ARMED = 1  # breakout detected, monitoring for Condition 2


class Hilo:
    def __init__(self, **kwargs):

        # from parameters
        self.strategy = kwargs["strategy"]
        self.stop_time = kwargs["stop_time"]
        self._rest = kwargs["rest"]

        self.option_type = kwargs["option_type"]

        default_time = {"hour": 9, "minute": 14, "second": 59}
        low = self._rest.history(
            token=kwargs["option_token"],
            exchange=kwargs["option_exchange"],
            loc=pdlm.now("Asia/Kolkata").replace(**default_time),
            key="intl",
        )
        high = self._rest.history(
            token=kwargs["option_token"],
            exchange=kwargs["option_exchange"],
            loc=pdlm.now("Asia/Kolkata").replace(**default_time),
            key="inth",
        )
        self._tradingsymbol = kwargs["tradingsymbol"]
        self._target_set_by_user = kwargs.get("target", "50%")
        self._last_price = kwargs.get("ltp", 10000)

        self._period_low = float("inf")
        self._prev_period_low = float("inf")
        self._traded_pivots = []
        self._stop = None
        self._target = None

        # todo
        if high is not None:
            highest = high + 100
            prices = [0, low, high, highest, highest]
            self.gridlines = Gridlines(prices=prices, reverse=False)
            self._state = BreakoutState.DEFAULT

            self._time_mgr = TimeManager({"minutes": 1})
            self._last_idx = self._time_mgr.current_index + 1

            # objects and dependencies
            self.trade_mgr = TradeManager(
                stock_broker=Helper.api(),
                symbol=self._tradingsymbol,
                exchange=kwargs["option_exchange"],
                quantity=kwargs["quantity"],
                tag=self.strategy,
            )
            self._count = 1

            # state variables
            self._removable = False
            self._path = deque(maxlen=20)
            self._fn = "wait_for_breakout"
            clear_screen()
        else:
            msg = "sorry could not calculate high"
            print(msg)
            logging.error("msg")
            __import__("sys").exit(1)

    def _set_stop(self):
        _, stop, target = self.gridlines.find_current_grid(self._last_price)
        self._stop = stop
        self._target = target
        return self._stop

    def wait_for_breakout(self):
        try:
            curr_idx = self._time_mgr.current_index
            stop_level = self._set_stop()  # Get the 100, 200, etc. line

            if self._stop in self._traded_pivots:
                logging.info(f"Ignoring: This pivot {self._stop} is already traded")
                return

            # --- PHASE 1: ARMING ---
            if self._state == BreakoutState.DEFAULT:
                if curr_idx > self._last_idx:
                    # We now use the guaranteed Low of the previous minute
                    if (
                        self._prev_period_low <= stop_level
                        and self._last_price > stop_level
                    ):
                        self._state = BreakoutState.ARMED
                        logging.info(
                            f"ARMED: {self._tradingsymbol} broke {stop_level} (Prev Low: {self._prev_period_low})"
                        )

                    self._last_idx = curr_idx
                return

            # --- PHASE 2: VALIDATION & EXECUTION ---
            if self._state == BreakoutState.ARMED:
                # 1. Monitoring Phase (Same Candle)
                if curr_idx == self._last_idx:
                    # If price drops back below the breakout line within the same candle, DISARM
                    if (
                        self._last_price <= self._stop
                        or self._last_price > self._target
                    ):
                        self._state = BreakoutState.DEFAULT
                        logging.info(
                            f"DISARMED: Price {self._last_price} < {self._stop} or > {self._target}"
                        )
                    return

                # 2. Execution Phase (Index has incremented)
                # Success! Price stayed above the line for the duration of the 'Arming' candle.
                is_entered = self.trade_mgr.complete_entry(price=self._last_price)

                self._state = BreakoutState.DEFAULT
                self._last_idx = curr_idx

                if is_entered:
                    self._fn = "place_exit_order"
                return

        except Exception as e:
            logging.error(f"Logic Error: {e}")

    def _set_new_stop(self):
        stop = self._stop
        fill = self.trade_mgr.position.average_price
        buffer = (fill - stop) / 2
        new_stop = fill - buffer
        rounded_ltp = round_down_to_tick(last_price=new_stop)
        self.trade_mgr.stop(stop_price=rounded_ltp)

    def place_exit_order(self):
        try:
            sell_order = self.trade_mgr.pending_exit(
                stop=self._stop - 100, orders=self._trades, last_price=self._last_price
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
            self._last_idx = self._time_mgr.current_index

            status = self.trade_mgr.is_trade_exited(self._last_price, self._trades)

            if status > 0:
                self._fn = "wait_for_breakout"
            if status == 2:
                self._traded_pivots.append(self._stop)

        except Exception as e:
            logging.error(f"{e} while exit order")
            print_exc()

    def remove_me(self):
        try:
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
        except Exception as e:
            logging.error(f"{e} in remove me")
            print_exc()

    def run(self, trades, quotes, positions):
        try:
            """needed for removing the object"""

            self._trades = trades

            ltp = quotes.get(self._tradingsymbol, None)
            if ltp is not None:
                self._last_price = float(ltp)

            # Reset logic for new minute
            curr_idx = self._time_mgr.current_index
            if curr_idx > self._last_idx:
                self._prev_period_low = self._period_low
                self._period_low = self._last_price  # Reset for new candle
            else:
                self._period_low = min(self._period_low, self._last_price)

            if is_time_past(self.stop_time):
                logging.info(f"REMOVING: {self._tradingsymbol} .. ")
                self.remove_me()
                return

            self._path.append((self._time_mgr.current_index, self._last_price))
            print("\033[H", end="")

            pingpong(self)
            return getattr(self, self._fn)()
        except Exception as e:
            logging.error(f"{e} in running {self._tradingsymbol}")
            print_exc()
