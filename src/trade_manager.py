from dataclasses import dataclass, asdict, field
from typing import Optional
from trade import Trade


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
        order_id = stock_broker.order_place(**kwargs)
        if order_id is not None:
            print(f"order# is {order_id}")
            trade.order_id = order_id
            return trade
        return None
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
        exit_order_args = asdict(self.position.exit)
        print(f"contents of position.ext {exit_order_args}")
        exit_order_args.update(kwargs)
        exit_order_args = {k: v for k, v in exit_order_args.items() if v is not None}
        self.stock_broker.order_modify(**exit_order_args)
        return True
