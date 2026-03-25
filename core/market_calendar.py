from datetime import datetime, time
import pytz

_HOURS: dict[str, tuple] = {
    "NYSE":    ("America/New_York", time(9, 30),  time(16, 0)),
    "NASDAQ":  ("America/New_York", time(9, 30),  time(16, 0)),
    "ARCA":    ("America/New_York", time(9, 30),  time(16, 0)),
    "LSE":     ("Europe/London",    time(8, 0),   time(16, 30)),
}

_MAP: dict[str, str] = {
    "PHAG": "LSE",   "SGOL": "ARCA",  "ICLN": "NASDAQ",
    "ENPH": "NASDAQ","MOO":  "ARCA",  "DBA":  "ARCA",
    "SPUS": "ARCA",  "HLAL": "ARCA",  "PHO":  "NASDAQ",
}


def is_market_open(ticker: str) -> tuple[bool, str]:
    ex              = _MAP.get(ticker, "NYSE")
    tz_name, op, cl = _HOURS[ex]
    now             = datetime.now(pytz.timezone(tz_name))

    if now.weekday() >= 5:
        return False, f"Week-end — {ex} fermé"

    t = now.time().replace(second=0, microsecond=0)
    if not (op <= t <= cl):
        return False, f"{ex} fermé (heure locale : {t})"

    return True, f"{ex} ouvert"
