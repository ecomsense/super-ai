import pandas as pd
from toolkit.fileutils import Fileutils
from typing import Dict, Optional
from src.constants import dct_sym, logging
from traceback import print_exc

def get_exchange_token_map_finvasia(csvfile, exchange):
    if Fileutils().is_file_not_2day(csvfile):
        url = f"https://api.shoonya.com/{exchange}_symbols.txt.zip"
        print(f"{url}")
        df = pd.read_csv(url)
        df.to_csv(csvfile, index=False)


class Symbol:
    """
    Class to get symbols from finvasia

    Parameters
    ----------
    symbol : str
        Symbol
    expiry : str
        Expiry

    Returns
    -------
    None
    """

    def __init__(self, exchange: str, base = None, symbol=None, expiry = None):
        self._exchange = exchange
        self._base = base
        self._symbol = symbol
        self._expiry = expiry
        self.csvfile = f"./data/{self._exchange}_symbols.csv"
        get_exchange_token_map_finvasia(self.csvfile, exchange)

    def get_atm(self, ltp) -> int:
        try:
            current_strike = ltp - (ltp % dct_sym[self._base]["diff"])
            next_higher_strike = current_strike + dct_sym[self._base]["diff"]
            if ltp - current_strike < next_higher_strike - ltp:
                return int(current_strike)
            return int(next_higher_strike)
        except Exception as e:
            logging.error(f"{e} Symbol: in getting atm")
            print_exc()

    def get_tokens(self, strike):
        try:
            df = pd.read_csv(self.csvfile)

            lst = [strike]
            for v in range(1, dct_sym[self._base]["depth"]):
                lst.append(strike + v * dct_sym[self._base]["diff"])
                lst.append(strike - v * dct_sym[self._base]["diff"])

            filtered_df = df[(df["StrikePrice"].isin(lst)) & (df["Symbol"] == self._symbol) & (df["Expiry"]==self._expiry)]

            if "Exchange" not in filtered_df.columns:
                raise KeyError("CSV file is missing 'Exchange' column")

            tokens_found = (
                filtered_df.assign(
                    tknexc=lambda x: x["Exchange"] + "|" + x["Token"].astype(str)
                )[
                    ["tknexc", "TradingSymbol"]
                ]
                .set_index("tknexc")
            )

            dct = tokens_found.to_dict()
            return dct["TradingSymbol"]
        except Exception as e:
            logging.error(f" {e} in Symbol while getting token")
            print_exc()

    def find_option_type(self, tradingsymbol: str) -> str | None:
        """
        Extracts option type from the CSV file if present.
        """
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

            # filter
            df = df[(df["Symbol"] == self._symbol) & (df["OptionType"]==contains)] 

            # convert the matches to list
            lst_of_tradingsymbols = df["TradingSymbol"].to_list()

            # filter quotes with generated list
            call_or_put_begins_with = {k:v for k, v in quotes.items() if k in lst_of_tradingsymbols}

            # Create a dictionary to store symbol to absolute difference mapping
            symbol_differences: Dict[str, float] = {}

            for symbol, ltp in call_or_put_begins_with.items():
                logging.info(f"Symbol:{symbol} difference {ltp} - {premium}")
                difference = abs(float(ltp) - premium)
                symbol_differences[symbol] = difference

            # Find the symbol with the lowest difference
            closest_symbol = min(
                symbol_differences, key=symbol_differences.get, default=None
            )
            return closest_symbol
        except Exception as e:
            logging.error(f"{e} Symbol: find closest premium")
            print_exc()
            

    def find_option_by_distance(
        self, atm: int, distance: int, c_or_p: str, dct_symbols: dict
    ):
        try:
            find_strike = atm + (distance * dct_sym[self._base]["diff"]) if c_or_p == "CE" else  atm - (distance * dct_sym[self._base]["diff"])
            logging.info(f"Symbol: found strike price {find_strike}")
            df = pd.read_csv(self.csvfile)
            logging.info(f"Symbol:{self._symbol} {c_or_p=} {find_strike=}")
            row = df[(df["Symbol"] == self._symbol) & (df["OptionType"] == c_or_p) & (df["StrikePrice"] == find_strike) & (df["Expiry"] == self._expiry)]
            if not row.empty:
                return row.iloc[0]
            raise Exception("Option not found")
        except Exception as e:
            logging.error(f"{e} Symbol: while find_option_by_distance")
            print_exc()


if __name__ == "__main__":
    symbols = Symbol("NFO", "NIFTY")
    dct_tokens = symbols.get_tokens(21500)
    print(dct_tokens)
    # print(symbols.find_option_type("BANKNIFTY28DEC23C47000"))
