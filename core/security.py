import hmac
import os
from fastapi import HTTPException, Header

_SECRET = os.getenv("AGENT_SECRET", "")


def verify_token(authorization: str = Header(...)) -> None:
    if not _SECRET:
        raise HTTPException(500, "AGENT_SECRET non configuré côté serveur")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Format requis : Authorization: Bearer <token>")
    token = authorization.removeprefix("Bearer ")
    if not hmac.compare_digest(token.encode(), _SECRET.encode()):
        raise HTTPException(403, "Token invalide")
