from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Hermes-бутстрап, которого касается импорт kanban_db, в «чужом» venv делает
# os.execv в интерпретатор из ~/.hermes/tools: pytest молча умирает посреди
# прогона (exit 1, без трейсбека). WebUI ничего не доустанавливает — флаг гасит
# ленивую доустановку на всё время тестов.
os.environ.setdefault("HERMES_DISABLE_LAZY_INSTALLS", "1")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    home = tmp_path / 'hermes-home'
    webui_state = tmp_path / 'kanban-webui-state'
    monkeypatch.setenv('HERMES_KANBAN_HOME', str(home))
    monkeypatch.setenv('HERMES_REAL_HOME', str(home))
    monkeypatch.setenv('HERMES_KANBAN_WEBUI_STATE', str(webui_state))
    monkeypatch.delenv('HERMES_KANBAN_DB', raising=False)
    monkeypatch.delenv('HERMES_KANBAN_BOARD', raising=False)
    monkeypatch.delenv('HERMES_KANBAN_WEBUI_TOKEN', raising=False)
    # Tests exercise a normal interactive process, not a delegated child: the
    # worker-spawn marker would fence the DB read-only and break init.
    monkeypatch.delenv('HERMES_DELEGATED_CHILD_CONTEXT', raising=False)
    from kanban_webui.hermes_imports import kanban_db

    kanban_db._INITIALIZED_PATHS.clear()
    from kanban_webui.app import create_app

    with TestClient(create_app()) as c:
        yield c
