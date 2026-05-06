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
    sym = "NATURALGAS22MAY26C240"
else:
    token = api.instrument_symbol('MCX', 'NATURALGAS22MAY26P260')
    name = "NATURALGAS_PUT"
    sym = "NATURALGAS22MAY26P260"

# Get stop
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

# Generate backtest signals
bt_signals = []
prev_trade = stop
last_entry_idx = 0

for i, c in enumerate(candles):
    t = c['time'][-8:]
    close = float(c['intc'])
    low = float(c['intl'])
    high = float(c['inth'])
    
    if low <= stop and close > stop and close < target:
        action = "SKIP (<3)" if last_entry_idx > 0 and i - last_entry_idx < 3 else "ENTRY"
        bt_signals.append((t[:5], close, signal="BREAKOUT", action=action))
        if action == "ENTRY":
            prev_trade = close
            last_entry_idx = i + 1
        continue
    
    if i >= 2:
        c1 = candles[i-1]
        c2 = candles[i-2]
        
        c2_red = float(c2['intc']) < float(c2['into'])
        c1_green = float(c1['intc']) > float(c1['into'])
        
        if c2_red and c1_green and close < target and close > prev_trade:
            action = "SKIP (<3)" if last_entry_idx > 0 and i - last_entry_idx < 3 else "ENTRY"
            bt_signals.append((t[:5], close, signal="2-CANDLE", action=action))
            if action == "ENTRY":
                prev_trade = close
                last_entry_idx = i + 1
            continue

# Get actual bot trades
with open("data/log.txt") as f:
    log = f.read()

actual = set()
for line in log.split('\n'):
    if "2026-05-06 18:" in line and "'remarks': 'ram'" in line and "COMPLETE" in line and sym in line:
        m = re.search(r"^2026-05-06 ([0-9:]+)", line)
        if m:
            actual.add(m.group(1)[:5])

# Merge into single list (all backtest + all actual trades not in backtest)
all_times = set()

for t, price, signal, action in bt_signals:
    all_times.add(t)

for t in actual:
    all_times.add(t)

# Build final list
signals = []

# Add backtest entries
for t, price, signal, action in bt_signals:
    bot = "BOT" if t in actual else "-"
    src = "BACKTEST"
    signals.append([t, price, signal, action, src, bot])

# Add actual trades not in backtest
for t in sorted(actual):
    if t not in [x[0] for x in bt_signals]:
        # Get price from candles
        price = "-"
        for c in candles:
            if c['time'][-8:].startswith(t):
                price = c['intc']
                break
        signals.append([t, price, "ACTUAL", "TRADE", "BOT", "BOT"])

# Sort by time
signals.sort(key=lambda x: x[0])

# Add target status
target_hit = any(float(c['inth']) >= target for c in candles)
signals.append(["-", "-", "TARGET", "HIT" if target_hit else "NOT_REACHED", "-", "-"])

# Write
filename = f"{S_DATA}backtest_{name}.csv"
with open(filename, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["time", "price", "signal", "action", "source", "bot"])
    writer.writerows(signals)

print(f"CSV: {filename}")
print(f"Total: {len(signals)}")