# src/main.py
from src.constants import (
    logging_func,
    S_SETG,
    TradeSet,
    yml_to_obj,
    get_symbol_fm_factory,
)

from src.sdk.helper import Helper
from src.core.build import Builder, stuff_atm, stuff_tradingsymbols
from src.core.strategy import create_strategies_from_params
from src.core.engine import Engine

from toolkit.kokoo import is_time_past, blink, kill_tmux
from traceback import print_exc

logging = logging_func(__name__)


def read_builders():
    # login to broker api
    Helper.api()
    quote = Helper._quote
    rest = Helper._rest

    builders = []
    while True:
        logging.debug("reading user trade settings")
        O_TRADESET = TradeSet().read()
        if not O_TRADESET or not any(O_TRADESET):
            break

        trade_settings = O_TRADESET.pop("trade")
        builder = (
            Builder(
                trade_settings=trade_settings,
                user_settings=O_TRADESET,
                quote=quote,
                rest=rest,
            )
            .merge_settings_and_symbols(symbol_factory=get_symbol_fm_factory())
            .find_expiry()
        )
        builders.append(builder)
    return builders


def main():
    try:
        # read common start time and stop time
        O_SETG = yml_to_obj(S_SETG)
        engine = Engine(O_SETG["start"], O_SETG["stop"])
        engine.wait_until_start()

        builders = read_builders()

        rest = Helper._rest
        quote = Helper._quote
        while not is_time_past(engine.stop):
            for builder in builders:
                if builder.can_build():
                    data = stuff_atm(builder._data, builder._meta)
                    lst_of_params = stuff_tradingsymbols(data, builder._meta)
                    strategies = create_strategies_from_params(lst_of_params)
                    engine.add_strategy(strategies)

                    builders.remove(builder)

            engine.tick(rest, quote)

            blink()
        else:
            logging.info(
                f"main: killing tmux because we started after stop time {engine.stop}"
            )
            kill_tmux()

    except KeyboardInterrupt:
        __import__("sys").exit()
    except Exception as e:
        logging.error(f"main: {e}")
        print_exc()


if __name__ == "__main__":
    main()
