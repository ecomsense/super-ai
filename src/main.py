# main.py
from src.constants import logging, S_SETG, TradeSet, yml_to_obj, get_symbol_fm_factory

from src.sdk.helper import Helper
from src.core.build import Builder
from src.core.engine import Engine

from toolkit.kokoo import is_time_past, blink, kill_tmux
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
        trade_settings = O_TRADESET.pop("trade")

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


def get_engine(): ...


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
        engine = Engine(
            strategy_name=trade_settings["strategy"],
            tokens_for_all_trading_symbols=tokens,
            symbols_to_trade=tradingsymbols,
        )
        strgy_to_be_removed = []
        strategies: list = engine.create_strategies()
        while strategies and (not is_time_past(trade_settings["stop"])):
            for strgy in strategies:
                # Get the run arguments dynamically from the builder
                run_args = engine.get_run_arguments()

                # Add strategy-specific run arguments that depend on loop state
                if engine.strategy_name == "openingbalance":
                    resp = strgy.run(
                        *run_args,
                        strgy_to_be_removed,
                    )
                    if resp == strgy._prefix:
                        strgy_to_be_removed.append(resp)
                else:
                    resp = strgy.run(*run_args)  # Pass the dynamically generated args

                # logging.info(f"main: {strgy._fn}")

            strategies = [strgy for strgy in strategies if not strgy._removable]
        else:
            logging.info(
                f"main: exit initialized because we are past trade stop time {trade_settings['stop']}"
            )
            orders = Helper._rest.orders()
            for item in orders:
                if (item["status"] == "OPEN") or (item["status"] == "TRIGGER_PENDING"):
                    order_id = item.get("order_id", None)
                    logging.info(f"cancelling open order {order_id}")
                    Helper.api().order_cancel(order_id)

            Helper._rest.close_positions()

        logging.info(
            f"main: killing tmux because we started after stop time {trade_settings['stop']}"
        )
        kill_tmux()
    except KeyboardInterrupt:
        __import__("sys").exit()
    except Exception as e:
        print_exc()
        logging.error(f"{e} while init")


if __name__ == "__main__":
    main()
