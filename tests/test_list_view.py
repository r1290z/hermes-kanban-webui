from __future__ import annotations


def _create(client, title, assignee=None, status=None, priority=None, body=None):
    payload = {'title': title}
    if assignee:
        payload['assignee'] = assignee
    if body:
        payload['body'] = body
    r = client.post('/api/tasks', json=payload)
    assert r.status_code == 200, r.text
    task_id = r.json()['task']['id']
    patch = {}
    if status:
        patch['status'] = status
    if priority is not None:
        patch['priority'] = priority
    if patch:
        r = client.patch(f'/api/tasks/{task_id}', json=patch)
        assert r.status_code == 200, r.text
    return task_id


def test_list_requires_no_special_setup_and_returns_shape(client):
    _create(client, 'List shape task', assignee='dev')
    r = client.get('/api/list')
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data) >= {'tasks', 'total', 'assignees', 'statuses'}
    assert data['total'] >= 1
    task = data['tasks'][0]
    for key in ('id', 'title', 'status', 'assignee', 'priority', 'created_at', 'updated_at',
                'run_count', 'comment_count', 'attachment_count'):
        assert key in task


def test_list_filter_by_assignee(client):
    _create(client, 'Alpha for dev', assignee='dev')
    _create(client, 'Beta for ops', assignee='ops')

    data = client.get('/api/list', params={'assignee': 'dev'}).json()
    titles = [task['title'] for task in data['tasks']]
    assert titles == ['Alpha for dev']
    assert data['total'] == 1
    assert 'dev' in data['assignees'] and 'ops' in data['assignees']

    both = client.get('/api/list', params={'assignee': 'dev,ops'}).json()
    assert both['total'] == 2


def test_list_filter_by_status(client):
    task_triage = _create(client, 'Triage one', assignee='dev', status='triage')
    _create(client, 'Blocked one', assignee='dev', status='blocked')

    data = client.get('/api/list', params={'status': 'blocked'}).json()
    assert [task['id'] for task in data['tasks']] != [task_triage]
    assert all(task['status'] == 'blocked' for task in data['tasks'])
    assert 'blocked' in data['statuses']

    several = client.get('/api/list', params={'status': 'blocked,triage'}).json()
    assert several['total'] == 2


def test_list_search_matches_title_and_body_case_insensitive(client):
    _create(client, 'Deploy payment service', assignee='dev', body='payout module')
    _create(client, 'Unrelated chore', assignee='dev')

    by_title = client.get('/api/list', params={'q': 'PAYMENT'}).json()
    assert [task['title'] for task in by_title['tasks']] == ['Deploy payment service']

    by_body = client.get('/api/list', params={'q': 'payout'}).json()
    assert by_body['total'] == 1

    none = client.get('/api/list', params={'q': 'zzz-no-such-thing'}).json()
    assert none['tasks'] == [] and none['total'] == 0


def test_list_search_escapes_like_wildcards(client):
    _create(client, '100% real task', assignee='dev')
    _create(client, 'underscore_task', assignee='dev')

    data = client.get('/api/list', params={'q': '100%'}).json()
    assert [task['title'] for task in data['tasks']] == ['100% real task']

    data = client.get('/api/list', params={'q': 'underscore_'}).json()
    assert [task['title'] for task in data['tasks']] == ['underscore_task']


def test_list_archived_toggle(client):
    _create(client, 'Keep me visible', assignee='dev')
    archived_id = _create(client, 'Archive me', assignee='dev', status='archived')

    default = client.get('/api/list').json()
    assert all(task['id'] != archived_id for task in default['tasks'])

    with_archive = client.get('/api/list', params={'archived': 1}).json()
    assert any(task['id'] == archived_id for task in with_archive['tasks'])


def test_list_sorting(client):
    _create(client, 'B task', assignee='dev', priority=5)
    _create(client, 'A task', assignee='dev', priority=1)

    by_title = client.get('/api/list', params={'sort': 'title', 'dir': 'asc'}).json()
    titles = [task['title'] for task in by_title['tasks'] if task['title'] in ('A task', 'B task')]
    assert titles == ['A task', 'B task']

    by_title_desc = client.get('/api/list', params={'sort': 'title', 'dir': 'desc'}).json()
    titles_desc = [task['title'] for task in by_title_desc['tasks'] if task['title'] in ('A task', 'B task')]
    assert titles_desc == ['B task', 'A task']

    by_priority = client.get('/api/list', params={'sort': 'priority', 'dir': 'asc'}).json()
    priorities = [task['title'] for task in by_priority['tasks'][:2]]
    assert priorities == ['A task', 'B task']

    unknown_sort = client.get('/api/list', params={'sort': 'hacker; DROP TABLE tasks'}).json()
    assert unknown_sort['total'] == 2


def test_list_counters_not_duplicated_for_multiple_runs(client):
    task_id = _create(client, 'Counted task', assignee='dev')
    for _ in range(3):
        r = client.post(f'/api/tasks/{task_id}/comments', json={'body': 'note'})
        assert r.status_code == 200, r.text

    data = client.get('/api/list', params={'q': 'Counted'}).json()
    assert data['total'] == 1
    task = data['tasks'][0]
    assert task['comment_count'] == 3
    assert task['run_count'] == 0
    assert task['attachment_count'] == 0


def test_list_empty_result_is_well_formed(client):
    data = client.get('/api/list', params={'assignee': 'nobody-xyz'}).json()
    assert data == {'tasks': [], 'total': 0, 'assignees': [], 'statuses': []}


def test_list_pagination(client):
    for index in range(5):
        _create(client, f'Page task {index:02d}', assignee='dev')

    first = client.get('/api/list', params={'sort': 'title', 'dir': 'asc', 'limit': 2, 'offset': 0}).json()
    second = client.get('/api/list', params={'sort': 'title', 'dir': 'asc', 'limit': 2, 'offset': 2}).json()
    assert first['total'] == 5
    assert len(first['tasks']) == 2
    assert first['tasks'][0]['id'] != second['tasks'][0]['id']
    titles = [task['title'] for task in first['tasks'] + second['tasks']]
    assert titles == sorted(titles)
