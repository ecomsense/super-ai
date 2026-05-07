import sys
sys.path.insert(0, '.')

from src.sdk.helper import Helper, S_DATA
import pendulum as pdlm
import csv
import re

api = Helper.api()

# Read log to find what instruments the bot traded
with open("data/log.txt") as f:
    log = f.read()

# Find the instrument from recent bot activity - use both May 6 and May 7 to capture all
# The bot may have traded yesterday and today

# Find the trading symbols from the log - look for RAM strategy entries
call_symbols = set()
put_symbols = set()

# Search for both dates to capture all trades
for line in log.split('\n'):
    if "'remarks': 'ram'" in line and "COMPLETE" in line:
        # Extract the symbol from lines like: 'tsym': 'NIFTY12MAY26C24300'
        # Use more robust regex
        match = re.search(r"'tsym':\s*'([^']+)'", line)
        if match:
            sym = match.group(1)
            if 'C' in sym:
                call_symbols.add(sym)
            elif 'P' in sym:
                put_symbols.add(sym)

print(f"Found CALL symbols: {sorted(call_symbols)}")
print(f"Found PUT symbols: {sorted(put_symbols)}")

# Use only the most recent call and put from today (1 each)
call_sym = sorted(call_symbols)[-1] if call_symbols else "NIFTY12MAY26C24000"
put_sym = sorted(put_symbols)[-1] if put_symbols else "NIFTY12MAY26P24200"

instrument = sys.argv[1] if len(sys.argv) > 1 else "call"

if instrument == "call":
    sym = call_sym
    token = api.instrument_symbol('NFO', sym)
    name = "NIFTY_CALL"
elif instrument == "put":
    sym = put_sym
    token = api.instrument_symbol('NFO', sym)
    name = "NIFTY_PUT"
else:
    sym = instrument
    token = api.instrument_symbol('NFO', sym)
    name = f"NIFTY_{sym}"

print(f"Using instrument: {sym}, token: {token}")

# Get stop from historical data
stop_hour, stop_min = 9, 14
stop_time = pdlm.now().replace(hour=stop_hour, minute=stop_min, second=59)
stop_data = api.historical('NFO', token, 
    stop_time.subtract(hours=1).timestamp(),
    stop_time.timestamp())

if stop_data:
    stop = float(stop_data[0]['intl'])
else:
    # Fallback to first available candle
    first_candle = api.historical('NFO', token, 
        pdlm.now().replace(hour=9, minute=15).timestamp(),
        pdlm.now().replace(hour=9, minute=20).timestamp())
    if first_candle:
        stop = float(first_candle[0]['intl'])
    else:
        print("ERROR: Could not get stop data")
        sys.exit(1)

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

# Get actual bot trades from log for TODAY (May 7)
today = "2026-05-07"
actual = set()
for line in log.split('\n'):
    if today in line and "'remarks': 'ram'" in line and "COMPLETE" in line and sym in line:
        m = re.search(rf"^{today} ([0-9:]+)", line)
        if m:
            actual.add(m.group(1)[:5])

print(f"Actual bot trades for {sym}: {sorted(actual)}")

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
    writer.writerow(["#", f"instrument={sym}"])
    writer.writerow(["#", f"stop={stop}"])
    writer.writerow(["#", f"target={target}"])
    writer.writerow(["time", "price", "signal", "action", "source", "bot"])
    writer.writerows(signals)

print(f"CSV: {filename}, Total: {len(signals)}")