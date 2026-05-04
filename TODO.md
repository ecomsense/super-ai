# TODO: Concurrent RAM Strategy Implementation

## Problem Statement

**Issue:** PE trade missed at 9:18 AM on 2026-04-30

**Root Cause:** CE and PE RAM strategies run sequentially in the main engine loop. When CE is busy (placing orders, managing positions), PE candles may not get processed, causing missed signals.

**Evidence:** 
- 09:17:44 - CE BUY order placed (automated)
- 09:18:58 - CE BUY order placed (automated)
- 09:19:46 - PE BUY order placed (MANUAL - customer punched)
- No automated PE orders found in logs (`remarks: 'ram'`)

**Solution:** 
1. Run CE and PE RAM strategies in parallel using `concurrent.futures.ThreadPoolExecutor`
2. Fetch position book ONCE per tick (before threads) to avoid rate limits
3. Pass position snapshot to all strategy threads

---

## Task Breakdown

| # | Task | File(s) | Parallel | Dependencies | Est. Time |
|---|------|---------|----------|--------------|-----------|
| 1 | Add position book snapshot to engine tick | `src/core/engine.py`, `src/providers/risk_manager.py` | ❌ | None | 20 min |
| 2 | Make RiskManager.new() thread-safe | `src/providers/risk_manager.py` | ❌ | Task 1 | 20 min |
| 3 | Add ThreadPoolExecutor to RAM strategy | `src/strategies/ram.py` | ❌ | Task 2 | 30 min |
| 4 | Update engine to submit strategies concurrently | `src/core/engine.py` | ❌ | Task 3 | 20 min |
| 5 | Add graceful shutdown handling | `src/strategies/ram.py`, `src/core/engine.py` | ❌ | Task 4 | 20 min |
| 6 | Add logging for thread execution | `src/strategies/ram.py` | ✅ | Task 3 | 15 min |
| 7 | Test concurrent execution with mock data | `tests/unit/test_ram_concurrent.py` | ❌ | Task 5, 6 | 30 min |

**Total Estimated Time:** ~2.5 hours

---

## Key Design Decision: Position Book Snapshot

**Problem:** If each thread calls `self.broker.positions` repeatedly, we hit API rate limits.

**Solution:** Fetch position book ONCE in `engine.tick()` before submitting threads, pass snapshot to all strategies.

```python
# In engine.py
def tick(self, rest, quote, live):
    # Fetch position book ONCE (before threads)
    position_book = rest.positions()
    
    # Submit strategies with position snapshot
    futures = []
    for strategy in self.strategies:
        future = self.executor.submit(strategy.run, quotes, position_book)
        futures.append(future)
    
    wait(futures, timeout=5.0)
```

**Benefits:**
- 50% reduction in API calls (1 vs 2 per tick)
- Consistent position state across all strategies
- No rate limit issues
- Simpler RiskManager (no locking on reads)

---

## Task Details

### Task 1: Add Position Book Snapshot to Engine Tick

**Files:** `src/core/engine.py`, `src/providers/risk_manager.py`

**Changes:**
1. In `engine.py`: Fetch `position_book = rest.positions()` at start of `tick()`
2. In `engine.py`: Pass `position_book` to `strategy.run(quotes, position_book)`
3. In `risk_manager.py`: Add `get_position_snapshot()` method that returns current positions list
4. Remove `self.broker.positions` calls from inside strategy threads

**Code Sketch:**
```python
# engine.py
def tick(self, rest, quote, live):
    # Fetch position book ONCE before threads
    position_book = rest.positions()
    
    # Submit strategies with position snapshot
    for strgy in self.strategies:
        strgy.run(quote.get_quotes(), position_book)
```

**Acceptance Criteria:**
- [ ] Position book fetched once per tick (not per strategy)
- [ ] All strategies receive same position snapshot
- [ ] No API calls to `broker.positions` from within threads
- [ ] Logs show position snapshot timing

---

### Task 2: Make RiskManager.new() Thread-Safe

