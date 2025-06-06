from constants import logging, O_SETG
from helper import Helper
from traceback import print_exc
from time_manager import TimeManager
import pendulum as pdlm
from trade import Trade


class Pivot:

    def __init__(self, prefix: str, symbol_info: dict, user_settings: dict):
        self._id = symbol_info["symbol"]
        self._buy_order = {}
        self._fill_price = 0
        self._sell_order = None
        self._orders = []
        self._target_price = None
        self._removable = False
        self._trade_manager = None
        self._reduced_target_sequence = 0
        self._t1 = user_settings["t1"]
        self._t2 = user_settings["t2"]
        self._prefix = prefix
        self.trade = Trade(
            symbol=symbol_info["symbol"],
            last_price=symbol_info["ltp"],
            exchange=user_settings["option_exchange"],
            quantity=user_settings["quantity"],
        )
        self._low = float(symbol_info["low"])
        self._stop = symbol_info["low"]
        self._target = self._t1
        self._txn = user_settings["txn"]
        self._time_mgr = TimeManager(rest_min=user_settings["rest_min"])
        self._fn = "wait_for_breakout"
