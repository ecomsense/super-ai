from src.trade import Trade
from src.constants import logging
from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass(slots=True)
class Position:
    symbol: Optional[str] = None
    entry: Trade = field(default_factory=Trade)
    exit: Trade = field(default_factory=Trade)
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    is_position: bool = True


def order_place(stock_broker, trade):
    try:
        kwargs = asdict(trade)
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        trade.order_id = stock_broker.order_place(**kwargs)
        return trade
    except Exception as e:
        print(f"{e} in order place")


class TradeManager:

    def __init__(self, stock_broker):
        self.stock_broker = stock_broker
        self.position = Position()

    def complete_entry(self, trade: Trade):
        self.position.entry = order_place(self.stock_broker, trade)
        return self.position.entry

    def pending_exit(self, trade: Trade):
        self.position.exit = order_place(self.stock_broker, trade)
        return self.position.exit

    def set_target_price(self, target_price):
        self.position.target_price = target_price

    def is_stopped(self, orders):
        flag = False
        for order in orders:
            if self.position.exit.order_id == order["order_id"]:
                flag = True
                break
        return flag

    def find_order_if_exists(self, needle, order_hay):
        for order in order_hay:
            if needle == order["order_id"]:
                return order
        return

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
            logging.debug(f"contents of position.ext {exit_order_args}")
            return self.stock_broker.order_modify(**exit_order_args)
        except Exception as e:
            logging.error(f"Error in complete_exit {e}")
