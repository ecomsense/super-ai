from src.constants import logging_func
from traceback import print_exc
from toolkit.kokoo import is_time_past, blink
from src.providers.ui import generate_table

logging = logging_func(__name__)


class Engine:

    def __init__(self, start, stop):
        self.strategies = []
        self.stop = stop
        self.start = start

    def wait_until_start(self):
        logging.info(f"WAITING: till Super-Ai starts at {self.start}")
        while not is_time_past(self.start):
            blink()

    def add_strategy(self, new_strats):
        if new_strats:
            self.strategies.extend(new_strats)

    def tick(self, rest, quote, live):
        try:
            if not self.strategies:
                return

            # Get the run arguments dynamically
            trades = rest.trades()

            needs_position = any(
                s.strategy == "openingbalance" for s in self.strategies
            )
            positions = rest.positions() if needs_position else None

            for strgy in self.strategies:
                run_args = trades, quote.get_quotes(), positions
                strgy.run(*run_args)  # Pass the dynamically generated args
                live.update(generate_table(strgy))

            self.strategies = [s for s in self.strategies if not s._removable]
        except Exception as e:
            print_exc()
            logging.error(f"{e} Engine: run while tick")
