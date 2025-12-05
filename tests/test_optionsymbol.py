# File: tests/test_optionsymbol.py

# Assuming your concrete class is named OptionSymbol
# and is located in src/sdk/symbol.py
from src.sdk.symbol import OptionSymbol


def test_option_symbol_creation_and_attributes():
    """
    Tests the instantiation of the concrete OptionSymbol class
    and verifies that all attributes are set correctly.
    """

    # 1. Input Data (taken from the previously failing test)
    test_params = {
        "base": "SENSEX",
        "symbol": "BSXOPT",
        "option_exchange": "BFO",
        "moneyness": -1,
        "expiry": "05-AUG-2025",
        "quantity": 20,
        "rest_min": 2,
        "diff": 100,
        "index": "BSE Sensex",
        "exchange": "BSE",
        "token": "1",
        "depth": 10,
        "atm": 81000,
    }

    # 2. Instantiate the concrete class
    # Use the **kwargs syntax for cleaner instantiation
    option_sym = OptionSymbol(**test_params)

    # 3. Assertions (Verifying the created object)

    # Check that the object is of the correct type
    assert isinstance(option_sym, OptionSymbol)

    # Check that the object's attributes match the input data
    assert option_sym.base == "SENSEX"
    assert option_sym.symbol == "BSXOPT"
    assert option_sym.expiry == "05-AUG-2025"
    assert option_sym.quantity == 20
    assert option_sym.atm == 81000
    assert option_sym.token == "1"

    # Optional: If OptionSymbol has methods, you can test them here,
    # e.g., assert option_sym.get_value() == expected_value
