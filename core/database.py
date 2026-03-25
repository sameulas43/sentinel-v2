import os
import sys
import json
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from core.config import DATABASE_URL


def _raw_log(event_type: str, data: dict, level: str = "info"):
    """Log minimal sans dépendance circulaire."""
    print(json.dumps({
        "ts":    datetime.now(timezone.utc).isoformat(),
        "agent": "database",
        "type":  event_type,
        "data":  data,
    }), file=sys.stderr if level == "error" else sys.stdout, flush=True)


def get_db():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """
    Exécute schema.sql de façon totalement idempotente.
    Peut être appelé à chaque redémarrage sans risque.
    """
    schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    if not os.path.exists(schema_path):
        _raw_log("database.schema_missing", {"path": schema_path}, level="error")
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
