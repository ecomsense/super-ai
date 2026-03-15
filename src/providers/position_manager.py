from dataclasses import asdict, replace
from typing import Dict, List
from src.constants import logging_func
from src.sdk.utils import round_down_to_tick
from src.config.interface import Trade, Position

logging = logging_func(__name__)


class PositionStatus:
    IN_POSITION, STOP_HIT, TARGET_REACHED = 0, 1, 2


class NewTradeManager:
    """The Worker: Handles broker logic for a single Position object."""

    def __init__(self, stock_broker, position: Position):
        self.stock_broker = stock_broker
        self.pos = position

    def _get_order_args(self, trade_obj: Trade):
        return {
            k: v
            for k, v in asdict(trade_obj).items()
            if v is not None and k != "order_id"
        }

    def place_order(self, trade: Trade):
        try:
            return self.stock_broker.order_place(**self._get_order_args(trade))
        except Exception as e:
            logging.error(f"TradeManager Error: Order Place {e}")
            raise

    def execute_entry(self, entry_price):
        self.pos.entry.price = entry_price + self.pos.slippage
        self.pos.entry.side = "B"
        self.pos.entry.order_id = self.place_order(self.pos.entry)
        if self.pos.entry.order_id is None:
            (
                self.pos.entry.order_type,
                self.pos.entry.price,
                self.pos.entry.trigger_price,
            ) = "MKT", 0.0, 0.0
            self.pos.entry.order_id = self.place_order(self.pos.entry)
        logging.info(f"Entry Placed: {self.pos.entry.order_id} @ {entry_price}")
        self.pos.state = "entry_pending"
        return self.pos.entry.order_id

    def sync_entry(self, last_price, orders):
        """Checks for fill or chases the market if pending."""
        order = next(
            (o for o in orders if o.get("order_id") == self.pos.entry.order_id), None
        )

        if order:
            # Trade filled: Set up exit SL
            self.pos.average_price = float(order["fill_price"])

            # Apply auto-trail logic if specified
            if self.pos.trail_percent is not None:
                dist = abs(self.pos.average_price - self.pos.stop_price)
                self.pos.stop_price = round_down_to_tick(
                    self.pos.stop_price + (dist * self.pos.trail_percent)
                )

            # Prepare Exit Trade
            self.pos.exit = replace(
                self.pos.entry,
                side="S",
                order_type="SL-LMT",
                trigger_price=self.pos.stop_price,
                price=self.pos.stop_price - self.pos.slippage,
                order_id=None,
            )
            self.pos.exit.order_id = self.place_order(self.pos.exit)
            self.pos.state = "in_position"
            logging.info(
                f"Filled: {self.pos.id} @ {self.pos.average_price}. Stop: {self.pos.stop_price}"
            )
        else:
            # Chasing Logic: Modify entry price to match market
            self.pos.entry.price = last_price + self.pos.slippage
            args = self._get_order_args(self.pos.entry)
            args.update(
                order_id=self.pos.entry.order_id, trigger_price=0.0, order_type="LMT"
            )
            self.stock_broker.order_modify(**args)

    def monitor_exit(self, last_price, orders, removable):
        """Checks for target/stop hits and handles broker exit logic."""
        order = next(
            (o for o in orders if o.get("order_id") == self.pos.exit.order_id), None
        )

        # Determine if target or stop was hit
        is_target = last_price > self.pos.target_price
        is_stop = last_price < self.pos.stop_price or removable

        # BFO Handshake or already exited check
        if order or self.pos.state in ["target_pending", "stop_pending"]:
            if not order:  # Place market order if BFO cancel confirmed
                (
                    self.pos.exit.order_type,
                    self.pos.exit.price,
                    self.pos.exit.trigger_price,
                ) = "MKT", 0.0, 0.0
                self.place_order(self.pos.exit)

            intent = (
                PositionStatus.TARGET_REACHED
                if self.pos.state == "target_pending"
                else PositionStatus.STOP_HIT
            )
            self.pos.state = "idle"
            return intent

        if is_target or is_stop:
            if self.pos.exit.exchange == "BFO":
                self.stock_broker.order_cancel(order_id=self.pos.exit.order_id)
                self.pos.state = "target_pending" if is_target else "stop_pending"
                return PositionStatus.IN_POSITION
            else:
                # Standard Market Exit
                args = self._get_order_args(self.pos.exit)
                args.update(
                    order_id=self.pos.exit.order_id,
                    trigger_price=0.0,
                    order_type="MKT",
                    price=0.0,
                )
                self.stock_broker.order_modify(**args)
                self.pos.state = "idle"
                return (
                    PositionStatus.TARGET_REACHED
                    if is_target
                    else PositionStatus.STOP_HIT
                )

        return PositionStatus.IN_POSITION


class PositionManager:
    """The Coordinator: Manages the registry of NewTradeManager instances."""

    def __init__(self, stock_broker):
        self.stock_broker = stock_broker
        self._managers: Dict[int, NewTradeManager] = {}

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
        # 1. Create Data Object
        pos = Position(
            symbol=symbol,
            stop_price=stop_loss,
            target_price=target,
            trail_percent=trail_percent,
        )
        pos.entry = Trade(symbol=symbol, exchange=exchange, quantity=quantity, tag=tag)

        # 2. Create Worker
        tm = NewTradeManager(self.stock_broker, pos)
        order_id = tm.execute_entry(entry_price)

        if order_id is not None:
            # 3. Register
            self._managers[pos.id] = tm
            return pos.id

        return None

    def status(
        self,
        pos_id: int,
        last_price: float,
        orders: List[dict],
        removable: bool = False,
    ) -> int:
        tm = self._managers.get(pos_id)
        # Lifecycle Management
        if tm.pos.state == "entry_pending":
            tm.sync_entry(last_price, orders)
            return PositionStatus.IN_POSITION

        if tm.pos.state in ["in_position", "target_pending", "stop_pending"]:
            res = tm.monitor_exit(last_price, orders, removable)

            # If trade is closed, remove from registry
            if tm.pos.state == "idle":
                logging.info(f"PM: Removing {pos_id} from tracking.")
                del self._managers[pos_id]
            return res

        return PositionStatus.IN_POSITION
