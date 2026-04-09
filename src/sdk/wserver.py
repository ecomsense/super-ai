from src.constants import logging_func
import time
from stock_brokers.flattrade.NorenApi import FeedType

logging = logging_func(__name__)


class Wserver:
    # flag to tell us if the websocket is open
    socket_opened = False
    ltp = {}

    def __init__(self, session, tokens):
        self.api = session
        self.tokens = tokens
        self.api.broker.start_websocket(
            order_update_callback=self.event_handler_order_update,
            subscribe_callback=self.event_handler_quote_update,
            socket_open_callback=self.open_callback,
            socket_close_callback=self.close_callback,
            socket_error_callback=self.error_callback,
        )

    def open_callback(self):
        self.socket_opened = True
        self.api.broker.subscribe(self.tokens, feed_type=FeedType.SNAPQUOTE)

    def close_callback(self):
        logging.warning("ws closed")
        self.socket_opened = False

    def error_callback(self, error):
        print(f"ws error: {error}")

    def event_handler_order_update(self, message):
        logging.info(f"order: {message}")

    def event_handler_quote_update(self, message):
        val = message.get("lp", False)
        if val:
            self.ltp[message["e"] + "|" + message["tk"]] = val

    def unsubscribe(self, tokens):
        self.api.broker.unsubscribe(tokens, feed_type=FeedType.SNAPQUOTE)

    def subscribe(self, tokens):
        self.api.broker.subscribe(tokens, feed_type=FeedType.SNAPQUOTE)


if __name__ == "__main__":
    from src.sdk.helper import Helper

    token = ["NSE|22", "NSE|26000"]
    wserver = Wserver(Helper.api(), token)
    try:
        ltp = {}
        while not ltp:
            ltp = wserver.ltp
            print("before subscribing", ltp)
            ltp = {}
            wserver.ltp = ltp
            wserver.unsubscribe(["NSE|22"])
            time.sleep(1)
        else:
            print("after unsubscribing", wserver.ltp)
    except KeyboardInterrupt:
        print("user interrupted")
    except Exception as e:
        print(e)
