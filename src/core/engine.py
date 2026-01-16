from src.constants import logging_func
from traceback import print_exc
from src.sdk.helper import Helper
from toolkit.kokoo import is_time_past, blink

logging = logging_func(__name__)


class Engine:

    def __init__(self, start, stop):
        self.strategies = []
        self.stop = stop
        logging.info(f"WAITING: till Engine start time {start}")
        while not is_time_past(start):
            blink()

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
                run_args = trades, quotes
                # Add strategy-specific run arguments that depend on loop state
                if strgy.name == "openingbalance":
                    strgy.run(
                        *run_args,
                        positions=Helper._rest.positions(),
                    )
                else:
                    strgy.run(*run_args)  # Pass the dynamically generated args

            self.strategies = [s for s in self.strategies if not s._removable]
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
