from src.constants import logging, O_SETG
from src.helper import Helper
from src.time_manager import TimeManager
from src.trade import Trade
import pendulum as pdlm
from traceback import print_exc
from json import loads


def compute(ohlc_prefix):
    try:
        high, low, close = (
            float(ohlc_prefix["inth"]),
            float(ohlc_prefix["intl"]),
            float(ohlc_prefix["intc"]),
        )
        pivot = (high + low + close) / 3.0
        """
        bc = (high + low) / 2.0
        tc = (pivot - bc) + pivot
        """
        R5 = (pivot * 4) + high - (4 * low)
        R4 = (pivot * 3) + high - (3 * low)
        R3 = high + (2 * (pivot - low))
        R2 = pivot + (high - low)
        R1 = (2 * pivot) - low
        S1 = (2 * pivot) - high
        S2 = pivot - (high - low)
        S3 = low - (2 * (high - pivot))
        S4 = (pivot * 3) - (high * 3) - low
        S5 = (pivot * 4) - (high * 4) - low
        r9 = R3 + R2 + R1 + pivot + S1 + S2 + S3
        lst = [r9, R5, R4, R3, R2, R1, pivot, S1, S2, S3, S4, S5, 0]
        lst = [int(item) for item in lst]
        return lst
    except Exception as e:
        logging.error(f"{e} while computing grid")
        print_exc()


class Grid:
    grid = {}

    @classmethod
    def run(cls, api, prefix, symbol_constant):
        try:
            if cls.grid.get(prefix, None) is None:
                start = pdlm.now().subtract(days=4).timestamp()
                now = pdlm.now().timestamp()
                ret = api.broker.get_daily_price_series(
                    exchange=symbol_constant[prefix]["exchange"],
                    tradingsymbol=symbol_constant[prefix]["index"],
                    startdate=start,
                    enddate=now,
                )
                ohlc = loads(ret[0])
                cls.grid[prefix] = compute(ohlc)
            return cls.grid[prefix]
        except Exception as e:
            logging.error(f"{e} while computing grid")
            print_exc()
            __import__("sys").exit(1)


class Gridlines:
    def __init__(self, prices: list, reverse: bool):
        print("prices", prices)
        levels = sorted(prices, reverse=reverse)
        self.lines = list(zip(levels[:-1], levels[1:]))
        print("gridlines", self.lines)

    def find_current_grid(self, ltp: float):
        for idx, (a, b) in enumerate(self.lines):
            low, high = min(a, b), max(a, b)
            if low <= ltp < high:
                logging.debug(f"pivot l:{low} ltp:{ltp} h:{high}")
                return idx


