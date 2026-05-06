"""
Simulate CandleManager - manual minute advancement
Run with: uv run python scripts/simulate_candle.py
"""
import pendulum as pdlm
from src.providers.candle_manager import CandleManager

cm = CandleManager()

# Start with a base minute
base = pdlm.now("Asia/Kolkata").start_of("minute")

# Simulate ticks arriving in real time pattern
print("=== Minute 0 (initial) ===")
cm._current = {"open": 100.0, "high": 105.0, "low": 98.0, "close": 103.0, "minute": base}

df = cm.transform()
print(df.to_string(index=False))

# Simulate transition to next minute
print("\n=== After minute change ===")
# Manually simulate what happens when new minute arrives
cm._completed.append(cm._current)
cm._current = {"open": 103.0, "high": 103.0, "low": 103.0, "close": 103.0, "minute": base.add(minutes=1)}
cm.add_tick(104.0)  # New tick

df = cm.transform()
print(df.to_string(index=False))

# Add more ticks in minute 1
print("\n=== After more ticks in minute 1 ===")
cm.add_tick(108.0)
cm.add_tick(101.0)

df = cm.transform()
print(df.to_string(index=False))

# Show completed count
print(f"\nCompleted: {len(cm._completed)}, Current: {cm._current}")