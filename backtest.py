import sys
sys.path.insert(0, '.')

from src.sdk.helper import Helper, S_DATA
import pendulum as pdlm
import csv
import re

api = Helper.api()

instrument = sys.argv[1] if len(sys.argv) > 1 else "call"

if instrument == "call":
    token = api.instrument_symbol('MCX', 'NATURALGAS22MAY26C240')
    name = "NATURALGAS_CALL"
else:
    token = api.instrument_symbol('MCX', 'NATURALGAS22MAY26P260')
    name = "NATURALGAS_PUT"

# Get bot trades from log (exclude user trades - need differentiator)
# Read actual bot trades
with open("data/log.txt") as f:
    log_content = f.read()

bot_trades = set()
# Parse log for bot trades (remarks=ram, COMPLETE)
for line in log_content.split('\n'):
    if "2026-05-06 18:" in line and "'remarks': 'ram'" in line and "COMPLETE" in line:
        if "NATURALGAS22MAY26" in line:
            m = re.search(r"^2026-05-06 ([0-9:]+)", line)
            if m:
                # Just take first 5 chars (HH:MM)
                bot_trades.add(m.group(1)[:5])

# Get stop from config
stop_time = pdlm.now().replace(hour=17, minute=59, second=59)
stop_data = api.historical('MCX', token, 
    stop_time.subtract(hours=1).timestamp(),
    stop_time.timestamp())

stop = float(stop_data[0]['intl'])
target = stop * 1.8

# Get candles
from_time = pdlm.now().replace(hour=18, minute=0).timestamp()
to_time = pdlm.now().replace(hour=23, minute=20).timestamp()
candles = api.historical('MCX', token, from_time, to_time)

# Generate signals with bot comparison
signals = []
prev_trade = stop
last_entry_idx = 0

for i, c in enumerate(candles):
    t = c['time'][-8:]
    close = float(c['intc'])
    low = float(c['intl'])
    high = float(c['inth'])
    
    # Entry 1: breakout
    if low <= stop and close > stop and close < target:
        bot = "BOT" if t[:5] in bot_trades else "-"
        if last_entry_idx > 0 and i - last_entry_idx < 3:
            signals.append([t, close, low, high, "BREAKOUT", "SKIP (<3)", "-"])
        else:
            signals.append([t, close, low, high, "BREAKOUT", "ENTRY", bot])
            prev_trade = close
            last_entry_idx = i + 1
        continue
    
    # Entry 2: 2-candle
    if i >= 2:
        c1 = candles[i-1]
        c2 = candles[i-2]
        
        c2_red = float(c2['intc']) < float(c2['into'])
        c1_green = float(c1['intc']) > float(c1['into'])
        
        if c2_red and c1_green and close < target and close > prev_trade:
            bot = "BOT" if t[:5] in bot_trades else "-"
            if last_entry_idx > 0 and i - last_entry_idx < 3:
                signals.append([t, close, low, high, "2-CANDLE", "SKIP (<3)", "-"])
            else:
                signals.append([t, close, low, high, "2-CANDLE", "ENTRY", bot])
                prev_trade = close
                last_entry_idx = i + 1
            continue

# Target status
target_hit = any(float(c['inth']) >= target for c in candles)

if target_hit:
    signals.append(["-", "-", "-", target, "TARGET", "HIT", "-"])
else:
    signals.append(["-", "-", "-", target, "TARGET", "NOT_REACHED", "-"])

# Write CSV with bot column
filename = f"{S_DATA}backtest_{name}.csv"
with open(filename, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["time", "close", "low", "high", "signal", "action", "bot"])
    writer.writerows(signals)

print(f"CSV: {filename}")
print(f"Total: {len(signals)}")