# main.py
from src.constants import logging, O_SETG
from src.helper import Helper
from toolkit.kokoo import is_time_past, blink, kill_tmux
from traceback import print_exc
from src.strategies.strategy import Builder  # Import the new builder


def main():
    try:
        logging.info(f"WAITING: till {O_SETG['trade']['start']}")
        while not is_time_past(O_SETG["trade"]["start"]):
            blink()

        # login to broker api
        Helper.api()

        # Initialize the StrategyBuilder with O_SETG
        builder = Builder(O_SETG)
        # StrategyBuilder has already populated Helper.tokens_for_all_trading_symbols
        # and retrieved symbols_to_trade during its initialization.

        # make strategy object for each symbol selected
        strategies: list = builder.create_strategies()

        strgy_to_be_removed = []
        sequence_info = (
            {}
        )  # Keep this in main for now as it seems to be state across strategies

        while strategies:
            for strgy in strategies:
                msg = f"{strgy.trade.symbol} ltp:{strgy.trade.last_price} {strgy._fn}"
                prefix = strgy._prefix

                # Get the run arguments dynamically from the builder
                run_args = builder.get_run_arguments(strgy)

                # Add strategy-specific run arguments that depend on loop state
                if builder.strategy_name == "openingbalance":
                    sequence_info[strgy._id] = dict(
                        _prefix=prefix,
                        _reduced_target_sequence=strgy._reduced_target_sequence,
                    )
                    resp = strgy.run(
                        *run_args,
                        strgy_to_be_removed,
                        sequence_info,
                    )
                    if isinstance(resp, str):
                        strgy_to_be_removed.append(resp)
                else:
                    resp = strgy.run(*run_args)  # Pass the dynamically generated args

                # logging.info(f"{msg} returned {resp}")

            strategies = [strgy for strgy in strategies if not strgy._removable]
        else:
            kill_tmux()
    except KeyboardInterrupt:
        __import__("sys").exit()
    except Exception as e:
        print_exc()
        logging.error(f"{e} while init")


if __name__ == "__main__":
    main()
