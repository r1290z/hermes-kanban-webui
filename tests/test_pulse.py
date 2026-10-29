from __future__ import annotations

import time


def _create_running_task(client, title: str) -> str:
    created = client.post('/api/tasks', json={'title': title, 'body': 'pulse test body'})
    assert created.status_code == 200, created.text
    task_id = created.json()['task']['id']
    claim = client.post(f'/api/tasks/{task_id}/claim', json={'claimer': 'test-worker', 'ttl_seconds': 600})
    assert claim.status_code == 200, claim.text
    heartbeat = client.post(f'/api/tasks/{task_id}/heartbeat', json={'note': 'alive'})
    assert heartbeat.status_code == 200, heartbeat.text
    return task_id


def test_pulse_requires_token(client, monkeypatch):
    monkeypatch.setenv('HERMES_KANBAN_WEBUI_TOKEN', 'secret-token')
    assert client.get('/api/pulse?tasks=t_x').status_code == 401
    ok = client.get('/api/pulse?tasks=t_x', headers={'X-Kanban-Token': 'secret-token'})
    assert ok.status_code == 200, ok.text
    data = ok.json()
    assert data['pulse'] == {}


def test_pulse_empty_tasks_returns_empty_pulse(client):
    data = client.get('/api/pulse').json()
    assert data['pulse'] == {}
    assert isinstance(data['now'], int)


def test_pulse_omits_tasks_without_active_run(client):
    _create_running_task(client, 'running one')
    done = client.post('/api/tasks', json={'title': 'idle one'})
    idle_id = done.json()['task']['id']

    # No ids requested at all.
    assert client.get('/api/pulse').json()['pulse'] == {}
    # Requested, but the task has no run.
    data = client.get(f'/api/pulse?tasks={idle_id}').json()
    assert data['pulse'] == {}


def test_pulse_elapsed_counts_from_started_at(client):
    task_id = _create_running_task(client, 'elapsed test')
    data = client.get(f'/api/pulse?tasks={task_id}').json()
    entry = data['pulse'][task_id]
    assert 0 <= entry['elapsed_sec'] <= 30
    assert 0 <= entry['heartbeat_age_sec'] <= 30
    assert entry['overdue'] is False
    assert entry['started_at'] <= data['now']

    # elapsed_sec == now - started_at of the active run (same clock).
    assert entry['elapsed_sec'] == data['now'] - entry['started_at']


def test_pulse_overdue_after_300s(client):
    task_id = _create_running_task(client, 'overdue test')
    from kanban_webui.hermes_imports import kanban_db

    conn = kanban_db.connect(board='default')
    try:
        conn.execute(
            "UPDATE task_runs SET last_heartbeat_at = ? WHERE task_id = ? AND status = 'running'",
            (int(time.time()) - 400, task_id),
        )
        conn.commit()
    finally:
        conn.close()

    data = client.get(f'/api/pulse?tasks={task_id}').json()
    entry = data['pulse'][task_id]
    assert entry['heartbeat_age_sec'] >= 400
    assert entry['overdue'] is True


def test_pulse_foreign_task_does_not_leak(client):
    first = _create_running_task(client, 'requested task')
    second = _create_running_task(client, 'not requested task')

    data = client.get(f'/api/pulse?tasks={first}').json()
    assert set(data['pulse']) == {first}
    assert second not in data['pulse']

    both = client.get(f'/api/pulse?tasks={first},{second}').json()
    assert set(both['pulse']) == {first, second}
