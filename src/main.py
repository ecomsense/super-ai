# main.py
from src.constants import (
    logging_func,
    S_SETG,
    TradeSet,
    yml_to_obj,
    get_symbol_fm_factory,
)

from src.sdk import symbol
from src.sdk.helper import Helper
from src.core.build import Builder, find_fno_tokens
from src.core.strategy import StrategyMaker
from src.core.engine import Engine

from toolkit.kokoo import is_time_past, blink, kill_tmux
from traceback import print_exc

logging = logging_func(__name__)


def read_engine_settings():
    O_SETG = yml_to_obj(S_SETG)
    logging.info(O_SETG)
    logging.info(f"WAITING: till Engine start time {O_SETG['start']}")
    while not is_time_past(O_SETG["start"]):
        blink()
    return O_SETG["stop"]


def read_trade_settings():
    lst = []
    Flag = True
    while Flag:
        O_TRADESET = TradeSet().read()
        if O_TRADESET and any(O_TRADESET):
            trade_settings = O_TRADESET.pop("trade")
            builder = Builder()
            symbol_to_trade = builder.merge_settings_and_symbols(
                user_settings=O_TRADESET, dct_sym=get_symbol_fm_factory()
            )
            symbol_to_trade = builder.find_expiry(symbol_to_trade)
            item = (trade_settings, symbol_to_trade)
            lst.append(item)
        else:
            Flag = False

    if any(lst):
        return lst
    logging.info("you have exhausted all strategies to run")
    __import__("sys").exit(1)


def main():
    try:
        # read common start time and stop time
        engine_stop = read_engine_settings()
        engine = Engine()

        merged_settings = read_trade_settings()

        # login to broker api
        Helper.api()

        while not is_time_past(engine_stop):
            for item in merged_settings[:]:

                trade_settings, symbol_to_trade = item

                if is_time_past(trade_settings["start"]):
                    missing_token = find_fno_tokens(symbols_to_trade=symbol_to_trade)
                    logging.debug(f"missing token: {missing_token}")

                    # make strategy object for each symbol selected
                    sgy = StrategyMaker(
                        tokens_for_all_trading_symbols=missing_token,
                        symbols_to_trade=symbol_to_trade,
                    ).create(trade_settings["strategy"])

                    engine.add_strategy(sgy)
                    merged_settings.remove(item)

            engine.tick()

            blink()
        else:
            logging.info(
                f"main: killing tmux because we started after stop time {engine_stop}"
            )
            kill_tmux()

    except KeyboardInterrupt:
        __import__("sys").exit()
    except Exception as e:
        logging.error(f"main: {e}")
        print_exc()


if __name__ == "__main__":
    main()