**File:** `src/providers/risk_manager.py`

**Changes:**
1. Import `threading` module
2. Add `self._lock = threading.Lock()` in `__init__`
3. Wrap `new()` method body with `with self._lock:`
4. Keep `_get_pos_from_api()` unlocked (called before threads)
5. Keep `_read_position()` and `_write_position()` unlocked (use snapshot)

**Code Sketch:**
```python
import threading

class RiskManager:
    def __init__(self, stock_broker):
        self.broker = stock_broker
        self._lock = threading.Lock()
        self.positions = []
    
    def new(self, symbol, exchange, quantity, entry_price, stop_loss, target, tag="no_tag"):
        with self._lock:
            # Order placement logic (thread-safe)
            order_no = self.broker.order_place(...)
            # Update internal state
            self.positions.append(position)
            return position.id
```

**Acceptance Criteria:**
- [ ] `RiskManager.new()` can be called from 2+ threads simultaneously
- [ ] No race conditions on `self.positions` list
- [ ] Order placement is atomic (no duplicate orders)
- [ ] Performance overhead < 5ms per call

---

### Task 3: Add ThreadPoolExecutor to RAM Strategy

**File:** `src/strategies/ram.py`

**Changes:**
1. Import `concurrent.futures.ThreadPoolExecutor`
2. Add `self.executor = ThreadPoolExecutor(max_workers=1)` in `__init__`
3. Rename `run()` to `_run_impl()` (actual logic)
4. Add new `run()` that submits to executor and returns `Future`
5. Add `shutdown()` method to cleanup executor
6. Accept `position_book` parameter in `run()`

**Code Sketch:**
```python
from concurrent.futures import ThreadPoolExecutor

class Ram:
    def __init__(self, **kwargs):
        # ... existing init ...
        self.executor = ThreadPoolExecutor(max_workers=1)
        self._running = True
    
    def run(self, quotes, position_book):
        """Submit to executor, return immediately."""
        return self.executor.submit(self._run_impl, quotes, position_book)
    
    def _run_impl(self, quotes, position_book):
        """Actual strategy logic (existing run() body)."""
        thread_id = threading.current_thread().name
        logging.info(f"[{thread_id}] {self._tradingsymbol} processing tick")
        # ... existing logic ...
    
    def shutdown(self):
        self._running = False
        self.executor.shutdown(wait=True)
```

**Acceptance Criteria:**
- [ ] Each RAM strategy runs in its own thread
- [ ] `run()` returns `Future` object immediately (non-blocking)
- [ ] `shutdown()` cleanly stops executor
- [ ] No threads left running after shutdown

---

### Task 4: Update Engine to Submit Strategies Concurrently

**File:** `src/core/engine.py`

**Changes:**
1. Add `from concurrent.futures import ThreadPoolExecutor, wait`
2. Add `self.executor = ThreadPoolExecutor(max_workers=10)` in `__init__`
3. In `tick()`: Submit all strategies to executor
4. Use `wait(futures, timeout=5.0)` to wait for completion
5. Handle exceptions from futures
6. Add `shutdown()` method to engine

**Code Sketch:**
```python
from concurrent.futures import ThreadPoolExecutor, wait

class Engine:
    def __init__(self, start, stop):
        # ... existing init ...
        self.executor = ThreadPoolExecutor(max_workers=10)
    
    def tick(self, rest, quote, live):
        # Fetch position book ONCE
        position_book = rest.positions()
        
        # Submit all strategies concurrently
        futures = []
        for strgy in self.strategies:
            future = strgy.run(quote.get_quotes(), position_book)
            futures.append(future)
        
        # Wait for all to complete
        done, not_done = wait(futures, timeout=5.0)
        
        # Handle exceptions
        for future in done:
            try:
                future.result()
            except Exception as e:
                logging.error(f"Strategy error: {e}")
    
    def shutdown(self):
        for strgy in self.strategies:
            strgy.shutdown()
        self.executor.shutdown(wait=True)
```

