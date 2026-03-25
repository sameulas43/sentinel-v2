IBKR_TO_YF: dict[str, str] = {
    "PHAG": "PHAG.L",
    "SGOL": "SGOL",
    "ICLN": "ICLN",
    "ENPH": "ENPH",
    "MOO":  "MOO",
    "DBA":  "DBA",
    "SPUS": "SPUS",
    "HLAL": "HLAL",
    "PHO":  "PHO",
}

IBKR_EXCHANGE: dict[str, str] = {
    "PHAG": "LSE",
    "SGOL": "ARCA",
    "ICLN": "NASDAQ",
    "ENPH": "NASDAQ",
    "MOO":  "ARCA",
    "DBA":  "ARCA",
    "SPUS": "ARCA",
    "HLAL": "ARCA",
    "PHO":  "NASDAQ",
}

IBKR_CURRENCY: dict[str, str] = {
    "PHAG": "GBP",
    "SGOL": "USD",
    "ICLN": "USD",
    "ENPH": "USD",
    "MOO":  "USD",
    "DBA":  "USD",
    "SPUS": "USD",
    "HLAL": "USD",
    "PHO":  "USD",
}


def to_yfinance(t: str) -> str:  return IBKR_TO_YF.get(t, t)
def get_exchange(t: str) -> str: return IBKR_EXCHANGE.get(t, "SMART")
def get_currency(t: str) -> str: return IBKR_CURRENCY.get(t, "USD")
