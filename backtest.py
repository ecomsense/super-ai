import sys
sys.path.insert(0, '.')

from src.sdk.helper import Helper, S_DATA
import pendulum as pdlm
import csv
import re
from collections import defaultdict

api = Helper.api()

# Get today's date
today = pdlm.now("Asia/Kolkata").format("YYYY-MM-DD")

# Read log to find traded symbols and sessions
with open("data/log.txt") as f:
    log = f.read()

# Find trading sessions (bot start times) for today
sessions = set()
for line in log.split('\n'):
    if today in line and "Strategy 'ram' start_time" in line:
        match = re.search(r"start_time:\s*(\d+):(\d+)", line)
        if match:
            sessions.add(f"{match.group(1)}:{match.group(2)}")

sessions = sorted(sessions)
print(f"Found sessions today: {sessions}")

# Find traded symbols for today
call_symbols = set()
put_symbols = set()

for line in log.split('\n'):
    if today in line and "'remarks': 'ram'" in line and "COMPLETE" in line:
        match = re.search(r"'tsym':\s*'([^']+)'", line)
        if match:
            sym = match.group(1)
            if 'C' in sym:
                call_symbols.add(sym)
            elif 'P' in sym:
                put_symbols.add(sym)

call_symbols = sorted(call_symbols)
put_symbols = sorted(put_symbols)

print(f"Call symbols: {call_symbols}")
print(f"Put symbols: {put_symbols}")

# Get stop for each symbol - try multiple times around the expected time
def get_stop(symbol):
    token = api.instrument_symbol('NFO', symbol)
    
    # Try different times - bot was trying around 09:15:59
    times_to_try = [
        pdlm.now("Asia/Kolkata").replace(hour=9, minute=15, second=59),
        pdlm.now("Asia/Kolkata").replace(hour=9, minute=14, second=59),
        pdlm.now("Asia/Kolkata").replace(hour=9, minute=16, second=0),
    ]
    
    for t in times_to_try:
        data = api.historical('NFO', token, t.timestamp(), t.add(seconds=2).timestamp())
        if data and data[0].get('intl'):
            return float(data[0]['intl'])
    
    return None

# Process symbols and create output files
file_count = 0

# Process CALL symbols
for i, sym in enumerate(call_symbols, 1):
    stop = get_stop(sym)
    if stop:
        target = stop * 1.5  # Default 50% target
        file_count += 1
        filename = f"{S_DATA}{i}_{sym}.csv"
        
        # Get candles for backtest
        from_time = pdlm.now("Asia/Kolkata").replace(hour=9, minute=15).timestamp()
        to_time = pdlm.now("Asia/Kolkata").replace(hour=15, minute=30).timestamp()
        candles = api.historical('NFO', api.instrument_symbol('NFO', sym), from_time, to_time)
        
        # Generate backtest signals
        signals = []
        prev_trade = stop
        last_entry_idx = 0
        
        for idx, c in enumerate(candles):
            t = c['time'][-8:][:5]
            close = float(c['intc'])
            low = float(c['intl'])
            
            # Check if bot was active at this time
            active = False
            for sess in sessions:
                sh, sm = map(int, sess.split(':'))
                sess_mins = sh * 60 + sm
                t_h, t_m = map(int, t.split(':'))
                t_mins = t_h * 60 + t_m
                if t_mins >= sess_mins:
                    active = True
                    break
            
            if not active:
                action = "INACTIVE"
            elif low <= stop and close > stop and close < target:
                action = "ENTRY" if last_entry_idx == 0 or idx - last_entry_idx >= 3 else "SKIP"
                if action == "ENTRY":
                    prev_trade = close
                    last_entry_idx = idx
                signals.append([t, close, "BREAKOUT", action])
            elif idx >= 2:
                c1 = candles[idx-1]
                c2 = candles[idx-2]
                c2_red = float(c2['intc']) < float(c2['into'])
                c1_green = float(c1['intc']) > float(c1['into'])
                if c2_red and c1_green and close < target and close > prev_trade:
                    action = "ENTRY" if last_entry_idx == 0 or idx - last_entry_idx >= 3 else "SKIP"
                    if action == "ENTRY":
                        prev_trade = close
                        last_entry_idx = idx
                    signals.append([t, close, "2-CANDLE", action])
            else:
                signals.append([t, close, "-", "WAITING"])
        
        # Write CSV
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["#", f"symbol={sym}"])
            writer.writerow(["#", f"stop={stop}"])
            writer.writerow(["#", f"target={target}"])
            writer.writerow(["#", f"sessions={','.join(sessions)}"])
            writer.writerow(["time", "price", "signal", "action"])
            writer.writerows(signals)
        
        print(f"Created {filename}")

# Process PUT symbols
for i, sym in enumerate(put_symbols, start=len(call_symbols)+1):
    stop = get_stop(sym)
    if stop:
        target = stop * 1.5
        file_count += 1
        filename = f"{S_DATA}{i}_{sym}.csv"
        
        # Get candles for backtest
        from_time = pdlm.now("Asia/Kolkata").replace(hour=9, minute=15).timestamp()
        to_time = pdlm.now("Asia/Kolkata").replace(hour=15, minute=30).timestamp()
        candles = api.historical('NFO', api.instrument_symbol('NFO', sym), from_time, to_time)
        
        # Generate backtest signals
        signals = []
        prev_trade = stop
        last_entry_idx = 0
        
        for idx, c in enumerate(candles):
            t = c['time'][-8:][:5]
            close = float(c['intc'])
            low = float(c['intl'])
            
            # Check if bot was active at this time
            active = False
            for sess in sessions:
                sh, sm = map(int, sess.split(':'))
                sess_mins = sh * 60 + sm
                t_h, t_m = map(int, t.split(':'))
                t_mins = t_h * 60 + t_m
                if t_mins >= sess_mins:
                    active = True
                    break
            
            if not active:
                action = "INACTIVE"
            elif low <= stop and close > stop and close < target:
                action = "ENTRY" if last_entry_idx == 0 or idx - last_entry_idx >= 3 else "SKIP"
                if action == "ENTRY":
                    prev_trade = close
                    last_entry_idx = idx
                signals.append([t, close, "BREAKOUT", action])
            elif idx >= 2:
                c1 = candles[idx-1]
                c2 = candles[idx-2]
                c2_red = float(c2['intc']) < float(c2['into'])
                c1_green = float(c1['intc']) > float(c1['into'])
                if c2_red and c1_green and close < target and close > prev_trade:
                    action = "ENTRY" if last_entry_idx == 0 or idx - last_entry_idx >= 3 else "SKIP"
                    if action == "ENTRY":
                        prev_trade = close
                        last_entry_idx = idx
                    signals.append([t, close, "2-CANDLE", action])
            else:
                signals.append([t, close, "-", "WAITING"])
        
        # Write CSV
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["#", f"symbol={sym}"])
            writer.writerow(["#", f"stop={stop}"])
            writer.writerow(["#", f"target={target}"])
            writer.writerow(["#", f"sessions={','.join(sessions)}"])
            writer.writerow(["time", "price", "signal", "action"])
            writer.writerows(signals)
        
        print(f"Created {filename}")

print(f"Total files created: {file_count}")