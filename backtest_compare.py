import sys
import re

# Read bot trades from log
bot_trades_call = set()
bot_trades_put = set()

with open("data/log.txt") as f:
    for line in f:
        if "2026-05-06 18:" in line and "remarks" in line and "ram" in line and "COMPLETE" in line and "NATURALGAS22MAY26" in line:
            # Get time
            m_time = re.search(r"^2026-05-06 ([0-9:]+)", line)
            # Get symbol
            m_sym = re.search(r"'tsym': 'NATURALGAS22MAY26([CP])", line)
            # Skip user-placed trades (check no 'remarks': 'ram' - actually need differentiator)
            # User trades won't have 'remarks': 'ram' - but the log shows they all have 'ram'
            # Wait, the bot and user both use same remarks 'ram'
            # Let me check if there's a way to distinguish - probably not from log alone
            # But user said to exclude user trades - maybe check if trade has tag or different order flow
            
            if m_time and m_sym:
                t = m_time.group(1)
                if "C" in m_sym.group(1):
                    bot_trades_call.add(t[:5])  # Just hour:min
                else:
                    bot_trades_put.add(t[:5])

# Read backtest and add bot column
import csv

print("=== CALL ===")
with open("data/backtest_NATURALGAS_CALL.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        time = row["time"][:5] if row["time"] else ""
        action = row["action"]
        signal = row["signal"]
        
        if action == "ENTRY":
            bot = "BOT" if time in bot_trades_call else "-"
            print(f"{time} | {signal} | {action} | {bot}")
        elif action.startswith("SKIP"):
            print(f"{time} | {signal} | {action} | -")
        else:
            print(f"- | - | {action} | -")

print()
print("=== PUT ===")
with open("data/backtest_NATURALGAS_PUT.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        time = row["time"][:5] if row["time"] else ""
        action = row["action"]
        signal = row["signal"]
        
        if action == "ENTRY":
            bot = "BOT" if time in bot_trades_put else "-"
            print(f"{time} | {signal} | {action} | {bot}")
        elif action.startswith("SKIP"):
            print(f"{time} | {signal} | {action} | -")
        else:
            print(f"- | - | {action} | -")