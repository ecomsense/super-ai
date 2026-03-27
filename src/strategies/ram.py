from enum import IntEnum
from traceback import print_exc

import pendulum as pdlm
from toolkit.kokoo import is_time_past, timer

from src.constants import logging_func
from src.providers.time_manager import TimeManager
from src.providers.grid import StopAndTarget
from src.sdk.utils import calc_highest_target

logging = logging_func(__name__)


def always_true():
    return True


class BreakoutState(IntEnum):
    DEFAULT = 0  # waiting fore new candle + breakout
    ARMED = 1  # breakout detected, monitoring for Condition 2


class Ram:
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
        self._tradingsymbol = kwargs["tradingsymbol"]
        self._last_price = kwargs.get("ltp", float("inf"))
        self.strategy = kwargs["strategy"]

        self.stop_time = kwargs["stop_time"]
        self.option_type = kwargs["option_type"]
        self.pm = kwargs["pm"]
        self._option_exchange = kwargs["option_exchange"]
        self._quantity = kwargs["quantity"]

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

        target_set_by_user = kwargs.get("target", "50%")

        # objects and dependencies
        high = calc_highest_target(high=low, target=target_set_by_user)
        prices = [(0, low), (low, high), (high, high)]
        logging.info(f"grid we are going to trade today {prices}")
        self.gridlines = StopAndTarget(prices)

        rest_time = kwargs.get("rest_time", {"minutes": 1})
        self._time_mgr = TimeManager(rest_time)
        self._last_idx = self._time_mgr.current_index + 1

        # strategy specific and optional
        self._trail = kwargs.get("trail", None)

        self._reentry = kwargs.get("reentry", None)
        if self._reentry:
            self._is_reentry = self._is_entry
            self._count = 1
        else:
            self._is_reentry = always_true

        # dummies
        self._low = low
        self._high = high
        self.pos_id = None
        self._armed_idx = -1

    def _set_stop(self):
        _, self._stop, self._target = self.gridlines.find_current_grid(self._last_price)
        return self._stop

    def wait_for_breakout(self, is_new_candle):
        try:
            curr_idx = self._time_mgr.current_index

            # --- PHASE 1: SEARCHING (DEFAULT STATE) ---
            if self._state == BreakoutState.DEFAULT and is_new_candle:
                # We only look for a NEW grid level when we aren't already tracking one
                stop_level = self._set_stop()

                if stop_level is None:
                    return

                # Check if the previous minute's price action crossed the CURRENT stop_level
                if (
                    self._prev_period_low <= stop_level
                    and self._last_price > stop_level
                ):
                    self._state = BreakoutState.ARMED
                    logging.info(
                        f"ARMED: {self._tradingsymbol} locked at {stop_level} on candle #{curr_idx} "
                        f"and prev candle lowest is {self._prev_period_low}"
                    )
                self._armed_idx = curr_idx
                return

            # --- PHASE 2: VALIDATION (ARMED STATE) ---
            if self._state == BreakoutState.ARMED and self._armed_idx == curr_idx:
                # 1. Monitoring Phase (Within the arming candle)
                # If price fails the breakout line or hits the next target TOO FAST
                if self._period_low < self._stop or self._last_price > self._target:
                    logging.info(
                        f"DISARMED: Low {self._period_low} violated locked levels "
                        f"(Stop: {self._stop}, Target: {self._target})"
                    )
                    self._state = BreakoutState.DEFAULT
                    return

                # 2. Execution Phase (Candle has closed, index has incremented)
                logging.info(f"SUCCESS: {self._tradingsymbol} held above {self._stop}")

                # We use self._stop as the reference for the entry
                if self._is_reentry():
                    self.pos_id = self.pm.new(
                        symbol=self._tradingsymbol,
                        exchange=self._option_exchange,
                        quantity=self._quantity,
                        tag=self.strategy,
                        entry_price=self._last_price,
                        stop_loss=0,
                        exit_method="target",
                        target=self._target,
                        trail_percent=self._trail,
                    )
                    if self.pos_id:
                        self._fn = "try_exiting_trade"
                else:
                    logging.info(
                        "SORRY: We are passing this trade due to odd/even rule"
                    )

                # Reset state for next cycle
                self._state = BreakoutState.DEFAULT
                self._last_idx = curr_idx

        except Exception as e:
            logging.error(f"Wait for breakout: {e}")
            print_exc()

    def _is_entry(self):
        is_odd = bool(self._count % 2)
        self._count += 1
        if self._reentry == "odd":
            return is_odd
        return not is_odd

    def try_exiting_trade(self):
        try:
            if self.pos_id is not None:
                status = self.pm.status(
                    pos_id=self.pos_id,
                    last_price=self._last_price,
                    orders=self._trades,
                    removable=self._removable,
                )

                if status in ["stop_hit", "position_unknown"]:
                    self.pos_id = None
                elif status == "target_reached" or is_time_past(self.stop_time):
                    # if target is reached there is no further trade for this symbol
                    # TODO
                    self._removable = True

        except Exception as e:
            logging.error(f"{e} while exit order")
            print_exc()

    def run(self, trades, quotes, positions):
        try:
            self._trades = trades
            ltp = quotes.get(self._tradingsymbol)
            if ltp is None:
                return
            self._last_price = float(ltp)

            # 1. Update Candle Logic (Minute Tracker)
            is_new_candle = False
            if self._time_mgr.current_index > self._last_idx:
                is_new_candle = True
                self._prev_period_low = self._period_low
                self._period_low = self._last_price
                self._last_idx = self._time_mgr.current_index
            else:
                self._period_low = min(self._period_low, self._last_price)

            # 2. Global Stop Time Check
            if is_time_past(self.stop_time):
                self._removable = True

            # 3. Main Logic Branch (Straightforward)
            if self.pos_id is None:
                self.wait_for_breakout(is_new_candle)
            else:
                self.try_exiting_trade()

        except Exception as e:
            logging.error(f"Run Error {self._tradingsymbol}: {e}")
            print_exc()
