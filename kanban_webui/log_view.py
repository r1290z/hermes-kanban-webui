"""Read-only "execution log" view over ``task_runs`` / ``task_events``.

The Kanban DB stays the single source of truth: this module only reads.
``hermes_cli.kanban_db.list_runs``/``list_events`` work per task, while the
log view needs a cross-task slice, so the queries here are plain read-only
``SELECT`` statements against the same tables.

Rules kept in one place:
* runs are ordered newest first (``started_at DESC, id DESC``);
* the ``before`` cursor is the ``started_at`` of the last row of the previous
  page, so no row is dropped or repeated at a page border;
* timestamps are rendered in the *server* local timezone, not UTC.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

SINCE_OPTIONS = ("today", "7d", "30d", "all")
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

_RUN_COLUMNS = """
    r.id AS id,
    r.task_id AS task_id,
    r.profile AS profile,
    r.step_key AS step_key,
    r.status AS status,
    r.outcome AS outcome,
    r.started_at AS started_at,
    r.ended_at AS ended_at,
    r.summary AS summary,
    r.error AS error,
    r.metadata AS metadata,
    t.title AS title,
    COALESCE(c.comment_count, 0) AS comment_count,
    COALESCE(a.attachment_count, 0) AS attachment_count
"""


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def since_cutoff(since: Optional[str], *, now: Optional[int] = None) -> Optional[int]:
    """Return the lower bound (epoch seconds) for a ``since`` filter.

    ``today`` -> local midnight, ``7d``/``30d`` -> that many days back,
    ``all``/unknown -> no bound at all.
    """
    key = (since or "all").strip().lower()
    if key in ("", "all"):
        return None
    now = int(now if now is not None else time.time())
    if key == "today":
        local = time.localtime(now)
        return int(time.mktime((local.tm_year, local.tm_mon, local.tm_mday, 0, 0, 0, 0, 0, -1)))
    if key == "7d":
        return now - 7 * 86400
    if key == "30d":
        return now - 30 * 86400
    return None


def server_tz_offset_minutes() -> int:
    """Minutes east of UTC for the server's local timezone."""
    return _offset_minutes(time.localtime())


