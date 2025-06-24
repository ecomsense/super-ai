from src.constants import O_CNFG, logging, O_SETG, S_DATA
from src.wserver import Wserver
import pendulum as pdlm
from toolkit.kokoo import blink, timer
import pandas as pd
from importlib import import_module
from traceback import print_exc


def df_to_csv(df, csv_file, is_index=False):
    df.to_csv(S_DATA + csv_file, index=is_index)


def get_broker():
    try:
        broker_name = O_CNFG.get("broker", None)
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
        # Initialize API with config
        if O_SETG["trade"].get("live", 0) == 0:
            from paper import Paper

            logging.info("Using paper trading")
            api = Paper(**O_CNFG)
        else:
            logging.info("Live trading mode")
            BrokerClass = get_broker()
            O_CNFG.pop("broker", None)
            api = BrokerClass(**O_CNFG)

        if api and api.authenticate():
            print("authentication successfull")
            return api
        else:
            print("Failed to authenticate. .. exiting")
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


def history(api, exchange, token, loc, key):
    try:
        i = 0
        for i in range(5):
            fm = (
                pdlm.now()
                .subtract(days=i)
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .timestamp()
            )
            to = pdlm.now().subtract(days=0).timestamp()
            data_now = api.historical(exchange, token, fm, to)
            # we have some data but it is not full
            while data_now and len(data_now) > 0 and len(data_now) < abs(loc):
                secs = 2
                logging.debug(f"found partial low data, retrying after ..{secs} secs")
                timer(secs)
                data_now = api.historical(exchange, token, fm, to)
            if data_now and len(data_now) >= abs(loc):
                logging.debug("successfully found low")
                return float(data_now[loc][key])
            blink()
            i += 1
            logging.debug("rewinding to the previous day ..")
    except Exception as e:
        logging.error(f"{e} in history")
    """
    finally:
        data_now = [{"intl": 22550}, {"intl": 22550}]
        return data_now
    """


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
                self._ws.api.broker.subscribe([ws_key], feed_type="d")
                quotes = self._ws.ltp
                ltp = quotes.get(ws_key, None)
                timer(0.25)
        except Exception as e:
            logging.error(f"{e} while get ltp")
            print_exc()
            self._subscribe_till_ltp(ws_key)

    def symbol_info(self, exchange, symbol):
        try:
            # TODO undo this code
            low = False
            if self.subscribed.get(symbol, None) is None:
                token = self._ws.api.instrument_symbol(exchange, symbol)
                key = exchange + "|" + str(token)
                if not low:
                    low = history(self._ws.api, exchange, token, loc=-2, key="intl")
                    logging.debug(f"got {low=} for {symbol=} and {token=}")
                self.subscribed[symbol] = {
                    "symbol": symbol,
                    "key": key,
                    # "low": 0,
                    "low": low,
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
        for pos in self._api.positions:
            if pos["quantity"] == 0:
                continue
            else:
                quantity = abs(pos["quantity"])

            logging.debug(f"trying to close {pos['symbol']}")
            if pos["quantity"] < 0:
                args = dict(
                    symbol=pos["symbol"],
                    quantity=quantity,
                    disclosed_quantity=quantity,
                    product="M",
                    side="B",
                    order_type="MKT",
                    exchange="NFO",
                    tag="close",
                )
                resp = self._api.order_place(**args)
                logging.info(f"api responded with {resp}")
            elif quantity > 0:
                args = dict(
                    symbol=pos["symbol"],
                    quantity=quantity,
                    disclosed_quantity=quantity,
                    product="M",
                    side="S",
                    order_type="MKT",
                    exchange="NFO",
                    tag="close",
                )
                resp = self._api.order_place(**args)
                logging.info(f"api responded with {resp}")

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
    from pprint import pprint
    from src.constants import S_DATA

    try:
        Helper.api()

        def trades():
            resp = Helper._rest.trades()
            if resp:
                pd.DataFrame(resp).to_csv(S_DATA + "trades.csv", index=False)
                print(pd.DataFrame(resp))

        def orders():
            resp = Helper._api.broker.get_order_book()
            if resp and any(resp):
                pd.DataFrame(resp).to_csv(S_DATA + "orders.csv", index=False)
                print(pd.DataFrame(resp))
            else:
                print("no response from orders")

        def test_history(exchange, symbol):
            token = Helper._api.broker.instrument_symbol(exchange, symbol)
            print("token", token)
            resp = history(Helper._api, exchange, token)
            pprint(resp)
            print(resp[-2]["intl"], resp[-2]["time"])

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
        resp = Helper._rest.pnl("rpnl")
        print(resp)
        orders()

        # test_history(exchange="NFO", symbol="BANKNIFTY27MAR25C50000")
    except Exception as e:
        print(e)
        print_exc()
