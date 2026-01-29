from src.constants import logging_func
from dataclasses import asdict
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

    def order_place(self, trade: Trade):
        try:
            kwargs = asdict(trade)
            kwargs = {k: v for k, v in kwargs.items() if v is not None}
            trade.order_id = self.stock_broker.order_place(**kwargs)
            return trade
        except Exception as e:
            logging.error(f"TradeManager: Order Place {e}")
            raise  # Re-raise the exception instead of printing the error message

    def __init__(self, stock_broker, symbol, exchange, tag="unknown"):
        self.stock_broker = stock_broker
        self.position = Position()
        self.trade = Trade(symbol=symbol, exchange=exchange, tag=tag)

    def stop(self, stop_price=None):
        if stop_price is not None:
            self.position.stop_price = stop_price
        return self.position.stop_price

    def target(self, target_price=None):
        if target_price is not None:
            self.position.target_price = target_price
        return self.position.target_price

    def _reset_trade(self):
        self.trade.filled_price = None
        self.trade.status = None
        self.trade.order_id = None

    def complete_entry(self, quantity, price):
        self.trade.side = "B"
        self.trade.quantity = quantity
        self.trade.disclosed_quantity = None
        self.trade.price = price  # type: ignore
        self.trade.trigger_price = 0.0
        self.trade.order_type = "LMT"
        self._reset_trade()
        self.position.entry = self.order_place(self.trade)
        return self.position.entry.order_id

    def pending_exit(self, stop, orders, last_price):

        order = find_order_if_exists(self.position.entry.order_id, orders)
        if isinstance(order, dict):
            self.position.entry.filled_price = float(order["fill_price"])
            self.position.average_price = float(order["fill_price"])

            # place sell order only if buy order is filled
            self.trade.side = "S"
            self.trade.disclosed_quantity = 0
            self.trade.price = stop - 2
            self.trade.trigger_price = stop
            self.trade.order_type = "SL-LMT"
            self._reset_trade()
            self.position.exit = self.order_place(self.trade)
            self.stop(stop_price=stop)
            return self.position.exit
        else:
            modify_price = last_price - 2
            resp = self._modify_to_enter(modify_price)
            logging.debug(f"modifying entry returned {resp}")

        logging.warning(
            f"{self.trade.symbol} buy order {self.position.entry.order_id} not complete, to place sell order. retrying ..."
        )
        return None

    def is_stopped(self, orders):
        flag = False
        for order in orders:
            if self.position.exit.order_id == order["order_id"]:
                flag = True
                break
        return flag

    def complete_exit(self, **kwargs):
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
            logging.debug(f"TRADE MANAGER: modifying args {exit_order_args}")
            return self.stock_broker.order_modify(**exit_order_args)
        except Exception as e:
            logging.error(f"Error in complete_exit {e}")

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
                price=last_price,
                order_type="LIMIT",
                last_price=last_price,
            )
            logging.debug(f"modify entry args {entry_order_args}")
            return self.stock_broker.order_modify(**entry_order_args)
        except Exception as e:
            logging.error(f"{e} Error in modify to enter")

    def is_trade_exited(self, last_price, orders, removable=None):

        order = find_order_if_exists(self.position.exit.order_id, orders)

        if isinstance(order, dict):
            logging.info(
                f"STOP HIT: {self.trade.symbol} buy avg:{self.position.average_price}  stop:{self.stop()}"
            )
            return 1  # stop hit

        elif last_price < self.stop() or removable:  # type: ignore
            kwargs = dict(
                trigger_price=0.0,
                price=round_down_to_tick(last_price),
                order_type="LIMIT",
                last_price=last_price,
            )
            resp = self.complete_exit(**kwargs)
            logging.info(
                f"KILLING STOP: returned {resp} cos ltp:{last_price} < stop:{self.stop()}"
            )
            return 2

        elif last_price > self.target():
            kwargs = dict(
                trigger_price=0.0,
                order_type="LIMIT",
                last_price=last_price,
            )
            resp = self.complete_exit(**kwargs)
            logging.info(f"TARGET REACHED: returned {resp}")
            return 3

        return 0
