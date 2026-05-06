"""
Simulate CandleManager - generates ticks until Ctrl+C.
Run with: uv run python scripts/simulate_candle.py
Press Ctrl+C to stop.
"""
import random
import time
import pendulum as pdlm
from src.providers.candle_manager import CandleManager

cm = CandleManager()

print("=== Simulating ticks (Ctrl+C to stop) ===\n")

tick_count = 0

try:
    while True:
        tick_count += 1
        
        # Generate random price
        price = round(100 + random.uniform(-5, 10), 2)
        cm.add_tick(price)
        
        # Print tick arrival
        now = pdlm.now("Asia/Kolkata")
        cur = cm._current
        print(f"tick {tick_count}: price={price} | current: O={cur['open']}, H={cur['high']}, L={cur['low']}, C={cur['close']} | {now.strftime('%H:%M:%S')}")
        
        # Small sleep to see output
        time.sleep(0.2)
        
except KeyboardInterrupt:
    print("\n=== Stopped ===")
    
    df = cm.transform()
    print(f"\nCompleted: {len(cm._completed)}")
    
    if not df.empty:
        print("\n=== All Candles ===")
        print(df.to_string(index=False))
    
    if cm._current:
        print(f"\nCurrent: O={cm._current['open']}, H={cm._current['high']}, L={cm._current['low']}, C={cm._current['close']}")