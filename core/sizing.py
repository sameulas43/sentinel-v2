"""
SENTINEL V2.0 — Sizing Module

SOURCE DE PRIX : IBKR uniquement via Execution Agent → GET /price/{ticker}

yfinance est INTERDIT pour toute décision de trading.
IBKR est la source unique de vérité pour les prix.
"""
import requests
from core.config import VPS_URL, AGENT_SECRET
from core.fractional_rules import supports_fractional, round_quantity, min_quantity
from core.logger import get_logger

log = get_logger("sizing")


def get_price_from_ibkr(ibkr_ticker: str) -> dict | None:
    if not VPS_URL:
        log("sizing.no_vps", {"ticker": ibkr_ticker}, level="error")
        return None
    try:
        r = requests.get(
            f"{VPS_URL}/price/{ibkr_ticker}",
            headers={"Authorization": f"Bearer {AGENT_SECRET}"},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
        log("sizing.price_error", {"ticker": ibkr_ticker, "status": r.status_code}, level="warning")
    except Exception as e:
        log("sizing.vps_error", {"ticker": ibkr_ticker, "error": str(e)}, level="error")
    return None


def compute_quantity(ibkr_ticker: str, montant_eur: float) -> dict:
    if montant_eur < 1.0:
        return {"ok": False, "reject_reason": "Montant < 1EUR refuse"}

    price_data = get_price_from_ibkr(ibkr_ticker)
    if not price_data:
        return {
            "ok": False,
            "reject_reason": f"Prix IBKR indisponible pour {ibkr_ticker}. VPS ou IB Gateway inactif.",
        }

    price_eur = price_data.get("price_eur", 0)
    if price_eur <= 0:
        return {"ok": False, "reject_reason": f"Prix EUR invalide pour {ibkr_ticker}"}

    quantity_raw = montant_eur / price_eur
    quantity     = round_quantity(ibkr_ticker, quantity_raw)
    min_qty      = min_quantity(ibkr_ticker)

    if quantity < min_qty:
        return {"ok": False, "reject_reason": f"{ibkr_ticker} : quantite {quantity} < minimum {min_qty}"}

    result = {
        "ok":           True,
        "ticker":       ibkr_ticker,
        "quantity":     quantity,
        "price_local":  price_data.get("price_local", 0),
        "currency":     price_data.get("currency", "USD"),
        "eur_rate":     price_data.get("eur_rate", 1.0),
        "price_eur":    round(price_eur, 4),
        "montant_eur":  montant_eur,
        "montant_reel": round(quantity * price_eur, 2),
        "fractional":   supports_fractional(ibkr_ticker) and (quantity % 1 != 0),
        "reject_reason": None,
        "source":       "ibkr",
    }
    log("sizing.computed", result)
    return result
