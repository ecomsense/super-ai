from traceback import print_exc

import pendulum as pdlm
from toolkit.kokoo import is_time_past, timer

from src.constants import logging_func
from src.providers.time_manager import TimeManager
from src.sdk.utils import calc_highest_target

from src.providers.risk_manager import RiskManager

logging = logging_func(__name__)


class Ram:
    def __init__(self, **kwargs):
        self._removable = False
        self._period_low = 1000000

        # from parameters
        self._tradingsymbol = kwargs["tradingsymbol"]
        self._last_price = kwargs.get("ltp", float("inf"))
        self.strategy = kwargs["strategy"]

        self.stop_time = kwargs["stop_time"]
        self.rm: RiskManager = kwargs["rm"]
        self._option_exchange = kwargs["option_exchange"]
        self._quantity = kwargs["quantity"]

        default_time = {"hour": 9, "minute": 14, "second": 59}
        low_candle_time = kwargs.get("low_candle_time", default_time)
        self._stop = None
        while self._stop is None:
            self._stop = kwargs["rest"].history(
                token=kwargs["option_token"],
                exchange=kwargs["option_exchange"],
                loc=pdlm.now("Asia/Kolkata").replace(**low_candle_time),
                key="intl",
            )
            timer(1)

        target_set_by_user = kwargs.get("target", "50%")

        # objects and dependencies
        self._target = calc_highest_target(high=self._stop, target=target_set_by_user)

        rest_time = kwargs.get("rest_time", {"minutes": 1})
        self._time_mgr = TimeManager(rest_time)
        self._armed_idx = self._time_mgr.current_index - 1
        self._last_idx = self._armed_idx
        self.pos_id = None

    def wait_for_breakout(self):
        try:
            curr_idx = self._time_mgr.current_index
            if (
                self._period_low <= self._stop
                and self._last_price > self._stop
                and self._armed_idx != curr_idx
            ):
                self.pos_id = self.rm.new(
                    symbol=self._tradingsymbol,
                    exchange=self._option_exchange,
                    quantity=self._quantity,
                    tag=self.strategy,
                    entry_price=self._last_price,
                    target=self._target,
                    stop_loss=0,
                )
                self._armed_idx = curr_idx

        except Exception as e:
            logging.error(f"Wait for breakout: {e}")
            print_exc()

    def try_exiting_trade(self):
        try:
            status = self.rm.status(
                pos_id=self.pos_id,
                last_price=self._last_price,
            )
            if is_time_past(self.stop_time) and status <= 0:
                self._removable = True
                self.pos_id = None

        except Exception as e:
            logging.error(f"{e} while exit order")
            print_exc()

    def run(self, quotes):
        try:
            # get quotes
            prev_price = self._last_price
            ltp = quotes.get(self._tradingsymbol)
            if ltp is None:
                return
            self._last_price = float(ltp)

            # 1. Update Candle Logic (Minute Tracker)
            curr_idx = self._time_mgr.current_index
            if curr_idx > self._last_idx:
                self._period_low = min(prev_price, self._last_price)
                self._last_idx = curr_idx
            else:
                self._period_low = min(self._period_low, self._last_price)

            # no need to wait for breakout if time is up
            if not is_time_past(self.stop_time) and not self._removable:
                self.wait_for_breakout()

            # if there are no positions then there is nothing to manage
            if self.pos_id and self._last_price > self._target:
                self.try_exiting_trade()

        except Exception as e:
            logging.error(f"Run Error {self._tradingsymbol}: {e}")
            print_exc()
