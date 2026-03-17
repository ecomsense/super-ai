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
    def add_trade(broker, trade: Trade):
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


class PositionManager:
    """The State Machine: Decides which broker action to take based on trade state."""

    def __init__(self, stock_broker):
        self.stock_broker = stock_broker
        self._positions: Dict[int, Position] = {}
        self.executor = NewTradeManager()

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

        pos.entry = Trade(
            symbol=symbol,
            quantity=quantity,
            disclosed_quantity=None,
            side="B",
            order_type="LMT",
            exchange=exchange,
            tag=tag,
            price=entry_price + pos.slippage,
            trigger_price=0.0,
        )

        pos.exit = Trade(
            symbol=symbol,
            quantity=quantity,
            disclosed_quantity=None,
            side="S",
            order_type="SL-LMT",
            exchange=exchange,
            tag=tag,
        )

        order_id = self.executor.add_trade(self.stock_broker, pos.entry)

        if order_id:
            pos.entry.order_id = order_id
            pos.state = "entry_pending"
            self._positions[pos.id] = pos
            logging.info(f"PM: [{pos.id}] New Entry {order_id} @ {entry_price}")
            return pos.id
        return None

    def _retry(self, pos, last_price):

        if pos.entry.side == "B":
            new_price = last_price + pos.slippage
            entry_or_exit = pos.entry
        else:
            new_price = last_price - pos.slippage
            entry_or_exit = pos.exit

        self.executor.modify_trade(
            self.stock_broker,
            entry_or_exit.order_id,
            price=new_price,
            order_type="LMT",
            trigger_price=0.0,
        )

    def status(
        self,
        pos_id: int,
        last_price: float,
        orders: List[dict],
        removable: bool = False,
    ) -> int:

        pos = self._positions.get(pos_id)
        if not pos:
            return PositionStatus.STOP_HIT

        # --- STATE: ENTRY_PENDING ---
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

                # 2. Action: Add Exit (SL-LMT)
                pos.exit.trigger_price = pos.stop_price
                pos.exit.price = pos.stop_price - pos.slippage

                exit_id = self.executor.add_trade(self.stock_broker, pos.exit)
                if exit_id:
                    pos.state = "in_position"
                    pos.exit.order_id = exit_id
                    logging.info(
                        f"PM: [{pos.id}] Filled. Exit Set: {exit_id} @ {pos.stop_price}"
                    )
            else:
                self._retry(pos, last_price)

            return PositionStatus.IN_POSITION

        # --- STATE: ACTIVE TRADING ---
        if pos.state in ["in_position", "target_pending", "stop_pending"]:
            order = next(
                (o for o in orders if o.get("order_id") == pos.exit.order_id), None
            )

            is_target = last_price > pos.target_price if pos.target_price else False
            is_stop = last_price < pos.stop_price or removable

            # Handle BFO Handshake / Pending Closure
            if order or pos.state in ["target_pending", "stop_pending"]:
                if not order:  # Cancellation confirmed at broker
                    # Action: Add Final Market Exit
                    pos.exit.order_type, pos.exit.price, pos.exit.trigger_price = (
                        "MKT",
                        0.0,
                        0.0,
                    )
                    self.executor.add_trade(self.stock_broker, pos.exit)

                intent = (
                    PositionStatus.TARGET_REACHED
                    if pos.state == "target_pending"
                    else PositionStatus.STOP_HIT
                )
                self._cleanup(pos_id)
                return intent

            # Trigger Logic
            if is_target or is_stop:
                if pos.exit.exchange == "BFO":
                    # Action: Cancel Trade
                    self.executor.cancel_trade(self.stock_broker, pos.exit.order_id)
                    pos.state = "target_pending" if is_target else "stop_pending"
                else:
                    # Action: Modify to Market
                    self.executor.modify_trade(
                        self.stock_broker,
                        pos.exit.order_id,
                        order_type="MKT",
                        price=0.0,
                        trigger_price=0.0,
                    )
                    intent = (
                        PositionStatus.TARGET_REACHED
                        if is_target
                        else PositionStatus.STOP_HIT
                    )
                    self._cleanup(pos_id)
                    return intent

        return PositionStatus.IN_POSITION

    def _cleanup(self, pos_id):
        if pos_id in self._positions:
            logging.info(f"PM: Removing tracker for position {pos_id}")
            del self._positions[pos_id]
