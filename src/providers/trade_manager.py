from src.constants import logging_func
from dataclasses import asdict, replace
from src.config.interface import Position, Trade
from src.sdk.utils import round_down_to_tick

logging = logging_func(__name__)


def find_order_if_exists(needle, order_hay):
    match = None
    for order in order_hay:
        if needle == order["order_id"]:
            match = order
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

    def stop(self, stop_price=None):
        if stop_price is not None:
            self.position.stop_price = stop_price
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
            kwargs = {k: v for k, v in kwargs.items() if v is not None}
            trade.order_id = self.stock_broker.order_place(**kwargs)
            return trade
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

        self.order_place(self.position.entry)
        logging.info(f"New entry:{position.entry.symbol} @{price}")

        self.position.state = "entry_pending"

        return self.position.entry.order_id

    def pending_exit(self, stop, orders, last_price):
        order = find_order_if_exists(self.position.entry.order_id, orders)

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
            logging.info(f"Stop Loss: {self.position.exit.symbol} @{stop}")
            self.order_place(self.position.exit)

            self.stop(stop_price=stop)

            return self.position.exit
        else:
            resp = self._modify_to_enter(last_price)

            logging.debug(f"modifying entry returned {resp}")

        logging.warning(
            f"{self.position.entry.symbol} buy order {self.position.entry.order_id} not complete, to place sell order. retrying ..."
        )
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

    def _modify_to_exit(self, **kwargs):
        try:
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
            logging.error(f"Error in complete_exit {e}")

    def is_trade_exited(self, last_price, orders, removable=None):

        order = find_order_if_exists(self.position.exit.order_id, orders)

        if isinstance(order, dict):
            logging.info(
                f"STOP HIT: {self.position.exit.symbol} buy avg:{self.position.average_price}  stop:{self.stop()}"
            )
            return 1  # stop hit

        elif last_price < self.stop() or removable:  # type: ignore
            kwargs = dict(
                trigger_price=0.0,
                price=round_down_to_tick(last_price),
                order_type="LIMIT",
                last_price=last_price,
            )
            resp = self._modify_to_exit(**kwargs)
            logging.info(
                f"KILLING STOP: returned {resp} cos ltp:{last_price} < stop:{self.stop()}"
            )
            return 1

        elif last_price > self.target():
            kwargs = dict(
                trigger_price=0.0,
                order_type="LIMIT",
                last_price=last_price,
            )
            resp = self._modify_to_exit(**kwargs)
            logging.info(f"TARGET REACHED: returned {resp}")
            return 2

        logging.debug(
            f"Progress: {self.position.exit.symbol} stop:{self.stop()} < ltp:{last_price} < target:{self.target()}"
        )
        return 0

    def run(self, orders, last_price, removable=None):

        state = self.position.state

        if state == "entry_pending":
            self.pending_exit(self.stop(), orders, last_price)

        elif state == "exit_pending":
            status = self.is_trade_exited(last_price, orders, removable)

            if status:
                self.position.state = "idle"
                return status

        return 0


"""
    def is_stopped(self, orders):
        flag = False
        for order in orders:
            if self.position.exit.order_id == order["order_id"]:
                flag = True
                break
        return flag
"""
