"""
SENTINEL V2.0 — Fill Tracker

Vérifie les décisions en pending_fill toutes les 5 minutes.
Gère le cas lost_on_restart (redémarrage VPS).
"""
import requests
from datetime import datetime, timezone
from core.config import VPS_URL, AGENT_SECRET, DISCORD_WEBHOOK
from core.database import fetch_all
from core.logger import get_logger
from agents.memory import update_decision, save_event

log = get_logger("fill_tracker")


def check_pending_fills():
    """Vérifie les ordres en pending_fill depuis plus de 2 minutes."""
    pending = fetch_all("""
        SELECT decision_id, ticker, action
        FROM decisions
        WHERE status = 'pending_fill'
          AND updated_at < NOW() - INTERVAL '2 minutes'
    """)

    if not pending:
        return

    log("fill_tracker.checking", {"count": len(pending)})

    for d in pending:
        did    = str(d["decision_id"])
        status = _query_status(did)

        if status == "filled":
            update_decision(did, status="executed")
            save_event("order.filled", "fill_tracker", did, {"ticker": d["ticker"]})
            log("fill_tracker.filled", {"decision_id": did, "ticker": d["ticker"]})

        elif status in ("cancelled", "failed"):
            update_decision(did, status="execution_failed")
            save_event("order.failed", "fill_tracker", did,
                       {"ticker": d["ticker"], "status": status})
            log("fill_tracker.failed", {
                "decision_id": did, "ticker": d["ticker"],
            }, level="warning")

        elif status == "submitted":
            log("fill_tracker.still_submitted", {
                "decision_id": did, "ticker": d["ticker"],
            })

        elif status == "lost_on_restart":
            # VPS a redémarré — statut IB inconnu — action manuelle requise
            update_decision(did, status="execution_failed")
            save_event("order.lost_on_restart", "fill_tracker", did, {
                "ticker":  d["ticker"],
                "note":    "VPS redémarré — statut IB inconnu — vérif manuelle requise",
                "time":    datetime.now(timezone.utc).isoformat(),
            })
            log("fill_tracker.lost_on_restart", {
                "decision_id": did, "ticker": d["ticker"],
            }, level="error")
            _alert(
                f"⚠️ `{did[:8]}` — {d['ticker']} — statut IB inconnu après "
                "redémarrage VPS. Vérification manuelle sur IB Gateway requise."
            )

        else:
            log("fill_tracker.unknown_status", {
                "decision_id": did, "status": status,
            }, level="warning")


def _query_status(decision_id: str) -> str:
    if not VPS_URL:
        return "unknown"
    try:
        r = requests.get(
            f"{VPS_URL}/order_status/{decision_id}",
            headers={"Authorization": f"Bearer {AGENT_SECRET}"},
            timeout=5,
        )
        if r.status_code == 200:
            return r.json().get("status", "unknown")
    except Exception as e:
        log("fill_tracker.vps_error", {"error": str(e)}, level="warning")
    return "unknown"


def _alert(msg: str):
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=5)
    except Exception:
        pass
