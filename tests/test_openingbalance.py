from src.strategies.openingbalance import BreakoutState, Openingbalance
from toolkit.fileutils import Fileutils


def flatten_no_rename(d, result=None):
    if result is None:
        result = {}

    for k, v in d.items():
        if isinstance(v, dict):
            # Recurse into the dictionary
            flatten_no_rename(v, result)
        else:
            # Assign the value to the flat result
            result[k] = v
    return result


def get_settings(strategy_name):
    return flatten_no_rename(
        Fileutils().read_file("./factory/" + strategy_name + ".yml")
    )


def test_ob_initialization(strategy_factory):
    strat = strategy_factory(Openingbalance, get_settings("openingbalance"))

    assert strat._stop == 100.0  # From mock_rest.history
    assert strat._fn == "wait_for_breakout"
