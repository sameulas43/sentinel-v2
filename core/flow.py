"""
SENTINEL V2.0 — Flow

Seule entité qui pilote les transitions d'état.
risk.py et validation.py calculent et retournent des résultats.
flow.py lit ces résultats et appelle update_decision().
"""
from datetime import datetime, timezone
from core.logger import get_logger
from core.kill_switch import is_killed
from core.database import fetch_all
from agents.memory import save_decision, update_decision, save_event, get_decision
from agents import risk, validation

log = get_logger("flow")


def run_proposal(proposal: dict, portfolio: dict) -> dict:
    """
    Orchestre Strategy → Risk → Validation → Manager → Execution.
    flow.py est le seul pilote des transitions d'état.
    """
    if is_killed():
        log("flow.killed", {})
        return {"success": False, "reason": "kill_switch"}

    # 1. Créer la décision (statut initial : pending)
    decision_id = save_decision({**proposal, "status": "pending"})
    log("flow.created", {
        "decision_id": decision_id, "ticker": proposal["ticker"],
    })

    # 2. Risk check — ne touche pas DB
    risk_ok, risk_reason = risk.check(proposal, portfolio)
    save_event("risk.check", "risk", decision_id,
               {"ok": risk_ok, "reason": risk_reason})

    if not risk_ok:
        update_decision(decision_id, status="blocked_risk")
        log("flow.risk_blocked", {
            "decision_id": decision_id, "reason": risk_reason,
        }, level="warning")
        _notify_blocked(decision_id, risk_reason)
        return {"success": False, "step": "risk",
                "decision_id": decision_id, "reason": risk_reason}

    update_decision(decision_id, status="risk_passed")

    # 3. Validation technique — ne touche pas DB
    val = validation.validate({**proposal, "decision_id": decision_id})
    save_event("validation.result", "validation", decision_id, val)

    if val["result"] != "validated":
        update_decision(decision_id,
            status="rejected_validation", score=val["score"])
        log("flow.validation_rejected", {
            "decision_id": decision_id,
            "score":       val["score"],
            "reason":      val.get("reason"),
        }, level="warning")
        _notify_blocked(decision_id,
            f"Rejetée — score {val['score']}/100 — {val.get('reason','')}")
        return {"success": False, "step": "validation",
                "decision_id": decision_id}

    update_decision(decision_id,
        status="validated",
        score=val["score"],
        requires_human_approval=val["requires_human_approval"],
    )

    # 4. Routage : humain ou auto
    if val["requires_human_approval"]:
        update_decision(decision_id, status="awaiting_human")
        log("flow.awaiting_human", {"decision_id": decision_id})
        _send_for_approval({
            **proposal,
            "decision_id": decision_id,
            "score":       val["score"],
        })
        return {"success": True, "step": "awaiting_human",
                "decision_id": decision_id}

    update_decision(decision_id, status="auto_approved")
    log("flow.auto_approved", {"decision_id": decision_id})
    return _execute(decision_id, proposal)


def handle_approval(decision_id: str, approved: bool) -> dict:
    """
    Appelé par discord_bot.py après clic ✅ ou ❌.
    Synchrone — s'exécute dans la coroutine du bot Discord.
    """
    ts = datetime.now(timezone.utc).isoformat()

    if not approved:
        update_decision(decision_id,
            status="rejected_human",
            samed_choice="rejected",
            samed_approved_at=ts,
        )
        log("flow.human_rejected", {"decision_id": decision_id})
        _notify_rejected(decision_id)
        return {"success": False, "decision_id": decision_id}

    update_decision(decision_id,
        status="human_approved",
        samed_choice="approved",
        samed_approved_at=ts,
    )
    log("flow.human_approved", {"decision_id": decision_id})

    proposal = get_decision(decision_id)
    if not proposal:
        log("flow.decision_not_found",
            {"decision_id": decision_id}, level="error")
        return {"success": False, "decision_id": decision_id}

    return _execute(decision_id, proposal)


def expire_stale_decisions():
    """
    Expire les décisions en awaiting_human depuis plus de 2h.
    Appelé par Guardian toutes les 10 minutes.
    """
    stale = fetch_all("""
        SELECT decision_id, ticker
        FROM decisions
        WHERE status = 'awaiting_human'
          AND updated_at < NOW() - INTERVAL '2 hours'
    """)

    for d in stale:
        did = str(d["decision_id"])
        update_decision(did,
            status="rejected_human",
            samed_choice="timeout",
        )
        save_event("decision.timeout", "flow", did, {
            "ticker":     d["ticker"],
            "expired_at": datetime.now(timezone.utc).isoformat(),
        })
        log("flow.timeout", {"decision_id": did, "ticker": d["ticker"]})
        _send_notification(
            f"⏱️ Décision `{did[:8]}` expirée — {d['ticker']} — "
            "aucune réponse après 2h"
        )


def _execute(decision_id: str, proposal: dict) -> dict:
    """Envoie l'ordre à l'Execution Agent via manager."""
    update_decision(decision_id, status="pending_fill")

    from agents.manager import send_to_execution
    result    = send_to_execution(decision_id, proposal)
    ib_status = result.get("status", "unknown")

    if ib_status == "filled":
        update_decision(decision_id, status="executed")
        _send_notification(
            f"✅ `{decision_id[:8]}` — {proposal['ticker']} exécuté "
            f"@ {result.get('avg_price', '?')}"
        )
    elif ib_status == "submitted":
        # Reste en pending_fill — fill_tracker prend le relais
        log("flow.pending_fill", {
            "decision_id": decision_id, "ticker": proposal["ticker"],
        })
    else:
        update_decision(decision_id, status="execution_failed")
        _send_notification(
            f"🔴 `{decision_id[:8]}` — {proposal['ticker']} "
            f"échec : {result.get('reason', ib_status)}"
        )

    return {**result, "decision_id": decision_id}


# ─── Helpers Discord ─────────────────────────────────────────────────────────

def _send_for_approval(decision: dict):
    """
    CHEMIN UNIQUE pour les validations humaines.
    Utilise run_coroutine_threadsafe via discord_bot.
    """
    from discord_bot import send_approval_request_sync
    try:
        send_approval_request_sync(decision)
    except RuntimeError as e:
        log("flow.discord_not_ready", {
            "decision_id": str(decision.get("decision_id", ""))[:8],
            "error":       str(e),
        }, level="warning")
    except TimeoutError:
        log("flow.discord_timeout", {
            "decision_id": str(decision.get("decision_id", ""))[:8],
        }, level="error")


def _notify_blocked(decision_id: str, reason: str):
    _send_notification(f"🚫 Décision `{str(decision_id)[:8]}` bloquée — {reason}")


def _notify_rejected(decision_id: str):
    _send_notification(f"❌ Décision `{str(decision_id)[:8]}` refusée par Samed")


def _send_notification(content: str):
    """Notifications informatives — webhook ou bot selon disponibilité."""
    from discord_bot import send_message_sync
    try:
        send_message_sync(content)
    except Exception as e:
        log("flow.notification_error", {"error": str(e)}, level="warning")