class Pivot:
    def __init__(
        self, prefix: str, symbol_info: dict, user_settings: dict, pivot_grids
    ):
        self._removable = False
        self._prefix = prefix
        self._id = symbol_info["symbol"]
        self._low = None
        self._time_mgr = TimeManager(rest_min=user_settings["rest_min"])
        self.trade = Trade(
            symbol=symbol_info["symbol"],
            last_price=symbol_info["ltp"],
            exchange=user_settings["option_exchange"],
            quantity=user_settings["quantity"],
        )
        base_expiry = user_settings["base"] + user_settings["expiry"]
        option_type = symbol_info["symbol"][len(base_expiry) :][0]
        reverse = True if option_type == "P" else False
        self.lines = Gridlines(prices=pivot_grids, reverse=reverse)
        self.is_breakout = "_index_breakout"
        self._fn = "wait_for_breakout"

    @property
    def curr_idx(self):
        try:
            return self._curr_idx
        except AttributeError:
            self._curr_idx = self.lines.find_current_grid(self.underlying_ltp)
            return self._curr_idx

    @curr_idx.setter
    def curr_idx(self, idx):
        self._curr_idx = idx

    @property
    def _index_breakout(self):
        idx = self.lines.find_current_grid(self.underlying_ltp)
        if idx > self.curr_idx and self._time_mgr.can_trade:
            # set the idx of the grid from which trade happened
            self.curr_idx = idx
            # set low to the new trade price
            self._low = self.trade.last_price
            self.is_breakout = "_option_breakout"
            return True

        self.curr_idx = idx
        msg = (
            f"{self.trade.symbol} waiting ... curr pivot: {idx} > prev pivot:{self.curr_idx} "
            f"and can_trade: {self._time_mgr.can_trade}"
        )
        logging.debug(msg)
        return False

    @property
    def _option_breakout(self):
        if self.trade.last_price >= self._low and self._time_mgr.can_trade:
            return True
        msg = (
            f"{self.trade.symbol} waiting ... ltp: {self.trade.last_price} > low: {self._low} "
            f"and can trade: {self._time_mgr.can_trade}"
        )
        logging.debug(msg)
        return False

    def _reset_trade(self):
        self.trade.filled_price = None
        self.trade.status = None
        self.trade.order_id = None

    def wait_for_breakout(self):
        try:
            if getattr(self, self.is_breakout):
                self.trade.side = "B"
                self.trade.disclosed_quantity = None
                self.trade.price = self.trade.last_price + 2
                self.trade.trigger_price = 0.0
                self.trade.order_type = "LMT"
                self.trade.tag = "entry_pivot"
                self._reset_trade()
                buy_order = self._trade_manager.complete_entry(self.trade)
                if buy_order.order_id is not None:
                    self._fn = "find_fill_price"
                else:
                    logging.warning(
                        f"got {buy_order} without buy order order id {self.trade.symbol}"
                    )
        except Exception as e:
            logging.error(f"{e} while waiting for breakout")
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
            self.trade.price = self._low - 2
            self.trade.trigger_price = self._low
            self.trade.order_type = "SL-LMT"
            self.trade.tag = "sl_pivot"
            self._reset_trade()
            sell_order = self._trade_manager.pending_exit(self.trade)
            if sell_order.order_id is not None:
                self._fn = "try_exiting_trade"
            else:
                logging.error(f"id is not found for sell {sell_order}")
        else:
            logging.error(
                f"order {self._trade_manager.position.entry.order_id} not complete"
            )

    def _is_stoploss_hit(self):
        try:
            if O_SETG["trade"].get("live", 0) == 0:
                logging.debug("CHECKING STOP IN PAPER MODE")
                return Helper.api.can_move_order_to_trade(
                    self._trade_manager.position.exit.order_id, self.trade.last_price
                )
            else:
                order = self._trade_manager.find_order_if_exists(
                    self._trade_manager.position.exit.order_id, self._orders
                )
                if isinstance(order, dict):
                    return True
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
            if self.lines.find_current_grid(self.underlying_ltp) > self.curr_idx:
                logging.info("TARGET reached")
                self._modify_to_exit()
                self.is_breakout = "_index_breakout"
                self._fn = "wait_for_breakout"
            elif self._is_stoploss_hit():
                logging.info(f"{self.trade.symbol} stop loss: {self._fill_price} hit")
                self._time_mgr.set_last_trade_time(pdlm.now("Asia/Kolkata"))
                self._fn = "wait_for_breakout"
            elif self.trade.last_price <= self._low:
                resp = self._modify_to_kill()
                logging.info(f"stop hit: kill returned {resp}")
                self._time_mgr.set_last_trade_time(pdlm.now("Asia/Kolkata"))
                self._fn = "wait_for_breakout"

        except Exception as e:
            logging.error(f"{e} while exit order")
            print_exc()

    def run(self, orders, ltps, underlying_ltp):
        try:
            self._orders = orders

            ltp = ltps.get(self.trade.symbol, None)
            if ltp is not None:
                self.trade.last_price = float(ltp)

            self.underlying_ltp = (
                underlying_ltp if underlying_ltp else self.underlying_ltp
            )

            return getattr(self, self._fn)()
        except Exception as e:
            logging.error(f"{e} in running {self.trade.symbol}")
            print_exc()


"""
into = history(
    api=api,
    exchange=symbol_constant[prefix]["exchange"],
    token=symbol_constant[prefix]["token"],
    loc=-1,
    key="into",
)
cls.grid[prefix]["into"] = into
"""
