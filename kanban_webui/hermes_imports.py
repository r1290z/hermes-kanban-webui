"""Hermes import helpers.

The service runs from this standalone repo but deliberately reuses the installed
Hermes Kanban DB module as the single source of truth.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def ensure_hermes_importable() -> None:
    """Put the local Hermes checkout on sys.path when it is not installed.

    A Hermes source checkout commonly lives at ~/.hermes/hermes-agent and may
    already be injected in Hermes sessions. The start script can run outside
    that environment, so path resolution is explicit and predictable.
    """
    candidates = []
    env_root = os.environ.get("HERMES_AGENT_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())

    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        hh = Path(hermes_home).expanduser()
        candidates.extend([
            hh / "hermes-agent",
            hh.parent / "hermes-agent",
            hh.parent.parent / ".hermes" / "hermes-agent",
        ])

    user = os.environ.get("USER")
    if user:
        candidates.append(Path("/home") / user / ".hermes" / "hermes-agent")

    candidates.extend(
        [
            Path.home() / ".hermes" / "hermes-agent",
            Path.home() / ".local" / "share" / "hermes-agent",
        ]
    )
    for candidate in candidates:
        if (candidate / "hermes_cli" / "kanban_db.py").is_file():
            s = str(candidate)
            if s not in sys.path:
                sys.path.insert(0, s)
            return


ensure_hermes_importable()

try:  # noqa: E402 - path setup above is intentional
    from hermes_cli import kanban_db  # type: ignore
except Exception as exc:  # pragma: no cover - depends on host install
    raise RuntimeError(
        "Could not import hermes_cli.kanban_db. Set HERMES_AGENT_ROOT to the "
        "Hermes Agent checkout that contains hermes_cli/kanban_db.py."
    ) from exc


def _bridge_facade_gaps() -> None:
    """Hermes split ``kanban_db`` into a facade + siblings; two names moved.

    ``connect`` now lives in ``hermes_cli.kanban_db_connect`` and is not
    re-exported, and ``active_run`` has no counterpart at all — ``list_runs``
    carries the same information. Without this shim every board request dies on
    ``AttributeError: module 'hermes_cli.kanban_db' has no attribute 'connect'``.
    """
    if not hasattr(kanban_db, "connect"):
        from hermes_cli.kanban_db_connect import connect  # type: ignore

        kanban_db.connect = connect  # type: ignore[attr-defined]

    if not hasattr(kanban_db, "active_run"):

        def active_run(conn, task_id):  # noqa: ANN001, ANN202
            for run in reversed(kanban_db.list_runs(conn, task_id, include_active=True)):
                if run.ended_at is None:
                    return run
            return None

        kanban_db.active_run = active_run  # type: ignore[attr-defined]


_bridge_facade_gaps()
