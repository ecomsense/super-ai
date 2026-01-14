from src.constants import logging_func
from src.sdk.helper import Helper

from src.providers.trade_manager import TradeManager
from src.providers.time_manager import TimeManager
from src.providers.utils import table

from traceback import print_exc
import pendulum as pdlm
from math import ceil


logging = logging_func(__name__)


class Openingbalance:
    def __init__(self, prefix: str, symbol_info: dict, user_settings: dict, rest):
        # initialize
        self._max_target_reached = 0
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
        self._last_idx = self._time_mgr.current_index
        self._is_armed = False
        self._breached_mid_candle = False
        self._entry_index = -1
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
            if self._stop is not None:
                intl = self._rest.history(
                    exchange=self._exchange,
                    token=self._token,
                    loc=pdlm.now("Asia/Kolkata").replace(hour=9, minute=16),
                    key="intl",
                )
                if intl is not None:
                    self._stop = intl
                    self._fn = "wait_for_breakout"
            return self._stop
        except Exception as e:
            logging.error(f"set stop for next trade: {e}")
            print_exc()

    def wait_for_breakout(self):
        try:
            curr_idx = self._time_mgr.current_index

            # Condition: Don't trade in the same candle as a previous entry
            if curr_idx == self._entry_index:
                return

            # PHASE 1: Detection of a New Candle & Breakout (Condition 1)
            # Only check for a fresh arming if we aren't currently validating one
            if not self._is_armed and curr_idx > self._last_idx:
                if self._last_price > self._stop:
                    self._is_armed = True
                    self._breached_mid_candle = False
                    self._last_idx = (
                        curr_idx  # Mark this candle as the "Validation" candle
                    )
                return

            # PHASE 2: Validation (Condition 2)
            # While we are in the same candle index where we armed
            if self._is_armed and curr_idx == self._last_idx:
                if self._last_price <= self._stop:
                    self._breached_mid_candle = True
                    self._is_armed = False  # Trip the safety: Disarm immediately
                return

            # PHASE 3: Execution on Next Candle (Condition 3)
            # If the index moves forward and we survived the validation phase
            if (
                self._is_armed
                and not self._breached_mid_candle
                and curr_idx > self._last_idx
            ):
                is_entered = self.trade_mgr.complete_entry(
                    quantity=self._quantity, price=self._last_price + 2
                )
                if is_entered:
                    self._entry_index = curr_idx
                    self._is_armed = False
                    self._fn = "place_exit_order"
                return

            # Update index tracker if no trade was taken
            if curr_idx > self._last_idx:
                self._last_idx = curr_idx

            logging.debug(
                f"WAITING: {self._symbol}: ltp{self._last_price} < stop:{self._stop}"
            )

        except Exception as e:
            print(f"Error in state machine: {e}")

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
            # if trail stopped return prefix
            is_prefix = self._set_target()
            if is_prefix:
                return self._prefix

            if self.trade_mgr.is_trade_exited(
                self._last_price, self._orders, removable=self._removable
            ):
                self._fn = "remove_me"
                return self._prefix
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
        if self._fn == "try_exiting_trade":
            self.trade_mgr.is_trade_exited(self._last_price, self._orders, True)
        elif self._fn == "wait_for_breakout":
            logging.info(
                f"REMOVING: {self._symbol} switching from waiting for breakout"
            )

        self._fn = "remove_me"
        self._removable = True

    def run(self, orders, ltps, prefixes: list, positions):
        try:
            self._orders = orders

            if positions and any(positions):
                self._positions = positions

            ltp = ltps.get(self._symbol, None)
            if ltp is not None:
                self._last_price = float(ltp)

            if self._prefix in prefixes:
                self.remove_me()

            result = getattr(self, self._fn)()
            table(self)
            return result
        except Exception as e:
            logging.error(f"{e} in running {self._symbol}")
            print_exc()
