import os
import sys
import json
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone


def _raw_log(event_type: str, data: dict, level: str = "info"):
    print(json.dumps({
        "ts":    datetime.now(timezone.utc).isoformat(),
        "agent": "database",
        "type":  event_type,
        "data":  data,
    }), file=sys.stderr if level == "error" else sys.stdout, flush=True)


def get_db():
    """
    Connexion Postgres via DATABASE_URL uniquement.
    Ne tente JAMAIS une connexion locale.
    Fail-fast explicite si DATABASE_URL vide.
    """
    # Import ici pour éviter l'exécution au build
    from core.config import DATABASE_URL

    if not DATABASE_URL:
        _raw_log("database.no_url", {
            "error": (
                "DATABASE_URL vide. "
                "Vérifier que le plugin PostgreSQL est lié au service sentinel-v2 "
                "dans Railway Variables avec ${{Postgres.DATABASE_URL}}"
            )
        }, level="error")
        raise RuntimeError(
            "DATABASE_URL manquant — "
            "aucune tentative de connexion locale effectuée."
        )

    # psycopg2 utilise DATABASE_URL directement
    # Jamais de socket local /var/run/postgresql/
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """Exécute schema.sql — idempotent."""
    schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"schema.sql introuvable : {schema_path}")

    db = get_db()
    try:
        with open(schema_path, "r") as f:
            sql = f.read()
        cur = db.cursor()
        cur.execute(sql)
        db.commit()
        _raw_log("database.init_ok", {})
    except Exception as e:
        db.rollback()
        _raw_log("database.init_error", {"error": str(e)}, level="error")
        raise
    finally:
        db.close()


def fetch_one(q: str, p: tuple = ()) -> dict | None:
    db  = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(q, p)
    row = cur.fetchone()
    db.close()
    return dict(row) if row else None


def fetch_all(q: str, p: tuple = ()) -> list:
    db  = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(q, p)
    rows = cur.fetchall()
    db.close()
    return [dict(r) for r in rows]


def execute(q: str, p: tuple = ()):
    db  = get_db()
    cur = db.cursor()
    cur.execute(q, p)
    db.commit()
    db.close()
