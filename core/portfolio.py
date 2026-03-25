"""
SENTINEL V2.0 — Portfolio Module

Source principale : VPS Execution Agent → GET /portfolio
Fallback          : dernier snapshot Postgres

NOTE V2.0 : Les valeurs de positions en EUR sont des approximations
basées sur avg_cost + taux FX live. Pas une vérité comptable stricte.
Usage : décisions DCA et risk checks, pas reporting comptable.
Migration V2.5 : prix market live via IB Market Data.
"""
import json
import requests
from datetime import datetime, timezone
from core.config import VPS_URL, AGENT_SECRET
from core.database import fetch_one, execute
from core.logger import get_logger

log = get_logger("portfolio")


def get_portfolio() -> dict:
    """
    Retourne le portefeuille courant.
    Lève RuntimeError si aucune source disponible.
    """
    if VPS_URL:
        portfolio = _fetch_from_vps()
        if portfolio:
            _save_snapshot(portfolio)
            return portfolio

    portfolio = _fetch_from_snapshot()
    if portfolio:
        age = _snapshot_age_seconds(portfolio)
        log("portfolio.using_snapshot", {"age_seconds": age})
        if age > 3600:
            log("portfolio.snapshot_stale", {"age_seconds": age}, level="warning")
        return portfolio

    log("portfolio.unavailable", {}, level="error")
    raise RuntimeError(
        "Portefeuille indisponible : VPS injoignable et aucun snapshot Postgres. "
        "Aucun ordre ne sera passé."
    )


def _fetch_from_vps() -> dict | None:
    try:
        r = requests.get(
            f"{VPS_URL}/portfolio",
            headers={"Authorization": f"Bearer {AGENT_SECRET}"},
            timeout=10,
        )
        if r.status_code == 200:
            data               = r.json()
            data["source"]     = "vps"
            data["fetched_at"] = datetime.now(timezone.utc).isoformat()
            log("portfolio.fetched_vps", {
                "total_eur": data.get("total_eur"),
                "cash_eur":  data.get("cash_eur"),
                "note":      data.get("note", ""),
            })
            return data
    except Exception as e:
        log("portfolio.vps_error", {"error": str(e)}, level="warning")
    return None


def _fetch_from_snapshot() -> dict | None:
    row = fetch_one(
        "SELECT * FROM portfolio_snapshots ORDER BY created_at DESC LIMIT 1"
    )
    if not row:
        return None
    return {
        "total_eur":      row["total_eur"],
        "cash_eur":       row["cash_eur"],
        "total_invested": row["total_invested"],
        "positions":      row["positions"] or {},
        "source":         "snapshot",
        "fetched_at":     row["created_at"].isoformat(),
    }


def _save_snapshot(p: dict):
    execute("""
        INSERT INTO portfolio_snapshots
            (total_eur, cash_eur, total_invested, positions, source)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        p.get("total_eur",      0.0),
        p.get("cash_eur",       0.0),
        p.get("total_invested", 0.0),
        json.dumps(p.get("positions", {})),
        p.get("source", "vps"),
    ))


def _snapshot_age_seconds(p: dict) -> int:
    fetched = p.get("fetched_at")
    if not fetched:
        return 99999
    try:
        dt  = datetime.fromisoformat(fetched)
        now = datetime.now(timezone.utc)
        return int((now - dt).total_seconds())
    except Exception:
        return 99999
