# File: tests/test_breakout.py

# Assuming your concrete class is named Breakout
# and is located in src/priveders/breakout.py

from src.providers.breakout import Breakout


def test_breakout():
    b = Breakout(bucket_time={"minutes": 1})

    b.set_bucket()

    flag = b.is_bucket()
    assert not flag
