from core.database import fetch_one, execute
from core.logger import get_logger

log = get_logger("kill_switch")


def is_killed() -> bool:
    try:
        row = fetch_one("SELECT value FROM settings WHERE key = 'kill_switch'")
        return bool(row and row["value"] == "true")
    except Exception as e:
        log("kill_switch.error", {"error": str(e)}, level="error")
        return False


def activate():
    execute("UPDATE settings SET value='true', updated_at=NOW() WHERE key='kill_switch'")
    log("kill_switch.activated", {})


def deactivate():
    execute("UPDATE settings SET value='false', updated_at=NOW() WHERE key='kill_switch'")
    log("kill_switch.deactivated", {})
