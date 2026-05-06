"""
Simulate CandleManager - shows transform() output like strategy.
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
        
        # Get candles like strategy does
        candle = cm.transform()
        
        if not candle.empty:
            # Show all available candles
            now = pdlm.now("Asia/Kolkata")
            print(f"\ntick {tick_count} at {now.strftime('%H:%M:%S')}:")
            
            for i in range(len(candle)):
                row = candle.iloc[i]
                idx = len(candle) - 1 - i
                print(f"  [{idx}] O={row['open']}, H={row['high']}, L={row['low']}, C={row['close']}")
        
        time.sleep(0.3)
        
except KeyboardInterrupt:
    print("\n=== Stopped ===")
    
    candle = cm.transform()
    print(f"\nTotal candles: {len(candle)}")
    
    if not candle.empty:
        print("\n=== All Candles ===")
        for i in range(len(candle)):
            row = candle.iloc[i]
            print(f"  [{i}] O={row['open']}, H={row['high']}, L={row['low']}, C={row['close']}")