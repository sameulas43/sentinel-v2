from core.logger import get_logger

log = get_logger("state_machine")

TRANSITIONS: dict[str, list[str]] = {
    "pending":               ["risk_passed",       "blocked_risk"],
    "risk_passed":           ["validated",          "rejected_validation"],
    "validated":             ["awaiting_human",     "auto_approved"],
    "awaiting_human":        ["human_approved",     "rejected_human"],
    "auto_approved":         ["pending_fill",       "execution_failed"],
    "human_approved":        ["pending_fill",       "execution_failed"],
    "pending_fill":          ["executed",           "cancelled",  "execution_failed"],
    # Terminaux
    "executed":              [],
    "cancelled":             [],
    "blocked_risk":          [],
    "rejected_validation":   [],
    "rejected_human":        [],
    "execution_failed":      [],
}

TERMINAL: set[str] = {
    "executed", "cancelled", "blocked_risk",
    "rejected_validation", "rejected_human", "execution_failed",
}


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, [])


def transition(decision_id: str, current: str, target: str) -> bool:
    if not can_transition(current, target):
        log("state_machine.refused", {
            "decision_id": decision_id,
            "from":        current,
            "to":          target,
            "allowed":     TRANSITIONS.get(current, []),
        }, level="error")
        return False
    log("state_machine.ok", {
        "decision_id": decision_id, "from": current, "to": target,
    })
    return True


def is_terminal(status: str) -> bool:
    return status in TERMINAL
