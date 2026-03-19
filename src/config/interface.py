# src/config/interface

from dataclasses import dataclass, field
from typing import Optional, Any
from random import randint


def generate_id():
    # Returns a 6-digit unique identifier for the trade
    return randint(100000, 999999)


@dataclass
class PivotData:
    """
    Runtime state holder for Pivot strategy.
    """

    low: Optional[float] = None
    first_trade_at: Optional[Any] = None


@dataclass(slots=True)
class Trade:
    symbol: Optional[str] = None
    quantity: Optional[int] = None
    disclosed_quantity: Optional[int] = None
    product: str = "M"
    side: Optional[str] = None
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    order_type: Optional[str] = None
    exchange: Optional[str] = None
    tag: Optional[str] = None
    last_price: Optional[float] = None
    filled_price: Optional[float] = None
    status: Optional[str] = None
    order_id: Optional[str] = None


@dataclass(slots=True)
class Position:
    id: int = field(default_factory=generate_id)
    symbol: Optional[str] = None
    entry: Trade = field(default_factory=Trade)
    exit: Trade = field(default_factory=Trade)
    average_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    state: str = "idle"
    slippage: float = 0.0
    trail_percent: Optional[float] = None
    ex: Any = field(init=False, repr=False, default=None)


@dataclass(slots=True)
class OptionData:
    """A dataclass to hold the core attributes of a financial symbol."""

    exchange: str
    base: Optional[str] = None
    symbol: Optional[str] = None
    diff: Optional[int] = None
    depth: Optional[int] = None
    expiry: Optional[str] = None
    token: Optional[str] = None
