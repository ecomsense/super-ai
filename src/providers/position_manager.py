from dataclasses import asdict, replace
from typing import Dict, List
from src.constants import logging_func
from src.sdk.utils import round_down_to_tick
from src.config.interface import Trade, Position

logging = logging_func(__name__)


class BSEManager:
    def __init__(self) -> None:
        pass


class MCXManager:
    def __init__(self, broker, pos, tag, exit_method) -> None:
        self.broker = broker
        self.template = Trade(
            symbol=pos.symbol,
            quantity=pos.quantity,
            disclosed_quantity=0,  # NFO expects to be 0 atleast for Sell orders
            exchange="MCX",
            tag=tag,
            order_type="LMT",
            trigger_price=0.0,
            side="B",
        )
        self.exit_method = exit_method
        self.entry_or_exit = "entry"
        self.next_fn = "create_entry"

    def create_entry(self, pos, last_price):
        try:
            price = last_price + pos.slippage

            # 2. Build the Trade using the template
            pos.entry = replace(self.template, price=price)
            pos.entry.order_id = self.broker.order_place(**_get_args(pos.entry))
            if pos.entry.order_id:
                pos.state = "entry_pending"
                logging.info(f"{pos.state} {pos.entry.order_id} @ {last_price}")
                self.next_fn = "wait_for_entry"
        except Exception as e:
            logging.error(f"Create Entry: {e}")
        return pos

    def wait_for_entry(self, pos, last_price):
        try:
            if pos.average_price:
                pos = self.create_exit(pos, last_price)
        except Exception as e:
            logging.info(f"Wait for entry: {e}")
        finally:
            return pos

    def create_exit(self, pos, last_price):
        try:
            if self.exit_method == "target":
                pos.exit = replace(
                    self.template,
                    side="S",
                    price=pos.target_price,
                    trigger_price=0,
                    order_type="LMT",
                )

            else:
                pos.exit = replace(
                    self.template,
                    side="S",
                    price=pos.stop_price - pos.slippage,
                    trigger_price=pos.stop_price,
                    order_type="SL-LMT",
                )
            pos.exit.order_id = self.broker.order_place(**_get_args(pos.exit))
            if pos.exit.order_id:
                pos.state = "exit_pending"
                logging.info(f"{pos.state} {pos.exit.order_id} @ {last_price}")
                self.next_fn = "cancel"
        except Exception as e:
            logging.error(f"Exit Trade: {e} {pos.exit.order_id} @ {last_price}")
        finally:
            return pos

    def cancel(self, pos, last_price):
        try:
            order_id = pos.state
            if pos.state == "target_pending" or pos.state == "stop_pending":
                order_id = pos.exit.order_id
                resp = self.broker.order_cancel(order_id=pos.exit.order_id)
                logging.info(f"Cancel Order: {resp}")
                self.next_fn = "final_exit"
        except Exception as e:
            logging.error(f"Cancel Trade {order_id}: {e} @ {last_price}")
        finally:
            return pos

    def final_exit(self, pos, last_price):
        try:
            price = last_price - pos.slippage
            pos.exit = replace(self.template, price=price, side="S")
            pos.exit.order_id = self.broker.order_place(**_get_args(pos.exit))
            if pos.exit.order_id:
                logging.info(f"{pos.state} {pos.entry.order_id} @ {last_price}")
                pos.state = (
                    "target_reached" if pos.state == "target_pending" else "stop_hit"
                )
                self.next_fn = "do_nothing"
        except Exception as e:
            logging.error(f"Final exit: {e} order id {pos.exit.order_id}")
        finally:
            return pos

    def do_nothing(self, pos, last_price):
        logging.info(
            f"{pos.symbol} with status: {pos.state} @{last_price=} waiting for cleanup"
        )
        return pos


def _get_args(trade: Trade):
    return {k: v for k, v in asdict(trade).items() if k != "order_id" and v is not None}


