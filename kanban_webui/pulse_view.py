"""Batch "run pulse" payload: how long each running run has been going and
when its worker last heartbeated.

Read-only SELECT over ``task_runs`` (one query for the whole batch — the UI
polls this every 10 s and must not issue one request per card). The overdue
rule mirrors the existing run monitor: heartbeat age > 300 s.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from .operations import HEARTBEAT_OVERDUE_SECONDS


def build_pulse_payload(conn, tasks_param: str, *, now: Optional[int] = None) -> dict[str, Any]:
    moment = int(now if now is not None else time.time())
    requested = [value.strip() for value in (tasks_param or "").split(",") if value.strip()]
    if not requested:
        return {"now": moment, "pulse": {}}
    placeholders = ",".join("?" for _ in requested)
    # Single SELECT: only tasks currently in the `running` status with an
    # active (status='running') run. JOIN on tasks keeps tasks whose status
    # already moved on (or foreign ids never requested) out of the answer;
    # ORDER BY r.id so the newest running row wins if data ever doubles up.
    rows = conn.execute(
        f"""
        SELECT r.task_id AS task_id,
               r.profile AS profile,
               r.started_at AS started_at,
               r.last_heartbeat_at AS run_heartbeat_at,
               t.last_heartbeat_at AS task_heartbeat_at
        FROM task_runs r
        JOIN tasks t ON t.id = r.task_id
        WHERE r.status = 'running'
          AND t.status = 'running'
          AND r.task_id IN ({placeholders})
        ORDER BY r.id
        """,
        requested,
    ).fetchall()
    pulse: dict[str, dict[str, Any]] = {}
    for row in rows:
        heartbeat_at = row["run_heartbeat_at"] or row["task_heartbeat_at"]
        heartbeat_age = moment - int(heartbeat_at) if heartbeat_at else None
        pulse[row["task_id"]] = {
            "elapsed_sec": max(0, moment - int(row["started_at"] or 0)),
            "heartbeat_age_sec": heartbeat_age,
            "overdue": bool(heartbeat_age is not None and heartbeat_age > HEARTBEAT_OVERDUE_SECONDS),
            "profile": row["profile"],
            "started_at": int(row["started_at"] or 0),
        }
    return {"now": moment, "pulse": pulse}
