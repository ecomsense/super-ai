# rich_demo_flowchart.py
from rich.console import Console
from rich.table import Table
from rich.live import Live
import random
import time

console = Console()

instruments = ["NIFTY_CALL", "NIFTY_PUT", "BANKNIFTY_CALL", "BANKNIFTY_PUT"]
states = ["WAITING", "ENTERED", "MONITOR", "EXIT_PENDING", "DONE"]
common_states = ["PAIR_IDLE", "ONE_ENTERED", "BOTH_ENTERED", "EXITING", "PAIR_DONE"]

# Current state storage
instrument_states = {inst: "WAITING" for inst in instruments}
pair_states = {"NIFTY": "PAIR_IDLE", "BANKNIFTY": "PAIR_IDLE"}


def generate_random_update():
    inst = random.choice(instruments)
    state = random.choice(states)
    instrument_states[inst] = state

    pair = "NIFTY" if "NIFTY" in inst else "BANKNIFTY"
    pair_states[pair] = random.choice(common_states)


def render_table():
    table = Table(title="Trading Strategy Flowchart")
    table.add_column("Instrument", justify="center")
    table.add_column("State", justify="center", style="bold")
    table.add_column("Pair State", justify="center", style="cyan")

    # NIFTY row
    for inst in ["NIFTY_CALL", "NIFTY_PUT"]:
        table.add_row(
            inst,
            f"[red]{instrument_states[inst]}[/red]"
            if instrument_states[inst] != "WAITING"
            else instrument_states[inst],
            f"[magenta]{pair_states['NIFTY']}[/magenta]",
        )

    # BANKNIFTY row
    for inst in ["BANKNIFTY_CALL", "BANKNIFTY_PUT"]:
        table.add_row(
            inst,
            f"[red]{instrument_states[inst]}[/red]"
            if instrument_states[inst] != "WAITING"
            else instrument_states[inst],
            f"[magenta]{pair_states['BANKNIFTY']}[/magenta]",
        )

    return table


# Live updating loop
with Live(render_table(), refresh_per_second=2) as live:
    while True:
        generate_random_update()
        live.update(render_table())
        time.sleep(1)
