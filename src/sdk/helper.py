from src.constants import logging_func, S_SETG, S_DATA, yml_to_obj
from src.sdk.wserver import Wserver

import pendulum as pdlm
from toolkit.kokoo import blink
import pandas as pd
from importlib import import_module
from traceback import print_exc

from json import dumps, loads
from pprint import pprint

logging = logging_func(__name__)


def df_to_csv(df, csv_file, is_index=False):
    df.to_csv(S_DATA + csv_file, index=is_index)


def compress_candles(
    data_now, tz="Asia/Kolkata", return_last_only=True, exclude_today=True
):
    """
    Compress intraday data (list of dicts) into daily OHLC (+ optional volume and oi).
    Requires a 'time' column. If it's missing, function will fail.
    """
    if not data_now:
        return None

    df = pd.DataFrame(data_now)

    # --- require time column ---
    if "time" not in df.columns:
        raise ValueError("No 'time' column found in data")

    # parse 'time' as tz-aware datetime
    s = pd.to_datetime(df["time"], dayfirst=True, errors="raise")
    s = s.dt.tz_localize(tz, nonexistent="raise", ambiguous="raise")
    df.index = s
    df.index.name = "time"

    # --- numeric conversion ---
    numeric_cols = ["into", "inth", "intl", "intc", "v", "oi"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # exclude today’s partial data if requested
    if exclude_today:
        today_local = pd.Timestamp.now(tz=tz).date()
        df = df[df.index.date != today_local]
        if df.empty:
            return None

    # aggregate to daily OHLC (+ optional v, oi)
    agg = {}
    if "into" in df.columns:
        agg["into"] = "first"  # open
    if "inth" in df.columns:
        agg["inth"] = "max"  # high
    if "intl" in df.columns:
        agg["intl"] = "min"  # low
    if "intc" in df.columns:
        agg["intc"] = "last"  # close
    if "v" in df.columns:
        agg["v"] = "sum"  # volume
    if "oi" in df.columns:
        agg["oi"] = "last"  # open interest

    daily = df.resample("1D").agg(agg)

    # drop incomplete rows (no close)
    if "intc" in daily.columns:
        daily = daily.dropna(subset=["intc"])

    if daily.empty:
        return None

    if return_last_only:
        daily = daily.tail(1)

    out = daily.reset_index()
    out["date"] = out["time"].dt.strftime("%Y-%m-%d")
    out = out.drop(columns=["time"])

    # ensure plain python types
    return loads(dumps(out.to_dict(orient="records"), default=str))[0]


def get_broker(cnfg):
    try:
        broker_name = cnfg.get("broker", None)
        if not broker_name:
            raise ValueError("broker not specified in credential file")

        # Dynamically import the broker module
        module_path = f"stock_brokers.{broker_name}.{broker_name}"
        broker_module = import_module(module_path)

        logging.info(f"BrokerClass: {broker_module}")
        # Get the broker class (assuming class name matches the broker name)
        return getattr(broker_module, broker_name.capitalize())

    except Exception as e:
        print(f"{e} while logging in")
        __import__("sys").exit(1)


def login():
    try:
        O_CNFG = yml_to_obj()
        O_SETG = yml_to_obj(S_SETG)
        # Initialize API with config
        if O_SETG.get("live", 0) == 0:
            from paper import Paper

            logging.info("Using paper trading")
            api = Paper(**O_CNFG)
        else:
            logging.info("Live trading mode")
            BrokerClass = get_broker(O_CNFG)
            # O_CNFG.pop("broker", None)
            api = BrokerClass(**O_CNFG)

        if api.authenticate():
            print("authentication successfull")
            return api
        else:
            print("Failed to authenticate. .. exiting")
            for attr in dir(api):
                if not callable(getattr(api, attr)) and not attr.startswith("__"):
                    print(f"{attr} = {getattr(api, attr)}")

    except Exception as e:
        print(f"login exception {e}")
        __import__("sys").exit(1)


# add a decorator to check if wait_till is past
def is_not_rate_limited(func):
    # Decorator to enforce a 1-second delay between calls
    def wrapper(*args, **kwargs):
        while pdlm.now() < Helper.wait_till:
            blink()
        Helper.wait_till = pdlm.now().add(seconds=1)
        return func(*args, **kwargs)

    return wrapper


class QuoteApi:
    subscribed = {}

    def __init__(self, ws):
        self._ws = ws

    def get_quotes(self):
        try:
            quote = {}
            ltps = self._ws.ltp
            quote = {
                symbol: ltps.get(values["key"])
                for symbol, values in self.subscribed.items()
            }
        except Exception as e:
            logging.error(f"{e} while getting quote")
            print_exc()
        finally:
            return quote

    def _subscribe_till_ltp(self, ws_key):
        try:
            quotes = self._ws.ltp
            ltp = quotes.get(ws_key, None)
            while ltp is None:
                self._ws.subscribe([ws_key])
                quotes = self._ws.ltp
                ltp = quotes.get(ws_key, None)
                print(f"trying to get quote for {ws_key} {ltp}")
                blink()
        except Exception as e:
            logging.error(f"{e} while get ltp")
            print_exc()

    def symbol_info(self, exchange, symbol, token=None):
        try:
            if self.subscribed.get(symbol, None) is None:
                if token is None:
                    logging.info(f"Helper: getting token for {exchange} {symbol}")
                    token = str(self._ws.api.instrument_symbol(exchange, symbol))
                key = exchange + "|" + str(token)
                self.subscribed[symbol] = {
                    "symbol": symbol,
                    "key": key,
                    "token": token,
                    "ltp": self._subscribe_till_ltp(key),
                }
            if self.subscribed.get(symbol, None) is not None:
                quotes = self._ws.ltp
                ws_key = self.subscribed[symbol]["key"]
                self.subscribed[symbol]["ltp"] = float(quotes[ws_key])
                return self.subscribed[symbol]
        except Exception as e:
            logging.error(f"{e} while symbol info")
            print_exc()


class RestApi:

    completed_trades = []
    _positions = [{}]
    _positions_last_updated = pdlm.now().subtract(seconds=1)

    def __init__(self, session):
        self._api = session

    def daily(self, exchange, tradingsymbol):
        try:
            start = pdlm.now().subtract(days=5).timestamp()
            now = pdlm.now().timestamp()
            ret = self._api.broker.get_daily_price_series(  # type: ignore
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                startdate=start,
                enddate=now,
            )
            if ret is not None and any(ret):
                return loads(ret[0])
            else:
                return None
        except Exception as e:
            logging.error(f"{e} while computing grid")
            print_exc()

    def yesterday(self, exchange, token):
        try:
            token = str(token)
            fm = (
                pdlm.now()
                .subtract(days=5)
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .timestamp()
            )
            to = pdlm.now().subtract(days=0).timestamp()

            data_now = self._api.historical(exchange, token, fm, to)

            if not isinstance(data_now, list):
                return None
            else:
                pprint(data_now)
                return compress_candles(data_now)
        except Exception as e:
            logging.error(f"{e} while compressing candle")
            print_exc()

    def history(self, exchange, token, loc, key):
        try:
            token = str(token)
            fm = (
                pdlm.now()
                .subtract(days=0)
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .timestamp()
            )
            to = pdlm.now().subtract(days=0).timestamp()

            data_now = self._api.historical(exchange, token, fm, to)

            if not isinstance(data_now, list):
                return None

            if isinstance(loc, int):
                # we have some data but it is not full
                if len(data_now) < abs(loc):
                    logging.warning(f"TODO: found partial data {data_now}")
                    return None

                if len(data_now) >= abs(loc):
                    logging.debug(f"DATA NOW: {data_now[loc]}")
                    low = float(data_now[loc][key])
                    return low

            else:
                # "time": "18-08-2025 09:30:00"
                new_data = []
                for d in data_now:
                    if isinstance(d, dict) and d.get("time", None):
                        str_time = d["time"]
                        t = pdlm.from_format(
                            str_time, "DD-MM-YYYY HH:mm:ss", tz="Asia/Kolkata"
                        )
                        if t >= loc:
                            logging.debug(f"CANDLE {str_time}: {key}:{d[key]}")
                            new_data.append(float(d[key]))
                        else:
                            logging.debug(f"skipping after {str_time} candles")
                            break

                if any(new_data):
                    return min(new_data)

            return None

        except Exception as e:
            logging.error(f" {str(e)} in history")
            print_exc()

    def ltp(self, exchange, token):
        try:
            resp = self._api.scriptinfo(exchange, token)
            if resp is not None:
                return float(resp["lp"])
            else:
                return None
        except Exception as e:
            message = f"{e} while ltp"
            logging.warning(message)
            print_exc()

    def one_side(self, bargs):
        try:
            resp = self._api.order_place(**bargs)
            return resp
        except Exception as e:
            message = f"helper error {e} while placing order {bargs}"
            logging.warning(message)
            print_exc()

    def modify_order(self, args):
        try:
            resp = self._api.order_modify(**args)
            return resp
        except Exception as e:
            message = f"helper error {e} while modifying order"
            logging.warning(message)
            print_exc()

    def order_cancel(self, order_id):
        try:
            resp = self._api.order_cancel(order_id)
            return resp
        except Exception as e:
            message = f"helper error {e} while cancelling order"
            logging.warning(message)
            print_exc()

    def positions(self):
        try:
            now = pdlm.now()
            if self._positions_last_updated < now:
                self._positions_last_updated = now.add(seconds=4)
                resp = self._api.positions
                if resp and any(resp):
                    # print(orders[0].keys())
                    self._positions = resp
            return self._positions

        except Exception as e:
            logging.warning(f"Error fetching positions: {e}")
            print_exc()

    def orders(self):
        try:
            orders = self._api.orders
            if orders and any(orders):
                # print(orders[0].keys())
                return orders
            return [{}]

        except Exception as e:
            logging.warning(f"Error fetching orders: {e}")
            print_exc()

    @is_not_rate_limited
    def trades(self):
        try:
            from_api = []  # Return an empty list on failure
            from_api = self._api.trades
        except Exception as e:
            logging.warning(f"Error fetching trades: {e}")
            print_exc()
        finally:
            return from_api

    def close_positions(self):
        try:
            for pos in self._api.positions:
                if not pos or pos["quantity"] == 0:
                    continue
                else:
                    quantity = abs(pos["quantity"])

                logging.debug(f"trying to close {pos['symbol']}")
                args = dict(
                    symbol=pos["symbol"],
                    quantity=quantity,
                    disclosed_quantity=quantity,
                    product=pos["prd"],
                    order_type="MKT",
                    exchange=pos["exchange"],
                    tag="close",
                    side="B",
                )
                args["side"] = "B" if pos["quantity"] < 0 else "S"
                resp = self._api.order_place(**args)
                logging.info(f"close position {pos['symbol']} responded with {resp}")
        except Exception as e:
            logging.error("f{e} RestApi: close positions")
            print_exc()

    def pnl(self, key="urmtom"):
        try:
            ttl = 0
            resp = [{}]
            resp = self._api.positions
            """
            keys = [
                "symbol",
                "quantity",
                "last_price",
                "urmtom",
                "rpnl",
            ]
            """
            if resp and any(resp):
                pd.DataFrame(resp).to_csv(S_DATA + "positions.csv", index=False)
                # calc value
                # list []
                # dict {}
                # list_of_dict = [
                # {},
                # {},
                # ]

                for pos in resp:
                    ttl += pos[key]
        except Exception as e:
            message = f"while calculating {e}"
            logging.warning(f"api responded with {message}")
            print_exc()
        finally:
            return ttl


class Helper:
    _api = None

    @classmethod
    def api(cls):
        if cls._api is None:
            cls._api = login()
            cls._rest = RestApi(cls._api)
            ws = Wserver(cls._api, ["NSE:24"])
            cls._quote = QuoteApi(ws)
        cls.wait_till = pdlm.now().add(seconds=1)
        return cls._api


if __name__ == "__main__":
    from src.constants import S_DATA

    try:
        Helper.api()

        def trades():
            resp = Helper._rest.trades()
            if resp:
                pd.DataFrame(resp).to_csv(S_DATA + "trades.csv", index=False)
                print(pd.DataFrame(resp))

        def orders():
            resp = Helper._rest.orders()
            if resp and any(resp):
                pd.DataFrame(resp).to_csv(S_DATA + "orders.csv", index=False)
                print(pd.DataFrame(resp))
            else:
                print("no response from orders")

        def modify():
            args = {
                "symbol": "NIFTY28NOV24C23400",
                "exchange": "NFO",
                "order_id": "24112200115699",
                "price": 0.0,
                "price_type": "MARKET",
                "quantity": 25,
            }
            resp = Helper._rest.modify_order(args)
            print(resp)
            print(resp)

        def margin():
            resp = Helper._api.margins
            print(resp)

        trades()
        orders()
        resp = Helper._rest.pnl("rpnl")
        print(resp)

        df = Helper._rest.yesterday("NFO", "47764")
        print(df)

        """
        Helper._rest.close_positions()
        while True:
            idx = pdlm.now("Asia/Kolkata").subtract(hours=10)
            resp = history(
                api=Helper.api(), exchange="NFO", token="44604", loc=idx, key="intl"
            )
            print("history", resp)
    except KeyboardInterrupt:
        print("ctrl c pressed")
        """
    except Exception as e:
        print(e)
        print_exc()
