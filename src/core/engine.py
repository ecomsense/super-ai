from toolkit.kokoo import is_time_past, kill_tmux
from src.constants import logging_func

logging = logging_func(__name__)


class Engine:

    def __init__(self, strategies, trade_stop):
        self.strategies = strategies
        self.stop = trade_stop

    def run(self, strategy_name):
        try:
            strgy_to_be_removed = []
            while self.strategies and not is_time_past(self.stop):
                # Get the run arguments dynamically from the builder
                trades = Helper._rest.trades()
                quotes = Helper._quote.get_quotes()

                for strgy in self.strategies:
                    run_args = trades, quotes
                    # Add strategy-specific run arguments that depend on loop state
                    if strategy_name == "openingbalance":
                        resp = strgy.run(
                            *run_args,
                            strgy_to_be_removed,
                            positions=Helper._rest.positions(),
                        )
                        if resp == strgy._prefix:
                            strgy_to_be_removed.append(resp)
                    else:
                        resp = strgy.run(
                            *run_args
                        )  # Pass the dynamically generated args

                    # logging.info(f"main: {strgy._fn}")

                self.strategies = [
                    strgy for strgy in self.strategies if not strgy._removable
                ]
            """
            else:
                logging.info(
                    f"main: exit initialized because we are past trade stop time {self.stop}"
                )
                Helper._rest.orders()
                for item in orders:
                    if (
                        item.get("status", None) == "OPEN"
                        or item.get("status", None) == "TRIGGER_PENDING"
                    ):
                        order_id = item.get("order_id", None)
                        logging.info(f"cancelling open order {order_id}")
                        Helper._rest.order_cancel(order_id)

                Helper._rest.close_positions()
            """
            logging.info(
                f"main: killing tmux because we started after stop time {self.stop}"
            )
            kill_tmux()
        except KeyboardInterrupt:
            __import__("sys").exit()
        except Exception as e:
            print_exc()
            logging.error(f"{e} Engine: run while init")
