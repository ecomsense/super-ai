from src.constants import logging
from traceback import print_exc
from typing import Dict, Any


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
        S4 = (pivot * 3) - (high * 3 - low)
        logging.info(f"{S4=}")
        S5 = (pivot * 4) - (high * 4 - low)
        logging.info(f"{S5=}")
        lst = [R5, R4, R3, R2, R1, pivot, S1, S2, S3, S4, S5]
        # lst = [int(item) for item in lst]
        logging.info(f"computed pivots {lst}")
        return lst
    except Exception as e:
        logging.error(f"{e} while computing grid")
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
            logging.error(f"{e} while set grid")
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
        logging.info(f"Grid running: for {exchange} {tradingsymbol}")
        try:
            if cls.grid.get(tradingsymbol, None) is None:
                symbol_constant = rst.daily(
                    exchange=exchange, tradingsymbol=tradingsymbol
                )
                if symbol_constant is None:
                    symbol_constant = rst.yesterday(exchange=exchange, token=token)
                print(f"grid {symbol_constant}")
                cls.grid[tradingsymbol] = compute(symbol_constant)
            return cls.grid[tradingsymbol]
        except Exception as e:
            print_exc()
            logging.error(f"{e} while computing grid")
            __import__("sys").exit(1)


class Gridlines:
    def __init__(self, prices: list, reverse: bool):
        logging.info(f"prices {prices}")
        levels = sorted(prices, reverse=reverse)
        self.lines = list(zip(levels[:-1], levels[1:]))
        logging.info(f"gridlines {self.lines}")

    def find_current_grid(self, ltp: float) -> int:
        idx = -1
        for idx, (a, b) in enumerate(self.lines):
            lowest, highest = min(a, b), max(a, b)
            if lowest <= ltp < highest:
                return idx
        return idx
