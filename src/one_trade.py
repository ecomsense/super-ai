from src.constants import logging
from threading import Lock
from typing import List, Dict, Any

class OneTrade:
    """
    Manages the trade state for multiple prefixes using a class-level dictionary.
    The state tracks both a full history of traded symbols and the currently
    active symbols for each prefix.
    """
    # The class-level dictionary to hold the state for all prefixes
    _state: Dict[str, Any] = {
        "traded_once": []
    }
    # A class-level lock to prevent race conditions when modifying the state
    _lock = Lock()

    @classmethod
    def add(cls, prefix: str, tradingsymbol: str):
        """
        Adds a new trading symbol to the state in an atomic operation.
        
        This method performs two actions:
        1. Adds the tradingsymbol to the 'traded_once' list if it's not already there.
        2. Adds the tradingsymbol to the list for its specific prefix.
        
        Args:
            prefix: The market prefix (e.g., "NIFTY", "SENSEX").
            tradingsymbol: The specific trading symbol to add (e.g., "24JUN25CE26000").
        """
        with cls._lock:
            # 1. Add to the 'traded_once' list if not present
            if tradingsymbol not in cls._state["traded_once"]:
                cls._state["traded_once"].append(tradingsymbol)
                logging.info(f"Added '{tradingsymbol}' to traded_once history.")
            
            # 2. Add to the prefix's list
            if prefix not in cls._state:
                cls._state[prefix] = []
            
            if tradingsymbol not in cls._state[prefix]:
                cls._state[prefix].append(tradingsymbol)
                logging.info(f"Added '{tradingsymbol}' to active trades for '{prefix}'.")
            else:
                logging.warning(f"Symbol '{tradingsymbol}' is already an active trade for '{prefix}'.")

    @classmethod
    def remove(cls, prefix: str, tradingsymbol: str):
        """
        Removes a specific trading symbol from its active prefix list in an
        atomic operation.
        
        Args:
            prefix: The market prefix.
            tradingsymbol: The specific trading symbol to remove.
        """
        with cls._lock:
            if prefix in cls._state and tradingsymbol in cls._state[prefix]:
                cls._state[prefix].remove(tradingsymbol)
                logging.info(f"Removed '{tradingsymbol}' from active trades for '{prefix}'.")
            else:
                logging.warning(f"Attempted to remove non-existent symbol '{tradingsymbol}' from '{prefix}'.")

    @classmethod
    def is_traded_once(cls, tradingsymbol: str) -> bool:
        """
        Checks if a specific tradingsymbol has ever been traded.
        
        Args:
            tradingsymbol: The symbol to check.
        
        Returns:
            True if the symbol is in the traded_once list, False otherwise.
        """
        return tradingsymbol in cls._state["traded_once"]

    @classmethod
    def is_prefix_in_trade(cls, prefix: str) -> bool:
        """
        Checks if the list of active trades for a given prefix is not empty.
        
        Args:
            prefix: The prefix to check.
        
        Returns:
            True if there are active trades for the prefix, False otherwise.
        """
        return prefix in cls._state and len(cls._state[prefix]) > 0

    @classmethod
    def get_state(cls) -> Dict[str, Any]:
        """
        Returns the entire class-level state for debugging or inspection.
        """
        return cls._state

if __name__ == "__main__":
    # Example usage
    
    # Add an initial CE trade for NIFTY
    print("--- Adding first trades ---")
    OneTrade.add("NIFTY", "24JUN25CE26000")
    OneTrade.add("SENSEX", "24JUN25PE75000")
    
    print("\n--- Checking states after adding ---")
    # Both symbols should be in the traded_once history
    print(f"Has NIFTY CE been traded before? {OneTrade.is_traded_once('24JUN25CE26000')}")
    print(f"Is NIFTY currently in trade? {OneTrade.is_prefix_in_trade('NIFTY')}")
    print(f"Is SENSEX currently in trade? {OneTrade.is_prefix_in_trade('SENSEX')}")
    print(f"Is BANKNIFTY currently in trade? {OneTrade.is_prefix_in_trade('BANKNIFTY')}")
    
    print("\n--- Adding a second trade to NIFTY ---")
    OneTrade.add("NIFTY", "24JUN25PE25000")
    print(f"Current NIFTY trades: {OneTrade.get_state().get('NIFTY')}")
    
    print("\n--- Removing a trade ---")
    # Simulate a stop-loss on the PE position
    OneTrade.remove("NIFTY", "24JUN25PE25000")
    print(f"State after removing NIFTY PE: {OneTrade.get_state().get('NIFTY')}")
    
    print("\n--- Final state after all operations ---")
    print(f"Final state: {OneTrade.get_state()}")