class NFOManager:
    def __init__(self, broker, pos, tag, exit_method) -> None:
        self.broker = broker
        self.template = Trade(
            symbol=pos.symbol,
            quantity=pos.quantity,
            disclosed_quantity=0,  # NFO expects to be 0 atleast for Sell orders
            exchange="NFO",
            tag=tag,
            order_type="LMT",
            trigger_price=0.0,
            side="B",
        )
        self.exit_method = (exit_method,)
        self.entry_or_exit = "entry"
        self.next_fn = "create_entry"

    def create_entry(self, pos, last_price):
        try:
            price = last_price + pos.slippage

            # 2. Build the Trade using the template
            pos.entry = replace(self.template, price=price)
            pos.entry.order_id = self.broker.order_place(**_get_args(pos.entry))
            if pos.entry.order_id:
                pos.state = "entry_pending"
                logging.info(f"{pos.state} {pos.entry.order_id} @ {last_price}")
                self.next_fn = "wait_for_entry"
        except Exception as e:
            logging.error(f"Create Entry: {e}")
        return pos

    def wait_for_entry(self, pos, last_price):
        try:
            if pos.average_price:
                pos = self.create_exit(pos, last_price)
        except Exception as e:
            logging.info(f"Wait for entry: {e}")
        finally:
            return pos

    def create_exit(self, pos, last_price):
        try:
            if self.exit_method == "target":
                pos.exit = replace(
                    self.template,
                    side="S",
                    price=pos.target_price,
                    trigger_price=0,
                    order_type="LMT",
                )
            else:
                pos.exit = replace(
                    self.template,
                    side="S",
                    price=pos.stop_price - pos.slippage,
                    trigger_price=pos.stop_price,
                    order_type="SL-LMT",
                )
            pos.exit.order_id = self.broker.order_place(**_get_args(pos.exit))
            if pos.exit.order_id:
                pos.state = "exit_pending"
                logging.info(f"{pos.state} {pos.exit.order_id} @ {last_price}")
                self.next_fn = "modify"
        except Exception as e:
            logging.error(f"Exit Trade: {e} {pos.exit.order_id} @ {last_price}")
        finally:
            return pos

    def modify(self, pos, last_price):
        try:
            order_id = pos.state
            if pos.state == "target_pending" or pos.state == "stop_pending":
                order_id = pos.exit.order_id
                if self.exit_method == "target":
                    pos.exit = replace(
                        pos.exit,
                        price=last_price - pos.slippage,
                        order_type="LMT",
                        trigger_price=0.0,
                    )
                else:
                    pos.exit = replace(
                        pos.exit,
                        price=pos.stop_price - pos.slippage,
                        order_type="LMT",
                        trigger_price=0.0,
                    )
                self.broker.order_modify(order_id=order_id, **_get_args(pos.exit))
                self.next_fn = "cancel"
        except Exception as e:
            logging.error(f"Modify Trade {order_id}: {e} @ {last_price}")
        finally:
            return pos

    def cancel(self, pos, last_price):
        try:
            order_id = pos.exit.order_id
            self.broker.order_cancel(order_id=pos.exit.order_id)
            self.next_fn = "final_exit"
        except Exception as e:
            logging.error(f"Cancel Trade {order_id}: {e} @ {last_price}")
        finally:
            return pos

    def final_exit(self, pos, last_price):
        try:
            price = last_price - pos.slippage
            pos.exit = replace(self.template, price=price, side="S")
            pos.exit.order_id = self.broker.order_place(**_get_args(pos.exit))
            if pos.exit.order_id:
                logging.info(f"{pos.state} {pos.entry.order_id} @ {last_price}")
                pos.state = (
                    "target_reached" if pos.state == "target_pending" else "stop_hit"
                )
                self.next_fn = "do_nothing"
        except Exception as e:
            logging.error(f"Final exit: {e} order id {pos.exit.order_id}")
        finally:
            return pos

    def do_nothing(self, pos, last_price):
        logging.info(
            f"{pos.symbol} with status: {pos.state} @{last_price=} waiting for cleanup"
        )
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
        exit_method="target",
        target=None,
        trail_percent=None,
    ) -> int | None:

        pos = Position(
            symbol=symbol,
            quantity=quantity,
            stop_price=stop_loss,
            target_price=target,
            trail_percent=trail_percent,
            slippage=2.0,
        )
        executor = executors.get(exchange, NFOManager)

        # init an exchange executor instance
        pos.ex = executor(
            broker=self.stock_broker, pos=pos, tag=tag, exit_method=exit_method
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
    ) -> str:
        pos = self._positions.get(pos_id, None)

        if not pos:
            return "position_unknown"

        elif pos.state == "entry_pending":
            order = next(
                (o for o in orders if o.get("order_id") == pos.entry.order_id), None
            )
            if order:
                pos.average_price = float(order["fill_price"])

                if pos.trail_percent is not None and not isinstance(
                    pos.trail_percent, (int, float, str)
                ):
                    logging.warning(
                        f"Invalid trail_percent type: {type(pos.trail_percent)}"
                    )
                    # Skip trailing logic if it's a mock or invalid
                elif pos.trail_percent is not None:
                    # Use pos instead of self
                    tp_str = str(pos.trail_percent).strip("%")
                    try:
                        trail_val = float(tp_str) / 100
                        dist = abs(pos.average_price - pos.stop_price)
                        pos.stop_price = round_down_to_tick(
                            pos.stop_price + (dist * trail_val)
                        )
                    except ValueError:
                        logging.error(f"Could not convert trail_percent: {tp_str}")

        if pos.state == "exit_pending":
            order = next(
                (o for o in orders if o.get("order_id") == pos.exit.order_id), None
            )
            if order:
                pos.state = "stop_hit"

            else:
                is_target = last_price > pos.target_price if pos.target_price else False
                is_stop = last_price < pos.stop_price or removable
                if is_target or is_stop:
                    pos.state = "target_pending" if is_target else "stop_pending"

        elif pos.state in [
            "target_pending",
            "stop_pending",
        ]:
            order = next(
                (o for o in orders if o.get("order_id") == pos.exit.order_id), None
            )
            if order:
                pos.state = "target_reached" if "target_pending" else "stop_hit"

        elif pos.state in [
            "target_reached",
            "stop_hit",
        ]:
            self._cleanup(pos_id)
            return pos.state

        logging.info(
            f"position - {pos.state} stop:{pos.stop_price} < {last_price=} < target:{pos.target_price}"
        )
        self._positions[pos_id] = getattr(pos.ex, pos.ex.next_fn)(pos, last_price)
        return pos.state

    def _cleanup(self, pos_id):
        if pos_id in self._positions:
            logging.info(f"PM: Removing tracker for position {pos_id}")
            del self._positions[pos_id]
