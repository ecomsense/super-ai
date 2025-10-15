from src.constants import logging
from dataclasses import asdict
from src.config.interface import Position, Trade


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

    def __init__(self, stock_broker):
        self.stock_broker = stock_broker
        self.position = Position()

    def stop(self, stop_price=None):
        if stop_price is None:
            return self.position.stop_price
        self.position.stop_price = stop_price

    def fill_price(self, filled_price=None):
        if filled_price is None:
            return self.position.filled_price
        self.position.filled_price = filled_price

    def complete_entry(self, trade: Trade):
        self.position.entry = self.order_place(trade)
        return self.position.entry

    def pending_exit(self, trade: Trade):
        self.position.exit = self.order_place(trade)
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
            logging.debug(f"TRADE MANAGER: modifying args {exit_order_args}")
            return self.stock_broker.order_modify(**exit_order_args)
        except Exception as e:
            logging.error(f"Error in complete_exit {e}")
