from dataclasses import asdict, replace

from src.config.interface import Position, Trade
from src.constants import logging_func

logging = logging_func(__name__)
from typing import Any


class TradeStatus:
    IN_POSITION, STOP_HIT, TARGET_REACHED = 0, 1, 2


def find_dict_with_kv(val: str | int, lst_of_dct: list[dict[str, Any]]):
    return next((dct for dct in lst_of_dct if dct.get("order_id") == val), None)


class TradeManager:
    def __init__(self, stock_broker, symbol, exchange, quantity=None, tag="unknown"):
        self.stock_broker = stock_broker
        self.position = Position(slippage=2)
        self._trade_template = Trade(
            symbol=symbol, exchange=exchange, tag=tag, quantity=quantity
        )

    """
    setters and getters
    """

    def stop(self, stop_price=None, quiet=False):
        if stop_price is not None:
            self.position.stop_price = stop_price
            if not quiet:
                logging.debug(f"setting new {stop_price=}")
        return self.position.stop_price

    def target(self, target_price=None):
        if target_price is not None:
            self.position.target_price = target_price
            logging.debug(f"setting new {target_price=}")
        return self.position.target_price

    """
        order entries
    """

    # REFACTORED: Created a helper to consolidate dictionary cleaning logic used by all order methods
    def _get_order_args(self, trade_obj: Trade):
        return {
            k: v
            for k, v in asdict(trade_obj).items()
            if v is not None and k != "order_id"
        }

    def order_place(self, trade: Trade):
        try:
            # REFACTORED: Replaced manual dict popping with the new helper method
            return self.stock_broker.order_place(**self._get_order_args(trade))
        except Exception as e:
            logging.error(f"TradeManager: Order Place {e}")
            raise

    def complete_entry(self, price, quantity=None):

        self.position.entry = replace(
            self._trade_template,
            side="B",
            price=price + self.position.slippage,
            order_type="LMT",
            trigger_price=0.0,
            disclosed_quantity=None,
        )

        if quantity:
            self.position.entry.quantity = quantity

        order_id = self.order_place(self.position.entry)

        logging.info(f"New entry#: {order_id} {self.position.entry.symbol} @{price}")

        self.position.entry.order_id, self.position.state = order_id, "entry_pending"

        return order_id

    def pending_exit(self, stop, orders, last_price):
        order = find_dict_with_kv(self.position.entry.order_id, orders)
        if order:
            self.position.entry.filled_price = self.position.average_price = float(
                order["fill_price"]
            )
            self.position.exit = replace(
                self._trade_template,
                side="S",
                price=stop - self.position.slippage,
                trigger_price=stop,
                order_type="SL-LMT",
                disclosed_quantity=None,
            )

            order_id = self.order_place(self.position.exit)
            logging.info(f"Exit Order#: {order_id} {self.position.exit.symbol} @{stop}")
            self.position.exit.order_id = order_id
            self.stop(stop_price=stop, quiet=True)
            return order_id

        if self.position.state == "entry_pending":
            logging.warning(
                f"{self.position.entry.symbol} buy order {self.position.entry.order_id} pending"
            )
            return self._modify_to_enter(last_price)
        return None

    """
    order modifiers

    """

    def _modify_to_enter(self, last_price):
        # REFACTORED: Leveraged _get_order_args to remove the manual dictionary boilerplate
        self.position.entry.price = last_price - self.position.slippage
        args = self._get_order_args(self.position.entry)
        args.update(
            order_id=self.position.entry.order_id, trigger_price=0.0, order_type="LIMIT"
        )
        return self.stock_broker.order_modify(**args)

    def _modify_to_exit(self):
        # REFACTORED: Leveraged _get_order_args and simplified the dict update logic
        args = self._get_order_args(self.position.exit)
        args.update(
            order_id=self.position.exit.order_id,
            trigger_price=0.0,
            order_type="MKT",
            price=0.0,
        )
        return self.stock_broker.order_modify(**args)

    def is_trade_exited(self, last_price, orders, removable=None):
        order = find_dict_with_kv(self.position.exit.order_id, orders)
        # REFACTORED: Pre-calculated the potential return intent to avoid nested if/else logic later
        intent = (
            TradeStatus.TARGET_REACHED
            if self.position.state == "target_pending"
            else TradeStatus.STOP_HIT
        )

        # REFACTORED: Combined the BFO handshake and "already exited" checks into one block
        if order or (
            self.position.state in ["target_pending", "stop_pending"] and not order
        ):
            if not order:
                # Combined market exit configuration into one line
                (
                    self.position.exit.order_type,
                    self.position.exit.price,
                    self.position.exit.trigger_price,
                ) = "MKT", 0.0, 0.0
                self.position.exit.order_id = self.order_place(self.position.exit)
                logging.info(
                    f"Exited at Market: {self.position.exit.symbol} @{last_price}"
                )

            self.position.state, self.position.average_price = "idle", None
            return intent

        # REFACTORED: Used boolean flags to determine triggers, removing repetitive BFO/Exchange logic blocks
        is_target = last_price > self.target()
        is_stop = last_price < self.stop() or removable

        if is_target or is_stop:
            if self.position.exit.exchange == "BFO":
                self.stock_broker.order_cancel(order_id=self.position.exit.order_id)
                self.position.state = "target_pending" if is_target else "stop_pending"
                return TradeStatus.IN_POSITION
            else:
                self._modify_to_exit()
                self.position.state = "idle"
                return TradeStatus.TARGET_REACHED if is_target else TradeStatus.STOP_HIT

        return TradeStatus.IN_POSITION
