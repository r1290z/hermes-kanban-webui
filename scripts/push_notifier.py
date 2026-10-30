#!/usr/bin/env python3
"""Отправитель web-push по событиям Kanban (спека §10.2).

Читает ``task_events`` с ``id > `` курсора из ``~/.hermes/kanban-webui/push-cursor.json``
и отправляет пуш только на те события, ради которых телефон стоит доставать:

* ``completed`` — прогон завершён;
* ``worker_result`` с ``exit_code != 0`` — прогон упал;
* ``crashed``, ``timed_out``, ``blocked``.

``heartbeat`` (больше половины таблицы), ``created``, ``edited``, ``promoted``,
``dependency_wait``, ``attached`` — шум, они не отправляются никогда.

``kanban.db`` открывается read-only: база общая с CLI и диспетчером, отправитель
здесь только читатель. Подписки и курсор — в каталоге состояния WebUI.

Запуск (вручную или из таймера, см. deploy/systemd/):

    python scripts/push_notifier.py --dry-run     # печатает пейлоады, ничего не шлёт
    python scripts/push_notifier.py               # реальная отправка
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, TextIO

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # запуск как scripts/push_notifier.py
    sys.path.insert(0, str(ROOT))

from kanban_webui import push_view  # noqa: E402

# Ровно те виды событий, которые будят человека. Остальное — см. докстринг.
PUSH_KINDS = ("completed", "worker_result", "crashed", "timed_out", "blocked")
# Виды, которые длятся: к тексту добавляется время прогона.
DURATION_KINDS = {"completed", "crashed", "timed_out"}

TEXTS = {
    "completed": "Прогон завершён",
    "crashed": "Прогон сорвался",
    "timed_out": "Прогон прерван по таймауту",
    "blocked": "Задача заблокирована",
}

CURSOR_NAME = "push-cursor.json"
DEFAULT_LOOKBACK = 500

Sender = Callable[[dict[str, Any], dict[str, Any], Path], None]


@dataclass
class RunResult:
    events: int = 0
    sent: int = 0
    failed: int = 0
    dropped: int = 0
    subscriptions: int = 0
    last_event_id: int = 0
    notes: list[str] = field(default_factory=list)


# ===== Курсор =====


def cursor_path(state_dir: Optional[Path] = None) -> Path:
    return Path(state_dir or push_view.state_dir()) / CURSOR_NAME


def load_cursor(state_dir: Optional[Path] = None) -> Optional[int]:
    path = cursor_path(state_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        return int(data.get("last_event_id"))
    except (TypeError, ValueError):
        return None


def save_cursor(event_id: int, state_dir: Optional[Path] = None) -> None:
    """Атомарная запись: таймер не должен читать половину файла."""
    path = cursor_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"last_event_id": int(event_id)}), encoding="utf-8")
    tmp.replace(path)


# ===== Чтение событий =====


def kanban_db_path() -> Path:
    """Путь к kanban.db через hermes_cli (учитывает HERMES_KANBAN_DB и борд)."""
    try:
        from kanban_webui.hermes_imports import kanban_db

        return Path(kanban_db.kanban_db_path())
    except Exception:
        pinned = os.environ.get("HERMES_KANBAN_DB", "").strip()
        if pinned:
            return Path(pinned).expanduser()
        return Path.home() / ".hermes" / "kanban.db"


def read_only_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def max_event_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM task_events").fetchone()
    return int(row["m"])


def _parse_payload(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def is_pushworthy(kind: str, payload: dict[str, Any]) -> bool:
    if kind not in PUSH_KINDS:
        return False
    if kind == "worker_result":
        try:
            return int(payload.get("exit_code") or 0) != 0
        except (TypeError, ValueError):
            return True
    return True


def select_events(
    conn: sqlite3.Connection, after_id: int = 0, limit: int = 200
) -> list[dict[str, Any]]:
    """События после курсора, отфильтрованные до тех, что стоит отправлять."""
    placeholders = ",".join("?" for _ in PUSH_KINDS)
    rows = conn.execute(
        f"""
        SELECT e.id AS id, e.task_id AS task_id, e.run_id AS run_id, e.kind AS kind,
               e.payload AS payload, e.created_at AS created_at,
               t.title AS task_title, t.started_at AS task_started_at,
               r.started_at AS run_started_at
        FROM task_events e
        LEFT JOIN tasks t ON t.id = e.task_id
        LEFT JOIN task_runs r ON r.id = e.run_id
        WHERE e.id > ? AND e.kind IN ({placeholders})
        ORDER BY e.id ASC
        LIMIT ?
        """,
        (int(after_id), *PUSH_KINDS, int(limit)),
    ).fetchall()
    events = []
    for row in rows:
        item = dict(row)
        item["payload"] = _parse_payload(item["payload"])
        if not is_pushworthy(item["kind"], item["payload"]):
            continue
        events.append(item)
    return events


# ===== Пейлоад =====


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    if total < 60:
        return "меньше минуты"
    if total < 3600:
        return f"{total // 60} мин"
    hours, minutes = divmod(total // 60, 60)
    return f"{hours} ч {minutes} мин" if minutes else f"{hours} ч"


def build_payload(event: dict[str, Any], *, include_title: bool = False) -> dict[str, Any]:
    """Пейлоад контракта §10.2.

    Заголовок задачи по умолчанию не попадает в текст: он виден на локскрине,
    поэтому включается только ``PUSH_INCLUDE_TITLE=true`` (аргумент
    ``include_title``).
    """
    kind = event["kind"]
    task_id = event["task_id"]
    text = TEXTS.get(kind, "Kanban")
    if kind == "worker_result":
        code = event["payload"].get("exit_code")
        text = f"Прогон упал · код {code}" if code is not None else "Прогон упал"

    parts = [text, task_id]
    if kind in DURATION_KINDS:
        started = event.get("run_started_at") or event.get("task_started_at")
        if started:
            parts.append(format_duration(int(event["created_at"]) - int(started)))
    body = " · ".join(parts)
    if include_title and event.get("task_title"):
        body = f"{body} · {event['task_title']}"

    return {
        "title": "Kanban",
        "body": body,
        "tag": f"task:{task_id}",
        "task_id": task_id,
        "url": f"/#task={task_id}",
    }


# ===== Отправка =====


def send_webpush(subscription: dict[str, Any], payload: dict[str, Any], private_key_path: Path) -> None:
    """Реальная отправка. 404/410 прилетают как ``WebPushException``."""
    from pywebpush import webpush

    webpush(
        subscription_info=push_view.subscription_info(subscription),
        data=json.dumps(payload, ensure_ascii=False),
        vapid_private_key=str(private_key_path),
        vapid_claims={"sub": os.environ.get("PUSH_VAPID_SUB", "mailto:hermes@localhost")},
        ttl=int(os.environ.get("PUSH_TTL", "600")),
        timeout=15,
    )


def _status_code(exc: BaseException) -> Optional[int]:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None) if response is not None else None
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def include_title_default() -> bool:
    return os.environ.get("PUSH_INCLUDE_TITLE", "").strip().lower() in {"1", "true", "yes", "on"}


def run(
    *,
    db_path: Optional[Path] = None,
    state_dir: Optional[Path] = None,
    dry_run: bool = False,
    lookback: int = DEFAULT_LOOKBACK,
    limit: int = 200,
    sender: Optional[Sender] = None,
    out: Optional[TextIO] = None,
    include_title: Optional[bool] = None,
) -> RunResult:
    log = out if out is not None else sys.stdout
    store = Path(state_dir or push_view.state_dir())
    database = Path(db_path) if db_path is not None else kanban_db_path()
    include = include_title_default() if include_title is None else bool(include_title)
    result = RunResult()

    if not database.is_file():
        raise FileNotFoundError(f"нет базы Kanban: {database}")

    subscriptions = _subscriptions_in(store)
    result.subscriptions = len(subscriptions)

    conn = read_only_connect(database)
    try:
        cursor = load_cursor(store)
        newest = max_event_id(conn)
        if cursor is None:
            if dry_run:
                # Демонстрация: показываем разумное окно истории, курсор не пишем.
                cursor = max(0, newest - int(lookback))
                result.notes.append(f"курсора нет: dry-run смотрит назад до события {cursor}")
            else:
                # Без курсора начинаем «сейчас»: иначе первый запуск выпалит
                # сотни старых уведомлений разом.
                save_cursor(newest, store)
                result.last_event_id = newest
                result.notes.append(f"курсор инициализирован на {newest}, история не отправляется")
                return result
        events = select_events(conn, after_id=cursor, limit=limit)
    finally:
        conn.close()

    if not events:
        result.last_event_id = int(cursor or 0)
        result.notes.append("новых событий нет")
        return result

    send = sender or send_webpush
    private_key = Path(store) / "vapid-private.pem"
    if not dry_run and subscriptions and sender is None and not private_key.is_file():
        raise push_view.PushConfigError(
            f"нет VAPID-пары {private_key} — запустите scripts/make_vapid.py"
        )
    last_ok = int(cursor or 0)
    for event in events:
        payload = build_payload(event, include_title=include)
        if dry_run:
            print(
                f"[dry-run] event {event['id']} {event['kind']} {event['task_id']}: "
                f"{json.dumps(payload, ensure_ascii=False)}",
                file=log,
            )
            result.events += 1
            continue

        result.events += 1
        event_failed = False
        for subscription in list(subscriptions):
            try:
                send(subscription, payload, private_key)
                result.sent += 1
            except Exception as exc:  # noqa: BLE001 — решаем по статусу ответа FCM
                status = _status_code(exc)
                if status in {404, 410}:
                    _drop(subscription["endpoint"], store)
                    subscriptions.remove(subscription)
                    result.dropped += 1
                    print(
                        f"подписка {_short(subscription['endpoint'])} мертва ({status}), удалена",
                        file=log,
                    )
                else:
                    result.failed += 1
                    event_failed = True
                    print(
                        f"не отправлено событие {event['id']} "
                        f"на {_short(subscription['endpoint'])}: {exc}",
                        file=log,
                    )
        if event_failed:
            # Не перепрыгиваем событие, которое не ушло: следующий тик повторит.
            save_cursor(int(event["id"]) - 1, store)
            result.last_event_id = int(event["id"]) - 1
            result.notes.append(f"остановились на событии {event['id']}: повтор в следующий тик")
            return result
        last_ok = int(event["id"])
        save_cursor(last_ok, store)

    result.last_event_id = last_ok if not dry_run else int(cursor or 0)
    return result


def _short(endpoint: str) -> str:
    return endpoint[-24:] if len(endpoint) > 24 else endpoint


def _subscriptions_in(store: Path) -> list[dict[str, Any]]:
    db = store / "push.db"
    if not db.is_file():
        return []
    conn = push_view.connect(db)
    try:
        return push_view.list_subscriptions(conn)
    finally:
        conn.close()


def _drop(endpoint: str, store: Path) -> None:
    conn = push_view.connect(store / "push.db")
    try:
        push_view.delete_subscription(conn, endpoint)
    finally:
        conn.close()


# ===== CLI =====


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Отправка web-push по событиям Kanban")
    parser.add_argument("--dry-run", action="store_true", help="печатать пейлоады, ничего не отправляя")
    parser.add_argument("--db", type=Path, default=None, help="путь к kanban.db (по умолчанию из hermes_cli)")
    parser.add_argument("--state-dir", type=Path, default=None, help="каталог состояния WebUI")
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK, help="окно истории для dry-run без курсора")
    parser.add_argument("--limit", type=int, default=200, help="сколько событий брать за тик")
    parser.add_argument("--include-title", action="store_true", default=None, help="добавить заголовок задачи в текст")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run(
            db_path=args.db,
            state_dir=args.state_dir,
            dry_run=args.dry_run,
            lookback=args.lookback,
            limit=args.limit,
            include_title=args.include_title,
        )
    except (FileNotFoundError, push_view.PushConfigError) as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return 2

    mode = "dry-run" if args.dry_run else "отправка"
    print(
        f"{mode}: событий {result.events}, отправлено {result.sent}, "
        f"ошибок {result.failed}, мёртвых подписок {result.dropped}, "
        f"подписок {result.subscriptions}, курсор {result.last_event_id}"
    )
    for note in result.notes:
        print(f"  · {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