def _offset_minutes(local: time.struct_time) -> int:
    """Difference between the local wall clock and UTC, in minutes."""
    as_utc = time.gmtime(time.mktime(local))
    return int((time.mktime(local) - time.mktime(as_utc)) // 60)


def local_time_label(timestamp: Optional[int]) -> Optional[str]:
    """``HH:MM`` for today, ``DD.MM HH:MM`` for older rows (server local time)."""
    if not timestamp:
        return None
    stamp = time.localtime(int(timestamp))
    today = time.localtime()
    if stamp.tm_yday == today.tm_yday and stamp.tm_year == today.tm_year:
        return time.strftime("%H:%M", stamp)
    return time.strftime("%d.%m %H:%M", stamp)


def _parse_metadata(raw: Any) -> Any:
    if raw in (None, ""):
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return raw


def _run_row_to_dict(row) -> dict[str, Any]:
    started_at = int(row["started_at"] or 0)
    ended_at = row["ended_at"]
    duration = None
    if ended_at is not None and started_at:
        duration = int(ended_at) - started_at
    return {
        "id": int(row["id"]),
        "task_id": row["task_id"],
        "title": row["title"] or "",
        "profile": row["profile"],
        "step_key": row["step_key"],
        "status": row["status"],
        "outcome": row["outcome"],
        "started_at": started_at,
        "ended_at": int(ended_at) if ended_at is not None else None,
        "duration_sec": duration,
        "started_at_label": local_time_label(started_at),
        "ended_at_label": local_time_label(ended_at) if ended_at is not None else None,
        "summary": row["summary"],
        "error": row["error"],
        "metadata": _parse_metadata(row["metadata"]),
        "attachment_count": int(row["attachment_count"] or 0),
        "comment_count": int(row["comment_count"] or 0),
    }


def _clamp_limit(limit: Optional[int]) -> int:
    try:
        value = int(limit) if limit is not None else DEFAULT_LIMIT
    except (TypeError, ValueError):
        value = DEFAULT_LIMIT
    return max(1, min(value, MAX_LIMIT))


def build_log_payload(
    conn,
    *,
    assignee: Optional[str] = None,
    outcome: Optional[str] = None,
    task: Optional[str] = None,
    since: Optional[str] = None,
    limit: Optional[int] = None,
    before: Optional[int] = None,
    before_id: Optional[int] = None,
    q: Optional[str] = None,
) -> dict[str, Any]:
    """Return the execution-log page: finished runs, newest first."""
    limit = _clamp_limit(limit)
    where: list[str] = []
    params: list[Any] = []

    if assignee:
        where.append("r.profile = ?")
        params.append(assignee)
    if outcome:
        where.append("r.outcome = ?")
        params.append(outcome)
    if task:
        where.append("r.task_id = ?")
        params.append(task)
    cutoff = since_cutoff(since)
    if cutoff is not None:
        where.append("r.started_at >= ?")
        params.append(cutoff)
    if before is not None:
        # Cursor: the last row of the previous page. The id tie-breaker keeps
        # rows that share a started_at second on the correct side of the border.
        if before_id is not None:
            where.append("(r.started_at < ? OR (r.started_at = ? AND r.id < ?))")
            params.extend([int(before), int(before), int(before_id)])
        else:
            where.append("r.started_at < ?")
            params.append(int(before))
    needle = (q or "").strip()
    if needle:
        pattern = _like_pattern(needle.lower())
        where.append(
            "(LOWER(COALESCE(r.summary,'')) LIKE ? ESCAPE '\\'"
            " OR LOWER(COALESCE(r.error,'')) LIKE ? ESCAPE '\\'"
            " OR LOWER(COALESCE(t.title,'')) LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern, pattern, pattern])

    where_sql = f" WHERE {' AND '.join(where)}" if where else ""

    rows = conn.execute(
        f"""
        SELECT {_RUN_COLUMNS}
        FROM task_runs r
        LEFT JOIN tasks t ON t.id = r.task_id
        LEFT JOIN (
            SELECT task_id, COUNT(*) AS comment_count FROM task_comments GROUP BY task_id
        ) c ON c.task_id = r.task_id
        LEFT JOIN (
            SELECT task_id, COUNT(*) AS attachment_count FROM task_attachments GROUP BY task_id
        ) a ON a.task_id = r.task_id
        {where_sql}
        ORDER BY r.started_at DESC, r.id DESC
        LIMIT ?
        """,
        [*params, limit + 1],
    ).fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]
    runs = [_run_row_to_dict(row) for row in rows]

    next_before = runs[-1]["started_at"] if runs else None
    next_before_id = runs[-1]["id"] if runs else None

    profiles = [
        row["profile"]
        for row in conn.execute(
            "SELECT DISTINCT profile FROM task_runs WHERE profile IS NOT NULL AND profile != '' ORDER BY profile"
        ).fetchall()
    ]
    outcomes = [
        row["outcome"]
        for row in conn.execute(
            "SELECT DISTINCT outcome FROM task_runs WHERE outcome IS NOT NULL AND outcome != '' ORDER BY outcome"
        ).fetchall()
    ]
    total = int(
        conn.execute(
            f"SELECT COUNT(*) AS n FROM task_runs r LEFT JOIN tasks t ON t.id = r.task_id{where_sql}",
            params,
        ).fetchone()["n"]
    )

    return {
        "runs": runs,
        "total": total,
        "next_before": next_before,
        "next_before_id": next_before_id,
        "has_more": has_more,
        "profiles": profiles,
        "outcomes": outcomes,
        "server_now": int(time.time()),
        "server_tz_offset_minutes": server_tz_offset_minutes(),
    }


def build_log_events_payload(
    conn,
    *,
    assignee: Optional[str] = None,
    outcome: Optional[str] = None,
    task: Optional[str] = None,
    since: Optional[str] = None,
    kind: Optional[str] = None,
    include_heartbeat: bool = False,
    limit: Optional[int] = None,
    before: Optional[int] = None,
    before_id: Optional[int] = None,
) -> dict[str, Any]:
    """Return the event feed of the log view (heartbeats excluded by default)."""
    limit = _clamp_limit(limit)
    where: list[str] = []
    params: list[Any] = []

    if kind:
        where.append("e.kind = ?")
        params.append(kind)
    if not include_heartbeat:
        where.append("e.kind != 'heartbeat'")
    if task:
        where.append("e.task_id = ?")
        params.append(task)
    if assignee:
        # A run-less event inherits the profile of the task it belongs to.
        where.append("(r.profile = ? OR (e.run_id IS NULL AND t.assignee = ?))")
        params.extend([assignee, assignee])
    if outcome:
        where.append("r.outcome = ?")
        params.append(outcome)
    cutoff = since_cutoff(since)
    if cutoff is not None:
        where.append("e.created_at >= ?")
        params.append(cutoff)
    if before is not None:
        if before_id is not None:
            where.append("(e.created_at < ? OR (e.created_at = ? AND e.id < ?))")
            params.extend([int(before), int(before), int(before_id)])
        else:
            where.append("e.created_at < ?")
            params.append(int(before))

    where_sql = f" WHERE {' AND '.join(where)}" if where else ""

    rows = conn.execute(
        f"""
        SELECT e.id AS id, e.task_id AS task_id, e.run_id AS run_id, e.kind AS kind,
               e.payload AS payload, e.created_at AS created_at,
               t.title AS title, r.profile AS profile, r.outcome AS outcome
        FROM task_events e
        LEFT JOIN tasks t ON t.id = e.task_id
        LEFT JOIN task_runs r ON r.id = e.run_id
        {where_sql}
        ORDER BY e.created_at DESC, e.id DESC
        LIMIT ?
        """,
        [*params, limit + 1],
    ).fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]

    events = []
    for row in rows:
        payload = None
        if row["payload"]:
            try:
                payload = json.loads(row["payload"])
            except Exception:
                payload = row["payload"]
        events.append(
            {
                "id": int(row["id"]),
                "task_id": row["task_id"],
                "run_id": row["run_id"],
                "kind": row["kind"],
                "payload": payload,
                "created_at": int(row["created_at"] or 0),
                "created_at_label": local_time_label(row["created_at"]),
                "title": row["title"] or "",
                "profile": row["profile"],
                "outcome": row["outcome"],
            }
        )

    kinds = [
        row["kind"]
        for row in conn.execute("SELECT DISTINCT kind FROM task_events ORDER BY kind").fetchall()
    ]

    return {
        "events": events,
        "next_before": events[-1]["created_at"] if events else None,
        "next_before_id": events[-1]["id"] if events else None,
        "has_more": has_more,
        "kinds": kinds,
        "include_heartbeat": bool(include_heartbeat),
        "server_now": int(time.time()),
        "server_tz_offset_minutes": server_tz_offset_minutes(),
    }
