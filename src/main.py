# main.py
from src.constants import logging, S_SETG, TradeSet, yml_to_obj

from src.sdk.helper import Helper
from src.core.build import Builder  # Import the new builder

from toolkit.kokoo import is_time_past, blink, kill_tmux
from traceback import print_exc


def main():
    try:
        O_SETG = yml_to_obj(S_SETG)
        print(O_SETG)
        logging.info(f"WAITING: till Algo start time {O_SETG['start']}")
        while not is_time_past(O_SETG["start"]):
            blink()

        # login to broker api
        Helper.api()

        O_TRADESET = TradeSet().read()

        if isinstance(O_TRADESET, dict):
            trade_settings = O_TRADESET.pop("trade")

            # Initialize the StrategyBuilder from settings
            logging.info(f"BUILDING: {trade_settings['strategy']}")

            builder = Builder(
                user_settings=O_TRADESET, strategy_name=trade_settings["strategy"]
            )
            # StrategyBuilder has already populated Helper.tokens_for_all_trading_symbols
            # and retrieved symbols_to_trade during its initialization.

            strgy_to_be_removed = []
            # make strategy object for each symbol selected
            strategies: list = builder.create_strategies()

            trade_start = trade_settings["start"]
            logging.info(f"WAITING: till trade start time {trade_start=}")
            while not is_time_past(trade_start):
                blink()

            while strategies and (not is_time_past(trade_settings["stop"])):
                for strgy in strategies:
                    # Get the run arguments dynamically from the builder
                    run_args = builder.get_run_arguments(strgy)

                    # Add strategy-specific run arguments that depend on loop state
                    if builder.strategy_name == "openingbalance":
                        resp = strgy.run(
                            *run_args,
                            strgy_to_be_removed,
                        )
                        if resp == strgy._prefix:
                            strgy_to_be_removed.append(resp)
                    else:
                        resp = strgy.run(
                            *run_args
                        )  # Pass the dynamically generated args

                    # logging.info(f"main: {strgy._fn}")

                strategies = [strgy for strgy in strategies if not strgy._removable]
            else:
                logging.info(
                    f"main: exit initialized because we are past trade stop time {trade_settings['stop']}"
                )
                orders = Helper._rest.orders()
                for item in orders:
                    if (item["status"] == "OPEN") or (
                        item["status"] == "TRIGGER_PENDING"
                    ):
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