**Acceptance Criteria:**
- [ ] All strategies run concurrently
- [ ] Engine waits for strategy completion before next tick
- [ ] Exceptions from strategies are logged, not crashed
- [ ] `shutdown()` called on market close

---

### Task 5: Add Graceful Shutdown Handling

**Files:** `src/strategies/ram.py`, `src/core/engine.py`, `src/main.py`

**Changes:**
1. Add `shutdown()` method to `Ram` class (Task 3)
2. Add `shutdown()` method to `Engine` class (Task 4)
3. In `main.py`: Wrap engine loop in try/except
4. Handle `KeyboardInterrupt` and call `engine.shutdown()`
5. Handle market close time and call `engine.shutdown()`

**Code Sketch:**
```python
# main.py
try:
    while not is_time_past(engine.stop):
        # ... existing loop ...
        engine.tick(rest, quote, live)
except KeyboardInterrupt:
    logging.info("KeyboardInterrupt received, shutting down")
    engine.shutdown()
    sys.exit()
```

**Acceptance Criteria:**
- [ ] Clean shutdown on `KeyboardInterrupt` (Ctrl+C)
- [ ] Clean shutdown on market close time
- [ ] No orphaned threads after shutdown
- [ ] All pending orders handled before shutdown

---

### Task 6: Add Logging for Thread Execution

**File:** `src/strategies/ram.py`

**Changes:**
1. Import `threading` module
2. Add thread ID to all log messages in `_run_impl()`
3. Log strategy start/stop events
4. Log signal detection with thread info
5. Log order placement timing

**Code Sketch:**
```python
import threading

def _run_impl(self, quotes, position_book):
    thread_id = threading.current_thread().name
    logging.info(f"[{thread_id}] {self._tradingsymbol} starting tick")
    
    # ... existing logic ...
    
    if signal_detected:
        logging.info(f"[{thread_id}] Signal detected for {self._tradingsymbol} @ {self._last_price}")
        self._on_signal(curr_idx)
```

**Acceptance Criteria:**
- [ ] All log messages include thread ID (e.g., `[ThreadPoolExecutor-1_0]`)
- [ ] Can distinguish CE vs PE thread in logs
- [ ] Signal detection logged with timestamp and price
- [ ] Order placement logged with thread info

---

### Task 7: Test Concurrent Execution

**File:** `tests/unit/test_ram_concurrent.py`

**Changes:**
1. Create mock quotes generator
2. Create mock RiskManager (no real orders)
3. Create CE and PE RAM strategy instances
4. Run both strategies concurrently
5. Verify both process signals independently
6. Verify no race conditions on shared state

**Code Sketch:**
```python
def test_concurrent_ram_strategies():
    ce_strategy = Ram(tradingsymbol="NIFTY05MAY26C23700", ...)
    pe_strategy = Ram(tradingsymbol="NIFTY05MAY26P23900", ...)
    
    # Mock quotes
    quotes = {
        "NIFTY05MAY26C23700": 340.0,
        "NIFTY05MAY26P23900": 160.0,
    }
    
    # Mock position book
    position_book = []
    
    # Run concurrently
    ce_future = ce_strategy.run(quotes, position_book)
    pe_future = pe_strategy.run(quotes, position_book)
    
    # Wait for completion
    ce_future.result(timeout=5.0)
    pe_future.result(timeout=5.0)
    
    # Verify both processed
    assert ce_strategy._last_price == 340.0
    assert pe_strategy._last_price == 160.0
```

**Acceptance Criteria:**
- [ ] Test passes consistently (no flakiness)
- [ ] Both strategies process quotes independently
- [ ] No race conditions detected
- [ ] Test completes in < 10 seconds

---

## Code Quality Analysis & Refactoring Recommendations

After reviewing `ram.py`, `risk_manager.py`, and `engine.py`, here are quality issues and refactoring suggestions:

### Critical Issues

