# tests/test_symbol.py

from src.sdk.symbol import Symbol


def test_symbol_creation():
    sym = Symbol(
        base="SENSEX",
        symbol="BSXOPT",
        option_exchange="BFO",
        moneyness=-1,
        expiry="05-AUG-2025",
        quantity=20,
        rest_min=2,
        diff=100,
        index="BSE Sensex",
        exchange="BSE",
        token="1",
        depth=10,
        atm=81000,
    )

    assert sym.base == "SENSEX"
    assert sym.symbol == "BSXOPT"
    assert sym.option_exchange == "BFO"
    assert sym.quantity == 20
    assert sym.atm == 81000
