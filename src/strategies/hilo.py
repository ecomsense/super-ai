from collections import deque
from enum import IntEnum
from traceback import print_exc

import pendulum as pdlm
from toolkit.kokoo import is_time_past, timer

from src.constants import logging_func
from src.providers.time_manager import TimeManager
from src.providers.trade_manager import TradeManager
from src.providers.grid import StopAndTarget
from src.providers.ui import clear_screen, pingpong
from src.sdk.helper import Helper
from src.sdk.utils import round_down_to_tick, calc_highest_target

logging = logging_func(__name__)

def always_true(): return True

class BreakoutState(IntEnum):
    DEFAULT = 0  # waiting fore new candle + breakout
    ARMED = 1  # breakout detected, monitoring for Condition 2


class Hilo:
    def __init__(self, **kwargs):
        """
        trail: 50%  #optional 
        reentry: odd  #optional odd | even
        """
        self._removable = False
        self._period_low = float("inf")
        self._prev_period_low = float("inf")
        self._stop = None
        self._target = None
        self._state = BreakoutState.DEFAULT

        # from parameters
        self._rest = kwargs["rest"]
        self._tradingsymbol = kwargs["tradingsymbol"]
        self._last_price = kwargs.get("ltp", float("inf"))
        self.strategy = kwargs["strategy"]

        self.stop_time = kwargs["stop_time"]
        self.option_type = kwargs["option_type"]


        default_time = {"hour": 9, "minute": 14, "second": 59}
        low_candle_time = kwargs.get("low_candle_time", default_time)
        low = None
        while low is None:
            low = kwargs["rest"].history(
                token=kwargs["option_token"],
                exchange=kwargs["option_exchange"],
                loc=pdlm.now("Asia/Kolkata").replace(**low_candle_time),
                key="intl",
            )
            timer(1)

        high = kwargs["rest"].history(
            token=kwargs["option_token"],
            exchange=kwargs["option_exchange"],
            loc=pdlm.now("Asia/Kolkata").replace(**low_candle_time),
            key="inth",
        )
        target_set_by_user = kwargs.get("target", "50%")

        # objects and dependencies
        highest = calc_highest_target(high=high, target=target_set_by_user)
        prices = [
            (0, low), 
            (low, calc_highest_target(low, target_set_by_user)), 
            (high, highest),
            (highest, highest)
            ]
        logging.info(f"grid we are going to trade today {prices}")
        self.stop_and_target = StopAndTarget(prices)

        rest_time = kwargs.get("rest_time", {"minutes": 1})
        self._time_mgr = TimeManager(rest_time)
        self._last_idx = self._time_mgr.current_index + 1

        self.trade_mgr = TradeManager(
            stock_broker=Helper.api(),
            symbol=self._tradingsymbol,
            exchange=kwargs["option_exchange"],
            quantity=kwargs["quantity"],
            tag=self.strategy,
        )

        # strategy specific and optional
        self._trail = kwargs.get("trail", None)
        if isinstance(self._trail, str) and self._trail.endswith("%"):
            self._set_new_stop = self._new_stop 
        else: 
            self._set_new_stop = self._no_new_stop

        self._reentry = kwargs.get("reentry", None)
        if self._reentry: 
            self._is_reentry = self._is_entry 
            self._count = 1
        else:
            self._is_reentry = always_true

        # state variables
        self._path = deque(maxlen=20)
        self._fn = "wait_for_breakout"
        clear_screen()

    def _set_stop(self):
        stop, target = self.stop_and_target.calc(self._last_price)
        self._stop = stop
        self._target = target
        return self._stop

    def wait_for_breakout(self):
        try:
            curr_idx = self._time_mgr.current_index

            # --- PHASE 1: SEARCHING (DEFAULT STATE) ---
            if self._state == BreakoutState.DEFAULT:
                # We only look for a NEW grid level when we aren't already tracking one
                stop_level = self._set_stop()

                if stop_level is None:
                    return

                if curr_idx > self._last_idx:
                    # Check if the previous minute's price action crossed the CURRENT stop_level
                    if (
                        self._prev_period_low <= stop_level
                        and self._last_price > stop_level
                    ):
                        self._state = BreakoutState.ARMED
                        logging.info(
                            f"ARMED: {self._tradingsymbol} locked at {stop_level}. "
                            f"Validating for candle index {curr_idx}..."
                        )
                    self._last_idx = curr_idx
                return

            # --- PHASE 2: VALIDATION (ARMED STATE) ---
            if self._state == BreakoutState.ARMED:
                # 1. Monitoring Phase (Within the arming candle)
                if curr_idx == self._last_idx:
                    # If price fails the breakout line or hits the next target TOO FAST
                    if (
                        self._last_price <= self._stop
                        or self._last_price > self._target
                    ):
                        logging.info(
                            f"DISARMED: Price {self._last_price} violated locked levels "
                            f"(Stop: {self._stop}, Target: {self._target})"
                        )
                        self._state = BreakoutState.DEFAULT
                    return

                # 2. Execution Phase (Candle has closed, index has incremented)
                logging.info(
                    f"SUCCESS: {self._tradingsymbol} held above {self._stop}. Entering Trade."
                )

                # We use self._stop as the reference for the entry
                if self._is_reentry():
                    is_entered = self.trade_mgr.complete_entry(price=self._last_price)
                    if is_entered:
                        self._fn = "place_exit_order"

                # Reset state for next cycle
                self._state = BreakoutState.DEFAULT
                self._last_idx = curr_idx

        except Exception as e:
            logging.error(f"Logic Error: {e}")

    
    def _is_entry(self):
        is_odd = bool(self._count  % 2)
        self._count += 1
        if self._reentry == "odd":
            return is_odd
        return not is_odd

        

    def place_exit_order(self):
        try:
            sell_order = self.trade_mgr.pending_exit(
                stop=self._stop, orders=self._trades, last_price=self._last_price
            )

            if sell_order and sell_order.order_id:
                self.trade_mgr.target(target_price=self._target)

                self._set_new_stop()

                self._fn = "try_exiting_trade"
        except Exception as e:
            logging.error(f"{e} while place exit order")
            print_exc()

    def _new_stop(self):
        # 1. Extract the percentage (e.g., "50%" -> 0.50)
        # Using .strip("%") allows us to convert the user input to a math-ready float
        trail_percent = float(str(self._trail).strip("%")) / 100
        
        stop = self._stop
        fill = self.trade_mgr.position.average_price
        
        # 2. Calculate the total risk/distance
        # total_distance represents the full 100% gap.
        total_distance = abs(fill - stop)
        
        # 3. Apply the user-defined trailing factor
        # If user sets 50%, we move the stop 50% of the way towards the fill price.
        new_stop = stop + (total_distance * trail_percent)
        
        # 4. Finalize and execute
        rounded_stop = round_down_to_tick(last_price=new_stop)
        
        # Only move the stop if it's actually an improvement (protection)
        # For Buy: new_stop > old_stop
        self.trade_mgr.stop(stop_price=rounded_stop)

    def _no_new_stop(self):
        return

    def try_exiting_trade(self):
        try:
            self._last_idx = self._time_mgr.current_index

            status = self.trade_mgr.is_trade_exited(self._last_price, self._trades)

            if status > 0:
                self._fn = "wait_for_breakout"
            if status == 2:
                self._removable =True
                self._fn = "remove_me"

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
