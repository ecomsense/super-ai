from src.constants import logging, O_SETG
from src.helper import Helper, history
from src.trade_manager import TradeManager
from src.time_manager import TimeManager
from src.trade import Trade
from src.one_trade import OneTrade
from traceback import print_exc
import pendulum as pdlm

class Openingbalance:
    def __init__(
        self, prefix: str, symbol_info: dict, user_settings: dict
    ):
        self._id = symbol_info["symbol"]
        self._buy_order = {}
        self._fill_price = 0
        self._sell_order = None
        self._orders = []
        self._target_price = None
        self._removable = False
        self._t1 = user_settings["t1"]
        self._t2 = user_settings["t2"]
        self._prefix = prefix
        self.trade = Trade(
            symbol=symbol_info["symbol"],
            last_price=symbol_info["ltp"],
            exchange=user_settings["option_exchange"],
            quantity=user_settings["quantity"],
        )
        self._token = symbol_info["token"]
        self._low = symbol_info["low"]
        self._stop = symbol_info["low"]
        self._target = self._t1
        self._max_target_reached = 0
        self._txn = user_settings["txn"]
        self._time_mgr = TimeManager(rest_min=user_settings["rest_min"])
        self._fn = "wait_for_breakout"
        self._trade_manager = TradeManager(Helper.api())


    def _is_trailstopped(self, percent):
        # set max target reached
        if max(percent, self._max_target_reached) == percent:
            self._max_target_reached = percent

        trailing_target = self._max_target_reached / 2

        # if currently above stop% and below trailing target
        if self._t2 <= percent < trailing_target:
            msg = f"#TSL 50 PERC: {self.trade.symbol} {percent=} < {trailing_target=}"
            logging.info(msg)
            return True
        elif percent < self._t2 < self._max_target_reached:
            msg = f"#TSL T2 HIT: {self.trade.symbol} {percent=} < t2={self._t2}"
            logging.info(msg)
            return True
        
        #msg = f"#TRAIL: {self.trade.symbol} either {percent=} < {self._t2} or its > {trailing_target=}"
        msg = f"#TRAIL: {self.trade.symbol} {percent=} vs  max target reached:{self._max_target_reached}"
        logging.info(msg)
        return False

    """
    @property
    def reduced_target_sequence(self):
        return self._reduced_target_sequence

    @reduced_target_sequence.setter
    def reduced_target_sequence(self, sequence):
        if self._reduced_target_sequence == sequence - 1:
            self._reduced_target_sequence = sequence
            logging.debug(f"new target sequence reached {self._reduced_target_sequence}")

    """

    def _reset_trade(self):
        self.trade.filled_price = None
        self.trade.status = None
        self.trade.order_id = None

    def wait_for_breakout(self):
        try:
            if self.trade.last_price > self._stop and self._time_mgr.can_trade:
                if not OneTrade.is_traded_once(self.trade.symbol) or not OneTrade.is_prefix_in_trade(prefix=self._prefix):
                    self.trade.side = "B"
                    self.trade.disclosed_quantity = None
                    self.trade.price = self.trade.last_price + 2
                    self.trade.trigger_price = 0.0
                    self.trade.order_type = "LMT"
                    self.trade.tag = "entry_ob"
                    self._reset_trade()
                    buy_order = self._trade_manager.complete_entry(self.trade)
                    if buy_order.order_id is not None:
                        logging.info(f"BREAKOUT: {self.trade.symbol} ltp:{self.trade.last_price} > stop:{self._stop}")
                        OneTrade.add(self._prefix, self.trade.symbol)
                        self._fn = "find_fill_price"
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
            self.trade.price = self._stop - 2
            self.trade.trigger_price = self._stop
            self.trade.order_type = "SL-LMT"
            self.trade.tag = "sl_ob"
            self._reset_trade()
            sell_order = self._trade_manager.pending_exit(self.trade)
            if sell_order.order_id is not None:
                self._fn = "try_exiting_trade"
                logging.info(f"FILLED: {self.trade.symbol} at {self._fill_price}")
            else:
                logging.error(f"id is not found for sell {sell_order}")
        else:
            logging.error(
                f"order {self._trade_manager.position.entry.order_id} not complete"
            )

    def _set_target(self):
        try:
            rate_to_be_added = txn_cost = 0
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
                total_profit = total_profit - abs(m2m)
                logging.debug(f"{total_profit=} excluding current {m2m=} if in profit")

                # calculate txn cost
                count = len(
                    [
                        order["order_id"]
                        for order in self._orders
                        if order["symbol"].startswith(self._prefix)
                    ]
                )
                count = 1 if count == 0 else count / 2
                count = count + 0.5 if txn_cost % 1 == 0.5 else count
                txn_cost = count * self._txn
                logging.debug(f"{txn_cost=} for {count} trades * txn_rate:{self._txn}")

                if total_profit < 0:
                    rate_to_be_added = abs(total_profit) / self.trade.quantity
                    logging.debug(
                        f"{rate_to_be_added=} because of negative {total_profit=}"
                    )
            else:
                logging.warning(f"no positions for {self.trade.symbol} in {resp}")

            target_buffer = self._target * self._fill_price / 100
            target_virtual = (
                self._fill_price + target_buffer + rate_to_be_added + txn_cost
            )
            logging.debug(
                f"target_price {target_virtual} = fill + {target_buffer=} + {rate_to_be_added=} + {txn_cost=}"
            )
            target_progress = (
                (target_virtual - target_buffer - self.trade.last_price)
                / self._fill_price
                * 100
                * -1
            )

            # trailing
            if self._is_trailstopped(target_progress):
                resp = self._modify_to_exit()
                logging.debug(f"SELL MODIFY: {self.trade.symbol} got {resp}")
                self._fn = "remove_me"
                return True

            self._trade_manager.set_target_price(round(target_virtual / 0.05) * 0.05)
            self._fn = "try_exiting_trade"
            return None
        except Exception as e:
            print_exc()
            logging.error(f"{e} while set target")

    def _is_stoploss_hit(self):
        try:
            if O_SETG.get("live", 1) == 1:
                order = self._trade_manager.find_order_if_exists(
                    self._trade_manager.position.exit.order_id, self._orders
                )
                if isinstance(order, dict):
                    return True
            else:
                logging.debug("CHECKING STOP IN PAPER MODE")
                return Helper.api.can_move_order_to_trade(
                    self._trade_manager.position.exit.order_id, self.trade.last_price
                )
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
            # if trail stopped return prefix
            is_prefix = self._set_target()
            if is_prefix:
                return self._prefix

            # from 2nd trade onwards set actual low as stop
            # self._set_new_stop_from_low()

            if self._is_stoploss_hit():
                logging.info(f"SL HIT: {self.trade.symbol} stop order {self._trade_manager.position.exit.order_id}")
                self._fn = "wait_for_breakout"
                OneTrade.remove(self._prefix, self.trade.symbol)
            elif self.trade.last_price <= self._stop:
                resp = self._modify_to_kill()
                logging.info(f"KILLED: {self.trade.symbol} {self.trade.last_price} < stop ... got {resp}")
                self._fn = "wait_for_breakout"
                OneTrade.remove(self._prefix, self.trade.symbol)
            elif self.trade.last_price >= self._trade_manager.position.target_price:
                resp = self._modify_to_exit()
                logging.info(f"TARGET REACHED: {self.trade.symbol} {self.trade.last_price} < target price ... got {resp}")
                self._fn = "remove_me"
                OneTrade.remove(self._prefix, self.trade.symbol)
                return self._prefix
            else:
                msg = f"PROGRESS: {self.trade.symbol} target {self._trade_manager.position.target_price} < {self.trade.last_price} > sl {self._stop} "
                logging.info(msg)

            if self._fn == "wait_for_breakout":
                self._time_mgr.set_last_trade_time(pdlm.now("Asia/Kolkata"))

        except Exception as e:
            logging.error(f"{e} while exit order")
            print_exc()

    def remove_me(self):
        
        if self._fn == "find_fill_price":
            self.find_fill_price()
            return

        if self._fn == "try_exiting_trade":
            resp = self._modify_to_exit()
            logging.info(f"REMOVING: {self.trade.symbol} modify got {resp}")
        elif self._fn == "wait_for_breakout":
            logging.info(
                f"REMOVING: {self.trade.symbol} switching from waiting for breakout"
            )
        self._fn = "remove_me"
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
            logging.error(f"{e} in running {self.trade.symbol}")
            print_exc()

    