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
            candles = self._candle.get_candles()
            curr_idx = len(candles)
            
            # Need at least 1 candle
            if curr_idx < 1:
                return
            
            # Current candle
            curr = candles[-1]
            
            if (
                curr["low"] <= self._stop
                and curr["close"] > self._stop
                and self._armed_idx != curr_idx
            ):
                self._on_signal(curr_idx)
                self.prev_trade_at = self._stop
                return

            # Need at least 3 completed candles for 2-candle pattern
            if curr_idx < 4 or (curr_idx - self._armed_idx) < 3:
                return
            
            # Need at least 3 candles back (-1 is current, -2 and -3 are previous)
            if curr_idx < 3:
                return
            
            c2 = candles[-3]  # 3rd candle from end
            c1 = candles[-2]  # 2nd candle from end
            
            if (
                c2["close"] < c2["open"]
                and c1["close"] > c1["open"]
                and curr["close"] < self._target
                and curr["close"] > self.prev_trade_at
            ):
                self._on_signal(curr_idx)
                self.prev_trade_at = curr["close"]

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

    def run(self, position_book, quotes):
        try:
            self.rm.positions = position_book

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