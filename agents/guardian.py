import schedule
import time
import requests
from core.config import VPS_URL, AGENT_SECRET, DISCORD_WEBHOOK
from core.database import get_db, execute
from core.logger import get_logger

log = get_logger("guardian")


def check_vps():
    """Ping le health endpoint du VPS Execution Agent."""
    if not VPS_URL:
        log("guardian.no_vps_url", {}, level="warning")
        return

    start = time.time()
    try:
        r       = requests.get(f"{VPS_URL}/health", timeout=5)
        latency = int((time.time() - start) * 1000)
        ok      = r.status_code == 200
    except Exception as e:
        latency = -1
        ok      = False
        log("guardian.vps_down", {"error": str(e)}, level="error")
        _alert("🔴 Execution Agent VPS DOWN — vérification manuelle requise")

    execute("""
        INSERT INTO heartbeats (agent_name, last_seen, status, latency_ms)
        VALUES (%s, NOW(), %s, %s)
        ON CONFLICT (agent_name) DO UPDATE
        SET last_seen  = NOW(),
            status     = EXCLUDED.status,
            latency_ms = EXCLUDED.latency_ms,
            updated_at = NOW()
    """, ("execution", "ok" if ok else "down", latency))

    log("guardian.heartbeat", {
        "agent":      "execution",
        "status":     "ok" if ok else "down",
        "latency_ms": latency,
    })


def check_postgres():
    """Vérifie que Postgres répond."""
    try:
        db = get_db()
        db.cursor().execute("SELECT 1")
        db.close()
        log("guardian.postgres_ok", {})
    except Exception as e:
        log("guardian.postgres_down", {"error": str(e)}, level="error")
        _alert("🔴 Postgres inaccessible — Sentinel en danger")


def check_timeouts():
    """Expire les décisions en awaiting_human depuis plus de 2h."""
    from core.flow import expire_stale_decisions
    expire_stale_decisions()
    log("guardian.timeout_check_done", {})


def check_pending_fills():
    """Vérifie les ordres en pending_fill."""
    from core.fill_tracker import check_pending_fills as _check
    _check()


def _alert(msg: str):
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=5)
    except Exception as e:
        log("guardian.alert_error", {"error": str(e)}, level="error")


def run():
    """Thread guardian — scheduler local isolé."""
    log("guardian.started", {})
    s = schedule.Scheduler()

    s.every(5).minutes.do(check_vps)
    s.every(5).minutes.do(check_postgres)
    s.every(5).minutes.do(check_pending_fills)
    s.every(10).minutes.do(check_timeouts)

    # Rapport santé chaque mercredi à 09h00
    s.every().wednesday.at("09:00").do(_weekly_health_report)

    # Premier check immédiat
    check_vps()
    check_postgres()

    while True:
        s.run_pending()
        time.sleep(30)


def _weekly_health_report():
    from core.database import fetch_all
    errors = fetch_all("""
        SELECT COUNT(*) AS cnt FROM events
        WHERE event_type LIKE '%.failed' OR event_type LIKE '%.error'
          AND created_at > NOW() - INTERVAL '7 days'
    """)
    count = errors[0]["cnt"] if errors else 0
    _alert(
        f"🛡️ **Rapport santé hebdo**\n"
        f"Erreurs 7j : {count}\n"
        f"Guardian : ✅ actif"
    )
