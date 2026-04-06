from src.constants import logging_func

from src.config.interface import OptionData

import requests
import io
import pandas as pd
from toolkit.fileutils import Fileutils
from typing import Dict, Optional, Protocol
from traceback import print_exc

logging = logging_func(__name__)


def get_exchange_token_map_finvasia(csvfile, exchange):
    if Fileutils().is_file_not_2day(csvfile):
        url = f"https://api.shoonya.com/{exchange}_symbols.txt.zip"
        print(f"{url}")
        df = pd.read_csv(url)
        df.to_csv(csvfile, index=False)


def get_exchange_token_map_flattrade(csvfile, exchange="NFO"):
    """
    Fetches the scrip master from Flattrade and returns a
    dictionary mapping {Symbol: Token} for lookups.
    """
    # Flattrade V2 requires lowercase exchange in the URL
    url = f"https://api.flattrade.in/v2/scrip_master/{exchange.lower()}"

    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

    try:
        # Flattrade requires POST, even if no body is sent
        response = requests.post(url, headers=headers, timeout=15)

        if response.status_code == 200 and response.text.strip():
            # Flattrade returns a CSV string.
            # Columns usually include: 'Token', 'LotSize', 'Symbol', 'TradingSymbol'...
            df = pd.read_csv(io.StringIO(response.text))

            # Create a dictionary for fast lookup: { 'NIFTY24APR22500CE': '54321' }
            # Note: Verify column names in the first run as they can vary slightly by segment.
            token_map = pd.Series(df.Token.values, index=df.TradingSymbol).to_dict()

            return token_map
        else:
            print(f"Error: Server returned {response.status_code} or empty body.")
            return {}

    except Exception as e:
        print(f"Failed to fetch Flattrade Token Map: {e}")
        return {}


# Usage example:
# nfo_map = get_exchange_token_map_flattrade('NFO')
# token = nfo_map.get('NIFTY26MAR2622500CE')


class Symbol(Protocol):
    # (The protocol definition as above)
    def get_atm(self, ltp: float) -> int: ...
    def get_tokens(self, strike: int) -> Dict[str, str]: ...
    def find_option_type(self, tradingsymbol: str) -> Optional[str]: ...
    def find_closest_premium(
        self, quotes: Dict[str, float], premium: float, contains: str
    ) -> Optional[str]: ...
    def find_option_by_distance(
        self, atm: int, distance: int, c_or_p: str
    ) -> str | None: ...


class OptionSymbol(Symbol):
    """
    Class to get symbols from finvasia, implementing the SymbolProtocol.
    """

    def __init__(self, data: OptionData):
        self._data = data
        self.csvfile = f"./data/{self._data.exchange}_symbols.csv"
        get_exchange_token_map_flattrade(self.csvfile, self._data.exchange)
        logging.info(f"init OptionSymbol {data}")

    def get_atm(self, ltp: float) -> int:
        current_strike = ltp - (ltp % self._data.diff)
        return int(
            current_strike - self._data.diff
            if ltp - current_strike < self._data.diff
            else current_strike
        )

    def _find_expiry(self):
        """
        find
        """
        df = pd.read_csv(self.csvfile, usecols=["Symbol", "Expiry"])

        df = df[df.Symbol == self._data.symbol]

        df = df.drop_duplicates(subset=["Expiry"])

        df["Sort_Key"] = pd.to_datetime(df["Expiry"], format="%d-%b-%Y")

        today = pd.to_datetime("today").normalize()

        df = df[df["Sort_Key"] >= today]

        df = df.sort_values(by=["Sort_Key"])

        if len(df.index) > 0:
            first_row = df.iloc[0]["Expiry"]
            return first_row
        print(df.head())
        raise f"cannot find no row found for this symbol {self._data.symbol}"

    def get_tokens(self, strike: int) -> Dict[str, str]:
        try:
            df = pd.read_csv(self.csvfile)
            lst = [strike]
            for v in range(1, self._data.depth):
                lst.append(strike + v * self._data.diff)
                lst.append(strike - v * self._data.diff)
            filtered_df = df[
                (df["StrikePrice"].isin(lst))
                & (df["Symbol"] == self._data.symbol)
                & (df["Expiry"] == self._data.expiry)
            ]

            if "Exchange" not in filtered_df.columns:
                raise KeyError("CSV file is missing 'Exchange' column")

            tokens_found = filtered_df.assign(
                tknexc=lambda x: x["Exchange"] + "|" + x["Token"].astype(str)
            )[["tknexc", "TradingSymbol"]].set_index("tknexc")

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
            df = df[
                (df["Symbol"] == self._data.symbol) & (df["OptionType"] == contains)
            ]
            lst_of_tradingsymbols = df["TradingSymbol"].to_list()
            call_or_put_begins_with = {
                k: v for k, v in quotes.items() if k in lst_of_tradingsymbols
            }
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

    def find_option_by_distance(
        self, atm: int, distance: int, c_or_p: str
    ) -> str | None:
        try:
            find_strike = (
                atm + (distance * self._data.diff)
                if c_or_p == "CE"
                else atm - (distance * self._data.diff)
            )
            logging.info(f"Symbol: found strike price {find_strike}")
            df = pd.read_csv(self.csvfile)
            logging.info(
                f"Symbol:{self._data.symbol} {c_or_p=} {find_strike=} for expiry{self._data.expiry}"
            )
            row = df[
                (df["Symbol"] == self._data.symbol)
                & (df["OptionType"] == c_or_p)
                & (df["StrikePrice"] == find_strike)
                & (df["Expiry"] == self._data.expiry)
            ]
            if not row.empty:
                return row.iloc[0]
            raise Exception("Option not found")
        except Exception as e:
            logging.error(f"{e} Symbol: while find_option_by_distance")
            print_exc()


if __name__ == "__main__":
    data = OptionData(
        exchange="BFO",
        base="SENSEX",
        symbol="BSXOPT",
        diff=100,
        depth=10,
        expiry=None,
        token=None,
    )

    os = OptionSymbol(data)
    resp = os.find_option_by_distance(atm=77500, distance=3, c_or_p="CE")
    print(resp)
