import sys
sys.path.insert(0, '.')

from src.sdk.helper import Helper, S_DATA
import pendulum as pdlm
import csv
import re

api = Helper.api()

instrument = sys.argv[1] if len(sys.argv) > 1 else "call"

# NIFTY options
if instrument == "call":
    token = api.instrument_symbol('NFO', 'NIFTY12MAY26C24000')
    name = "NIFTY_CALL"
    sym = "NIFTY12MAY26C24000"
    stop_hour, stop_min = 9, 14
else:
    token = api.instrument_symbol('NFO', 'NIFTY12MAY26P24200')
    name = "NIFTY_PUT"
    sym = "NIFTY12MAY26P24200"
    stop_hour, stop_min = 9, 14

# Try to get stop, fallback to first candle
stop_time = pdlm.now().replace(hour=stop_hour, minute=stop_min, second=59)
stop_data = api.historical('NFO', token, 
    stop_time.subtract(hours=1).timestamp(),
    stop_time.timestamp())

if stop_data:
    stop = float(stop_data[0]['intl'])
else:
    # Use first available candle
    first_candle = api.historical('NFO', token, 
        pdlm.now().replace(hour=9, minute=15).timestamp(),
        pdlm.now().replace(hour=9, minute=20).timestamp())
    stop = float(first_candle[0]['intl'])

target = stop * 1.5  # Default 50% for NIFTY

# Get candles from 9:15 to 15:30
from_time = pdlm.now().replace(hour=9, minute=15).timestamp()
to_time = pdlm.now().replace(hour=15, minute=30).timestamp()
candles = api.historical('NFO', token, from_time, to_time)

print(f"Stop: {stop}, Target: {target}, Candles: {len(candles)}")

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
        bt_signals.append((t[:5], close, "BREAKOUT", action))
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
            bt_signals.append((t[:5], close, "2-CANDLE", action))
            if action == "ENTRY":
                prev_trade = close
                last_entry_idx = i + 1
            continue

# Get actual bot trades
with open("data/log.txt") as f:
    log = f.read()

actual = set()
for line in log.split('\n'):
    if "2026-05-06" in line and "'remarks': 'ram'" in line and "COMPLETE" in line and sym in line:
        m = re.search(r"^2026-05-06 ([0-9:]+)", line)
        if m:
            actual.add(m.group(1)[:5])

# Merge
signals = []
for t, price, signal, action in bt_signals:
    bot = "BOT" if t in actual else "-"
    signals.append([t, price, signal, action, "BACKTEST", bot])

for t in sorted(actual):
    if t not in [x[0] for x in bt_signals]:
        price = "-"
        for c in candles:
            if c['time'][-8:].startswith(t):
                price = c['intc']
                break
        signals.append([t, price, "ACTUAL", "TRADE", "BOT", "BOT"])

signals.sort(key=lambda x: x[0])

target_hit = any(float(c['inth']) >= target for c in candles)
signals.append(["-", "-", "TARGET", "HIT" if target_hit else "NOT_REACHED", "-", "-"])

filename = f"{S_DATA}backtest_{name}.csv"
with open(filename, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["time", "price", "signal", "action", "source", "bot"])
    writer.writerows(signals)

print(f"CSV: {filename}, Total: {len(signals)}")