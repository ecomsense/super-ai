from dataclasses import dataclass
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
