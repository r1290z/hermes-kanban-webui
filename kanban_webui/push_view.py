"""Web-push: VAPID-ключ и подписки (спека §10.2).

Маршруты:

* ``GET    /api/push/key``       → ``{"public_key": "<base64url>"}``
* ``POST   /api/push/subscribe`` → 201, upsert по ``endpoint``
* ``DELETE /api/push/subscribe`` → 204

Хранилище — свой SQLite ``~/.hermes/kanban-webui/push.db``: ``kanban.db`` общий
с CLI и диспетчером, писать в него из веб-слоя нельзя. Приватный VAPID-ключ
живёт рядом (``vapid-private.pem``, chmod 600) и никогда не отдаётся странице —
только распакованная публичная точка P-256, которую ждёт
``pushManager.subscribe({applicationServerKey})``.
"""
from __future__ import annotations

import base64
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

from .config import get_settings

router = APIRouter(prefix="/api/push")

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id         INTEGER PRIMARY KEY,
    endpoint   TEXT UNIQUE NOT NULL,
    p256dh     TEXT NOT NULL,
    auth       TEXT NOT NULL,
    ua         TEXT,
    created_at INTEGER NOT NULL
)
"""


class PushConfigError(RuntimeError):
    """VAPID-пара ещё не сгенерирована (scripts/make_vapid.py)."""


def state_dir() -> Path:
    """Каталог состояния, общий с сервисом: ``HERMES_KANBAN_WEBUI_STATE``."""
    return Path(get_settings().state_dir)


def db_path() -> Path:
    return state_dir() / "push.db"


def vapid_private_key_path() -> Path:
    return state_dir() / "vapid-private.pem"


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    """Открыть push.db, создав каталог и таблицу при первом обращении."""
    target = Path(path) if path is not None else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def upsert_subscription(
    conn: sqlite3.Connection,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    ua: Optional[str] = None,
    created_at: Optional[int] = None,
) -> None:
    """Одна строка на endpoint: переустановка PWA присылает новые ключи."""
    conn.execute(
        """
        INSERT INTO subscriptions (endpoint, p256dh, auth, ua, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(endpoint) DO UPDATE SET
            p256dh = excluded.p256dh,
            auth   = excluded.auth,
            ua     = excluded.ua
        """,
        (endpoint, p256dh, auth, ua, int(created_at if created_at is not None else time.time())),
    )
    conn.commit()


def delete_subscription(conn: sqlite3.Connection, endpoint: str) -> bool:
    cursor = conn.execute("DELETE FROM subscriptions WHERE endpoint = ?", (endpoint,))
    conn.commit()
    return cursor.rowcount > 0


def list_subscriptions(conn: Optional[sqlite3.Connection] = None) -> list[dict[str, Any]]:
    own = conn is None
    if own:
        conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, endpoint, p256dh, auth, ua, created_at FROM subscriptions ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if own and conn is not None:
            conn.close()


def subscription_info(row: dict[str, Any]) -> dict[str, Any]:
    """Форма, которую ждёт ``pywebpush.webpush``."""
    return {
        "endpoint": row["endpoint"],
        "keys": {"p256dh": row["p256dh"], "auth": row["auth"]},
    }


def vapid_public_key(path: Optional[Path] = None) -> str:
    """Публичный ключ VAPID в base64url без паддинга (распакованная точка)."""
    pem = Path(path) if path is not None else vapid_private_key_path()
    if not pem.is_file():
        raise PushConfigError(f"нет VAPID-пары {pem} — запустите scripts/make_vapid.py")
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid

    vapid = Vapid.from_file(str(pem))
    raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


# ===== Маршруты =====


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=1)
    auth: str = Field(min_length=1)


class SubscriptionBody(BaseModel):
    endpoint: str = Field(min_length=1)
    keys: SubscriptionKeys
    ua: Optional[str] = None

    @field_validator("endpoint")
    @classmethod
    def _endpoint_must_be_url(cls, value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("endpoint должен быть абсолютным http(s)-URL")
        return value.strip()


class EndpointBody(BaseModel):
    endpoint: str = Field(min_length=1)


@router.get("/key")
def get_key() -> dict[str, str]:
    try:
        return {"public_key": vapid_public_key()}
    except PushConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/subscribe", status_code=201)
def subscribe(body: SubscriptionBody) -> dict[str, Any]:
    conn = connect()
    try:
        upsert_subscription(
            conn,
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
            ua=body.ua,
        )
        total = conn.execute("SELECT COUNT(*) AS c FROM subscriptions").fetchone()["c"]
    finally:
        conn.close()
    return {"ok": True, "subscriptions": int(total)}


@router.delete("/subscribe", status_code=204)
def unsubscribe(body: EndpointBody) -> Response:
    conn = connect()
    try:
        delete_subscription(conn, body.endpoint)
    finally:
        conn.close()
    return Response(status_code=204)
