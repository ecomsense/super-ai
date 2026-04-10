from traceback import print_exc

import pendulum as pdlm
from toolkit.kokoo import is_time_past, timer

from src.constants import logging_func
from src.providers.candle_manager import CandleManager
from src.sdk.utils import calc_highest_target

from src.providers.risk_manager import RiskManager

logging = logging_func(__name__)


class Ram:
    def __init__(self, **kwargs):
        self._removable = False

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
            timer(0.5)
            self._stop = kwargs["rest"].history(
                token=kwargs["option_token"],
                exchange=kwargs["option_exchange"],
                loc=pdlm.now("Asia/Kolkata").replace(**low_candle_time),
                key="intl",
            )

        self.prev_trade_at = self._stop

        target_set_by_user = kwargs.get("target", "50%")

        # objects and dependencies
        self._target = calc_highest_target(high=self._stop, target=target_set_by_user)

        rest_time = kwargs.get("rest_time", {"minutes": 1})

        self._candle = CandleManager(rest_time["minutes"])
        self._candle.add_tick(self._last_price)

        self._armed_idx = 0
        self.pos_id = None

    def _on_signal(self, curr_idx):
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

    def wait_for_breakout(self):
        try:
            candle = self._candle.transform()
            curr_idx = len(candle)
            if (
                candle.iloc[-1]["low"] <= self._stop
                and self._last_price > self._stop
                and self._armed_idx != curr_idx
            ):
                self._on_signal(curr_idx)
                self.prev_trade_at = self._stop
                return

            # two candle condition
            if curr_idx < 4 or (curr_idx - self._armed_idx) < 3:
                return

            if (
                (candle.iloc[-3]["close"] < candle.iloc[-3]["open"])
                and (candle.iloc[-2]["close"] > candle.iloc[-2]["open"])
                and self._last_price < self._target
                and self._last_price > self.prev_trade_at
            ):
                self._on_signal(curr_idx)
                self.prev_trade_at = self._last_price

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
            ltp = quotes.get(self._tradingsymbol)
            if ltp is None:
                return
            self._last_price = float(ltp)
            self._candle.add_tick(self._last_price)

            # no need to wait for breakout if time is up
            if not is_time_past(self.stop_time) and not self._removable:
                self.wait_for_breakout()

            # if there are no positions then there is nothing to manage
            if self.pos_id and self._last_price > self._target:
                self.try_exiting_trade()

        except Exception as e:
            logging.error(f"Run Error {self._tradingsymbol}: {e}")
            print_exc()
