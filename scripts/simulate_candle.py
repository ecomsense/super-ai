"""
Simulate CandleManager - show ticks flowing into add_tick every ~0.5s.
Run with: uv run python scripts/simulate_candle.py
Takes ~30 seconds for 4 simulated minutes (real time).
"""
import random
import time
import pendulum as pdlm
from src.providers.candle_manager import CandleManager

cm = CandleManager()

print(f"Start: {pdlm.now('Asia/Kolkata').strftime('%H:%M:%S')}")
print("=== Simulating ticks flowing into add_tick() ===\n")

tick_count = 0
minute = 0
ticks_per_minute = 20  # 20 ticks = 1 per 3 seconds (for 60s minute)

while minute < 4:
    tick_count += 1
    
    # Generate price with some variation
    price = round(100 + random.uniform(-5, 10), 2)
    
    # Call add_tick with this price
    cm.add_tick(price)
    
    # Print tick arriving
    now = pdlm.now("Asia/Kolkata")
    print(f"  add_tick({price}) at {now.strftime('%H:%M:%S')}")
    
    # Show after first tick of each minute
    if tick_count % 20 == 1:
        print(f"  --- Minute {minute} started ---")
    
    # Show after last tick of each minute (before new minute)
    if tick_count % 20 == 0:
        df = cm.transform()
        if not df.empty:
            row = df.iloc[-1]
            print(f"  Minute {minute} DONE: O={row['open']}, H={row['high']}, L={row['low']}, C={row['close']}")
        minute += 1
        print()
    
    time.sleep(0.5)  # 500ms between ticks
    
print(f"End: {pdlm.now('Asia/Kolkata').strftime('%H:%M:%S')}")
print("\n=== Final Candles ===")
df = cm.transform()
print(df.to_string(index=False))
print(f"\nCompleted: {len(cm._completed)}, Current: {cm._current}")