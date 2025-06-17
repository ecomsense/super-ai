import pytest
import pandas as pd
import os
import re  # re-import needed for symbols.py logic

# Import the Symbols class and dct_sym.
# This assumes you run pytest from your project root directory.
# If 'toolkit' is at the project root, adjust 'src.toolkit.fileutils' accordingly.
# Given your folder structure, it's most likely src/toolkit/fileutils.py or just external library.
# For this test, since we're not mocking Fileutils, we don't need to explicitly import it
# unless we plan to use it to setup test data, which we'll handle with pure pandas/os.
from src.symbols import Symbols, dct_sym


# --- Fixtures ---


@pytest.fixture
def symbols_instance():
    """Provides a Symbols instance for tests."""
    return Symbols(option_exchange="NFO", base="BANKNIFTY", expiry="26JUN24")


@pytest.fixture
def sample_quotes_dict():
    """Provides a sample quotes dictionary for find_closest_premium and calc_straddle_value."""
    return {
        "BANKNIFTY26JUN24C50000": 150.0,
        "BANKNIFTY26JUN24P50000": 200.0,
        "BANKNIFTY26JUN24C50100": 100.0,
        "BANKNIFTY26JUN24P50100": 250.0,
        "BANKNIFTY26JUN24C49900": 200.0,
        "BANKNIFTY26JUN24P49900": 150.0,
        "NIFTY26JUN24C22000": 50.0,  # Irrelevant symbol for some tests
    }


@pytest.fixture
def test_symbol_csv_path(tmp_path):
    """
    Creates a dummy CSV file in a temporary 'data' directory for testing get_tokens.
    This replaces the need for mocking pd.read_csv by providing a real, controlled file.
    """
    # Create a dummy 'data' directory inside the temporary path
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)

    csv_file_path = data_dir / "NFO_symbols.csv"

    # Create a DataFrame with relevant data
    data = {
        "Token": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
        "TradingSymbol": [
            "BANKNIFTY26JUN24C50000",
            "BANKNIFTY26JUN24P50000",
            "BANKNIFTY26JUN24C50100",  # strike + 1*diff
            "BANKNIFTY26JUN24P50100",  # strike + 1*diff
            "BANKNIFTY26JUN24C49900",  # strike - 1*diff
            "BANKNIFTY26JUN24P49900",  # strike - 1*diff
            "BANKNIFTY26JUN24C50200",  # strike + 2*diff
            "BANKNIFTY26JUN24P50200",  # strike + 2*diff
            "BANKNIFTY26JUN24C49800",  # strike - 2*diff
            "BANKNIFTY26JUN24P49800",  # strike - 2*diff
            "NIFTY26JUN24C22000",  # other symbol
            "NIFTY26JUN24P22000",  # other symbol
        ],
        "Exchange": ["NFO"] * 12,
        "Expiry": ["26JUN24"] * 12,
        "OptionType": ["C", "P", "C", "P", "C", "P", "C", "P", "C", "P", "C", "P"],
        "StrikePrice": [
            50000,
            50000,
            50100,
            50100,
            49900,
            49900,
            50200,
            50200,
            49800,
            49800,
            22000,
            22000,
        ],
    }
    pd.DataFrame(data).to_csv(csv_file_path, index=False)

    yield str(csv_file_path)


# --- Tests ---


def test_init(symbols_instance):
    """Test the constructor."""
    assert symbols_instance._option_exchange == "NFO"
    assert symbols_instance._base == "BANKNIFTY"
    assert symbols_instance.expiry == "26JUN24"
    # The csvfile path will still be relative here, but for test_get_tokens
    # we'll explicitly change it to the temporary path.
    assert symbols_instance.csvfile == "../data/NFO_symbols.csv"


def test_get_atm(symbols_instance):
    """Test get_atm function."""
    # Test for NIFTY
    symbols_instance._base = "NIFTY"
    assert symbols_instance.get_atm(19876) == 19900
    assert symbols_instance.get_atm(19924) == 19900
    assert symbols_instance.get_atm(19925) == 19950  # Exactly halfway, should go up
    assert symbols_instance.get_atm(19974) == 19950

    # Test for BANKNIFTY
    symbols_instance._base = "BANKNIFTY"
    assert symbols_instance.get_atm(45321) == 45300
    assert symbols_instance.get_atm(45350) == 45400  # Exactly halfway, should go up
    assert symbols_instance.get_atm(45349) == 45300


