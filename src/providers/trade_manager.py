from dataclasses import asdict, replace

from src.config.interface import Position, Trade
from src.constants import logging_func

logging = logging_func(__name__)
from typing import Any

def find_dict_with_kv(val: str | int, lst_of_dct: list[dict[str, Any]]):
    match = None
    for dct in lst_of_dct:
        if val == dct["order_id"]:
            match = dct
            break
    return match


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

    def order_place(self, trade: Trade):
        try:
            kwargs = asdict(trade)
            _ = kwargs.pop("order_id", None)
            kwargs = {k: v for k, v in kwargs.items() if v is not None}
            return self.stock_broker.order_place(**kwargs)
        except Exception as e:
            logging.error(f"TradeManager: Order Place {e}")
            raise  # Re-raise the exception instead of printing the error message

    def complete_entry(self, price, quantity=None):

        # reset average price a.k.a fill price
        self.position.average_price = None

        self.position.entry = replace(self._trade_template)

        if quantity:
            self.position.entry.quantity = quantity

        self.position.entry.side = "B"
        self.position.entry.disclosed_quantity = None
        self.position.entry.price = price + self.position.slippage  # type: ignore
        self.position.entry.trigger_price = 0.0
        self.position.entry.order_type = "LMT"

        order_id = self.order_place(self.position.entry)
        logging.info(f"New entry#: {order_id} {self.position.entry.symbol} @{price}")
        self.position.entry.order_id = order_id
        self.position.state = "entry_pending"
        return order_id

    def pending_exit(self, stop, orders, last_price):

        order = find_dict_with_kv(self.position.entry.order_id, orders)
        if isinstance(order, dict):
            self.position.entry.filled_price = float(order["fill_price"])
            self.position.average_price = float(order["fill_price"])

            # place sell order only if buy order is filled
            self.position.exit = replace(self._trade_template)
            self.position.exit.side = "S"
            self.position.exit.disclosed_quantity = 0
            self.position.exit.price = stop - self.position.slippage
            self.position.exit.trigger_price = stop
            self.position.exit.order_type = "SL-LMT"

            
            order_id = self.order_place(self.position.exit)
            logging.info(f"Exit Order#: {order_id} {self.position.exit.symbol} @{stop}")
            self.position.exit.order_id = order_id
            self.stop(stop_price=stop, quiet=True)
            return order_id


        # our earlier attempt to modify order failed 
        # TODO try cancel here
        if self.position.state == "entry_pending":
            msg =f"{self.position.entry.symbol} buy order {self.position.entry.order_id} is {self.position.state}"
            logging.warning(msg)
            resp = self._modify_to_enter(last_price)
            logging.debug(f"modifying exit returned {resp}")
        return None

    """
        order modifiers
    """

    def _modify_to_enter(self, last_price):
        try:
            entry_order_args = dict(
                order_id=self.position.entry.order_id,
                symbol=self.position.entry.symbol,
                quantity=self.position.entry.quantity,
                disclosed_quantity=self.position.entry.disclosed_quantity,
                product=self.position.entry.product,
                side=self.position.entry.side,
                exchange=self.position.entry.exchange,
                trigger_price=0.0,
                price=last_price - self.position.slippage,
                order_type="LIMIT",
                last_price=last_price,
            )
            logging.debug(f"modify entry args {entry_order_args}")
            return self.stock_broker.order_modify(**entry_order_args)
        except Exception as e:
            logging.error(f"{e} Error in modify to enter")

    def _modify_to_exit(self):
        try:
            kwargs = dict(trigger_price=0.0, order_type="MKT", price=0.0)
            exit_order_args = dict(
                order_id=self.position.exit.order_id,
                symbol=self.position.exit.symbol,
                quantity=self.position.exit.quantity,
                disclosed_quantity=self.position.exit.disclosed_quantity,
                product=self.position.exit.product,
                side=self.position.exit.side,
                price=self.position.exit.price,
                exchange=self.position.exit.exchange,
            )
            exit_order_args.update(kwargs)
            logging.debug(f"modifying args {exit_order_args}")
            return self.stock_broker.order_modify(**exit_order_args)
        except Exception as e:
            logging.error(f"Error in _modify_to_exit {e}")


    def is_trade_exited(self, last_price, orders, removable=None):
        final_status_intent = 2 if self.position.state == "target_pending" else 1
        order = find_dict_with_kv(self.position.exit.order_id, orders)
        if isinstance(order, dict):
            self.position.state = "idle"
            return final_status_intent

        # 1. BFO HANDSHAKE: VERIFY CANCEL
        if self.position.state in ["target_pending", "stop_pending"]:
            
            # If NOT in tradebook, cancel successful.
            if not order:
                # Replace with MKT
                self.position.exit.order_type = "MKT"
                self.position.exit.price = 0.0
                self.position.exit.trigger_price = 0.0
                
                order_id = self.order_place(self.position.exit)
                logging.info(f"Exited at Market: #{order_id} ?. {self.position.exit.symbol} @{last_price}")
                self.position.exit.order_id = order_id
                self.position.state = "idle"
                return final_status_intent
            
            else: # Filled before cancel
                 self.position.state = "idle"
                 return final_status_intent 


        # TARGET REACHED
        if last_price > self.target():
            if self.position.exit.exchange == "BFO":
                # BFO: Must Cancel First
                self.stock_broker.order_cancel(order_id=self.position.exit.order_id)
                self.position.state = "target_pending"
                return 0
            else:
                self._modify_to_exit()
                return 2

        # STOP HIT OR REMOVABLE
        elif last_price < self.stop() or removable:
            if self.position.exit.exchange == "BFO":
                # BFO: Must Cancel First
                self.stock_broker.order_cancel(order_id=self.position.exit.order_id)
                self.position.state = "stop_pending"
                return 0
            else:
                self._modify_to_exit()
                return 1

        return 0

