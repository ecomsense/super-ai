import pandas as pd
import re
from toolkit.fileutils import Fileutils
from typing import Dict, Optional
from constants import dct_sym


class Symbols:
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

    def __init__(self, option_exchange: str, base: str, expiry: str):
        self._option_exchange = option_exchange
        self._base = base
        self.expiry = expiry
        self.csvfile = f"./data/{self._option_exchange}_symbols.csv"

    def get_exchange_token_map_finvasia(self):
        if Fileutils().is_file_not_2day(self.csvfile):
            url = f"https://api.shoonya.com/{self._option_exchange}_symbols.txt.zip"
            print(f"{url}")
            df = pd.read_csv(url)
            # filter the response
            df = df[
                (df["Exchange"] == self._option_exchange)
                # & (df["TradingSymbol"].str.contains(self._base + self.expiry))
            ][["Token", "TradingSymbol"]]
            # split columns with necessary values
            df[["Symbol", "Expiry", "OptionType", "StrikePrice"]] = df[
                "TradingSymbol"
            ].str.extract(r"([A-Z]+)(\d+[A-Z]+\d+)([CP])(\d+)")
            df.to_csv(self.csvfile, index=False)

    def get_atm(self, ltp) -> int:
        current_strike = ltp - (ltp % dct_sym[self._base]["diff"])
        next_higher_strike = current_strike + dct_sym[self._base]["diff"]
        if ltp - current_strike < next_higher_strike - ltp:
            return int(current_strike)
        return int(next_higher_strike)

    def get_tokens(self, strike):
        df = pd.read_csv(self.csvfile)
        lst = []
        lst.append(self._base + self.expiry + "C" + str(strike))
        lst.append(self._base + self.expiry + "P" + str(strike))
        for v in range(1, dct_sym[self._base]["depth"]):
            lst.append(
                self._base
                + self.expiry
                + "C"
                + str(strike + v * dct_sym[self._base]["diff"])
            )
            lst.append(
                self._base
                + self.expiry
                + "P"
                + str(strike + v * dct_sym[self._base]["diff"])
            )
            lst.append(
                self._base
                + self.expiry
                + "C"
                + str(strike - v * dct_sym[self._base]["diff"])
            )
            lst.append(
                self._base
                + self.expiry
                + "P"
                + str(strike - v * dct_sym[self._base]["diff"])
            )

        df["Exchange"] = self._option_exchange
        tokens_found = (
            df[df["TradingSymbol"].isin(lst)]
            .assign(tknexc=df["Exchange"] + "|" + df["Token"].astype(str))[
                ["tknexc", "TradingSymbol"]
            ]
            .set_index("tknexc")
        )
        dct = tokens_found.to_dict()
        return dct["TradingSymbol"]

    def find_closest_premium(
        self, quotes: Dict[str, float], premium: float, contains: str
    ) -> Optional[str]:
        contains = self.expiry + contains
        # Create a dictionary to store symbol to absolute difference mapping
        symbol_differences: Dict[str, float] = {}

        for base, ltp in quotes.items():
            if re.search(re.escape(contains), base):
                difference = abs(ltp - premium)
                symbol_differences[base] = difference

        # Find the symbol with the lowest difference
        closest_symbol = min(
            symbol_differences, key=symbol_differences.get, default=None
        )

        return closest_symbol

    def find_symbol_in_moneyness(self, tradingsymbol, ce_or_pe, price_type):
        def find_strike(ce_or_pe):
            search = self._base + self.expiry + ce_or_pe
            # find the remaining string in the symbol after removing search
            strike = re.sub(search, "", tradingsymbol)
            return search, int(strike)

        search, strike = find_strike(ce_or_pe)
        if ce_or_pe == "C":
            if price_type == "ITM":
                return search + str(strike - dct_sym[self._base]["diff"])
            else:
                return search + str(strike + dct_sym[self._base]["diff"])
        else:
            if price_type == "ITM":
                return search + str(strike + dct_sym[self._base]["diff"])
            else:
                return search + str(strike - dct_sym[self._base]["diff"])

    def calc_straddle_value(self, atm: int, quotes: list):
        ce = self._base + self.expiry + "C" + str(atm)
        pe = self._base + self.expiry + "P" + str(atm)
        return quotes[ce] + quotes[pe]

    def find_option_type(self, tradingsymbol):
        option_pattern = re.compile(rf"{self._base}{self.expiry}([CP])\d+")
        match = option_pattern.match(tradingsymbol)
        if match:
            return match.group(1)  # Returns 'C' for call, 'P' for put
        else:
            return False

    def find_option_by_distance(
        self, atm: int, distance: int, c_or_p: str, dct_symbols: dict
    ):
        try:
            match = {}
            if c_or_p == "C":
                find_strike = atm + (distance * dct_sym[self._base]["diff"])
            else:
                find_strike = atm - (distance * dct_sym[self._base]["diff"])
            option_pattern = self._base + self.expiry + c_or_p + str(find_strike)

            for k, v in dct_symbols.items():

                if v == option_pattern:
                    match.update({"symbol": v, "token": k.split("|")[-1]})
                    break
            if any(match):
                return match
            else:
                raise Exception("Option not found")
        except Exception as e:
            print(f"{e} while find_option_by_distance")


if __name__ == "__main__":
    symbols = Symbols("NFO", "BANKNIFTY", "26JUN24")
    symbols.get_exchange_token_map_finvasia()
    dct_tokens = symbols.get_tokens(50000)
    print(dct_tokens)
    # print(symbols.find_option_type("BANKNIFTY28DEC23C47000"))