| File | Line | Issue | Severity | Fix |
|------|------|-------|----------|-----|
| `ram.py` | 32-39 | Blocking loop in `__init__` waits for API | 🔴 High | Move to async init or factory function |
| `risk_manager.py` | 17, 108 | `self.broker.positions` called multiple times | 🔴 High | Cache positions, use snapshot (Task 1) |
| `risk_manager.py` | 99-139 | `status()` has confusing return values (0, qty, -1) | 🟡 Medium | Return enum or raise exceptions |
| `engine.py` | 30-37 | Commented-out code | 🟢 Low | Remove dead code |

---

### Refactoring Recommendations

#### 1. **ram.py: Remove Blocking Loop from `__init__`**

**Current:**
```python
def __init__(self, **kwargs):
    # ...
    self._stop = None
    while self._stop is None:  # BLOCKING!
        timer(0.5)
        self._stop = kwargs["rest"].history(...)
```

**Problem:** Blocks thread initialization, delays strategy startup.

**Suggested Fix:**
```python
@classmethod
def create(cls, **kwargs):
    """Factory method that handles async initialization."""
    instance = cls(**kwargs)
    instance._stop = None
    while instance._stop is None:
        timer(0.5)
        instance._stop = kwargs["rest"].history(...)
    return instance
```

**Benefit:** Clear separation of concerns, easier to test.

---

#### 2. **risk_manager.py: Extract Position Book Logic**

**Current:**
```python
def _get_pos_from_api(self, symbol: str):
    positions = self.broker.positions  # API call every time!
    return next((p for p in positions if p["symbol"] == symbol), {})
```

**Problem:** Called multiple times per tick, hits rate limits.

**Suggested Fix:**
```python
def refresh_positions(self, position_book: list):
    """Update internal state from snapshot (called once per tick)."""
    self.positions = position_book

def _get_position(self, symbol: str) -> dict:
    """Get position from cached snapshot (no API call)."""
    return next((p for p in self.positions if p.get("symbol") == symbol), {})
```

**Benefit:** No API calls during strategy execution, consistent state.

---

#### 3. **risk_manager.py: Use Enum for Status Return Values**

**Current:**
```python
def status(self, pos_id: str, last_price: float) -> int:
    # Returns: 0 (success), qty (pending), -1 (error)
    # Confusing!
```

**Suggested Fix:**
```python
from enum import IntEnum

class ExitStatus(IntEnum):
    SUCCESS = 0
    PENDING = 1
    ERROR = -1
    NO_POSITION = -2

def status(self, pos_id: str, last_price: float) -> ExitStatus:
    if symbol is None:
        return ExitStatus.NO_POSITION
    if order_no:
        return ExitStatus.SUCCESS
    return ExitStatus.PENDING
```

**Benefit:** Clear semantics, type-safe, easier to handle in caller.

---

#### 4. **engine.py: Remove Dead Code**

**Current:**
```python
def tick(self, rest, quote, live):
    """
    # Get the run arguments dynamically
    trades = rest.trades()
    needs_position = any(...)
    positions = rest.positions() if needs_position else None
    """
    # ... actual code ...
```

**Problem:** Commented code is technical debt.

**Suggested Fix:** Delete lines 30-44 (commented block).

**Benefit:** Cleaner code, less confusion.

---

#### 5. **ram.py: Extract Magic Numbers to Constants**

**Current:**
```python
if curr_idx < 4 or (curr_idx - self._armed_idx) < 3:
    return
```

**Problem:** Magic numbers (4, 3) are unclear.

**Suggested Fix:**
```python
# At class level
MIN_CANDLES_REQUIRED = 4
MIN_CANDLES_BETWEEN_TRADES = 3

# In method
if curr_idx < self.MIN_CANDLES_REQUIRED or \
   (curr_idx - self._armed_idx) < self.MIN_CANDLES_BETWEEN_TRADES:
    return
```

**Benefit:** Self-documenting code, easier to tune parameters.

---

#### 6. **ram.py: Use Dataclass for Strategy Config**

