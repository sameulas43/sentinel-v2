from core.policy_engine import get_risk_rules, get_allocation
from core.kill_switch import is_killed
from core.logger import get_logger

log = get_logger("risk")


def check(proposal: dict, portfolio: dict) -> tuple[bool, str]:
    """
    Vérifie les règles de risque.
    Ne modifie PAS la base de données — retourne (ok, raison).
    """
    if is_killed():
        return False, "Kill switch actif"

    rules      = get_risk_rules()
    allocation = get_allocation()
    ticker     = proposal["ticker"]
    montant    = proposal["montant_eur"]
    total      = portfolio.get("total_eur",  0.0)
    cash       = portfolio.get("cash_eur",   0.0)

    if cash < rules["min_cash_eur"]:
        return False, f"Cash {cash:.2f}€ < minimum {rules['min_cash_eur']}€"
    if montant > cash:
        return False, f"Montant {montant}€ > cash {cash:.2f}€"

    target      = allocation.get(ticker, 0.0)
    current_val = portfolio.get("positions", {}).get(ticker, 0.0)
    current_pct = current_val / total if total > 0 else 0.0
    max_pct     = target + rules["max_deviation_from_target_pct"]

    if current_pct >= max_pct:
        return False, (
            f"{ticker} sur-pondéré : {current_pct*100:.1f}% "
            f"vs cible {target*100:.0f}%+{rules['max_deviation_from_target_pct']*100:.0f}%"
        )

    invested = portfolio.get("total_invested", 0.0)
    if invested > 0 and total > 0:
        drawdown = (invested - total) / invested
        if drawdown > rules["max_drawdown_pct"]:
            return False, (
                f"Drawdown {drawdown*100:.1f}% "
                f"> max {rules['max_drawdown_pct']*100:.0f}%"
            )

    log("risk.passed", {"ticker": ticker, "montant": montant})
    return True, "ok"
