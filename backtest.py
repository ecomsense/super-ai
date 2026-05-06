import sys
sys.path.insert(0, '.')

from src.sdk.helper import Helper, S_DATA
import pendulum as pdlm
import csv

api = Helper.api()

instrument = sys.argv[1] if len(sys.argv) > 1 else "call"

if instrument == "call":
    token = api.instrument_symbol('MCX', 'NATURALGAS22MAY26C240')
    name = "NATURALGAS_CALL"
else:
    token = api.instrument_symbol('MCX', 'NATURALGAS22MAY26P260')
    name = "NATURALGAS_PUT"

# Get stop from config (low at 17:59:59)
stop_time = pdlm.now().replace(hour=17, minute=59, second=59)
stop_data = api.historical('MCX', token, 
    stop_time.subtract(hours=1).timestamp(),
    stop_time.timestamp())

stop = float(stop_data[0]['intl'])

# Target: 80%
target = stop * 1.8

# Get candles from 18:00
from_time = pdlm.now().replace(hour=18, minute=0).timestamp()
to_time = pdlm.now().replace(hour=23, minute=20).timestamp()

candles = api.historical('MCX', token, from_time, to_time)

# Generate ALL signals (multi-entry allowed)
signals = []
prev_trade = stop
armed_idx = 0

for i, c in enumerate(candles):
    t = c['time'][-8:]
    close = float(c['intc'])
    low = float(c['intl'])
    high = float(c['inth'])
    
    # Skip same candle
    if armed_idx == i + 1:
        continue
    
    # Entry 1: breakout
    if low <= stop and close > stop and close < target:
        signals.append([t, close, low, high, "BREAKOUT", "ENTRY"])
        prev_trade = close
        armed_idx = i + 1
        continue
    
    # Entry 2: 2-candle (red then green)
    if i >= 2:
        c1 = candles[i-1]
        c2 = candles[i-2]
        
        c2_red = float(c2['intc']) < float(c2['into'])
        c1_green = float(c1['intc']) > float(c1['into'])
        
        if c2_red and c1_green and close < target and close > prev_trade:
            signals.append([t, close, low, high, "2-CANDLE", "ENTRY"])
            prev_trade = close
            armed_idx = i + 1
            continue
    
    # Skipped: too soon after last signal
    if i >= 1:
        breakout = (low <= stop and close > stop and close < target)
        
        if breakout and armed_idx > 0 and i - armed_idx < 3:
            signals.append([t, close, low, high, "BREAKOUT", "SKIP (<3)"])
            continue
        
        if i >= 2:
            c1 = candles[i-1]
            c2 = candles[i-2]
            
            c2_red = float(c2['intc']) < float(c2['into'])
            c1_green = float(c1['intc']) > float(c1['into'])
            
            two_candle = c2_red and c1_green and close < target and close > prev_trade
            
            if two_candle and armed_idx > 0 and i - armed_idx < 3:
                signals.append([t, close, low, high, "2-CANDLE", "SKIP (<3)"])
                continue

# Check for exit if target was reached
target_hit = False
for c in candles:
    if float(c['inth']) >= target:
        target_hit = True
        break

if target_hit:
    signals.append(["-", "-", "-", target, "TARGET", "HIT"])
else:
    signals.append(["-", "-", "-", target, "TARGET", "NOT_REACHED"])

# Write CSV
filename = f"{S_DATA}backtest_{name}.csv"
with open(filename, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["time", "close", "low", "high", "signal", "action"])
    writer.writerows(signals)

print(f"CSV: {filename}")
print(f"Total: {len(signals)}")