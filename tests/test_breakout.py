# File: tests/test_breakout.py

# Assuming your concrete class is named Breakout
# and is located in src/priveders/breakout.py

from src.providers.time_manager import SimpleBucket


def test_simple_bucket():
    b = SimpleBucket(bucket_time={"minutes": 1})

    b.set_bucket()

    flag = b.is_bucket()
    assert not flag
