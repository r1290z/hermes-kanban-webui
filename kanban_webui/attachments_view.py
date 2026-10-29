"""Task attachments: listing, safe streaming download, and upload.

The blob lives under ``kanban_db.attachments_root(board)`` and its metadata row
in ``task_attachments``. ``stored_path`` comes from the DB and is untrusted: it
is only used after a ``Path.resolve()`` containment check against the board's
attachments root. The DB ``filename`` never becomes part of a filesystem path —
it only surfaces in the ``Content-Disposition`` header.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Iterator, Optional
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from .hermes_imports import kanban_db

DOWNLOAD_CHUNK_BYTES = 256 * 1024
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

AttachmentTooLarge = getattr(kanban_db, "AttachmentTooLarge", ValueError)


def _resolve_within_root(board: str, stored_path: str) -> Path:
    """Resolve the DB-provided path and refuse anything outside the root."""
    root = kanban_db.attachments_root(board=board).resolve()
    resolved = Path(str(stored_path or "")).resolve()
    if not resolved.is_relative_to(root):
        raise HTTPException(
            status_code=403,
            detail="attachment stored_path is outside the attachments directory",
        )
    return resolved


def _attachment_row(conn, task_id: str, attachment_id: int):
    row = conn.execute(
        "SELECT * FROM task_attachments WHERE id = ? AND task_id = ?",
        (attachment_id, task_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"attachment {attachment_id} not found for task {task_id}")
    return row


def build_attachments_payload(conn, task_id: str, *, board: str) -> list[dict[str, Any]]:
    """Attachment metadata for the drawer, newest first, with a missing-file flag."""
    rows = conn.execute(
        "SELECT * FROM task_attachments WHERE task_id = ? ORDER BY created_at DESC, id DESC",
        (task_id,),
    ).fetchall()
    root = kanban_db.attachments_root(board=board).resolve()
    payload: list[dict[str, Any]] = []
    for row in rows:
        resolved = Path(str(row["stored_path"] or "")).resolve()
        missing = not (resolved.is_relative_to(root) and resolved.is_file())
        payload.append(
            {
                "id": int(row["id"]),
                "filename": row["filename"],
                "size": int(row["size"] or 0),
                "content_type": row["content_type"],
                "uploaded_by": row["uploaded_by"],
                "created_at": int(row["created_at"] or 0),
                "missing": missing,
            }
        )
    return payload


def _iter_file(path: Path, chunk: int = DOWNLOAD_CHUNK_BYTES) -> Iterator[bytes]:
    with open(path, "rb") as handle:
        while True:
            data = handle.read(chunk)
            if not data:
                return
            yield data


def build_download_response(conn, task_id: str, attachment_id: int, *, board: str) -> StreamingResponse:
    row = _attachment_row(conn, task_id, attachment_id)
    path = _resolve_within_root(board, row["stored_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="attachment file is missing on disk")

    filename = str(row["filename"] or f"attachment_{attachment_id}")
    content_type = str(row["content_type"] or "").strip() or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    disposition = "inline" if content_type.startswith("image/") else "attachment"
    headers = {
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(filename)}",
        "Content-Length": str(path.stat().st_size),
    }
    return StreamingResponse(_iter_file(path), media_type=content_type, headers=headers)


def store_upload(conn, task_id: str, *, board: str, filename: str, content_type: Optional[str], data: bytes) -> int:
    """Persist an uploaded blob through Hermes' single attachment write path.

    ``store_attachment_bytes`` sanitizes the filename, writes a collision-free
    blob under the task's attachments dir, and records the row (plus the
    ``attached`` event) via ``kanban_db.add_attachment`` — no direct table writes.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"attachment exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
    try:
        return kanban_db.store_attachment_bytes(
            conn,
            task_id,
            filename,
            data,
            content_type=content_type,
            uploaded_by="ui",
            board=board,
        )
    except AttachmentTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
