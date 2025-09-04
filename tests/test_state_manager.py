import pytest
from src.state_manager import StateManager

# Use a pytest fixture to reset the StateManager's class-level state
# before each test. This ensures that tests are isolated and do not
# affect each other.
@pytest.fixture(autouse=True)
def reset_state_manager():
    """Resets the StateManager's internal state before each test."""
    StateManager._state = {}

def test_initialize_prefix():
    """
    Test the `initialize_prefix` method.
    It should correctly initialize the state for a new prefix with default values.
    """
    prefix = "TEST_NIFTY"
    StateManager.initialize_prefix(prefix)
    state = StateManager._state.get(prefix)
    
    assert state is not None
    assert state["is_in_trade"] is False
    assert state["CE"]["count"] == 0
    assert state["PE"]["count"] == 0
    assert state["CE"]["idx"] == 1000
    assert state["PE"]["idx"] == -1
    
def test_start_trade():
    """
    Test the `start_trade` method.
    It should set `is_in_trade` to True and increment the trade count.
    """
    prefix = "TEST_BANKNIFTY"
    option_type = "CE"
    StateManager.start_trade(prefix, option_type)
    
    assert StateManager.is_in_trade(prefix, "PE") is True
    assert StateManager._state[prefix][option_type]["count"] == 1
    
    # Test starting another trade of the same type
    StateManager.start_trade(prefix, option_type)
    assert StateManager._state[prefix][option_type]["count"] == 2
    
def test_end_trade():
    """
    Test the `end_trade` method.
    It should set `is_in_trade` to False and reset the count of the other option type.
    """
    prefix = "TEST_FINNIFTY"
    
    # Simulate a trade being in progress
    StateManager.start_trade(prefix, "PE")
    assert StateManager.is_in_trade(prefix, "CE") is True
    
    # End the trade
    StateManager.end_trade(prefix, "CE")
    
    assert StateManager.is_in_trade(prefix, "PE") is False
    assert StateManager._state[prefix]["CE"]["count"] == 0
    assert StateManager._state[prefix]["PE"]["count"] == 1
    
def test_is_in_trade():
    """
    Test the `is_in_trade` method.
    It should return True if a trade is in progress, False otherwise.
    """
    prefix = "TEST_SENSEX"
    
    # Initially, no trade is in progress
    assert StateManager.is_in_trade(prefix, "CE") is False
    
    # Start a trade
    StateManager.start_trade(prefix, "CE")
    assert StateManager.is_in_trade(prefix, "PE") is True
    
    # End the trade
    StateManager.end_trade(prefix, "CE")
    assert StateManager.is_in_trade(prefix, "PE") is False

def test_is_max_trade_reached():
    """
    Test the `is_max_trade_reached` method.
    It should return True when the maximum trade count is reached.
    """
    prefix = "TEST_MIDCPNIFTY"
    
    # Simulate trades until the max is reached
    for _ in range(StateManager._max_trades):
        assert not StateManager.is_max_trade_reached(prefix, "CE")
        StateManager.start_trade(prefix, "CE")
    
    # The last trade should make the condition True
    assert StateManager.is_max_trade_reached(prefix, "CE") is True
    
    # Test the other option type
    assert StateManager.is_max_trade_reached(prefix, "PE") is False
    
def test_set_get_idx():
    """
    Test the `set_idx` and `get_idx` methods.
    It should correctly set and retrieve the index for each option type.
    """
    prefix = "TEST_NIFTY"
    
    # Test setting and getting CE index
    ce_idx = 500
    StateManager.set_idx(prefix, "CE", ce_idx)
    assert StateManager.get_idx(prefix, "CE") == ce_idx
    
    # Test setting and getting PE index
    pe_idx = 120
    StateManager.set_idx(prefix, "PE", pe_idx)
    assert StateManager.get_idx(prefix, "PE") == pe_idx
    
    # Ensure CE index remains unchanged
    assert StateManager.get_idx(prefix, "CE") == ce_idx
