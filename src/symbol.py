import pandas as pd
from toolkit.fileutils import Fileutils
from typing import Dict, Optional, Literal, Protocol
from src.constants import logging
from traceback import print_exc
from dataclasses import dataclass

def get_exchange_token_map_finvasia(csvfile, exchange):
    if Fileutils().is_file_not_2day(csvfile):
        url = f"https://api.shoonya.com/{exchange}_symbols.txt.zip"
        print(f"{url}")
        df = pd.read_csv(url)
        df.to_csv(csvfile, index=False)

@dataclass(frozen=True)
class OptionData:
    """A dataclass to hold the core attributes of a financial symbol."""
    exchange: str
    base: Optional[str] = None
    symbol: Optional[str] = None
    diff: Optional[int] = None
    depth: Optional[int] = None
    expiry: Optional[str] = None
    token: Optional[str] = None

class Symbol(Protocol):
    # (The protocol definition as above)
    def get_atm(self, ltp: float) -> int: ...
    def get_tokens(self, strike: int) -> Dict[str, str]: ...
    def find_option_type(self, tradingsymbol: str) -> Optional[str]: ...
    def find_closest_premium(self, quotes: Dict[str, float], premium: float, contains: str) -> Optional[str]: ...
    def find_option_by_distance(self, atm: int, distance: int, c_or_p: str) -> str | None: ...


class OptionSymbol(Symbol):
    """
    Class to get symbols from finvasia, implementing the SymbolProtocol.
    """
    def __init__(self, OptionData):
        self._data = OptionData
        self.csvfile = f"./data/{self._data.exchange}_symbols.csv"
        get_exchange_token_map_finvasia(self.csvfile, self._data.exchange)

    def get_atm(self, ltp: float) -> int:
        current_strike = ltp - (ltp % self._data.diff)
        return int(current_strike - self._data.diff if ltp - current_strike < self._data.diff else current_strike)

    def get_tokens(self, strike: int) -> Dict[str, str]:
        try:
            df = pd.read_csv(self.csvfile)
            lst = [strike]
            for v in range(1, self._data.depth):
                lst.append(strike + v * self._data.diff)
                lst.append(strike - v * self._data.diff)
            filtered_df = df[(df["StrikePrice"].isin(lst)) & (df["Symbol"] == self._data.symbol) & (df["Expiry"] == self._data.expiry)]

            if "Exchange" not in filtered_df.columns:
                raise KeyError("CSV file is missing 'Exchange' column")

            tokens_found = (
                filtered_df.assign(
                    tknexc=lambda x: x["Exchange"] + "|" + x["Token"].astype(str)
                )[["tknexc", "TradingSymbol"]].set_index("tknexc")
            )

            dct = tokens_found.to_dict()
            return dct.get("TradingSymbol", {})
        except Exception as e:
            logging.error(f" {e} in Symbol while getting token")
            print_exc()
            return {}
            
    def find_option_type(self, tradingsymbol: str) -> Optional[str]:
        df = pd.read_csv(self.csvfile)
        row = df[df["TradingSymbol"] == tradingsymbol]
        if not row.empty:
            return row.iloc[0]["OptionType"]
        return None

    def find_closest_premium(
        self, quotes: Dict[str, float], premium: float, contains: str
    ) -> Optional[str]:
        try:
            df = pd.read_csv(self.csvfile)
            df = df[(df["Symbol"] == self._data.symbol) & (df["OptionType"] == contains)] 
            lst_of_tradingsymbols = df["TradingSymbol"].to_list()
            call_or_put_begins_with = {k:v for k, v in quotes.items() if k in lst_of_tradingsymbols}
            symbol_differences: Dict[str, float] = {}

            for symbol, ltp in call_or_put_begins_with.items():
                logging.info(f"Symbol:{symbol} difference {ltp} - {premium}")
                difference = abs(float(ltp) - premium)
                symbol_differences[symbol] = difference

            closest_symbol = min(
                symbol_differences, key=symbol_differences.get, default=None
            )
            return closest_symbol
        except Exception as e:
            logging.error(f"{e} Symbol: find closest premium")
            print_exc()
            return None

    def find_option_by_distance(self, atm: int, distance: int, c_or_p: str) -> str | None:
        try:
            find_strike = atm + (distance * self._data.diff) if c_or_p == "CE" else atm - (distance * self._data.diff)
            logging.info(f"Symbol: found strike price {find_strike}")
            df = pd.read_csv(self.csvfile)
            logging.info(f"Symbol:{self._data.symbol} {c_or_p=} {find_strike=}")
            row = df[(df["Symbol"] == self._data.symbol) & (df["OptionType"] == c_or_p) & (df["StrikePrice"] == find_strike) & (df["Expiry"] == self._data.expiry)]
            if not row.empty:
                return row.iloc[0]
            raise Exception("Option not found")
        except Exception as e:
            logging.error(f"{e} Symbol: while find_option_by_distance")
            print_exc()

if __name__ == "__main__":
    data = OptionData(
        exchange="NFO",
        base="NIFTY",
        symbol="NIFTY",
        diff=50,
        depth=10,
        expiry="21-AUG-2025",
    )
    symbols = OptionSymbol(data)
    dct_tokens = symbols.get_tokens(24500)
    #print(dct_tokens)
    
    option_data = symbols.find_option_by_distance(atm=24500, distance=1, c_or_p="CE")
    print(option_data)