def test_get_tokens(symbols_instance, test_symbol_csv_path):
    """
    Test get_tokens function by providing a pre-existing, controlled CSV file.
    This avoids mocking pd.read_csv directly.
    """
    # Override the csvfile path of the instance to point to our temporary test file
    symbols_instance.csvfile = test_symbol_csv_path

    strike = 50000

    # Define expected tokens based on dct_sym["BANKNIFTY"]["depth"] (which is 25)
    # and the sample data created in test_symbol_csv_path.
    # The sample data provides tokens for strike +/- 0, 1, 2 * diff.
    # So for depth 25, it will attempt to find more, but only these will exist in the dummy file.
    expected_tokens = {
        "NFO|1": "BANKNIFTY26JUN24C50000",
        "NFO|2": "BANKNIFTY26JUN24P50000",
        "NFO|3": "BANKNIFTY26JUN24C50100",
        "NFO|4": "BANKNIFTY26JUN24P50100",
        "NFO|5": "BANKNIFTY26JUN24C49900",
        "NFO|6": "BANKNIFTY26JUN24P49900",
        "NFO|7": "BANKNIFTY26JUN24C50200",
        "NFO|8": "BANKNIFTY26JUN24P50200",
        "NFO|9": "BANKNIFTY26JUN24C49800",
        "NFO|10": "BANKNIFTY26JUN24P49800",
    }

    result = symbols_instance.get_tokens(strike)
    assert result == expected_tokens


def test_find_closest_premium_found(symbols_instance, sample_quotes_dict):
    """Test find_closest_premium when a closest symbol is found."""
    premium_to_find = 155.0
    contains_str = "C"  # Looking for Call options
    # BANKNIFTY26JUN24C50000 (150.0) is closer than BANKNIFTY26JUN24C50100 (100.0)
    # Difference for C50000: |150 - 155| = 5
    # Difference for C50100: |100 - 155| = 55
    # Difference for C49900: |200 - 155| = 45
    expected_symbol = "BANKNIFTY26JUN24C50000"
    result = symbols_instance.find_closest_premium(
        sample_quotes_dict, premium_to_find, contains_str
    )
    assert result == expected_symbol


def test_find_closest_premium_not_found(symbols_instance, sample_quotes_dict):
    """Test find_closest_premium when no matching symbol is found."""
    premium_to_find = 10.0
    contains_str = "XX"  # No such option type
    result = symbols_instance.find_closest_premium(
        sample_quotes_dict, premium_to_find, contains_str
    )
    assert result is None  # Should return None if no match


def test_find_closest_premium_empty_quotes(symbols_instance):
    """Test find_closest_premium with an empty quotes dictionary."""
    result = symbols_instance.find_closest_premium({}, 100.0, "C")
    assert result is None


def test_find_symbol_in_moneyness_ce_itm(symbols_instance):
    """Test find_symbol_in_moneyness for Call ITM."""
    symbols_instance._base = "BANKNIFTY"  # Ensure base is set for diff calculation
    tradingsymbol = "BANKNIFTY26JUN24C50000"
    result = symbols_instance.find_symbol_in_moneyness(tradingsymbol, "C", "ITM")
    assert result == "BANKNIFTY26JUN24C49900"


def test_find_symbol_in_moneyness_ce_otm(symbols_instance):
    """Test find_symbol_in_moneyness for Call OTM."""
    symbols_instance._base = "BANKNIFTY"
    tradingsymbol = "BANKNIFTY26JUN24C50000"
    result = symbols_instance.find_symbol_in_moneyness(tradingsymbol, "C", "OTM")
    assert result == "BANKNIFTY26JUN24C50100"


def test_find_symbol_in_moneyness_pe_itm(symbols_instance):
    """Test find_symbol_in_moneyness for Put ITM."""
    symbols_instance._base = "BANKNIFTY"
    tradingsymbol = "BANKNIFTY26JUN24P50000"
    result = symbols_instance.find_symbol_in_moneyness(tradingsymbol, "P", "ITM")
    assert result == "BANKNIFTY26JUN24P50100"


