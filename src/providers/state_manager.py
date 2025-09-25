# src/state_manager.py

from src.constants import logging
from threading import Lock
from typing import Dict, Any


class StateManager:
    """
    _state = {"NIFTY": {"is_in_trade": True, "CE": {"idx": 0, "count": 1 }, "PE": {"idx": 1, "count": 1} },
    """

    _state: Dict[str, Any] = {}
    _lock = Lock()
    _max_trades = 5

    @classmethod
    def initialize_prefix(cls, prefix: str):
        with cls._lock:
            if prefix not in cls._state:
                cls._state[prefix] = {
                    "is_traded_once": False,
                    "is_in_trade": False,
                    "CE": {"count": 0, "idx": 1000},
                    "PE": {"count": 0, "idx": -1},
                }
                logging.info(f"Initialized state for prefix '{prefix}'.")

    @classmethod
    def traded_once(cls, prefix: str):
        with cls._lock:
            cls._state[prefix]["is_traded_once"] = True

    @classmethod
    def is_traded_once(cls, prefix: str) -> bool:
        with cls._lock:
            return cls._state[prefix]["is_traded_once"]

    @classmethod
    def start_trade(cls, prefix: str, option_type: str):
        with cls._lock:
            cls._state[prefix]["is_in_trade"] = True
            cls._state[prefix][option_type]["count"] += 1

    @classmethod
    def end_trade(cls, prefix: str, other_option_type: str):
        with cls._lock:
            cls._state[prefix]["is_in_trade"] = False
            cls._state[prefix][other_option_type]["count"] = 0

    @classmethod
    def is_in_trade(cls, prefix: str) -> bool:
        with cls._lock:
            return cls._state[prefix]["is_in_trade"]

    @classmethod
    def get_trade_count(cls, prefix: str, option_type: str) -> int:
        with cls._lock:
            return cls._state[prefix][option_type]["count"]

    @classmethod
    def set_idx(cls, prefix: str, option_type: str, idx: int):
        """Sets the indices for both CE and PE options for a given prefix."""
        with cls._lock:
            cls._state[prefix][option_type]["idx"] = idx
        logging.info(f"SET INDEX: {prefix} {option_type} to {idx}")

    @classmethod
    def get_idx(cls, prefix: str, option_type: str) -> int:
        """Returns the current index for a given option type."""
        with cls._lock:
            return cls._state[prefix][option_type]["idx"]
