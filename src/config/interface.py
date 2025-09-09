from dataclasses import dataclass, field
from typing import Optional


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
    symbol: Optional[str] = None
    entry: Trade = field(default_factory=Trade)
    exit: Trade = field(default_factory=Trade)
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    is_position: bool = True


@dataclass(frozen=True)
class OptionData:
    """A dataclass to hold the core attributes of a financial symbol."""

    exchange: str
    base: Optional[str] = None
    symbol: Optional[str] = None
    diff: Optional[int] = None
    depth: Optional[int] = None
    expiry: Optional[str] = None
    token: Optional[str] = None
