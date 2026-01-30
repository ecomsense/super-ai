from src.constants import S_DATA
from src.sdk.helper import Helper
import pendulum as pdlm
import pandas as pd
from traceback import print_exc
import sys

try:
    api = Helper.api()
    rest = Helper._rest

    def download_history(exchange, symbol):
        token = api.instrument_symbol(exchange, symbol)
        if not token:
            print(f"FAILURE: i have no idea on {exchange} {symbol} you are searching")
            sys.exit(1)

        fm = (
            pdlm.now()
            .subtract(days=5)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
        to = pdlm.now().subtract(days=0).timestamp()

        resp = api.historical(exchange, str(token), fm, to)
        if resp and any(resp):
            pd.DataFrame(resp).to_csv(S_DATA + symbol + ".csv", index=False)
            print("SUCCESS! check data directory for the historical data")
        else:
            print(f"sorry! unable to get history for {symbol} and {exchange}")

except Exception as e:
    print(e)
    print_exc()

if __name__ == "__main__":
    if len(sys.argv) > 2:
        exchange = (sys.argv[1]).upper()
        symbol = sys.argv[2].upper()
        download_history(exchange, symbol)
    else:
        print("pass <exchange> <symbol>")
        print("example: NFO BANKNIFTY24FEB26P59600")
