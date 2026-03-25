from core.policy_engine import get_risk_rules, is_halal
from core.market_calendar import is_market_open
from core.logger import get_logger

log = get_logger("validation")


def validate(proposal: dict) -> dict:
    """
    Valide techniquement une proposition.
    Ne modifie PAS la base de données — retourne un dict résultat.
    flow.py lit ce résultat et pilote les transitions.
    """
    score  = 100
    issues = []
    rules  = get_risk_rules()

    # Halal check
    if not is_halal(proposal["ticker"]):
        log("validation.halal_fail", {"ticker": proposal["ticker"]}, level="warning")
        return {
            "result":                  "rejected",
            "score":                   0,
            "reason":                  "Actif non halal",
            "requires_human_approval": False,
        }

    # Marché ouvert
    open_, reason = is_market_open(proposal["ticker"])
    if not open_:
        score -= 30
        issues.append(reason)

    # Montant minimum
    if proposal.get("montant_eur", 0) < 1.0:
        score -= 20
        issues.append("Montant < 1€")

    result   = "validated" if score >= 70 else "rejected"
    requires = (
        not rules["paper_mode"]
        or proposal.get("montant_eur", 0) > rules["requires_human_approval_above_eur"]
    )

    log("validation.result", {
        "ticker": proposal["ticker"],
        "score":  score,
        "result": result,
    })

    return {
        "result":                  result,
        "score":                   score,
        "reason":                  "; ".join(issues) if issues else None,
        "requires_human_approval": requires,
    }