**Current:**
```python
def __init__(self, **kwargs):
    self._tradingsymbol = kwargs["tradingsymbol"]
    self._last_price = kwargs.get("ltp", float("inf"))
    self.strategy = kwargs["strategy"]
    # ... 20+ lines of kwargs extraction ...
```

**Suggested Fix:**
```python
from dataclasses import dataclass

@dataclass
class RamConfig:
    tradingsymbol: str
    strategy: str
    stop_time: pdlm.DateTime
    rm: RiskManager
    option_exchange: str
    quantity: int
    ltp: float = float("inf")
    target: str = "50%"
    rest_time: dict = None

class Ram:
    def __init__(self, config: RamConfig):
        self._tradingsymbol = config.tradingsymbol
        self._last_price = config.ltp
        # ...
```

**Benefit:** Type-safe, IDE autocomplete, easier to validate.

---

#### 7. **engine.py: Separate UI Logic from Engine**

**Current:**
```python
def tick(self, rest, quote, live):
    # ...
    tbl_rich = []
    for strgy in self.strategies:
        strgy.run(quote.get_quotes())
        tbl_rich.append(generate_table(strgy))  # UI coupling!
    live.update(Columns(tbl_rich))
```

**Problem:** Engine is coupled to Rich UI library.

**Suggested Fix:**
```python
def tick(self, rest, quote):
    """Pure logic, no UI."""
    for strgy in self.strategies:
        strgy.run(quote.get_quotes())
    self.strategies = [s for s in self.strategies if not s._removable]

def render(self, live):
    """Separate UI rendering."""
    tbl_rich = [generate_table(s) for s in self.strategies]
    live.update(Columns(tbl_rich))
```

**Benefit:** Engine can be tested without UI, easier to swap UI frameworks.

---

### Priority Order for Refactoring

| Priority | Refactoring | Effort | Impact |
|----------|-------------|--------|--------|
| 🔴 P0 | Position book snapshot (Task 1) | Low | High |
| 🔴 P0 | Thread-safe RiskManager (Task 2) | Low | High |
| 🟡 P1 | Remove dead code (engine.py) | Trivial | Medium |
| 🟡 P1 | Status enum (risk_manager.py) | Low | Medium |
| 🟢 P2 | Extract magic numbers (ram.py) | Low | Low |
| 🟢 P2 | Dataclass config (ram.py) | Medium | Medium |
| 🟢 P2 | Separate UI logic (engine.py) | Medium | Medium |

---

### Summary

**Must-do for concurrent execution:**
1. Position book snapshot (Task 1)
2. Thread-safe `RiskManager.new()` (Task 2)

**Should-do for code quality:**
3. Remove dead code
4. Status enum for clarity

**Nice-to-have:**
5. Magic number extraction
6. Dataclass config
7. UI separation

---

**Recommendation:** Implement Tasks 1-7 first (concurrent execution), then tackle P1/P2 refactoring in a separate PR.

---

## Rollback Plan

If concurrent execution causes issues:
1. Revert `engine.py` to sequential strategy iteration
2. Keep `RiskManager` thread-safety (no harm)
3. Debug issues in isolation
4. Re-enable concurrent execution after fix

---

## Success Metrics

| Metric | Before | After |
|--------|--------|-------|
| Signal detection latency | ~1-2 sec | < 500ms |
| Missed signals per day | 1-2 | 0 |
| Max concurrent strategies | 1 | 10+ |
| Thread count | 1 | 3 (main + CE + PE) |

---

## Implementation Order

```
Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6 → Task 7
   │        │        │        │        │        │        │
   ▼        ▼        ▼        ▼        ▼        ▼        ▼
 Position  Thread   RAM     Engine  Shutdown Logging  Tests
 Snapshot  Safety   Executor
```

**Parallel Execution:** Task 6 (Logging) can be done in parallel with Task 4-5

---

## Rollback Plan

If concurrent execution causes issues:
1. Revert `engine.py` to sequential strategy iteration
2. Keep `RiskManager` thread-safety (no harm)
3. Keep position book snapshot (reduces API calls)
4. Debug issues in isolation
5. Re-enable concurrent execution after fix

