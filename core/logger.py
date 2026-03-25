import json
import logging
import sys
from datetime import datetime, timezone

KNOWN_MODULES = {
    "manager", "strategy", "risk", "validation",
    "guardian", "execution", "discord", "flow",
    "memory", "portfolio", "database", "sizing",
    "state_machine", "kill_switch", "fill_tracker",
    "sentinel", "discord_bot",
}

_loggers: dict = {}


def get_logger(module: str):
    """
    Retourne une fonction log_json(event_type, data, level)
    avec l'identité du module.

    Usage :
        from core.logger import get_logger
        log = get_logger("strategy")
        log("strategy.started", {})
        log("order.failed", {"ticker": "SGOL"}, level="error")
    """
    if module not in _loggers:
        logger = logging.getLogger(module)
        if not logger.handlers:
            h = logging.StreamHandler(sys.stdout)
            h.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(h)
            logger.setLevel(logging.INFO)
            logger.propagate = False
        _loggers[module] = logger

    logger = _loggers[module]

    def log_json(event_type: str, data: dict = {}, level: str = "info") -> dict:
        entry = {
            "ts":    datetime.now(timezone.utc).isoformat(),
            "agent": module,
            "type":  event_type,
            "data":  data,
        }
        line = json.dumps(entry, ensure_ascii=False)
        getattr(logger, level)(line)
        return entry

    return log_json
