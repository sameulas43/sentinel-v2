import schedule
import time
import requests
from core.config import DISCORD_WEBHOOK, AGENT_SECRET, VPS_URL
from core.sizing import compute_quantity
from core.logger import get_logger
from agents.memory import get_pending, update_decision

log = get_logger("manager")


# ─── Discord ─────────────────────────────────────────────────────────────────

def send_discord(content: str):
    """
    Notifications informatives uniquement (confirmations, alertes, rapports).
    Utilise send_message_sync si bot disponible, webhook en fallback.
    """
    try:
        from discord_bot import send_message_sync
        send_message_sync(content)
        return
    except Exception:
        pass

    # Fallback webhook — notifications non-critiques seulement
    if DISCORD_WEBHOOK:
        try:
            requests.post(DISCORD_WEBHOOK, json={"content": content}, timeout=5)
        except Exception as e:
            log("manager.discord_error", {"error": str(e)}, level="error")


def send_for_approval(decision: dict):
    """
    CHEMIN UNIQUE pour les validations humaines.
    Délègue à discord_bot.send_approval_request_sync() → ApprovalView.
    Jamais de webhook simple pour les approbations.
    """
    from discord_bot import send_approval_request_sync
    try:
        send_approval_request_sync(decision)
    except RuntimeError as e:
        log("manager.discord_not_ready", {
            "decision_id": str(decision.get("decision_id", ""))[:8],
            "error":       str(e),
        }, level="warning")
    except TimeoutError:
        log("manager.discord_timeout", {
            "decision_id": str(decision.get("decision_id", ""))[:8],
        }, level="error")


def notify_blocked(decision_id: str, reason: str):
    send_discord(f"🚫 Décision `{str(decision_id)[:8]}` bloquée — {reason}")


def notify_rejected(decision_id: str):
    send_discord(f"❌ Décision `{str(decision_id)[:8]}` refusée par Samed")


# ─── Execution ────────────────────────────────────────────────────────────────

def send_to_execution(decision_id: str, proposal: dict) -> dict:
    """Calcule la quantité réelle et envoie l'ordre au VPS."""
    sizing = compute_quantity(proposal["ticker"], proposal["montant_eur"])
    if not sizing.get("ok"):
        log("manager.sizing_failed", {
            "ticker": proposal["ticker"],
            "reason": sizing.get("reject_reason"),
        }, level="error")
        return {"success": False, "status": "refused",
                "reason": sizing.get("reject_reason")}

    if not VPS_URL:
        log("manager.no_vps_url", {}, level="error")
        return {"success": False, "status": "failed", "reason": "VPS_URL non configuré"}

    try:
        r = requests.post(
            f"{VPS_URL}/order",
            json={
                "ticker":      proposal["ticker"],
                "action":      proposal["action"],
                "quantity":    sizing["quantity"],
                "montant_eur": proposal["montant_eur"],
                "event_id":    str(decision_id),
                "paper_mode":  proposal.get("paper_mode", True),
            },
            headers={"Authorization": f"Bearer {AGENT_SECRET}"},
            timeout=30,
        )
        result = r.json()
        log("manager.order_sent", {
            "decision_id": str(decision_id)[:8],
            "ticker":      proposal["ticker"],
            "status":      result.get("status"),
        })
        return result
    except Exception as e:
        log("manager.execution_error", {"error": str(e)}, level="error")
        return {"success": False, "status": "failed", "reason": str(e)}


# ─── Rapports ─────────────────────────────────────────────────────────────────

def morning_report():
    pending = get_pending()
    send_discord(
        f"☀️ **Rapport matinal SENTINEL**\n"
        f"Décisions en attente : {len(pending)}"
    )


def evening_report():
    send_discord("🌙 **SENTINEL actif** — bonne soirée")


def run():
    """Thread manager — scheduler local isolé."""
    log("manager.started", {})
    s = schedule.Scheduler()

    s.every().day.at("09:00").do(morning_report)
    s.every().day.at("20:00").do(evening_report)

    while True:
        s.run_pending()
        time.sleep(30)
