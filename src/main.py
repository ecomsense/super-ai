# main.py
from src.constants import logging, S_SETG, TradeSet, yml_to_obj, get_symbol_fm_factory

from src.sdk.helper import Helper
from src.core.build import Builder
from src.core.strategy import StrategyMaker, Engine

from toolkit.kokoo import is_time_past, blink
from traceback import print_exc


def login_and_get_settings():
    O_SETG = yml_to_obj(S_SETG)
    logging.info(O_SETG)

    O_TRADESET = TradeSet().read()
    if O_TRADESET and any(O_TRADESET):
        trade_settings = O_TRADESET.get("trade", None)
        if not trade_settings:
            logging.info(f"you have exhausted all strategies to run in {O_TRADESET}")
            __import__("sys").exit(1)

    logging.info(f"WAITING: till Algo start time {O_SETG['start']}")
    while not is_time_past(O_SETG["start"]):
        blink()

    return O_TRADESET


def main():
    try:
        O_TRADESET = login_and_get_settings()
        trade_settings = O_TRADESET.pop("trade", None)
        dct_sym = get_symbol_fm_factory()

        # login to broker api
        Helper.api()
        builder = Builder()
        tokens = builder.merge_settings_and_symbols(
            user_settings=O_TRADESET, dct_sym=dct_sym
        )
        tradingsymbols = builder.find_fno_tokens(symbols_to_trade=tokens)
        logging.info(f"tokens for trading: {tokens}")
        logging.info(f"tradingsymbol: {tradingsymbols}")

        trade_start = trade_settings["start"]
        logging.info(f"WAITING: till trade start time {trade_start=}")
        while not is_time_past(trade_start):
            blink()

        # make strategy object for each symbol selected
        strategy_name = trade_settings["strategy"]
        logging.info(f"BUILDING: {strategy_name}")
        strategies = StrategyMaker(
            tokens_for_all_trading_symbols=tokens,
            symbols_to_trade=tradingsymbols,
        ).create(strategy_name)

        engine = Engine(strategies=strategies, trade_stop=trade_settings["stop"])
        engine.run(strategy_name)
    except Exception as e:
        logging.error(f"main: {e}")
        print_exc()


if __name__ == "__main__":
    main()
