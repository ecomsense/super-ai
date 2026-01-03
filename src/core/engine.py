from toolkit.kokoo import is_time_past
from src.constants import logging_func
from traceback import print_exc

logging = logging_func(__name__)


class Engine:

    def __init__(self):
        self.strategies = []
        self.stop = trade_stop

    def add_strategy(self, new_strats):
        if new_strats:
            self.strategies.extend(new_strats)

    def tick(self):
        try:
            if not self.strategies:
                return

            # Get the run arguments dynamically from the builder
            trades = Helper._rest.trades()
            quotes = Helper._quote.get_quotes()

            for strgy in self.strategies:
                strgy_to_be_removed = []
                run_args = trades, quotes
                # Add strategy-specific run arguments that depend on loop state
                if strgy.name == "openingbalance":
                    resp = strgy.run(
                        *run_args,
                        strgy_to_be_removed,
                        positions=Helper._rest.positions(),
                    )
                    if resp == strgy._prefix:
                        strgy_to_be_removed.append(resp)
                else:
                    resp = strgy.run(*run_args)  # Pass the dynamically generated args

                # logging.info(f"main: {strgy._fn}")

                self.strategies = [s for s in self.strategies if not strgy._removable]
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
        except Exception as e:
            print_exc()
            logging.error(f"{e} Engine: run while tick")
