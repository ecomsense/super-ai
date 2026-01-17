# src/main.py
from src.constants import (
    logging_func,
    S_SETG,
    TradeSet,
    yml_to_obj,
    get_symbol_fm_factory,
)

from src.sdk.helper import Helper
from src.core.build import Builder
from src.core.strategy import StrategyMaker
from src.core.engine import Engine

from toolkit.kokoo import is_time_past, blink, kill_tmux
from traceback import print_exc

logging = logging_func(__name__)


def read_builders():
    builders = []
    while True:
        O_TRADESET = TradeSet().read()
        if not O_TRADESET or not any(O_TRADESET):
            break

        trade_settings = O_TRADESET.pop("trade")
        builder = Builder(
            trade_settings=trade_settings,
            user_settings=O_TRADESET,
            symbol_factory=get_symbol_fm_factory(),
        )
        builders.append(builder)

    if not any(builders):
        logging.info("you have exhausted all strategies to run")
        __import__("sys").exit(1)

    return builders


def main():
    try:
        # read common start time and stop time
        O_SETG = yml_to_obj(S_SETG)
        engine = Engine(O_SETG["start"], O_SETG["stop"])
        engine.wait_until_start()

        builders = read_builders()

        # login to broker api
        Helper.api()

        rest = Helper._rest
        quote = Helper._quote
        while not is_time_past(engine.stop):
            for builder in builders[:]:
                if builder.can_build():
                    logging.info(f"main: building params for {builder.strategy}")
                    tokens_for_all_trading_symbols = builder.find_fno_tokens()
                    if tokens_for_all_trading_symbols:
                        sgy = StrategyMaker(
                            tokens_for_all_trading_symbols=tokens_for_all_trading_symbols,
                            symbols_to_trade=builder.symbols_to_trade,
                        ).create(
                            strategy_name=builder.strategy,
                            stop_time=builder.stop,
                            quote=quote,
                            rest=rest,
                        )
                        engine.add_strategy(sgy)

                    else:
                        logging.error(
                            f"main: no tokens found, skipping strategy {builder.strategy}"
                        )

                    # make strategy object for each symbol selected
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
