# fixed_demo_flowchart.py
from textual.app import App, ComposeResult
from textual.widgets import Static, Header, Footer
from textual.containers import Grid
import asyncio
import random

instruments = ["NIFTY_CALL", "NIFTY_PUT", "BANKNIFTY_CALL", "BANKNIFTY_PUT"]
states = ["WAITING", "ENTERED", "MONITOR", "EXIT_PENDING", "DONE"]
common_states = ["PAIR_IDLE", "ONE_ENTERED", "BOTH_ENTERED", "EXITING", "PAIR_DONE"]


async def generate_events(event_queue):
    while True:
        inst = random.choice(instruments)
        state = random.choice(states)
        pair_state = random.choice(common_states)
        await event_queue.put((inst, state, pair_state))
        await asyncio.sleep(1)


class FlowChartApp(App):
    CSS = """
    Grid {
        grid-size: 2 3;
        grid-gutter: 1 4;
        padding: 1;
    }
    Static {
        border: round white;
        padding: 1;
        content-align: center middle;
    }
    """

    def __init__(self):
        super().__init__()
        self.instrument_states = {inst: "WAITING" for inst in instruments}
        self.pair_state = "PAIR_IDLE"

    def compose(self) -> ComposeResult:
        yield Header()
        with Grid():
            # Row 1: NIFTY pair
            yield Static("NIFTY_CALL", id="NIFTY_CALL")
            yield Static("NIFTY_PUT", id="NIFTY_PUT")
            yield Static("PAIR_STATE\nNIFTY", id="PAIR_STATE_NIFTY")
            # Row 2: BANKNIFTY pair
            yield Static("BANKNIFTY_CALL", id="BANKNIFTY_CALL")
            yield Static("BANKNIFTY_PUT", id="BANKNIFTY_PUT")
            yield Static("PAIR_STATE\nBANKNIFTY", id="PAIR_STATE_BN")
        yield Footer()

    async def on_mount(self):
        event_queue = asyncio.Queue()
        asyncio.create_task(generate_events(event_queue))

        while True:
            while not event_queue.empty():
                inst, state, pair_state = await event_queue.get()
                self.instrument_states[inst] = state
                if "NIFTY" in inst:
                    self.query_one("#PAIR_STATE_NIFTY", Static).update(
                        f"PAIR_STATE\n{pair_state}"
                    )
                else:
                    self.query_one("#PAIR_STATE_BN", Static).update(
                        f"PAIR_STATE\n{pair_state}"
                    )

                for inst_name, inst_state in self.instrument_states.items():
                    color = "red" if inst_state != "WAITING" else "white"
                    self.query_one(f"#{inst_name}", Static).update(
                        f"[{color}]{inst_name}\n{inst_state}[/{color}]"
                    )
            await asyncio.sleep(0.1)


if __name__ == "__main__":
    FlowChartApp().run()
