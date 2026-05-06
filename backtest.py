import sys
sys.path.insert(0, '.')

from src.sdk.helper import Helper, S_DATA
import pendulum as pdlm
import csv
import re

api = Helper.api()

if len(sys.argv) < 2:
    print("Usage: python backtest.py <instrument> [exchange]")
    sys.exit(1)

instrument = sys.argv[1]
exchange = sys.argv[2] if len(sys.argv) > 2 else "NFO"

# Determine call or put
if "C" in instrument and any(c.isdigit() for c in instrument.split("C")[-1][:5]):
    opt_type = "CALL"
elif "P" in instrument and any(c.isdigit() for c in instrument.split("P")[-1][:5]):
    opt_type = "PUT"
else:
    opt_type = "UNKNOWN"

base = "NATURALGAS" if "NATURALGAS" in instrument else "NIFTY"
name = f"{base}_{opt_type}"

token = api.instrument_symbol(exchange, instrument)

# Stop time
if "NATURALGAS" in instrument:
    stop_hour, stop_min = 17, 59
else:
    stop_hour, stop_min = 9, 14

stop_time = pdlm.now().replace(hour=stop_hour, minute=stop_min, second=59)
stop_data = api.historical(exchange, token, 
    stop_time.subtract(hours=1).timestamp(),
    stop_time.timestamp())

if stop_data:
    stop = float(stop_data[0]['intl'])
else:
    first = api.historical(exchange, token, 
        pdlm.now().replace(hour=9, minute=15).timestamp(),
        pdlm.now().replace(hour=9, minute=20).timestamp())
    stop = float(first[0]['intl'])

target = stop * 1.5

# Time range
if "NATURALGAS" in instrument:
    from_time = pdlm.now().replace(hour=18, minute=0).timestamp()
    to_time = pdlm.now().replace(hour=23, minute=20).timestamp()
    start_time = "18:00"
    end_time = "23:20"
else:
    from_time = pdlm.now().replace(hour=9, minute=15).timestamp()
    to_time = pdlm.now().replace(hour=15, minute=30).timestamp()
    start_time = "9:15"
    end_time = "15:30"

candles = api.historical(exchange, token, from_time, to_time)

# Get bot session times from log
with open("data/log.txt") as f:
    log = f.read()

# Find session start times
session_starts = []
for line in log.split('\n'):
    if "2026-05-06" in line and "Strategy 'ram' start_time" in line:
        # Extract timestamp from log line, format: "2026-05-06 HH:MM:SS"
        m = re.search(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", line)
        if m:
            session_starts.append(m.group(1))  # "2026-05-06 HH:MM"

# Sort sessions
session_starts = sorted(set(session_starts))

session_info = ", ".join(session_starts) if session_starts else start_time

print(f"Instrument: {instrument}, Stop: {stop}, Target: {target}, Sessions: {session_info}")

# Determine if bot was running at a given time
def was_running(check_time):
    """Check if bot was running at check_time (HH:MM format)"""
    for i, session in enumerate(session_starts):
        # session = "2026-05-06 HH:MM"
        session_hhmm = session[-5:]  # "HH:MM"
        
        # Convert to comparable minutes
        sh = int(session_hhmm.split(':')[0])
        sm = int(session_hhmm.split(':')[1])
        ct = int(check_time.split(':')[0])
        cm = int(check_time.split(':')[1])
        
        session_mins = sh * 60 + sm
        check_mins = ct * 60 + cm
        
        if check_mins >= session_mins:
            # Check if next session exists
            if i + 1 < len(session_starts):
                next_session = session_starts[i + 1]
                nh = int(next_session[-5:].split(':')[0])
                nm = int(next_session[-5:].split(':')[1])
                next_mins = nh * 60 + nm
                if check_mins < next_mins:
                    return True
            else:
                # Last session - assume running until end of day
                return True
    return False

# Backtest signals
bt_signals = []
prev_trade = stop
last_entry_idx = 0

for i, c in enumerate(candles):
    t = c['time'][-8:]
    close = float(c['intc'])
    low = float(c['intl'])
    
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
actual = set()
for line in log.split('\n'):
    if "2026-05-06" in line and "'remarks': 'ram'" in line and "COMPLETE" in line and instrument in line:
        m = re.search(r"^2026-05-06 ([0-9:]+)", line)
        if m:
            actual.add(m.group(1)[:5])

# Merge - now with stopped status
signals = []
for t, price, signal, action in bt_signals:
    if t in actual:
        bot = "BOT"
    elif action == "ENTRY" and not was_running(t):
        bot = "STOPPED"  # Bot wasn't running
    else:
        bot = "-"
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

# Write CSV
filename = f"{S_DATA}backtest_{name}.csv"
with open(filename, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["#", f"instrument={instrument}"])
    writer.writerow(["#", f"stop={stop}"])
    writer.writerow(["#", f"target={target}"])
    writer.writerow(["#", f"session={session_info}"])
    writer.writerow(["time", "price", "signal", "action", "source", "bot"])
    writer.writerows(signals)

print(f"CSV: {filename}, Total: {len(signals)}")