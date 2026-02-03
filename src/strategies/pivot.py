from src.constants import logging_func

from toolkit.kokoo import is_time_past
from src.sdk.helper import Helper
from src.sdk.utils import round_down_to_tick

from src.providers.trade_manager import TradeManager
from src.providers.time_manager import TimeManager
from src.providers.grid import Gridlines
from src.providers.utils import table

from traceback import print_exc

from enum import IntEnum

logging = logging_func(__name__)


class BreakoutState(IntEnum):
    DEFAULT = 0  # waiting fore new candle + breakout
    ARMED = 1  # breakout detected, monitoring for Condition 2


class Pivot:

    def __init__(self, **kwargs):
        # initialize
        self._trades = []

        # from parameters
        self.strategy = kwargs["strategy"]
        self.stop_time = kwargs["stop_time"]
        self._rest = kwargs["rest"]

        self.option_type = kwargs["option_type"]
        self._option_token = kwargs["option_token"]
        self._option_exchange = kwargs["option_exchange"]
        self._quantity = kwargs["quantity"]
        self._tradingsymbol = kwargs["tradingsymbol"]

        self._last_price = kwargs.get("ltp", 10000)

        prices = [
            0,
            100,
            200,
            300,
            400,
            500,
            600,
            700,
            800,
            900,
            1000,
            1100,
            1200,
            1300,
            1400,
            1500,
            1600,
        ]
        self.gridlines = Gridlines(prices=prices, reverse=False)
        self._state = BreakoutState.DEFAULT
        self._stop = None
        self._target = None

        self._time_mgr = TimeManager({"minutes": 1})
        self._last_idx = self._time_mgr.current_index
        # objects and dependencies
        self.trade_mgr = TradeManager(
            stock_broker=Helper.api(),
            symbol=self._tradingsymbol,
            exchange=self._option_exchange,
            quantity=self._quantity,
            tag=self.strategy,
        )
        self._count = 1
        # state variables
        self._removable = False
        self._fn = "wait_for_breakout"

    """
    def is_breakout(self):
        try:

            if self._is_breakout:

                self._count += 1

                if self._count % 2 == 0:
                    # 3. place entry
                    order_id = self.trade_mgr.complete_entry(price=self._last_price)
                    if order_id:
                        self._fn = "place_exit_order"
                        return
                else:
                    logging.debug(
                        f"SKIPPING TRADE# {self._count-2}: ltp:{self._last_price} pivot:{self._stop}"
                    )

        except Exception as e:
            logging.error(f"{e} while waiting for breakout")
            print_exc()
    """

    def _set_stop(self):
        _, stop, target = self.gridlines.find_current_grid(self._last_price)
        self._stop = stop
        self._target = target
        return self._stop

    def wait_for_breakout(self):
        try:
            curr_idx = self._time_mgr.current_index

            # --- PHASE 1: ARMING (Condition 1) ---
            if self._state == BreakoutState.DEFAULT:
                if curr_idx > self._last_idx:
                    # Mark this candle as "seen" regardless of price action
                    self._last_idx = curr_idx

                    if self._last_price > self._set_stop():  # ignore
                        self._state = BreakoutState.ARMED
                        logging.info(
                            f"ARMED: {self._tradingsymbol} @{self._last_price} > {self._stop}"
                        )
                return  # Exit Phase 1

            # --- PHASE 2: VALIDATION & EXECUTION ---
            if self._state == BreakoutState.ARMED:
                # 1. Monitoring Phase (Same Candle)
                if curr_idx == self._last_idx:
                    if self._last_price <= self._stop:
                        self._state = BreakoutState.DEFAULT
                        logging.info(
                            f"DISARMED: {self._tradingsymbol} - Stop {self._stop} breached @{self._last_price}"
                        )
                    return

                # 2. Execution Phase (Index has incremented)
                # Since we are still ARMED and the index changed, Step 2 was successful.
                is_entered = self.trade_mgr.complete_entry(price=self._last_price)

                # Reset state before moving to the next phase
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
        new_stop = fill + buffer
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
            if self.trade_mgr.is_trade_exited(self._last_price, self._trades):
                self._fn = "wait_for_breakout"
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
            if status > 0:
                self._fn = "remove_me"
            return

        self._removable = True

    def run(self, trades, quotes, positions):
        try:

            """needed for removing the object"""

            self._trades = trades

            ltp = quotes.get(self._tradingsymbol, None)
            if ltp is not None:
                self._last_price = float(ltp)

            if is_time_past(self.stop_time):
                logging.info(f"REMOVING: {self._tradingsymbol} .. ")
                self.remove_me()
                return

            table(self)
            return getattr(self, self._fn)()
        except Exception as e:
            logging.error(f"{e} in running {self._tradingsymbol}")
            print_exc()