def test_find_symbol_in_moneyness_pe_otm(symbols_instance):
    """Test find_symbol_in_moneyness for Put OTM."""
    symbols_instance._base = "BANKNIFTY"
    tradingsymbol = "BANKNIFTY26JUN24P50000"
    result = symbols_instance.find_symbol_in_moneyness(tradingsymbol, "P", "OTM")
    assert result == "BANKNIFTY26JUN24P49900"


def test_calc_straddle_value(symbols_instance, sample_quotes_dict):
    """Test calc_straddle_value."""
    atm_strike = 50000
    # From sample_quotes_dict: BANKNIFTY26JUN24C50000 = 150.0, BANKNIFTY26JUN24P50000 = 200.0
    expected_value = 150.0 + 200.0
    result = symbols_instance.calc_straddle_value(atm_strike, sample_quotes_dict)
    assert result == expected_value


def test_calc_straddle_value_missing_key(symbols_instance, sample_quotes_dict):
    """Test calc_straddle_value when a key is missing."""
    # Create a quotes dict where one of the straddle legs is missing
    quotes_missing_pe = {
        "BANKNIFTY26JUN24C50000": 150.0,
        # "BANKNIFTY26JUN24P50000" is missing
    }
    atm_strike = 50000
    with pytest.raises(KeyError):  # Expect a KeyError because the key won't be found
        symbols_instance.calc_straddle_value(atm_strike, quotes_missing_pe)


def test_find_option_type_call(symbols_instance):
    """Test find_option_type for a Call option."""
    result = symbols_instance.find_option_type("BANKNIFTY26JUN24C50000")
    assert result == "C"


def test_find_option_type_put(symbols_instance):
    """Test find_option_type for a Put option."""
    result = symbols_instance.find_option_type("BANKNIFTY26JUN24P50000")
    assert result == "P"


def test_find_option_type_invalid(symbols_instance):
    """Test find_option_type for an invalid trading symbol."""
    result = symbols_instance.find_option_type("INVALID_SYMBOL")
    assert result is False


def test_find_option_by_distance_call(symbols_instance):
    """Test find_option_by_distance for a Call option."""
    atm = 50000
    distance = 1  # One strike away
    c_or_p = "C"
    # Create a minimal dct_symbols for this specific test case
    dct_symbols = {
        "NFO|1": "BANKNIFTY26JUN24C50000",
        "NFO|3": "BANKNIFTY26JUN24C50100",  # This is the target for C, distance 1
        "NFO|5": "BANKNIFTY26JUN24C49900",
    }
    expected_match = {"symbol": "BANKNIFTY26JUN24C50100", "token": "3"}
    result = symbols_instance.find_option_by_distance(
        atm, distance, c_or_p, dct_symbols
    )
    assert result == expected_match


def test_find_option_by_distance_put(symbols_instance):
    """Test find_option_by_distance for a Put option."""
    atm = 50000
    distance = 1
    c_or_p = "P"
    # Create a minimal dct_symbols for this specific test case
    dct_symbols = {
        "NFO|2": "BANKNIFTY26JUN24P50000",
        "NFO|4": "BANKNIFTY26JUN24P50100",
        "NFO|6": "BANKNIFTY26JUN24P49900",  # This is the target for P, distance 1
    }
    expected_match = {"symbol": "BANKNIFTY26JUN24P49900", "token": "6"}
    result = symbols_instance.find_option_by_distance(
        atm, distance, c_or_p, dct_symbols
    )
    assert result == expected_match


def test_find_option_by_distance_not_found(symbols_instance, capsys):
    """Test find_option_by_distance when option is not found, checking print output."""
    atm = 50000
    distance = 100  # Very far distance, unlikely to exist
    c_or_p = "C"
    dct_symbols = {}  # Empty dict to simulate not found

    # We call the method and then check its return value and the printed output.
    result = symbols_instance.find_option_by_distance(
        atm, distance, c_or_p, dct_symbols
    )
    assert result is None  # Should return None if not found and exception is handled

    # Capture stdout to check the print statement
    captured = capsys.readouterr()
    assert "Option not found while find_option_by_distance" in captured.out
