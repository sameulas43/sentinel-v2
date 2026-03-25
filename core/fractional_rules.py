"""Règles fractional shares par ticker IBKR."""

FRACTIONAL_BY_TICKER: dict[str, bool] = {
    "SGOL": True,  "PHAG": False, "ICLN": True,
    "ENPH": True,  "MOO":  True,  "DBA":  True,
    "SPUS": True,  "HLAL": True,  "PHO":  True,
}

DECIMALS_BY_TICKER: dict[str, int] = {
    "SGOL": 4, "PHAG": 0, "ICLN": 4,
    "ENPH": 4, "MOO":  4, "DBA":  4,
    "SPUS": 4, "HLAL": 4, "PHO":  4,
}

MIN_QTY_BY_TICKER: dict[str, float] = {
    "SGOL": 0.001, "PHAG": 1.0,   "ICLN": 0.001,
    "ENPH": 0.001, "MOO":  0.001, "DBA":  0.001,
    "SPUS": 0.001, "HLAL": 0.001, "PHO":  0.001,
}


def supports_fractional(ticker: str) -> bool:
    return FRACTIONAL_BY_TICKER.get(ticker, False)

def round_quantity(ticker: str, qty: float) -> float:
    d = DECIMALS_BY_TICKER.get(ticker, 4)
    return float(int(qty)) if d == 0 else round(qty, d)

def min_quantity(ticker: str) -> float:
    return MIN_QTY_BY_TICKER.get(ticker, 1.0)
