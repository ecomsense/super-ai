from tabulate import tabulate
import os
import sys


def table(cls_obj):
    items = [
        [k, v]
        for k, v in cls_obj.__dict__.items()
        if isinstance(v, float) or isinstance(v, int) or isinstance(v, str)
    ]
    print(tabulate(items, tablefmt="fancy_grid"))


def clear_screen():
    # \033[2J: Clears the entire screen
    # \033[H:  Moves cursor to home (top-left)
    # \033[3J: Clears the scrollback buffer (optional but recommended)
    sys.stdout.write("\033[2J\033[H\033[3J")
    sys.stdout.flush()


def pingpong(pivot):
    """
    Ping-Pong box UI
    ----------------
    - Vertical axis : price
    - Horizontal    : time (deque order)
    - Shows only:
        * Current box
        * Next (upper) box
    - Long-only visual intuition
    """

    # ================= HEADER =================
    state = pivot._state.name
    state_icon = "🟢" if state == "ARMED" else "⚪"

    print("\n" + "=" * 60)
    print(f"SYMBOL : {pivot._tradingsymbol}")
    print(f"STATE  : {state_icon} {state}")
    print(f"PRICE  : {round(pivot._last_price, 2)}")
    print(f"FN     : {pivot._fn}")
    print("=" * 60)

    # ================= BOX CALC =================
    box_idx, box_low, box_high = pivot.gridlines.find_current_grid(pivot._last_price)
    box_size = box_high - box_low

    # current box (where price is)
    curr_low = box_low
    curr_high = box_high

    # next box (upside / future)
    next_low = box_high
    next_high = box_high + box_size

    # ================= PATH =================
    # Use FULL deque length (no truncation)
    path = list(getattr(pivot, "_path", []))
    prices = [p for _, p in path]

    # Determine horizontal offset
    terminal_width = os.get_terminal_size().columns
    # If PE, start at 50% width, otherwise start at 0
    offset = (terminal_width // 2) if pivot.option_type.upper() == "PE" else 0

    # ANSI code for moving cursor to a specific column
    # Note: ANSI columns are 1-indexed
    move_to = f"\033[{offset + 1}G"

    def render_box(title, low, high):
        print(f"{move_to}\n{move_to}{title} ({low} – {high})")

        levels = 8
        step = (high - low) / levels

        for i in range(levels + 1):
            level_price = high - i * step
            label = f"{int(level_price):>5} |"

            row = ""
            for p in prices:
                if abs(p - level_price) < step / 2:
                    row += " ○"
                else:
                    row += "  "

            # Print the line with the specific column offset
            print(f"{move_to}{label}{row}")

    # ================= RENDER =================
    # Print HEADER with offset
    print(f"{move_to}{'=' * 40}")
    print(f"{move_to}SYMBOL : {pivot._tradingsymbol}")
    print(f"{move_to}STATE  : {state_icon} {state}")
    print(f"{move_to}PRICE  : {round(pivot._last_price, 2)}")
    print(f"{move_to}{'=' * 40}")

    render_box(f"BOX {box_idx + 1}", next_low, next_high)
    render_box(f"BOX {box_idx}", curr_low, curr_high)
