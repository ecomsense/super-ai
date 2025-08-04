# main.py
from src.constants import logging, O_SETG, O_TRADESET
from src.helper import Helper, RestApi
from toolkit.kokoo import is_time_past, blink, kill_tmux
from traceback import print_exc
from src.strategies.strategy import Builder  # Import the new builder


def main():
    try:
        logging.info(f"WAITING: till Algo start time {O_SETG['start']}")
        while not is_time_past(O_SETG["start"]):
            blink()

        trade_settings = O_TRADESET.pop("trade")

        # Initialize the StrategyBuilder with O_SETG
        logging.info(f"BUILDING: {trade_settings['strategy']}")


        # login to broker api
        Helper.api()
        for _, v in O_TRADESET.items():
            v["symbol"] = v.get("symbol", v["base"])

        builder = Builder(user_settings=O_TRADESET, strategy_name=trade_settings["strategy"])
        # StrategyBuilder has already populated Helper.tokens_for_all_trading_symbols
        # and retrieved symbols_to_trade during its initialization.

        # make strategy object for each symbol selected
        strategies: list = builder.create_strategies()

        strgy_to_be_removed = []
        """
        sequence_info = (
            {}
        )  # Keep this in main for now as it seems to be state across strategies
        """
        trade_start = trade_settings["start"]
        logging.info(f"WAITING: till trade start time {trade_start=}")
        while not is_time_past(trade_start):
            blink()

        while strategies and (not is_time_past(trade_settings["stop"])):
            for strgy in strategies:
                #prefix = strgy._prefix

                # Get the run arguments dynamically from the builder
                run_args = builder.get_run_arguments(strgy)

                # Add strategy-specific run arguments that depend on loop state
                if builder.strategy_name == "openingbalance":
                    """
                    sequence_info[strgy._id] = dict(
                        _prefix=prefix,
                        _reduced_target_sequence=strgy._reduced_target_sequence,
                    )
                    """
                    resp = strgy.run(
                        *run_args,
                        strgy_to_be_removed,
                    )
                    if resp == strgy._prefix:
                        strgy_to_be_removed.append(resp)
                else:
                    resp = strgy.run(*run_args)  # Pass the dynamically generated args

                # logging.info(f"{msg} returned {resp}")

            strategies = [strgy for strgy in strategies if not strgy._removable]
        else: 
            orders = Helper._rest.orders()
            for item in orders:
                if (item["status"] == "OPEN") or (
                    item["status"] == "TRIGGER_PENDING"
                ):
                    order_id = item.get("order_id", None)
                    logging.info(f"cancelling open order {order_id}")
                    Helper.api().order_cancel(order_id)

            Helper._rest.close_positions()
    
        kill_tmux()
    except KeyboardInterrupt:
        __import__("sys").exit()
    except Exception as e:
        print_exc()
        logging.error(f"{e} while init")


if __name__ == "__main__":
    main()
