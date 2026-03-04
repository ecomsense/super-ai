from ast import Tuple
from traceback import print_exc
from typing import Any, Dict

from src.constants import logging_func
from src.sdk.utils import round_down_to_tick

log = logging_func(__name__)


def compute(ohlc_prefix):
    try:
        high, low, close = (
            float(ohlc_prefix["inth"]),
            float(ohlc_prefix["intl"]),
            float(ohlc_prefix["intc"]),
        )
        pivot = (high + low + close) / 3.0
        log.info(f"{pivot=}")
        R5 = (pivot * 4) + high - (4 * low)
        log.info(f"{R5=}")
        R4 = (pivot * 3) + high - (3 * low)
        log.info(f"{R4=}")
        R3 = high + (2 * (pivot - low))
        log.info(f"{R3=}")
        R2 = pivot + (high - low)
        log.info(f"{R2=}")
        R1 = (2 * pivot) - low
        log.info(f"{R1=}")
        S1 = (2 * pivot) - high
        log.info(f"{S1=}")
        S2 = pivot - (high - low)
        log.info(f"{S2=}")
        S3 = low - (2 * (high - pivot))
        log.info(f"{S3=}")
        S4 = (pivot * 3) - (high * 3 - low)
        log.info(f"{S4=}")
        S5 = (pivot * 4) - (high * 4 - low)
        log.info(f"{S5=}")
        lst = [R5, R4, R3, R2, R1, pivot, S1, S2, S3, S4, S5]
        # lst = [int(item) for item in lst]
        log.info(f"computed pivots {lst}")
        return lst
    except Exception as e:
        log.error(f"{e} while computing grid")
        print_exc()


class Grid:
    grid = {}

    @classmethod
    def set(cls, prefix: str, symbol_constant: Dict[str, Any]):
        try:
            if cls.grid.get(prefix, None) is None:
                cls.grid[prefix] = compute(symbol_constant)
            return cls.grid[prefix]
        except Exception as e:
            log.error(f"{e} while set grid")
            print_exc()

    @classmethod
    def get(cls, rst, exchange: str, tradingsymbol: str, token: str):
        """
        Computes the grid levels for the given symbol and prefix.

        Args:
            api: An instance of the Helper class.
            prefix: The market prefix.
            symbol_constant: A dictionary containing information about the symbol.

        Returns:
            A list of 11 integers representing the grid levels.
        """
        log.info(f"Grid running: for {exchange} {tradingsymbol}")
        try:
            if cls.grid.get(tradingsymbol, None) is None:
                symbol_constant = rst.daily(
                    exchange=exchange, tradingsymbol=tradingsymbol
                )
                if symbol_constant is None:
                    symbol_constant = rst.yesterday(exchange=exchange, token=token)
                log.info(f"OHLC: {symbol_constant}")
                cls.grid[tradingsymbol] = compute(symbol_constant)
            return cls.grid[tradingsymbol]
        except Exception as e:
            print_exc()
            log.error(f"{e} while computing grid")
            __import__("sys").exit(1)


class Gridlines:
    def __init__(self, prices: list, reverse: bool):
        log.info(f"prices {prices}")
        levels = sorted(prices, reverse=reverse)
        self.lines = list(zip(levels[:-1], levels[1:]))
        log.info(f"gridlines {self.lines}")

    def find_current_grid(self, ltp: float):
        idx = -1
        for idx, (a, b) in enumerate(self.lines):
            lowest, highest = min(a, b), max(a, b)
            if lowest <= ltp < highest:
                return idx, lowest, highest
        return idx, None, None


def pivot_to_stop_and_target(pivots: list):
    lst_of_tuples = None
    log.info(f"{pivots}")
    level = sorted(pivots, reverse=False)
    level = [item for item in level if item > 0]
    new_lst = []
    for item in level:
        resp = round(round_down_to_tick(item), 2)
        new_lst.append(resp)
    lst_of_tuples = list(zip(new_lst, new_lst[1:]))
    return lst_of_tuples

class StopAndTarget:

    def __init__(self, stops_and_targets: list[tuple]) -> None:
        # 1. Validate Type
        if not isinstance(stops_and_targets, list):
            msg = f"Expected list for stops_and_targets, got {type(stops_and_targets).__name__}" 
            log.error(msg)
            raise TypeError(msg)

        # 2. Validate Contents
        if not all(isinstance(item, tuple) for item in stops_and_targets):
            msg = "All items in stops_and_targets must be Tuples"
            log.error(msg)
            raise ValueError(msg)

        self._stops_and_targets = stops_and_targets
        log.info("Successfully initialized stops_and_targets.")

    def find_current_grid(self, last_price):
        if not isinstance(last_price, (int,float)):
            msg =f"last price is not of expected type {last_price}"
            log.error(msg)
            raise ValueError(msg)

        idx = -1
        for idx, stop_and_target in enumerate(self._stops_and_targets):
            stop, target = stop_and_target
            if stop < last_price < target:
                return idx, stop, target
        return idx, None, None



if __name__ == "__main__":
    from src.sdk.helper import Helper

    """
    Helper.api()
    rst = Helper._rest
    sym = {}
    resp = Grid().get(rst=rst, exchange="NSE", tradingsymbol="NIFTY 50", token="26000")
    print("begin", resp, "end")
    """
    try:
        pivots = [25, 30, 5, -2]
        resp = pivot_to_stop_and_target(pivots)
        assert resp == [(5, 25), (25, 30)], "not sorted"
        print(resp)
        pivots = [0, 5, 25, 25]
        print(pivots)
        gl = Gridlines(prices=pivots, reverse=False)
        curr, lowest, highest = gl.find_current_grid(4.05)
        assert curr == 0, "idx is not 0"
        assert lowest == 0, "lowest is not 0"
        assert highest == 5.0, "highest is not 5"
    except Exception as e:
        print(e)


