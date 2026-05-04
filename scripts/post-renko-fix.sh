#!/bin/bash
# Post-fix: Verify renko.py fixes and imports
# Issue: renko.py syntax error

echo "=== Post-fix verification ==="

# Verify syntax
if /home/pannet1/py/finvasia/bin/python -c "import ast; ast.parse(open('src/strategies/renko.py').read())" 2>/dev/null; then
    echo "OK: renko.py parses correctly"
else
    echo "FAIL: renko.py still has syntax errors"
fi

# Verify imports
if /home/pannet1/py/finvasia/bin/python -c "
import sys; sys.path.insert(0, '.')
from src.strategies.renko import Renko
print('OK: Renko class loads')
" 2>/dev/null; then
    echo "OK: Renko imports work"
else
    echo "FAIL: Renko import broken"
fi

# Verify all strategies
if /home/pannet1/py/finvasia/bin/python -c "
import sys; sys.path.insert(0, '.')
for s in ['hilo','oblegacy','openingbalance','pivot','pivotindex','ram','renko','rounded']:
    mod = __import__(f'src.strategies.{s}', fromlist=[s.capitalize()])
    getattr(mod, s.capitalize())
print('OK: All 8 strategies load')
" 2>/dev/null; then
    echo "OK: All strategies load"
else
    echo "FAIL: Some strategies broken"
fi
