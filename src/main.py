# main.py
from src.constants import logging, S_SETG, TradeSet, yml_to_obj, get_symbol_fm_factory

from src.sdk.helper import Helper
from src.core.build import Builder
from src.core.strategy import StrategyMaker, Engine

from toolkit.kokoo import is_time_past, blink
from traceback import print_exc


def build_symbol_and_settings():
    O_SETG = yml_to_obj(S_SETG)
    logging.info(O_SETG)

    logging.info(f"WAITING: till Algo start time {O_SETG['start']}")
    while not is_time_past(O_SETG["start"]):
        blink()

    # login to broker api
    Helper.api()

    O_TRADESET = TradeSet().read()
    if O_TRADESET and any(O_TRADESET):
        trade_settings = O_TRADESET.pop("trade", None)
        if not trade_settings:
            logging.info(f"you have exhausted all strategies to run in {O_TRADESET}")
            __import__("sys").exit(1)

        dct_sym = get_symbol_fm_factory()

        builder = Builder(
            user_settings=O_TRADESET,
            dct_sym=dct_sym,
        )
        # StrategyBuilder has already populated Helper.tokens_for_all_trading_symbols
        # and retrieved symbols_to_trade during its initialization.
        #
        tokens = builder.tokens_for_all_trading_symbols
        tradingsymbols = builder.symbols_to_trade
        logging.info(f"tokens for trading: {tokens}")
        logging.info(f"tradingsymbol: {tradingsymbols}")
        return trade_settings, tokens, tradingsymbols


def main():
    try:
        trade_settings, tokens, tradingsymbols = build_symbol_and_settings()
        # Initialize the StrategyBuilder from settings
        logging.info(f"BUILDING: {trade_settings['strategy']}")

        trade_start = trade_settings["start"]
        logging.info(f"WAITING: till trade start time {trade_start=}")

        while not is_time_past(trade_start):
            blink()

        # make strategy object for each symbol selected
        strgy = StrategyMaker(
            tokens_for_all_trading_symbols=tokens,
            symbols_to_trade=tradingsymbols,
        )
        strategy_name = trade_settings["strategy"]
        strategies: list = strgy.create(strategy_name=strategy_name)

        engine = Engine(strategies=strategies, trade_stop=trade_settings["stop"])
        engine.run(strategy_name)
    except Exception as e:
        logging.error(f"main: {e}")
        print_exc()


if __name__ == "__main__":
    main()
