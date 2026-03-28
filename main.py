"""
SENTINEL V2.0 — Point d'entrée Railway.

Ordre de démarrage :
1. check_vars()  — vérification variables au runtime
2. init_db()     — initialisation PostgreSQL
3. Threads daemon (guardian, manager)
4. Bot Discord dans le thread principal
5. Strategy démarre dans on_ready() — une seule fois
"""
import sys
import threading
from core.logger import get_logger

log = get_logger("sentinel")


def check_vars():
    """
    Vérification des variables critiques au runtime.
    Railway injecte les variables uniquement au runtime, pas au build.
    Arrêt propre avec message clair si une variable manque.
    """
    from core.config import (
        DATABASE_URL, DISCORD_TOKEN,
        DISCORD_CHANNEL, AGENT_SECRET,
    )

    missing = []
    warnings = []

    if not DATABASE_URL:
        missing.append("DATABASE_URL")
    if not DISCORD_TOKEN:
        missing.append("DISCORD_TOKEN")
    if not AGENT_SECRET:
        warnings.append("AGENT_SECRET vide — communications VPS non sécurisées")
    if DISCORD_CHANNEL == 0:
        warnings.append("DISCORD_CHANNEL_ID absent — messages Discord désactivés")

    for w in warnings:
        log("sentinel.config_warning", {"warning": w}, level="warning")

    if missing:
        log("sentinel.missing_vars", {
            "missing": missing,
            "action":  "Ajouter ces variables dans Railway → sentinel-v2 → Variables",
        }, level="error")
        sys.exit(1)

    log("sentinel.vars_ok", {
        "DATABASE_URL":       "OK",
        "DISCORD_TOKEN":      "OK",
        "AGENT_SECRET":       "OK" if AGENT_SECRET else "MANQUANT",
        "DISCORD_CHANNEL_ID": DISCORD_CHANNEL,
    })


def main():
    log("sentinel.started", {"version": "2.0"})

    # 1. Variables
    check_vars()

    # 2. Base de données
    try:
        from core.database import init_db
        init_db()
        log("sentinel.db_ok", {})
    except Exception as e:
        log("sentinel.db_error", {
            "error": str(e),
            "hint":  "Vérifier DATABASE_URL et le plugin PostgreSQL Railway",
        }, level="error")
        sys.exit(1)

    # 3. Threads daemon
    from agents.guardian import run as run_guardian
    from agents.manager  import run as run_manager
    import discord_bot

    threads = [
        threading.Thread(target=run_guardian, name="guardian", daemon=True),
        threading.Thread(target=run_manager,  name="manager",  daemon=True),
    ]
    for t in threads:
        t.start()
        log("sentinel.thread_started", {"thread": t.name})

    log("sentinel.discord_starting", {
        "note": "Strategy démarrera après on_ready Discord"
    })

    # 4. Bot Discord dans le thread principal
    # Si le bot s'arrête → process s'arrête → Railway redémarre
    discord_bot.run_discord_bot()
    sys.exit(0)


if __name__ == "__main__":
    main()
