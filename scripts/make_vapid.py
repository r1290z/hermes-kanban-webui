#!/usr/bin/env python3
"""Генерация VAPID-пары для web-push (спека §10.2).

Один раз на сервер:

    python scripts/make_vapid.py

Кладёт приватный ключ в ``~/.hermes/kanban-webui/vapid-private.pem`` (chmod 600,
каталог 700) и печатает публичный ключ в base64url — тот же, что отдаёт
``GET /api/push/key``. Приватный ключ не попадает ни в git, ни в тело задачи.

Повторный запуск безопасен: если пара уже есть, скрипт её не трогает и просто
печатает публичный ключ. ``--force`` перегенерирует пару — после этого все
существующие подписки становятся недействительными (403 от FCM), их надо
оформить заново с телефона.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # запуск как scripts/make_vapid.py
    sys.path.insert(0, str(ROOT))

from kanban_webui import push_view  # noqa: E402


def generate(private_key_path: Path) -> str:
    """Создать пару и вернуть публичный ключ (base64url)."""
    from py_vapid import Vapid

    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(private_key_path.parent, 0o700)

    vapid = Vapid()
    vapid.generate_keys()
    vapid.save_key(str(private_key_path))
    os.chmod(private_key_path, 0o600)
    return push_view.vapid_public_key(private_key_path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="VAPID-пара для web-push KanbanWebUI")
    parser.add_argument("--state-dir", type=Path, default=None, help="каталог состояния WebUI")
    parser.add_argument("--force", action="store_true", help="перегенерировать существующую пару")
    args = parser.parse_args(argv)

    directory = Path(args.state_dir) if args.state_dir else push_view.state_dir()
    private_key_path = directory / "vapid-private.pem"

    if private_key_path.is_file() and not args.force:
        print(f"пара уже есть: {private_key_path}")
        print(f"public_key: {push_view.vapid_public_key(private_key_path)}")
        print("перегенерировать: --force (все текущие подписки после этого недействительны)")
        return 0

    key = generate(private_key_path)
    print(f"приватный ключ: {private_key_path} (chmod 600)")
    print(f"public_key: {key}")
    if args.force:
        print("пара перегенерирована: оформите подписку на телефоне заново")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
