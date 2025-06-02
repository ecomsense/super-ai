from constants import logging, O_SETG
from helper import Helper
from traceback import print_exc
from time_manager import TimeManager
import pendulum as pdlm
from trade import Trade


class Openingbalance:

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
        self._t1 = 10
        self._t2 = 2
        self._prefix = prefix
        self.trade = Trade(
            symbol=symbol_info["symbol"],
            last_price=symbol_info["ltp"],
            exchange=user_settings["option_exchange"],
            quantity=user_settings["quantity"],
        )
        self._low = float(symbol_info["low"])
        self._stop = symbol_info["low"]
        # self._target = user_settings["target"]
        self._target = self._t1
        self._txn = user_settings["txn"]
        self._time_mgr = TimeManager(rest_min=user_settings["rest_min"])
        self._fn = "wait_for_breakout"

    @property
    def reduced_target_sequence(self):
        return self._reduced_target_sequence

    @reduced_target_sequence.setter
    def reduced_target_sequence(self, sequence):
        if self._reduced_target_sequence == sequence - 1:
            self._reduced_target_sequence = sequence
            logging.info(f"new target sequence reached {self._reduced_target_sequence}")

    def _reset_trade(self):
        self.trade.filled_price = None
        self.trade.status = None
        self.trade.order_id = None

    def wait_for_breakout(self):
        """if trading below above is true, we wait for ltp to be equal or greater than low"""
        try:
            if self.trade.last_price >= self._low and self._time_mgr.can_trade:
                self.trade.side = "B"
                self.trade.disclosed_quantity = None
                self.trade.price = self.trade.last_price + 2
                self.trade.trigger_price = 0.0
                self.trade.order_type = "LMT"
                self.trade.tag = "entry_ob"
                self._reset_trade()
                buy_order = self._trade_manager.complete_entry(self.trade)
                if buy_order.order_id is not None:
                    self._fn = "find_fill_price"
                    self.reduced_target_sequence = 1
                else:
                    logging.warning(
                        f"got {buy_order} without buy order order id {self.trade.symbol}"
                    )
        except Exception as e:
            print(f"{e} while waiting for breakout")

    def find_fill_price(self):
        order = self._trade_manager.find_order_if_exists(
            self._trade_manager.position.entry.order_id, self._orders
        )
        if isinstance(order, dict):
            self._fill_price = float(order["fill_price"])
            # place sell order only if buy order is filled
            self.trade.side = "S"
            self.trade.disclosed_quantity = 0
            self.trade.price = self._low - 2
            self.trade.trigger_price = self._low
            self.trade.order_type = "SL-LMT"
            self.trade.tag = "sl_ob"
            self._reset_trade()
            sell_order = self._trade_manager.pending_exit(self.trade)
            if sell_order.order_id is not None:
                self._fn = "try_exiting_trade"
            else:
                logging.error(f"id is not found for sell {sell_order}")
        else:
            logging.error(
                f"order {self._trade_manager.position.entry.order_id} not complete"
            )

    def _set_target(self):
        try:
            rate_to_be_added = 0
            logging.debug(f"setting target for {self.trade.symbol}")
            resp = Helper._rest.positions()
            if resp and any(resp):
                total_profit = sum(
                    item["rpnl"] + item["urmtom"]
                    for item in resp
                    if item["symbol"].startswith(self._prefix)
                )
                m2m = next(
                    (
                        item["urmtom"]
                        for item in resp
                        if item["symbol"] == self.trade.symbol
                    ),
                    0,
                )
                total_profit = total_profit - m2m if m2m > 0 else total_profit
                logging.debug(f"looking to add loss if any {total_profit=}")
                if total_profit < 0:
                    count = len(
                        [
                            order
                            for order in self._orders
                            if order["symbol"].startswith(self._prefix)
                        ]
                    )
                    rate_to_be_added = abs(total_profit) / self.trade.quantity
                    txn_cost = count * self._txn / 2
                    txn_cost = txn_cost + 0.5 if txn_cost % 1 == 0.5 else txn_cost
                    logging.debug(
                        f"txn: {txn_cost} = orders:{count} * txn_rate:{self._txn} / 2"
                    )
                    rate_to_be_added += txn_cost
                    logging.debug(
                        f"final {rate_to_be_added=} because of negative {total_profit=} and {txn_cost=} "
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
        try:
            kwargs = dict(
                trigger_price=0.0,
                order_type="LIMIT",
                last_price=self.trade.last_price,
            )
            return self._trade_manager.complete_exit(**kwargs)
        except Exception as e:
            logging.error(f"{e} while modify to exit {self.trade.symbol}")
            print_exc()

    def _modify_to_kill(self):
        try:
            kwargs = dict(
                price=0.0,
                order_type="MARKET",
                last_price=self.trade.last_price,
            )
            return self._trade_manager.complete_exit(**kwargs)
        except Exception as e:
            logging.error(f"{e} while modify to exit {self.trade.symbol}")
            print_exc()

    def try_exiting_trade(self):
        try:
            self._set_target()
            if self._is_stoploss_hit():
                self._time_mgr.set_last_trade_time(pdlm.now("Asia/Kolkata"))
                self._fn = "wait_for_breakout"
                self.reduced_target_sequence = 2
            elif self.trade.last_price< self._low:
                resp = self._modify_to_kill()
                logging.debug(f"kill returned {resp}")
                self._fn = "wait_for_breakout"
                self.reduced_target_sequence = 2
            elif self.trade.last_price >= self._trade_manager.position.target_price:
                resp = self._modify_to_exit()
                logging.debug(f"modify returned {resp}")
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
        if self._fn == "find_fill_price":
            self.find_fill_price()
            return

        if self._fn == "try_exiting_trade":
            logging.info(f"{self.trade.symbol} going to REMOVE after force modify")
            resp = self._modify_to_exit()
            logging.debug(f"modify returned {resp}")
        elif self._fn == "wait_for_breakout":
            logging.info(
                f"{self.trade.symbol} going to REMOVE without waiting for breakout"
            )
        self._fn = "remove_me"
        self._removable = True

    def run(self, orders, ltps, prefixes: list, sequence_info: dict):
        try:
            self._orders = orders

            ltp = ltps.get(self.trade.symbol, None)
            if ltp is not None:
                self.trade.last_price = float(ltp)

            if self._prefix in prefixes:
                self.remove_me()

            for id, info in sequence_info.items():
                if (
                    id != self._id and #if ce != pe
                    info["_prefix"] == self._prefix and # if nifty == nifty
                    info["_reduced_target_sequence"] == 2 and # if pe tgt seq == 2
                    self.reduced_target_sequence == 2 # if my (ce) tgt seq == 2
                ):
                    self._target = self._t2
                    break

            result = getattr(self, self._fn)()
            return result
        except Exception as e:
            logging.error(f"{e} in running {self.trade.symbol}")
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
