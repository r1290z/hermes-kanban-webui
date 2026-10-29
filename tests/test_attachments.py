"""Attachment endpoints: list, safe streaming download, upload."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from kanban_webui.hermes_imports import kanban_db


def _create_task(client, title="att task"):
    res = client.post("/api/tasks", json={"title": title, "body": "b"})
    assert res.status_code == 200
    return res.json()["task"]["id"]


def _attach(task_id, filename, data, content_type="application/octet-stream", uploaded_by="tester"):
    conn = kanban_db.connect()
    try:
        return kanban_db.store_attachment_bytes(
            conn, task_id, filename, data, content_type=content_type, uploaded_by=uploaded_by
        )
    finally:
        conn.close()


def _raw_attach(task_id, filename, stored_path, size=1, content_type="application/octet-stream"):
    """Insert a metadata row directly (simulates a corrupted/foreign stored_path)."""
    conn = kanban_db.connect()
    try:
        return kanban_db.add_attachment(
            conn,
            task_id,
            filename=filename,
            stored_path=stored_path,
            content_type=content_type,
            size=size,
            uploaded_by="tester",
        )
    finally:
        conn.close()


def test_list_returns_only_own_task_attachments(client):
    task_a = _create_task(client, "A")
    task_b = _create_task(client, "B")
    _attach(task_a, "report.md", b"hello a", content_type="text/markdown")
    _attach(task_b, "other.md", b"hello b", content_type="text/markdown")

    res = client.get(f"/api/tasks/{task_a}/attachments")
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list)
    assert len(items) == 1
    item = items[0]
    assert item["filename"] == "report.md"
    assert item["size"] == len(b"hello a")
    assert item["content_type"] == "text/markdown"
    assert item["uploaded_by"] == "tester"
    assert item["missing"] is False

    empty = client.get(f"/api/tasks/{_create_task(client, 'C')}/attachments")
    assert empty.status_code == 200
    assert empty.json() == []


def test_download_matches_db_size(client):
    task = _create_task(client)
    payload = b"x" * 4261
    att_id = _attach(task, "CLEANUP_REPORT.md", payload, content_type="text/markdown")

    res = client.get(f"/api/tasks/{task}/attachments/{att_id}")
    assert res.status_code == 200
    assert len(res.content) == len(payload)
    assert res.headers["content-type"].startswith("text/markdown")
    assert "attachment" in res.headers["content-disposition"].lower()
    assert "CLEANUP_REPORT.md" in res.headers["content-disposition"]


def test_download_image_is_inline(client):
    task = _create_task(client)
    att_id = _attach(task, "pic.png", b"\x89PNG\r\n", content_type="image/png")

    res = client.get(f"/api/tasks/{task}/attachments/{att_id}")
    assert res.status_code == 200
    assert res.headers["content-disposition"].startswith("inline")


def test_foreign_task_attachment_is_404(client):
    task_a = _create_task(client, "A")
    task_b = _create_task(client, "B")
    att_b = _attach(task_b, "b.md", b"b data")

    res = client.get(f"/api/tasks/{task_a}/attachments/{att_b}")
    assert res.status_code == 404


def test_stored_path_outside_attachments_dir_is_403(client):
    task = _create_task(client)
    att_id = _raw_attach(task, "passwd", "/etc/passwd", size=100)

    res = client.get(f"/api/tasks/{task}/attachments/{att_id}")
    assert res.status_code == 403


def test_missing_file_on_disk_is_404_and_flagged(client):
    task = _create_task(client)
    conn = kanban_db.connect()
    try:
        root = kanban_db.attachments_root()
        stored = root / task / "ghost.bin"
    finally:
        conn.close()
    att_id = _raw_attach(task, "ghost.bin", str(stored), size=17)

    listing = client.get(f"/api/tasks/{task}/attachments").json()
    assert listing[0]["missing"] is True

    res = client.get(f"/api/tasks/{task}/attachments/{att_id}")
    assert res.status_code == 404


def test_upload_stores_file_and_returns_list(client):
    task = _create_task(client)
    res = client.post(
        f"/api/tasks/{task}/attachments",
        files={"file": ("заметка.md", io.BytesIO("привет".encode("utf-8")), "text/markdown")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    attachments = body["attachments"]
    assert len(attachments) == 1
    assert attachments[0]["filename"] == "заметка.md"
    assert attachments[0]["uploaded_by"] == "ui"

    att_id = body["attachment_id"]
    got = client.get(f"/api/tasks/{task}/attachments/{att_id}")
    assert got.status_code == 200
    assert got.content == "привет".encode("utf-8")


def test_upload_over_limit_is_413(client, monkeypatch):
    import kanban_webui.attachments_view as view

    task = _create_task(client)
    monkeypatch.setattr(view, "MAX_UPLOAD_BYTES", 4)
    res = client.post(
        f"/api/tasks/{task}/attachments",
        files={"file": ("big.bin", io.BytesIO(b"12345678"), "application/octet-stream")},
    )
    assert res.status_code == 413


def test_attachment_counts_in_board_and_list(client):
    task = _create_task(client)
    _attach(task, "one.md", b"1")
    _attach(task, "two.md", b"22")

    board = client.get("/api/board").json()
    board_item = next(t for t in board["tasks"] if t["id"] == task)
    assert board_item["attachment_count"] == 2

    listing = client.get("/api/list").json()
    list_item = next(t for t in listing["tasks"] if t["id"] == task)
    assert list_item["attachment_count"] == 2
