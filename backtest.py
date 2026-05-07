import sys
sys.path.insert(0, '.')

from src.sdk.helper import Helper, S_DATA
import pendulum as pdlm
import csv
import re

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

# Get stop for each symbol - try multiple times
def get_stop(symbol):
    token = api.instrument_symbol('NFO', symbol)
    
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

def is_bot_active(t, sessions):
    """Check if bot was active at time t (HH:MM format)"""
    t_h, t_m = map(int, t.split(':'))
    t_mins = t_h * 60 + t_m
    
    for sess in sessions:
        sh, sm = map(int, sess.split(':'))
        sess_mins = sh * 60 + sm
        if t_mins >= sess_mins:
            return True
    return False

def generate_backtest(sym, stop, sessions, is_put=False):
    """Generate backtest with correct RAM strategy logic"""
    target = stop * 1.5
    
    token = api.instrument_symbol('NFO', sym)
    from_time = pdlm.now("Asia/Kolkata").replace(hour=9, minute=15).timestamp()
    to_time = pdlm.now("Asia/Kolkata").replace(hour=15, minute=30).timestamp()
    candles = api.historical('NFO', token, from_time, to_time)
    
    signals = []
    prev_trade_at = stop  # Start with stop price
    armed_idx = 0  # Track which candle index was last triggered
    
    for idx, c in enumerate(candles):
        t = c['time'][-8:][:5]
        close = float(c['intc'])
        low = float(c['intl'])
        
        # Check if bot was active
        if not is_bot_active(t, sessions):
            signals.append([t, close, "-", "INACTIVE"])
            continue
        
        # Need at least 1 candle
        if idx < 1:
            signals.append([t, close, "-", "WAITING"])
            continue
        
        # BREAKOUT: low <= stop and close > stop
        if low <= stop and close > stop:
            # Breakout can always trigger, updates prev_trade_at to stop
            signals.append([t, close, "BREAKOUT", "ENTRY"])
            prev_trade_at = stop  # Reset to stop
            armed_idx = idx + 1  # Mark this candle as the trigger point
            continue
        
        # Need at least 4 candles for 2-candle pattern (current + 3 previous)
        if idx < 3:
            signals.append([t, close, "-", "WAITING"])
            continue
        
        # Check 3 candles since last entry
        if (idx + 1) - armed_idx < 3:
            signals.append([t, close, "-", "WAITING"])
            continue
        
        # 2-CANDLE: need red(-3), green(-2), and close > prev_trade_at
        c1 = candles[idx - 1]
        c2 = candles[idx - 2]
        
        c2_red = float(c2['intc']) < float(c2['into'])
        c1_green = float(c1['intc']) > float(c1['into'])
        
        if c2_red and c1_green and close < target and close > prev_trade_at:
            signals.append([t, close, "2-CANDLE", "ENTRY"])
            prev_trade_at = close  # Update to current close
            armed_idx = idx + 1
            continue
        
        signals.append([t, close, "-", "WAITING"])
    
    return signals

# Process all symbols
file_count = 0

for i, sym in enumerate(call_symbols, 1):
    stop = get_stop(sym)
    if stop:
        signals = generate_backtest(sym, stop, sessions)
        file_count += 1
        filename = f"{S_DATA}{i}_{sym}.csv"
        
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["#", f"symbol={sym}"])
            writer.writerow(["#", f"stop={stop}"])
            writer.writerow(["#", f"target={stop * 1.5}"])
            writer.writerow(["#", f"sessions={','.join(sessions)}"])
            writer.writerow(["time", "price", "signal", "action"])
            writer.writerows(signals)
        
        print(f"Created {filename}")

for i, sym in enumerate(put_symbols, start=len(call_symbols)+1):
    stop = get_stop(sym)
    if stop:
        signals = generate_backtest(sym, stop, sessions, is_put=True)
        file_count += 1
        filename = f"{S_DATA}{i}_{sym}.csv"
        
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["#", f"symbol={sym}"])
            writer.writerow(["#", f"stop={stop}"])
            writer.writerow(["#", f"target={stop * 1.5}"])
            writer.writerow(["#", f"sessions={','.join(sessions)}"])
            writer.writerow(["time", "price", "signal", "action"])
            writer.writerows(signals)
        
        print(f"Created {filename}")

print(f"Total files created: {file_count}")