import pytest
import pandas as pd
from src.sdk.helper import compress_candles


def test_compress_candles_daily_ohlc(monkeypatch):
    # Force pandas to think "now" is 2025-09-19 in Asia/Kolkata
    monkeypatch.setattr(
        pd.Timestamp, "now", lambda tz=None: pd.Timestamp("2025-09-19 10:00:00", tz=tz)
    )

    data_now = [
        {
            "time": "18-09-2025 09:15:00",
            "into": "100",
            "inth": "105",
            "intl": "99",
            "intc": "104",
            "v": "1000",
            "oi": "50",
        },
        {
            "time": "18-09-2025 15:30:00",
            "into": "104",
            "inth": "110",
            "intl": "98",
            "intc": "108",
            "v": "2000",
            "oi": "55",
        },
        {
            "time": "19-09-2025 09:15:00",
            "into": "200",
            "inth": "210",
            "intl": "190",
            "intc": "205",
            "v": "3000",
            "oi": "60",
        },
    ]

    result = compress_candles(
        data_now, tz="Asia/Kolkata", return_last_only=True, exclude_today=True
    )

    expected = {
        "into": 100.0,
        "inth": 110.0,
        "intl": 98.0,
        "intc": 108.0,
        "v": 3000.0,
        "oi": 55.0,
        "date": "2025-09-18",
    }

    assert result == expected
