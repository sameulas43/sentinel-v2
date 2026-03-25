import json
from core.database import get_db, fetch_one, fetch_all, execute
from core.logger import get_logger
from core.state_machine import transition

log = get_logger("memory")


def save_decision(d: dict) -> str:
    """Sauvegarde une décision et retourne le decision_id via RETURNING."""
    db  = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO decisions
            (type, source_agent, ticker, action, montant_eur, broker,
             paper_mode, requires_human_approval, score, raison, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING decision_id
    """, (
        d.get("type"),
        d.get("source_agent"),
        d.get("ticker"),
        d.get("action"),
        d.get("montant_eur"),
        d.get("broker",                  "IBKR"),
        d.get("paper_mode",              True),
        d.get("requires_human_approval", True),
        d.get("score"),
        d.get("raison"),
        d.get("status",                  "pending"),
    ))
    decision_id = str(cur.fetchone()[0])
    db.commit()
    db.close()
    log("memory.saved", {"decision_id": decision_id, "ticker": d.get("ticker")})
    return decision_id


def update_decision(decision_id: str, status: str = None, **kwargs) -> bool:
    """
    Met à jour une décision.
    Si status est fourni, valide la transition via state_machine avant d'écrire.
    """
    if status:
        current = fetch_one(
            "SELECT status FROM decisions WHERE decision_id = %s", (decision_id,)
        )
        if not current:
            log("memory.not_found", {"decision_id": decision_id}, level="error")
            return False
        if not transition(decision_id, current["status"], status):
            return False
        kwargs["status"] = status

    if not kwargs:
        return True

    fields = ", ".join(f"{k} = %s" for k in kwargs)
    execute(
        f"UPDATE decisions SET {fields}, updated_at = NOW() WHERE decision_id = %s",
        list(kwargs.values()) + [decision_id],
    )
    return True


def save_event(event_type: str, source: str,
               decision_id: str = None, payload: dict = {}):
    execute(
        "INSERT INTO events (event_type, source_agent, decision_id, payload) "
        "VALUES (%s, %s, %s, %s)",
        (event_type, source, decision_id, json.dumps(payload)),
    )


def get_decision(decision_id: str) -> dict | None:
    return fetch_one(
        "SELECT * FROM decisions WHERE decision_id = %s", (decision_id,)
    )


def get_pending() -> list:
    return fetch_all("""
        SELECT * FROM decisions
        WHERE status NOT IN (
            'executed','cancelled','blocked_risk',
            'rejected_validation','rejected_human','execution_failed'
        )
        ORDER BY created_at
    """)
