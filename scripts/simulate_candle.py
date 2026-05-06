"""
Simulate CandleManager - show ticks flowing into add_tick each second.
Run with: uv run python scripts/simulate_candle.py
Takes 4 REAL minutes (240 seconds).
"""
import random
import time
import pendulum as pdlm
from src.providers.candle_manager import CandleManager

cm = CandleManager()

print(f"Start: {pdlm.now('Asia/Kolkata').strftime('%H:%M:%S')}")
print("=== Simulating ticks at 1 per second ===\n")
print("Each minute = 60 seconds")
print("Total: 4 minutes = 240 seconds\n")

# 1 tick per second for 4 minutes = 240 ticks
tick_count = 0

while tick_count < 240:
    tick_count += 1
    
    price = round(100 + random.uniform(-5, 10), 2)
    cm.add_tick(price)
    
    # Show tick arriving (every 10 ticks to reduce noise)
    if tick_count % 10 == 0:
        now = pdlm.now("Asia/Kolkata")
        print(f"  tick {tick_count}: add_tick({price}) at {now.strftime('%H:%M:%S')}")
    
    # Show candle state at end of each minute
    if tick_count % 60 == 0:
        df = cm.transform()
        if not df.empty:
            minute_num = tick_count // 60
            row = df.iloc[-1]
            print(f"  --- Minute {minute_num} ended ---")
            print(f"  O={row['open']}, H={row['high']}, L={row['low']}, C={row['close']}")
            print()
    
    time.sleep(1)  # 1 second between ticks
    
print(f"End: {pdlm.now('Asia/Kolkata').strftime('%H:%M:%S')}")
print("\n=== Final Candles ===")
df = cm.transform()
print(df.to_string(index=False))
print(f"\nCompleted: {len(cm._completed)}")
print(f"Current: {cm._current}")