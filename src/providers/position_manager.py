from dataclasses import asdict, replace
from typing import Dict, List
from src.constants import logging_func
from src.sdk.utils import round_down_to_tick
from src.config.interface import Trade, Position

logging = logging_func(__name__)


class PositionStatus:
    IN_POSITION, STOP_HIT, TARGET_REACHED = 0, 1, 2


class NewTradeManager:
    """
    The Stateless Executor:
    Does not care about strategy or state; only knows how to talk to the broker.
    """

    @staticmethod
    def _get_args(trade: Trade):
        return {
            k: v for k, v in asdict(trade).items() if v is not None and k != "order_id"
        }

    @staticmethod
    def enter_trade(broker, trade: Trade):
        try:
            return broker.order_place(**NewTradeManager._get_args(trade))
        except Exception as e:
            logging.error(f"Broker: Add Trade Error: {e}")
            return None

    @staticmethod
    def modify_trade(broker, order_id, **kwargs):
        try:
            return broker.order_modify(order_id=order_id, **kwargs)
        except Exception as e:
            logging.error(f"Broker: Modify Trade Error {order_id}: {e}")
            return None

    @staticmethod
    def cancel_trade(broker, order_id):
        try:
            return broker.order_cancel(order_id=order_id)
        except Exception as e:
            logging.error(f"Broker: Cancel Trade Error {order_id}: {e}")
            return None


class BSEManager:
    def __init__(self) -> None:
        pass


class MCXManager:
    def __init__(self) -> None:
        pass


def _get_args(trade: Trade):
    return {k: v for k, v in asdict(trade).items() if k != "order_id"}


class NFOManager:
    def __init__(self, broker, pos, tag) -> None:
        self.broker = broker
        self.template = Trade(
            symbol=pos.symbol,
            quantity=pos.quantity,
            disclosed_quantity=None,
            exchange="NFO",
            tag=tag,
            order_type="LMT",
            trigger_price=0.0,
            side="B"
        )
        self.entry_or_exit = "entry"
        self.next_fn = "create"

    def create_entry(self, pos, last_price):
        price = last_price + pos.slippage

        # 2. Build the Trade using the template
        pos.entry = replace(self.template, price=price)
        pos.entry.order_id = self.broker.order_place(**_get_args(pos.entry))
        if pos.entry.order_id:
            pos.state = "entry_pending"
            logging.info(f"{pos.state} {pos.entry.order_id} @ {last_price}")
            self.next_fn = "create_exit"
        return pos

    def create_exit(self, pos, last_price):
        pos.exit = replace(self.template, side="S", price=pos.stop - pos.slippage, trigger_price=pos.stop, order_type="SL-LMT")
        pos.exit.order_id = self.broker.order_place(**_get_args(pos.exit))
        if pos.exit.order_id:
            pos.state = "exit_pending"
            logging.info(f"{pos.state} {pos.exit.order_id} @ {last_price}")
            self.next_fn = "modify"
        return pos

    def modify(self, pos, last_price):
        try:
            if pos.state == "target_pending" or pos.state == "stop_pending"
                kwargs = dict(
                    order_type="LMT",
                    trigger_price=0.0,
                )
                resp = self.broker.order_modify(order_id=order_id, **kwargs)
                self.next_fn = "cancel"
        except Exception as e:
            logging.error(f"Modify Trade {order_id}: {e} in {resp} @ {last_price}")
        finally:
            return pos

    def cancel(self, pos, last_price):
        try:
            resp = broker.order_cancel(order_id=pos.exit.order_id)
            self.next_fn = "final_exit"
        except Exception as e:
            logging.error(f"Cancel Trade {order_id}: {e} in {resp} @ {last_price}")
        finally:
            return pos

    def final_exit(self, pos, last_price):
        price = last_price - pos.slippage
        pos.exit = replace(self.template, price=price, side="S")
        pos.exit.order_id = self.broker.order_place(**_get_args(pos.entry))
        if pos.exit.order_id:
            pos.state = "entry_pending"
            logging.info(f"{pos.state} {pos.entry.order_id} @ {last_price}")
            self.next_fn = "create_exit"
        return pos


executors = {"NFO": NFOManager, "BFO": BSEManager, "MCX": MCXManager}


class PositionManager:
    """The State Machine: Decides which broker action to take based on trade state."""

    def __init__(self, stock_broker):
        self.stock_broker = stock_broker
        self._positions: Dict[int, Position] = {}

    def new(
        self,
        symbol,
        exchange,
        quantity,
        tag,
        entry_price,
        stop_loss,
        target=None,
        trail_percent=None,
    ) -> int | None:

        pos = Position(
            symbol=symbol,
            stop_price=stop_loss,
            target_price=target,
            trail_percent=trail_percent,
            slippage=2.0,
        )
        pos.ex = executors.get(exchange)

        # init an exchange executor instance
        pos.ex(
            broker=self.stock_broker, pos=pos, symbol=symbol, quantity=quantity, tag=tag
        )

        pos = pos.ex.create_entry(pos, last_price=entry_price)
        if pos.entry.order_id:
            self._positions[pos.id] = pos
            return pos.id

        return None

    def status(
        self,
        pos_id: int,
        last_price: float,
        orders: List[dict],
        removable: bool = False,
    ) -> int:

        if pos.state == "entry_pending":
            order = next(
                (o for o in orders if o.get("order_id") == pos.entry.order_id), None
            )

            if order:
                # 1. Fill Logic
                pos.average_price = float(order["fill_price"])
                if pos.trail_percent is not None:
                    dist = abs(pos.average_price - pos.stop_price)
                    pos.stop_price = round_down_to_tick(
                        pos.stop_price + (dist * pos.trail_percent)
                    )

        elif pos.state in ["target_pending", "stop_pending"]:

            order = next(
                (o for o in orders if o.get("order_id") == pos.exit.order_id), None
            )
            if order:
                intent = (
                    PositionStatus.TARGET_REACHED
                    if pos.state == "target_pending"
                    else PositionStatus.STOP_HIT
                )
                self._cleanup(pos_id)
                return intent
        
        else: # exit_pending
            order = {}
            is_target = last_price > pos.target_price if pos.target_price else False
            is_stop = last_price < pos.stop_price or removable
            if is_target or is_stop:
                pos.state = "target_pending" if is_target else "stop_pending"

        self._positions[pos_id] = getattr(pos.ex, pos.next_fn)(pos, last_price)
        return PositionStatus.IN_POSITION

    def _cleanup(self, pos_id):
        if pos_id in self._positions:
            logging.info(f"PM: Removing tracker for position {pos_id}")
            del self._positions[pos_id]


"""
"""
