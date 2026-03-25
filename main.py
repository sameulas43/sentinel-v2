"""
SENTINEL V2.0 — Point d'entrée monolithe Railway.

Stratégie de démarrage :
  → guardian + manager démarrent dans des threads daemon.
  → strategy démarre DANS on_ready (discord_bot.py)
    après que bot.loop soit garanti disponible.
  → bot.run() dans le thread principal — bloque ici.
"""
import threading
from core.logger import get_logger
from core.database import init_db

log = get_logger("sentinel")


def main():
    log("sentinel.started", {"version": "2.0"})
    init_db()

    from agents.guardian import run as run_guardian
    from agents.manager  import run as run_manager
    import discord_bot

    # guardian et manager démarrent immédiatement
    # strategy démarre dans on_ready via discord_bot.py
    threads = [
        threading.Thread(target=run_guardian, name="guardian", daemon=True),
        threading.Thread(target=run_manager,  name="manager",  daemon=True),
    ]

    for t in threads:
        t.start()
        log("sentinel.thread_started", {"thread": t.name})

    log("sentinel.discord_starting", {
        "note": "strategy démarrera après on_ready"
    })

    # Thread principal — bloque ici jusqu'à arrêt du bot
    discord_bot.run_discord_bot()


if __name__ == "__main__":
    main()