---

## Success Metrics

| Metric | Before | After |
|--------|--------|-------|
| Signal detection latency | ~1-2 sec | < 500ms |
| Missed signals per day | 1-2 | 0 |
| API calls per tick | 2+ (CE + PE) | 1 (snapshot) |
| Max concurrent strategies | 1 | 10+ |
| Thread count | 1 | 3 (main + CE + PE) |

---

## Notes

- **Only RAM strategy** - All other strategies deprecated
- **No changes to candle logic** - only execution model changes
- **Maintain existing signal conditions** - breakout + two-candle pattern unchanged
- **Backward compatible** - existing strategies work without modification
- **Scalable** - can add more strategies without performance degradation
- **Rate limit safe** - position book fetched once per tick

---

## Future Improvement: Position Sync (2026-05-03)

**Issue:** Internal positions can drift from broker API state.

**Problem:** Two sources of position data:
1. `position_book` passed from engine tick
2. `_get_pos_from_api()` called internally in RiskManager

**Risk:** Manual trades outside system, API delays, partial fills can cause sync issues.

**Solution:** Update internal positions whenever we fetch from broker API:

```python
def _get_pos_from_api(self, symbol: str):
    api_pos = self.broker.positions
    broker_qty = next((p for p in api_pos if p["symbol"] == symbol), {}).get("quantity", 0)
    
    # Sync internal state
    internal = self._read_position(symbol)
    if internal:
        internal.quantity = broker_qty
    
    return broker_qty
```

**Benefits:**
- Single source of truth
- Fallback ready if API fails
- Remove need to pass position_book around

**Status:** TODO - wait for trading to stabilize after thread/futures changes

---

**Status:** Ready for implementation  
**Created:** 2026-04-30  
**Updated:** 2026-05-03 (added position sync improvement)  
**Priority:** Medium

---

## Task Progress

| # | Task | Status | Completed |
|---|------|--------|-----------|
| 1 | Position book snapshot | ✅ Done | 2026-04-30 |
| 2 | Thread-safe RiskManager.new() | ⏳ Pending | - |
| 3 | ThreadPoolExecutor to RAM | ⏳ Pending | - |
| 4 | Engine concurrent submission | ⏳ Pending | - |
| 5 | Graceful shutdown | ⏳ Pending | - |
| 6 | Logging for threads | ⏳ Pending | - |
| 7 | Test concurrent execution | ⏳ Pending | - |

## Task Progress

| # | Task | Status | Completed |
|---|------|--------|-----------|
| 1 | Position book snapshot | ✅ Done | 2026-04-30 |
| 2 | Thread-safe RiskManager.new() | ✅ Done | 2026-04-30 |
| 3 | ThreadPoolExecutor to RAM | ⏳ Pending | - |
| 4 | Engine concurrent submission | ⏳ Pending | - |
| 5 | Graceful shutdown | ⏳ Pending | - |
| 6 | Logging for threads | ⏳ Pending | - |
| 7 | Test concurrent execution | ⏳ Pending | - |

## Milestone: Concurrent Execution (2026-04-30)

### Completed
- ✅ Task 1: Position book snapshot in engine tick
- ✅ Task 2: Thread-safe RiskManager.new() with threading.Lock()

### Not Going to Implement (Tasks 3-7)
**Reason:** Only one RAM strategy type exists. CE and PE share the same RiskManager instance, created once. No actual concurrency benefit needed for single-strategy setup.

**Tasks kept for reference:**
- Task 3: ThreadPoolExecutor to RAM
- Task 4: Engine concurrent submission
- Task 5: Graceful shutdown
- Task 6: Logging for threads
- Task 7: Test concurrent execution

### Rollback Plan
If concurrent execution causes issues:
1. Revert `engine.py` to sequential strategy iteration
2. Keep `RiskManager` thread-safety (no harm)
3. Keep position book snapshot (reduces API calls)
4. Debug issues in isolation
5. Re-enable concurrent execution after fix

