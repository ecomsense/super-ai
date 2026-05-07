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

# Find bot entries from log
bot_entries = {}  # sym -> set of times (HH:MM) when bot took entry
for line in log.split('\n'):
    if today in line and "'remarks': 'ram'" in line and "COMPLETE" in line:
        match = re.search(r"'tsym':\s*'([^']+)'", line)
        time_match = re.search(r"(\d{2}:\d{2}):\d{2}", line)
        if match and time_match:
            sym = match.group(1)
            t = time_match.group(1)
            if sym not in bot_entries:
                bot_entries[sym] = set()
            bot_entries[sym].add(t)

print(f"Call symbols: {call_symbols}")
print(f"Put symbols: {put_symbols}")

print(f"Bot entries: {bot_entries}")

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

def generate_backtest(sym, stop, sessions, bot_entries, is_put=False):
    """Generate backtest with correct RAM strategy logic"""
    target = stop * 1.5
    
    token = api.instrument_symbol('NFO', sym)
    from_time = pdlm.now("Asia/Kolkata").replace(hour=9, minute=15).timestamp()
    to_time = pdlm.now("Asia/Kolkata").replace(hour=15, minute=30).timestamp()
    candles = list(reversed(api.historical('NFO', token, from_time, to_time)))
    
    signals = []
    prev_trade_at = stop  # Start with stop price
    armed_idx = len(candles)  # Initialize to high value so first check passes
    
    bot_sym_entries = bot_entries.get(sym, set())  # Get bot entries for this symbol
    
    for idx, c in enumerate(candles):
        t = c['time'][-8:][:5]
        close = float(c['intc'])
        low = float(c['intl'])
        
        # Check if bot was active
        if not is_bot_active(t, sessions):
            signals.append([t, close, low, stop, "-", "-", "-", "-", "-", "-", "-", "-", "-", "INACTIVE", "-"])
            continue
        
        # BREAKOUT: low <= stop and close > stop (check before idx check, can trigger on first candle)
        breakout_triggered = low <= stop and close > stop
        
        # Need at least 3 candles for 2-candle pattern (current + 3 previous)
        if idx < 3:
            if breakout_triggered:
                signal = "BREAKOUT"
                action = "ENTRY"
                prev_trade_at = stop
                armed_idx = idx + 1
            else:
                signal = "-"
                action = "WAITING"
            # Determine bot column
            if action == "ENTRY":
                if t in bot_sym_entries:
                    bot_col = "BOT"
                else:
                    bot_col = "-"
            else:
                bot_col = "-"
            signals.append([t, close, low, stop, "-", "-", "-", "-", "-", "-", "-", "-", signal, action, bot_col])
            continue
        
        # Check 3 candles since last entry (in chronological order, higher idx = later time)
        if idx - armed_idx < 3:
            signals.append([t, close, low, stop, "-", "-", "-", "-", "-", "-", "-", "-", "-", "WAITING", "-"])
            continue
        
        # 2-CANDLE: need red(-3), green(-2), and close > prev_trade_at
        c3 = candles[idx - 3]
        c2 = candles[idx - 2]
        
        c3_open = float(c3['into'])
        c3_close = float(c3['intc'])
        c3_red = c3_close < c3_open
        
        c2_open = float(c2['into'])
        c2_close = float(c2['intc'])
        c2_green = c2_close > c2_open
        
        two_candle_triggered = c3_red and c2_green and close < target and close > prev_trade_at
        
        # Determine signal and action
        if breakout_triggered:
            signal = "BREAKOUT"
            action = "ENTRY"
            prev_trade_at = stop  # Reset to stop
            armed_idx = idx + 1  # Mark this candle as the trigger point
        elif two_candle_triggered:
            signal = "2-CANDLE"
            action = "ENTRY"
            prev_trade_at = close  # Update to current close
            armed_idx = idx + 1
        else:
            signal = "-"
            action = "WAITING"
        
        # Determine bot column
        if action == "ENTRY":
            if t in bot_sym_entries:
                bot_col = "BOT"
            else:
                bot_col = "-"
        else:
            bot_col = "-"
        
        signals.append([
            t, close, low, stop,
            c3_open, c3_close, "RED" if c3_red else "GREEN",
            c2_open, c2_close, "GREEN" if c2_green else "RED",
            prev_trade_at, target,
            signal, action, bot_col
        ])
    
    return signals

# Process all symbols
file_count = 0

for i, sym in enumerate(call_symbols, 1):
    stop = get_stop(sym)
    if stop:
        signals = generate_backtest(sym, stop, sessions, bot_entries)
        file_count += 1
        filename = f"{S_DATA}{i}_{sym}.csv"
        
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["#", f"symbol={sym}"])
            writer.writerow(["#", f"stop={stop}"])
            writer.writerow(["#", f"target={stop * 1.5}"])
            writer.writerow(["#", f"sessions={','.join(sessions)}"])
            writer.writerow(["time", "price", "low", "stop", "c3_open", "c3_close", "c3_color", "c2_open", "c2_close", "c2_color", "prev_trade_at", "target", "signal", "action", "bot"])
            writer.writerows(signals)
        
        print(f"Created {filename}")

for i, sym in enumerate(put_symbols, start=len(call_symbols)+1):
    stop = get_stop(sym)
    if stop:
        signals = generate_backtest(sym, stop, sessions, bot_entries, is_put=True)
        file_count += 1
        filename = f"{S_DATA}{i}_{sym}.csv"
        
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["#", f"symbol={sym}"])
            writer.writerow(["#", f"stop={stop}"])
            writer.writerow(["#", f"target={stop * 1.5}"])
            writer.writerow(["#", f"sessions={','.join(sessions)}"])
            writer.writerow(["time", "price", "low", "stop", "c3_open", "c3_close", "c3_color", "c2_open", "c2_close", "c2_color", "prev_trade_at", "target", "signal", "action", "bot"])
            writer.writerows(signals)
        
        print(f"Created {filename}")

print(f"Total files created: {file_count}")