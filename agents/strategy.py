"""
SENTINEL V2.0 — Strategy Agent
Prix via IBKR uniquement. yfinance INTERDIT.
"""
import schedule
import time
import requests
from datetime import date
from core.policy_engine import get_risk_rules, get_allocation
from core.market_calendar import is_market_open
from core.config import VPS_URL, AGENT_SECRET
from core.portfolio import get_portfolio
from core.logger import get_logger

log = get_logger("strategy")


def get_price_ibkr(ticker: str) -> float | None:
    """Prix depuis IBKR via Execution Agent. Seule source autorisée."""
    if not VPS_URL:
        return None
    try:
        r = requests.get(
            f"{VPS_URL}/price/{ticker}",
            headers={"Authorization": f"Bearer {AGENT_SECRET}"},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("price_eur")
    except Exception as e:
        log("strategy.price_error", {"ticker": ticker, "error": str(e)}, level="warning")
    return None


def propose_dca():
    try:
        portfolio = get_portfolio()
    except RuntimeError as e:
        log("strategy.portfolio_unavailable", {"error": str(e)}, level="error")
        return

    rules = get_risk_rules()
    alloc = get_allocation()

    log("strategy.dca_start", {
        "budget": rules["monthly_dca_eur"],
        "month":  date.today().strftime("%Y-%m"),
    })

    for ticker, weight in alloc.items():
        ok, reason = is_market_open(ticker)
        if not ok:
            log("strategy.skip_market", {"ticker": ticker, "reason": reason})
            continue

        montant  = round(rules["monthly_dca_eur"] * weight, 2)
        requires = montant > rules["requires_human_approval_above_eur"]

        from core.flow import run_proposal
        run_proposal({
            "type":                    "trade.proposed",
            "source_agent":            "strategy",
            "ticker":                  ticker,
            "action":                  "BUY",
            "montant_eur":             montant,
            "broker":                  "IBKR",
            "paper_mode":              rules["paper_mode"],
            "requires_human_approval": requires,
            "raison":                  f"DCA {date.today().strftime('%B %Y')}",
        }, portfolio)


def check_dips():
    """Dip detection via prix IBKR uniquement."""
    try:
        portfolio = get_portfolio()
    except RuntimeError as e:
        log("strategy.portfolio_unavailable", {"error": str(e)}, level="error")
        return

    rules = get_risk_rules()
    alloc = get_allocation()

    for ticker in alloc:
        ok, _ = is_market_open(ticker)
        if not ok:
            continue

        price_eur = get_price_ibkr(ticker)
        if not price_eur:
            log("strategy.price_unavailable", {"ticker": ticker})
            continue

        # Comparer avec le prix moyen d'achat en portefeuille
        avg_cost = portfolio.get("avg_costs", {}).get(ticker)
        if not avg_cost:
            log("strategy.no_avg_cost", {"ticker": ticker})
            continue

        drop = (avg_cost - price_eur) / avg_cost
        if drop >= rules["dip_threshold_pct"]:
            reason = (
                f"{ticker} -{drop*100:.1f}% "
                f"sous le prix moyen d'achat"
            )
            log("strategy.dip_detected", {"ticker": ticker, "drop": round(drop, 4)})

            from core.flow import run_proposal
            run_proposal({
                "type":                    "trade.proposed",
                "source_agent":            "strategy",
                "ticker":                  ticker,
                "action":                  "BUY",
                "montant_eur":             10.0,
                "broker":                  "IBKR",
                "paper_mode":              rules["paper_mode"],
                "requires_human_approval": True,
                "raison":                  reason,
            }, portfolio)


def run():
    log("strategy.started", {})
    s = schedule.Scheduler()
    s.every().day.at("10:00").do(
        lambda: propose_dca() if date.today().day == 1 else None
    )
    s.every().day.at("09:00").do(check_dips)

    while True:
        s.run_pending()
        time.sleep(30)
