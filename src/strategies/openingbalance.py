"""
Purchase price for each trade plus 5% should be auto exit separately
Options stike chart respective 9.16 one min candle low will be stop loss
Buy will be manual  and sell will be algo with both target and stoploss.
Multiple trades will be triggered and to be tracked separetely.
"""

from constants import logging, O_SETG
from helper import Helper
from traceback import print_exc
from time_manager import TimeManager
import pendulum as pdlm
from trade import Trade


class Openingbalance:
    _id = None
    _buy_order = {}
    _fill_price = 0
    _sell_order = None
    _orders = []
    _is_trading_below_low = False
    _target_price = None
    _removable = False
    _trade_manager = None

    def __init__(self, prefix: str, symbol_info: dict, user_settings: dict):
        self._prefix = prefix
        self.trade = Trade(
            symbol=symbol_info["symbol"],
            last_price=symbol_info["ltp"],
            exchange=user_settings["option_exchange"],
            quantity=user_settings["quantity"],
        )
        self._low = float(symbol_info["low"])
        self._stop = symbol_info["low"]
        self._target = user_settings["target"]
        self._txn = user_settings["txn"]
        self._time_mgr = TimeManager(rest_min=user_settings["rest_min"])
        self._fn = "is_trading_below_low"

    def is_trading_below_low(self) -> bool:
        """checks if symbol is trading below or equal to low and return true or false"""
        if self.trade.last_price <= self._low:
            self._is_trading_below_low = True
            self._fn = "wait_for_breakout"
        return self._is_trading_below_low

    def wait_for_breakout(self):
        """if trading below above is true, we wait for ltp to be equal or greater than low"""
        try:
            if self.trade.last_price >= self._low and self._time_mgr.can_trade:
                self.trade.side = "B"
                self.trade.price = self.trade.last_price + 2
                self.trade.trigger_price = None
                self.trade.order_type = "LMT"
                self.trade.tag = "entry"
                buy_order = self._trade_manager.complete_entry(self.trade)
                if buy_order is not None:
                    self.trade.side = "S"
                    self.trade.disclosed_quantity = 0
                    self.trade.price = self._low - 2
                    self.trade.trigger_price = self._low
                    self.trade.order_type = "SL-LMT"
                    self.trade.tag = "stoploss"
                    sell_order = self._trade_manager.pending_exit(self.trade)
                    if sell_order is None:
                        raise Exception("sell order is not found")
                    else:
                        self._fn = "find_fill_price"
                else:
                    logging.warning(
                        f"unable to get buy order number for {self.trade.symbol}"
                    )
        except Exception as e:
            print(f"{e} while waiting for breakout")

    def find_fill_price(self):
        order = self._trade_manager.find_order_if_exists(
            self._trade_manager.position.entry.order_id, self._orders
        )
        if isinstance(order, dict):
            self._fill_price = float(order["fill_price"])
            self._fn = "try_exiting_trade"
        else:
            logging.warning(
                f"order not found {self._trade_manager.position.entry['order_id']}"
            )

    def _set_target(self):
        try:
            rate_to_be_added = 0
            logging.debug(f"setting target for {self.trade.symbol}")
            resp = Helper._rest.positions()
            if resp and any(resp):
                total_rpnl = sum(
                    item["rpnl"]
                    for item in resp
                    if item["symbol"].startswith(self._prefix)
                )
                logging.debug(f"looking to add loss if any {total_rpnl=}")
                if total_rpnl < 0:
                    count = len(
                        [
                            order
                            for order in self._orders
                            if order["symbol"].startswith(self._prefix)
                        ]
                    )
                    rate_to_be_added = abs(total_rpnl) / self.trade.quantity
                    txn_cost = int(count * self._txn / 2) + self._txn
                    logging.debug(
                        f"txn: {txn_cost} = orders:{count} * txn_rate:{self._txn} / 2"
                    )
                    rate_to_be_added += txn_cost
                    logging.debug(
                        f"final {rate_to_be_added=} because of negative {total_rpnl=} and {txn_cost=} "
                    )
            else:
                logging.warning(f"no positions for {self.trade.symbol} in {resp}")

            target_buffer = self._target * self._fill_price / 100
            target_virtual = self._fill_price + target_buffer + rate_to_be_added
            self._trade_manager.set_target_price(round(target_virtual / 0.05) * 0.05)
            self._fn = "try_exiting_trade"

        except Exception as e:
            print_exc()
            logging.error(f"{e} while set target")

    def _is_stoploss_hit(self):
        try:
            if O_SETG["trade"].get("live", 0) == 0:
                logging.debug("CHECKING STOP IN PAPER MODE")
                return Helper.api.can_move_order_to_trade(
                    self._trade_manager.position.exit.order_id, self.trade.last_price
                )
            else:
                order = self._trade_manager.find_order_if_exists(
                    self._trade_manager.position.exit.order_id, self._orders
                )
                if isinstance(order, dict):
                    return True

        except Exception as e:
            logging.error(f"{e} is stoploss hit {self.trade.symbol}")
            print_exc()

    def _modify_to_exit(self):
        kwargs = dict(
            trigger_price=0.0,
            order_type="LMT",
            tag=None,
            last_price=self.trade.last_price,
        )
        if self._trade_manager.complete_exit(**kwargs):
            return True
        return False

    def try_exiting_trade(self):
        try:
            self._set_target()
            if self._is_stoploss_hit():
                self._time_mgr.set_last_trade_time(pdlm.now("Asia/Kolkata"))
                self._is_trading_below_low = False
                self._fn = "is_trading_below_low"
                return True
            elif self.trade.last_price >= self._trade_manager.position.target_price:
                if self._modify_to_exit():
                    self._fn = "remove_me"
                    return self._prefix
            else:
                msg = (
                    f"{self.trade.symbol} target: {self._trade_manager.position.target_price} < {self.trade.last_price} > sl: {self._low} "
                    f"Remaining to target: {int(((self._trade_manager.position.target_price - self.trade.last_price) / (self._trade_manager.position.target_price - self._low)) * 100)}%"
                )
                logging.info(msg)

        except Exception as e:
            logging.error(f"{e} while exit order")
            print_exc()

    def remove_me(self):
        if self._fn == "try_exiting_trade":
            logging.info(f"{self.trade.symbol} going to REMOVE after force modify")
            _ = self._modify_to_exit()
        else:
            logging.info(
                f"{self.trade.symbol} going to REMOVE without waiting for breakout"
            )
        self._removable = True

    def run(self, orders, ltps, prefixes: list):
        try:
            self._orders = orders
            ltp = ltps.get(self.trade.symbol, None)
            if ltp is not None:
                self.trade.last_price = float(ltp)
            if self._prefix in prefixes:
                self.remove_me()
            result = getattr(self, self._fn)()
            return result
        except Exception as e:
            logging.error(f"{e} in run for buy order {self._id}")
            print_exc()


if __name__ == "__main__":

    def iter_tradebook(orders, search_id):
        try:
            for order in orders:
                print(order)
                if search_id == order["order_id"]:
                    print(f"{search_id} is found")
        except Exception as e:
            logging.error(f"{e} get order from book")
            print_exc()
