from src.constants import logging_func

from src.config.interface import OptionData

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


# The equivalent drop-in replacement for Flattrade using the working S3 endpoints
def get_exchange_token_map_flattrade(csvfile, exchange):
    if Fileutils().is_file_not_2day(csvfile):
        if exchange.upper() == "NFO":
            url = "https://flattrade.s3.ap-south-1.amazonaws.com/scripmaster/Nfo_Index_Derivatives.csv"
        elif exchange.upper() == "BFO":
            url = "https://flattrade.s3.ap-south-1.amazonaws.com/scripmaster/Bfo_Index_Derivatives.csv"
        else:
            # Fallback for other segments
            url = f"https://flattrade.s3.ap-south-1.amazonaws.com/scripmaster/Commodity.csv"

        print(f"{url}")
        df = pd.read_csv(url)
        # Standardize Flattrade columns to match Finvasia
        df.rename(
            columns={
                "Optiontype": "OptionType",
                "Strike": "StrikePrice",
                "Tradingsymbol": "TradingSymbol",
                "Lotsize": "LotSize",
            },
            inplace=True,
        )
        df.StrikePrice = df.StrikePrice.astype(int)
        df.to_csv(csvfile, index=False)


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
    ) -> Optional[str]: ...


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
    ) -> Optional[str]:
        try:
            find_strike = (
                atm + (distance * self._data.diff)
                if c_or_p == "CE"
                else atm - (distance * self._data.diff)
            )
            df = pd.read_csv(self.csvfile)
            # ... previous code ...
            logging.info(
                f"Target: Symbol={self._data.symbol}, Type={c_or_p}, Strike={find_strike}, Expiry={self._data.expiry}"
            )

            # Step 1: Symbol
            df_sym = df[df["Symbol"] == self._data.symbol]
            print(f"1. After Symbol filter: {len(df_sym)} rows remaining")
            if df_sym.empty:
                print(f"ERROR: Symbol '{self._data.symbol}' not found.")

            # Step 2: OptionType
            df_opt = df_sym[df_sym["OptionType"] == c_or_p]
            print(f"2. After OptionType filter: {len(df_opt)} rows remaining")
            if df_opt.empty and not df_sym.empty:
                print(f"ERROR: Available OptionTypes: {df_sym['OptionType'].unique()}")

            # Step 3: Strike Price (Forcing float comparison to be safe)
            df_strike = df_opt[
                df_opt["StrikePrice"].astype(float) == float(find_strike)
            ]
            print(f"3. After StrikePrice filter: {len(df_strike)} rows remaining")
            if df_strike.empty and not df_opt.empty:
                print(
                    f"ERROR: Looking for {float(find_strike)}. Available Strikes: {df_opt['StrikePrice'].head(10).unique()}..."
                )

            # Step 4: Expiry Date
            df_final = df_strike[df_strike["Expiry"] == self._data.expiry]
            print(f"4. After Expiry filter: {len(df_final)} rows remaining")
            if df_final.empty and not df_strike.empty:
                print(
                    f"ERROR: Looking for Expiry '{self._data.expiry}'. Available Expiries: {df_strike['Expiry'].unique()}"
                )

            # Final Check
            if not df_final.empty:
                print("SUCCESS: Option found!")
                return df_final.iloc[0]

            raise Exception("Option not found during step-by-step filtering.")
        except Exception as e:
            logging.error(f"{e} Symbol: while find_option_by_distance")
            print_exc()


if __name__ == "__main__":
    data = OptionData(
        exchange="NFO",
        base="NIFTY",
        symbol="NIFTY",
        diff=50,
        depth=25,
        expiry="28-APR-2026",
        token=None,
    )

    os = OptionSymbol(data)
    resp = os.find_option_by_distance(atm=24500, distance=3, c_or_p="CE")
    print(resp)
