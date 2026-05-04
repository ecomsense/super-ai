#!/bin/bash
# Pre-fix: Check for renko.py syntax error and broken imports
# Issue: renko.py syntax error

echo "=== Pre-fix checks ==="

# Check syntax error
if grep -q 'return self._trade_manager.complete_exit(\*\*kwargs):' src/strategies/renko.py 2>/dev/null; then
    echo "FAIL: renko.py has stray colon on line 114"
else
    echo "OK: renko.py syntax clean"
fi

# Check broken imports
if grep -q 'from src.helper import' src/strategies/renko.py 2>/dev/null; then
    echo "FAIL: renko.py has wrong import path (src.helper)"
else
    echo "OK: renko.py import paths correct"
fi

if grep -q 'from src.time_manager import' src/strategies/renko.py 2>/dev/null; then
    echo "FAIL: renko.py has wrong import path (src.time_manager)"
else
    echo "OK: renko.py import paths correct"
fi

# Check renkodf
if /home/pannet1/py/finvasia/bin/python -c "import renkodf" 2>/dev/null; then
    echo "OK: renkodf installed"
else
    echo "FAIL: renkodf not installed"
fi
