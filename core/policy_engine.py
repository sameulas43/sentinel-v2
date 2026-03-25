import json
import os

_DIR = os.path.join(os.path.dirname(__file__), "..", "policies")


def _load(name: str) -> dict:
    with open(os.path.join(_DIR, f"{name}.json")) as f:
        return json.load(f)


def get_allocation() -> dict:      return _load("allocation")
def get_risk_rules() -> dict:      return _load("risk_rules")
def get_halal_blacklist() -> dict: return _load("halal_blacklist")
def is_paper_mode() -> bool:       return get_risk_rules().get("paper_mode", True)

def is_halal(ticker: str) -> bool:
    return ticker not in get_halal_blacklist().get("tickers", [])
