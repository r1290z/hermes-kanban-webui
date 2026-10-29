"""Tests for the execution-log view (/api/log and /api/log/events)."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from kanban_webui.hermes_imports import kanban_db


def _db_path() -> Path:
    return kanban_db.kanban_db_path()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def _create_task(client, title: str, assignee: str | None = None) -> str:
    payload = {'title': title}
    if assignee:
        payload['assignee'] = assignee
    r = client.post('/api/tasks', json=payload)
    assert r.status_code == 200, r.text
    return r.json()['task']['id']


def _insert_run(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    profile: str = 'coder',
    outcome: str | None = 'completed',
    started_at: int | None = None,
    ended_at: int | None = None,
    summary: str | None = 'Готово',
    error: str | None = None,
    metadata: dict | None = None,
) -> int:
    now = int(time.time())
    started_at = started_at if started_at is not None else now
    cur = conn.execute(
        """
        INSERT INTO task_runs
            (task_id, profile, status, started_at, ended_at, outcome, summary, error, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            profile,
            outcome or 'running',
            started_at,
            ended_at,
            outcome,
            summary,
            error,
            json.dumps(metadata, ensure_ascii=False) if metadata else None,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _insert_event(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    kind: str = 'commented',
    run_id: int | None = None,
    created_at: int | None = None,
    payload: dict | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO task_events (task_id, run_id, kind, payload, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            task_id,
            run_id,
            kind,
            json.dumps(payload, ensure_ascii=False) if payload else None,
            created_at if created_at is not None else int(time.time()),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def test_log_returns_every_run_without_duplicates(client):
    task_id = _create_task(client, 'Лог: базовый прогон')
    conn = _conn()
    try:
        for index in range(4):
            _insert_run(conn, task_id, started_at=1_700_000_000 + index * 60)
    finally:
        conn.close()

    data = client.get('/api/log').json()
    runs = [run for run in data['runs'] if run['task_id'] == task_id]
    assert len(runs) == 4
    assert len({run['id'] for run in runs}) == 4
    # newest first
    assert [run['started_at'] for run in runs] == sorted(
        (run['started_at'] for run in runs), reverse=True
    )


def test_log_filters_by_outcome_and_profile(client):
    first = _create_task(client, 'Лог: фильтр один')
    second = _create_task(client, 'Лог: фильтр два')
    conn = _conn()
    try:
        _insert_run(conn, first, profile='coder', outcome='completed')
        _insert_run(conn, first, profile='hermes', outcome='blocked', error='нет доступа')
        _insert_run(conn, second, profile='coder', outcome='crashed')
    finally:
        conn.close()

    completed = client.get('/api/log', params={'outcome': 'completed'}).json()
    assert all(run['outcome'] == 'completed' for run in completed['runs'])
    assert any(run['task_id'] == first for run in completed['runs'])

    coder = client.get('/api/log', params={'assignee': 'coder'}).json()
    assert coder['runs']
    assert all(run['profile'] == 'coder' for run in coder['runs'])
    assert {run['task_id'] for run in coder['runs']} == {first, second}

    blocked = client.get('/api/log', params={'outcome': 'blocked'}).json()
    assert [run['task_id'] for run in blocked['runs']] == [first]
    assert blocked['runs'][0]['error'] == 'нет доступа'

    by_task = client.get('/api/log', params={'task': second}).json()
    assert {run['task_id'] for run in by_task['runs']} == {second}

    assert 'coder' in coder['profiles']
    assert 'completed' in completed['outcomes']


def test_log_cursor_does_not_lose_or_repeat_rows(client):
    task_id = _create_task(client, 'Лог: курсор')
    conn = _conn()
    try:
        for index in range(7):
            _insert_run(conn, task_id, started_at=1_700_000_000 + index * 60)
    finally:
        conn.close()

    seen: list[int] = []
    before = None
    before_id = None
    for _ in range(10):
        params = {'limit': 3}
        if before is not None:
            params['before'] = before
            params['before_id'] = before_id
        data = client.get('/api/log', params=params).json()
        seen.extend(run['id'] for run in data['runs'])
        if not data['has_more']:
            break
        before = data['next_before']
        before_id = data['next_before_id']

    assert len(seen) == len(set(seen)), 'a run was repeated across pages'
    assert len(seen) == 7, 'a run was lost across pages'


def test_log_duration_is_null_for_unfinished_run(client):
    task_id = _create_task(client, 'Лог: длительность')
    conn = _conn()
    try:
        closed = _insert_run(
            conn, task_id, started_at=1_700_000_000, ended_at=1_700_000_734
        )
        open_run = _insert_run(conn, task_id, started_at=1_700_001_000, ended_at=None)
    finally:
        conn.close()

    data = client.get('/api/log').json()
    by_id = {run['id']: run for run in data['runs']}
    assert by_id[closed]['duration_sec'] == 734
    assert by_id[open_run]['ended_at'] is None
    assert by_id[open_run]['duration_sec'] is None


def test_log_events_hide_heartbeat_by_default(client):
    task_id = _create_task(client, 'Лог: события')
    conn = _conn()
    try:
        run_id = _insert_run(conn, task_id)
        _insert_event(conn, task_id, kind='commented', run_id=run_id)
        _insert_event(conn, task_id, kind='heartbeat', run_id=run_id)
    finally:
        conn.close()

    without = client.get('/api/log/events').json()
    kinds = {event['kind'] for event in without['events']}
    assert 'heartbeat' not in kinds
    assert 'commented' in kinds

    with_hb = client.get('/api/log/events', params={'include_heartbeat': 1}).json()
    assert 'heartbeat' in {event['kind'] for event in with_hb['events']}

    only_hb = client.get('/api/log/events', params={'kind': 'heartbeat', 'include_heartbeat': 1}).json()
    assert {event['kind'] for event in only_hb['events']} == {'heartbeat'}


def test_log_events_are_newest_first_and_carry_task_title(client):
    task_id = _create_task(client, 'Лог: заголовок события')
    conn = _conn()
    try:
        _insert_event(conn, task_id, kind='created', created_at=1_700_000_000)
        _insert_event(conn, task_id, kind='completed', created_at=1_700_000_600)
    finally:
        conn.close()

    events = client.get('/api/log/events').json()['events']
    titles = [event['title'] for event in events]
    assert 'Лог: заголовок события' in titles
    created_at = [event['created_at'] for event in events]
    assert created_at == sorted(created_at, reverse=True)


def test_log_searches_summary_text_and_reports_filtered_total(client):
    task_id = _create_task(client, 'Лог: поиск по summary')
    conn = _conn()
    try:
        _insert_run(conn, task_id, started_at=1_700_000_000, summary='Портал переведён на два провайдера')
        _insert_run(conn, task_id, started_at=1_700_000_060, summary='Ротация ключей выполнена')
    finally:
        conn.close()

    found = client.get('/api/log', params={'q': 'провайдера'}).json()
    assert found['total'] == 1
    assert 'провайдера' in found['runs'][0]['summary']

    assert client.get('/api/log', params={'q': 'нетакого'}).json()['runs'] == []


def test_log_since_today_excludes_old_runs(client):
    task_id = _create_task(client, 'Лог: период')
    old = int(time.time()) - 40 * 86400
    conn = _conn()
    try:
        _insert_run(conn, task_id, started_at=old)
        _insert_run(conn, task_id, started_at=int(time.time()))
    finally:
        conn.close()

    today = client.get('/api/log', params={'since': 'today'}).json()
    assert today['total'] == 1
    assert today['runs'][0]['started_at'] > old

    everything = client.get('/api/log', params={'since': 'all'}).json()
    assert everything['total'] == 2


def test_log_requires_auth_with_token(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_KANBAN_HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('HERMES_KANBAN_WEBUI_TOKEN', 'secret-token')
    monkeypatch.delenv('HERMES_KANBAN_DB', raising=False)
    monkeypatch.delenv('HERMES_KANBAN_BOARD', raising=False)
    kanban_db._INITIALIZED_PATHS.clear()
    from fastapi.testclient import TestClient

    from kanban_webui.app import create_app

    with TestClient(create_app()) as guarded:
        assert guarded.get('/api/log').status_code == 401
        assert guarded.get('/api/log/events').status_code == 401
        ok = guarded.get('/api/log', headers={'X-Kanban-Token': 'secret-token'})
        assert ok.status_code == 200, ok.text


LIVE_DB = Path.home() / '.hermes' / 'kanban.db'


@pytest.mark.skipif(not LIVE_DB.exists(), reason='no live kanban.db on this host')
def test_live_database_runs_are_all_reported():
    """The log view must not hide any run of the real board."""
    conn = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        expected = int(conn.execute("SELECT COUNT(*) AS n FROM task_runs").fetchone()["n"])
        payload = build_live_payload(conn)
    finally:
        conn.close()

    assert expected > 0
    assert payload['total'] == expected
    ids = [run['id'] for run in payload['runs']]
    assert len(ids) == len(set(ids))
    assert len(ids) == min(expected, 200)


def build_live_payload(conn):
    from kanban_webui import log_view

    return log_view.build_log_payload(conn, limit=200)
