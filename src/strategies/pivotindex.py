from src.constants import logging, S_SETG, yml_to_obj

from src.sdk.helper import Helper
from src.config.interface import Trade

from src.providers.time_manager import TimeManager
from src.providers.trade_manager import TradeManager
from src.providers.state_manager import StateManager

import pendulum as pdlm
from traceback import print_exc
from sys import exit

MAX_TRADE_COUNT = 5

condition = {
    "PE": lambda curr, prev: curr < prev,
    "CE": lambda curr, prev: curr > prev,
}


class Pivotindex:

    def __init__(
        self, prefix: str, symbol_info: dict, user_settings: dict, pivot_grids
    ):
        # A hard coded
        self._removable = False
        self._stop = symbol_info["ltp"]
        self._low = symbol_info["ltp"]

        # 1. Core Attributes (directly from parameters)
        self._prefix = prefix
        self._id = symbol_info["symbol"]
        self.option_type = symbol_info["option_type"]
        self._index = user_settings["index"]
        self._token = symbol_info["token"]

        # 2. Derived Attributes (calculated from core attributes)
        self._other_option = "CE" if self.option_type == "PE" else "PE"
        self._condition = condition[self.option_type]
        self.underlying_ltp = float(user_settings["underlying_ltp"])

        # 3. Dependencies and Helper Objects
        self.trade = Trade(
            symbol=self._id,
            last_price=symbol_info["ltp"],
            exchange=user_settings["option_exchange"],
            quantity=user_settings["quantity"],
        )
        self.lines = Gridlines(prices=pivot_grids, reverse=False)
        self._time_mgr = TimeManager(rest_min=user_settings["rest_min"])
        self._trade_manager = TradeManager(Helper.api())

        # 4. State Variables
        self._low_cache = {}
        self._fn = "is_index_breakout"

        # 5. Class-level state management (if you choose to keep it)
        # Note: You can either keep these as class variables or pass them as parameters.
        # As discussed, using class variables is a design choice with pros and cons.
        idx = self.lines.find_current_grid(self.underlying_ltp)
        StateManager.initialize_prefix(prefix=self._prefix)
        StateManager.set_idx(prefix=self._prefix, option_type=self.option_type, idx=idx)
        logging.info(f"INITIAL IDX: {self._id} is set at {idx}")

    def _reset_trade(self):
        self.trade.filled_price = None
        self.trade.status = None
        self.trade.order_id = None

    def _entry(self):
        self.trade.side = "B"
        self.trade.disclosed_quantity = None
        self.trade.price = self.trade.last_price + 2  # type: ignore
        self.trade.trigger_price = 0.0
        self.trade.order_type = "LMT"
        self.trade.tag = "entry_pivot"
        self._reset_trade()

        buy_order = self._trade_manager.complete_entry(self.trade)
        if buy_order.order_id is not None:
            self._fn = "find_fill_price"
            return True
        logging.warning(
            f"got {buy_order} without buy order order id {self.trade.symbol}"
        )
        return False

    def is_index_breakout(self):
        try:
            # evaluate the condition
            curr_idx = self.lines.find_current_grid(self.underlying_ltp)
            prev_idx = StateManager.get_idx(self._prefix, self.option_type)

            if self._condition(curr_idx, prev_idx):
                logging.info(
                    f"INDEX BREAKOUT: {self._id} curr:{curr_idx}  prev:{prev_idx} ltp:{self.underlying_ltp}"
                )
                # update index for this option because breakout happened
                StateManager.set_idx(self._prefix, self.option_type, curr_idx)
                logging.info(f"INDEX SET: {self._id} curr:{curr_idx}")

                # set indices for other option only if not traded before
                if not StateManager.is_traded_once(self._prefix):
                    # update index for other option if not traded before
                    StateManager.set_idx(self._prefix, self._other_option, curr_idx)
                    logging.info(f"INDEX SET: for {self._other_option} curr:{curr_idx}")

                # hack to prevent index from updating again and again
                StateManager.traded_once(self._prefix)

                # wait for breakout
                self._fn = "wait_for_breakout"
                self.wait_for_breakout()
            else:
                self._low = self._stop = self.trade.last_price

        except Exception as e:
            logging.error(f"{e} while checking index breakout")
            print_exc()

    def wait_for_breakout(self):
        try:
            if self._time_mgr.can_trade and not StateManager.is_in_trade(self._prefix):
                if self.trade.last_price > self._stop:  # type: ignore
                    is_entered = self._entry()
                    if is_entered:
                        if (
                            StateManager.get_trade_count(self._prefix, self.option_type)
                            == 0
                        ):
                            self._last_buy_at = pdlm.now("Asia/Kolkata")
                        StateManager.start_trade(self._prefix, self.option_type)
            print(
                f"WAITING: {self._id}: ltp{self.trade.last_price} < stop:{self._stop}"
            )
        except Exception as e:
            logging.error(f"{e} while waiting for breakout")
            print_exc()

    def low(self):
        try:
            rst = Helper._rest
            intl = rst.history(
                exchange=self.trade.exchange,
                token=self._token,
                loc=self._last_buy_at,
                key="intl",
            )
            if intl:
                self._low = intl
            return intl
        except Exception as e:
            logging.error(f"Pivot: while getting error {e}")
            print_exc()

    def _set_stop_for_next_trade(self):
        try:
            count = StateManager.get_trade_count(self._prefix, self.option_type)
            if count < MAX_TRADE_COUNT:
                if count > 0:
                    _ = self.low()
                    if self._stop > self._low:
                        logging.info(
                            f"#{count} NEW STOP: {self._low} instead of old STOP {self._stop}"
                        )
                        self._stop = self._low
        except Exception as e:
            logging.error(f"set stop for next trade: {e}")
            print_exc()

    def find_fill_price(self):
        order = self._trade_manager.find_order_if_exists(
            self._trade_manager.position.entry.order_id, self._orders
        )
        if isinstance(order, dict):
            self._fill_price = float(order["fill_price"])
            # place sell order only if buy order is filled
            self.trade.side = "S"
            self.trade.disclosed_quantity = 0
            self.trade.price = self._stop - 2
            self.trade.trigger_price = self._stop
            self.trade.order_type = "SL-LMT"
            self.trade.tag = "sl_pivot"
            self._reset_trade()
            sell_order = self._trade_manager.pending_exit(self.trade)
            if sell_order.order_id is not None:
                self._fn = "try_exiting_trade"
            else:
                logging.error(f"id is not found for sell {sell_order}")
        else:
            logging.warning(
                f"{self.trade.symbol} buy order {self._trade_manager.position.entry.order_id} not complete, to find fill price"
            )

    def _is_stoploss_hit(self):
        try:
            O_SETG = yml_to_obj(S_SETG)
            if O_SETG.get("live", 1) == 1:
                order = self._trade_manager.find_order_if_exists(
                    self._trade_manager.position.exit.order_id, self._orders
                )
                if isinstance(order, dict):
                    return True
            else:
                logging.debug("CHECKING STOP IN PAPER MODE")
                return Helper.api.can_move_order_to_trade(
                    self._trade_manager.position.exit.order_id, self.trade.last_price
                )
        except Exception as e:
            logging.error(f"{e} is stoploss hit {self.trade.symbol}")
            print_exc()

    def _modify_to_exit(self):
        try:
            kwargs = dict(
                trigger_price=0.0,
                order_type="LIMIT",
                last_price=self.trade.last_price,
            )
            return self._trade_manager.complete_exit(**kwargs)
        except Exception as e:
            logging.error(f"{e} while modify to exit {self.trade.symbol}")
            print_exc()

    def _modify_to_kill(self):
        try:
            kwargs = dict(
                price=0.0,
                order_type="MARKET",
                last_price=self.trade.last_price,
            )
            return self._trade_manager.complete_exit(**kwargs)
        except Exception as e:
            logging.error(f"{e} while modify to exit {self.trade.symbol}")
            print_exc()

    def try_exiting_trade(self):
        try:
            # evaluate the condition
            curr, prev = self.lines.find_current_grid(
                self.underlying_ltp
            ), StateManager.get_idx(self._prefix, self.option_type)

            if self._condition(curr, prev):
                logging.info(
                    f"TARGET: {self.trade.symbol} curr:{curr} BROKE prev:{prev}"
                )
                self._modify_to_exit()
                exit(1)
            elif self._is_stoploss_hit():
                logging.info(
                    f"STOP HIT: {self.trade.symbol} with buy fill price {self._fill_price} hit stop {self._stop}"
                )
                self._fn = "wait_for_breakout"
            elif self.trade.last_price <= self._stop:  # type: ignore
                resp = self._modify_to_kill()
                logging.info(f"KILLING STOP: returned {resp}")
                self._fn = "wait_for_breakout"
            else:
                msg = f"PROGRESS: {self.trade.symbol} ltp:{self.trade.last_price} > stop:{self._stop}"
                print(msg)

            if self._fn == "wait_for_breakout":
                self._time_mgr.set_last_trade_time(pdlm.now("Asia/Kolkata"))
                # reset other option trades
                StateManager.end_trade(self._prefix, self._other_option)
                # reset stop and low
                self._stop = self._low = self.trade.last_price

        except Exception as e:
            logging.error(f"{e} while exit order")
            print_exc()

    def run(self, orders, ltps):
        try:
            self._orders = orders

            ltp = ltps.get(self.trade.symbol, None)
            if ltp is not None:
                self.trade.last_price = float(ltp)

            underlying = ltps.get(self._index, None)
            if underlying is not None:
                self.underlying_ltp = float(underlying)

            return getattr(self, self._fn)()
        except Exception as e:
            logging.error(f"{e} in running {self.trade.symbol}")
            print_exc()
