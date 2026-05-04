import logging
import threading
from traceback import print_exc
from typing import Optional
from src.config.interface import Position


class RiskManager:
    def __init__(self, stock_broker):
        self.broker = stock_broker
        self._lock = threading.Lock()
        self._positions = []  # Internal list of Position objects
        self.tag = "no_tag"
        self.slippage = 0.8  # for MCX

    @property
    def positions(self):
        return self._positions

    @positions.setter
    def positions(self, position_book):
        """Convert dict-based position book to Position objects."""
        self._positions = []
        for p in position_book:
            if isinstance(p, dict):
                # Convert dict to Position object
                pos = Position(
                    symbol=p.get("symbol", ""),
                    quantity=p.get("quantity", 0),
                    stop_price=p.get("stop_price", 0),
                    target_price=p.get("target_price", 0),
                )
                # Preserve the id if it exists
                if "id" in p:
                    pos.id = p["id"]
                self._positions.append(pos)
            else:
                # Already a Position object
                self._positions.append(p)

    def _get_pos_from_api(self, symbol: str):
        """Fetches real-time net quantity from the broker."""
        try:
            positions = self.broker.positions
            return next((p for p in positions if p["symbol"] == symbol), {})
        except Exception as e:
            logging.error(f"RM Error fetching positions: {e}")
            return {}

    def _read_position(self, symbol: str):
        """Finds the internal Position object for a symbol."""
        try:
            return next((p for p in self.positions if p.symbol == symbol), None)
        except Exception as e:
            logging.error(f"RM Error reading Positions: {e}")
            return None

    def _write_position(self, symbol: str, quantity: int):
        """Updates the quantity of an existing internal Position object."""
        try:
            pos_obj = self._read_position(symbol)
            if pos_obj:
                pos_obj.quantity = quantity
                logging.debug(
                    f"RM: Internal state updated for {symbol}: Qty {quantity}"
                )
                return pos_obj
        except Exception as e:
            logging.error(f"RM Error writing Position: {e}")

    def new(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        entry_price: float,
        stop_loss: float,
        target: float,
        tag="no_tag",
    ) -> Optional[int]:
        """Executes entry and creates/updates tracking."""
        with self._lock:
            try:
                self.tag = tag

                self.slippage = 1 if exchange == "MCX" else 2

                order_no = self.broker.order_place(
                    symbol=symbol,
                    exchange=exchange,
                    quantity=quantity,
                    side="BUY",
                    order_type="LIMIT",
                    trigger_price=0.0,
                    price=entry_price + self.slippage,
                    disclosed_quantity=0,
                    tag=self.tag,
                    product="NRML" if exchange == "MCX" else "MIS",
                )
                logging.info(f"RM: Buy Order #{order_no} for {symbol} @{entry_price}")

                # 2. Get actual total quantity from Broker
                api_pos = self._get_pos_from_api(symbol)
                total_qty = api_pos.get("quantity", quantity)

                # 3. Handle internal object state
                position = self._read_position(symbol)
                if position is None:
                    # Note: 'slippage' was in your snippet; ensure it's passed or defaulted
                    position = Position(
                        symbol=symbol,
                        quantity=total_qty,
                        stop_price=stop_loss,
                        target_price=target,
                    )
                    self.positions.append(position)
                else:
                    position = self._write_position(symbol, total_qty)

                return position.id

            except Exception as e:
                logging.error(f"RM New Position Error: {e}")
                print_exc()
                return None

    def status(self, pos_id: str, last_price: float) -> int:
        """
        Executes Flattening.
        Called by Ram strategy ONLY when an exit signal (Target/Time) is triggered.
        """
        with self._lock:
            try:
                symbol = next((p.symbol for p in self.positions if p.id == pos_id), None)
                if symbol is not None:
                    api_pos = self._get_pos_from_api(symbol)
                    qty_to_sell = int(api_pos.get("quantity", 0))

                    if qty_to_sell > 0:
                        exchange = api_pos.get("exchange", None)
                        self.slippage = 1 if exchange == "MCX" else 2
                        order_no = self.broker.order_place(
                            symbol=symbol,
                            exchange=exchange,
                            quantity=qty_to_sell,
                            side="SELL",
                            order_type="LIMIT",
                            trigger_price=0.0,
                            price=last_price - self.slippage,
                            disclosed_quantity=0,
                            tag=self.tag,
                            product="NRML" if exchange == "MCX" else "MIS",
                        )
                        logging.info(
                            f"RM: Exit Order #{order_no} for {symbol}. Qty: {qty_to_sell}@{last_price}"
                        )

                        # 4. Zero out the internal position
                        if order_no:
                            self._write_position(symbol, 0)
                            return 0

                        return qty_to_sell
                return -1

            except Exception as e:
                logging.error(f"RM Status (Exit) Error: {e}")
                print_exc()
                return -1
