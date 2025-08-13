from src.constants import logging, O_SETG
from src.helper import Helper, history
from src.time_manager import TimeManager
from src.trade_manager import TradeManager
from src.trade import Trade
import pendulum as pdlm
from traceback import print_exc
from json import loads
from typing import Dict, List, Any

def compute(ohlc_prefix):
    try:
        high, low, close = (
            float(ohlc_prefix["inth"]),
            float(ohlc_prefix["intl"]),
            float(ohlc_prefix["intc"]),
        )
        pivot = (high + low + close) / 3.0
        logging.info(f"{pivot=}")
        R5 = (pivot * 4) + high - (4 * low)
        logging.info(f"{R5=}")
        R4 = (pivot * 3) + high - (3 * low)
        logging.info(f"{R4=}")
        R3 = high + (2 * (pivot - low))
        logging.info(f"{R3=}")
        R2 = pivot + (high - low)
        logging.info(f"{R2=}")
        R1 = (2 * pivot) - low
        logging.info(f"{R1=}")
        S1 = (2 * pivot) - high
        logging.info(f"{S1=}")
        S2 = pivot - (high - low)
        logging.info(f"{S2=}")
        S3 = low - (2 * (high - pivot))
        logging.info(f"{S3=}")
        S4 = (pivot * 3) - (high * 3) - low
        logging.info(f"{S4=}")
        S5 = (pivot * 4) - (high * 4) - low
        logging.info(f"{S5=}")
        r9 = R3 + R2 + R1 + pivot + S1 + S2 + S3
        logging.info(f"{r9=}")
        lst = [r9, R5, R4, R3, R2, R1, pivot, S1, S2, S3, S4, S5, 0]
        lst = [int(item) for item in lst]
        return lst
    except Exception as e:
        logging.error(f"{e} while computing grid")
        print_exc()


class Grid:
    grid = {}

    @classmethod
    def run(
        cls, api: Helper, prefix: str, symbol_constant: Dict[str, Any]
    ):
        """
        Computes the grid levels for the given symbol and prefix.

        Args:
            api: An instance of the Helper class.
            prefix: The market prefix.
            symbol_constant: A dictionary containing information about the symbol.

        Returns:
            A list of 13 integers representing the grid levels.
        """
        logging.info(f"Grid running: {symbol_constant}")
        try:
            if cls.grid.get(prefix, None) is None:
                start = pdlm.now().subtract(days=5).timestamp()
                now = pdlm.now().timestamp()
                if all(k in symbol_constant for k in ["intl", "inth", "intc"]):
                    cls.grid[prefix] = compute(symbol_constant)
                else:
                    logging.info(f"Grid.run: {symbol_constant}")
                    ret = api.broker.get_daily_price_series( # type: ignore
                        exchange=symbol_constant["exchange"],
                        tradingsymbol=symbol_constant["index"],
                        startdate=start,
                        enddate=now,
                    )
                    if not ret:
                        msg = f'daily price series {symbol_constant["index"]} {ret}'
                        logging.error(msg)
                        __import__("sys").exit(1)
                    else:
                        ohlc = loads(ret[0])
                        logging.info(f"from grid {ohlc}")
                        cls.grid[prefix] = compute(ohlc)
            return cls.grid[prefix]
        except Exception as e:
            logging.error(f"{e} while computing grid")
            print_exc()
            __import__("sys").exit(1)


class Gridlines:
    def __init__(self, prices: list, reverse: bool):
        logging.info(f"prices {prices}")
        levels = sorted(prices, reverse=reverse)
        self.lines = list(zip(levels[:-1], levels[1:]))
        logging.info(f"gridlines {self.lines}")

    def find_current_grid(self, ltp: float)-> int:
        idx = -1
        for idx, (a, b) in enumerate(self.lines):
            lowest, highest = min(a, b), max(a, b)
            if lowest <= ltp < highest:
                logging.info(f"underlying ltp: {ltp} is between {lowest=} and {highest=}")
                return idx
        return idx


class Pivot:
    def __init__(
        self, prefix: str, symbol_info: dict, user_settings: dict, pivot_grids
    ):
        """
        Initializer for Pivot

        Parameters
        ----------
        prefix : str
            prefix of the strategy
        symbol_info : dict
            dictionary containing symbol information
        user_settings : dict
            dictionary containing user settings
        pivot_grids : list
            list of pivot levels

        Attributes
        ----------
        _removable : bool
            whether the strategy is removable
        _prefix : str
            prefix of the strategy
        _id : str
            id of the strategy
        _low : float
            lowest price of the index
        _time_mgr : TimeManager
            time manager for the strategy
        trade : Trade
            trade object
        lines : Gridlines
            gridlines object
        _fn : str
            name of the function to call
        _trade_manager : TradeManager
            trade manager for the strategy

        """

        self._removable = False
        self._prefix = prefix
        self._id = symbol_info["symbol"]
        self._low = 999999999
        self._stop = 999999999 
        self._time_mgr = TimeManager(rest_min=user_settings["rest_min"])
        self.trade = Trade(
            symbol=symbol_info["symbol"],
            last_price=symbol_info["ltp"],
            exchange=user_settings["option_exchange"],
            quantity=user_settings["quantity"],
        )
        self._token = symbol_info["token"]
        option_type = symbol_info["option_type"]
        reverse = True if option_type == "PE" else False
        self.lines = Gridlines(prices=pivot_grids, reverse=reverse)
        self._fn = "is_index_breakout"
        self._trade_manager = TradeManager(Helper.api())
    
    
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
    def low(self):
        intl = history(api=Helper.api(), exchange=self.trade.exchange, token=self._token, loc=0, key="intl")
        if intl:
            self._low = intl
        return self._low

    def is_index_breakout(self):
        idx = self.lines.find_current_grid(self.underlying_ltp)
        #todo introduce delay
        if idx > self.curr_idx:
            # set the idx of the grid from which trade happened
            self.curr_idx = idx
            self.fn = "wait_for_breakout"
            return True
        msg = f"underlying curr pivot:{idx} == prev pivot:{self.curr_idx}"
        logging.debug(msg)
        self.curr_idx = idx
        return False

    def _reset_trade(self):
        self.trade.filled_price = None
        self.trade.status = None
        self.trade.order_id = None

    def wait_for_breakout(self):
        try:
            if self._time_mgr.can_trade:
                current_low = self.low
                if self.trade.last_price > current_low
                    self._stop = current_low
                    logging.info(f"ENTRY: attempting with {self.trade.symbol}")
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
                else:
                    self._time_mgr.last_trade_time(pdlm.now("Asia/Kolkata"))

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
            current_underlying_grid = self.lines.find_current_grid(self.underlying_ltp) 
            if current_underlying_grid > self.curr_idx:
                logging.info("TARGET reached")
                self._modify_to_exit()
                self._fn = "wait_for_breakout"
            elif self._is_stoploss_hit():
                logging.info(f"STOP HIT: {self.trade.symbol} with buy fill price {self._fill_price} hit stop {self._stop}")
                self._time_mgr.set_last_trade_time(pdlm.now("Asia/Kolkata"))
                self._fn = "wait_for_breakout"
            elif self.trade.last_price <= self._stop:
                resp = self._modify_to_kill()
                logging.info(f"KILLING STOP: returned {resp}")
                self._time_mgr.set_last_trade_time(pdlm.now("Asia/Kolkata"))
                self._fn = "wait_for_breakout"
            else:
                logging.info(f"TARGET PROGRESS: {self.trade.symbol} ltp {self.trade.last_price} > {self._stop}")

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

