# Hermes Kanban WebUI (LAN fork)

Веб-интерфейс к базе Hermes Kanban (`~/.hermes/kanban.db`) — та же база, что у CLI
и у моста TaskView. Отдельной схемы и своего диспетчера здесь нет.

Форк от `PriuS2/HermesKanban` (Apache-2.0). Отличия:

- **Русский язык** — третий язык рядом с корейским и английским, включён по умолчанию;
  кнопка в шапке переключает RU → EN → KO.
- **Совместимость с текущим Hermes** — `hermes_imports.py` достраивает два имени,
  которых нет в фасаде `hermes_cli.kanban_db`: `connect` (переехал в
  `kanban_db_connect`) и `active_run` (собирается из `list_runs`). Без этого каждый
  запрос падал с `AttributeError`.
- **Ввод токена в браузере** — при 401 показывается панель, токен уходит в
  `localStorage`. Блокирующий `window.prompt()` не используется: он вешает загрузку.
- **LAN-режим** — слушает `0.0.0.0:8790`; защита от cross-origin мутаций включена.
- **Колонка «Бэклог»** для `scheduled` — парковка больше не падает в «Ожидают».
- **Мобильный вид** — колонка на экран, шапка сжата, фильтры под кнопкой,
  перемещение карточки долгим нажатием (touch не даёт dragover, перетаскивание
  на телефоне не работало вовсе).
- **Токен ссылкой** — `#token=...` во фрагменте: во фрагменте он не уходит на
  сервер и не попадает в логи прокси; после чтения адрес очищается.
- **`ALLOWED_HOSTS=*`** — режим для работы за обратным прокси с HTTPS.

## Настройки

Всё в `~/.hermes/kanban-webui.env`, юнит читает его через `EnvironmentFile`:
правка файла + `systemctl --user restart hermes-kanban-webui` — и всё.

## Уведомления на телефон (web-push)

Пуш приходит на телефон, только когда прогон закончился или сломался: `completed`,
`worker_result` с `exit_code != 0`, `crashed`, `timed_out`, `blocked`. `heartbeat`
(больше половины `task_events`), `created`, `edited`, `promoted`, `dependency_wait`
не отправляются никогда — иначе уведомления выключают через день.

**1. VAPID-пара (один раз).** Приватный ключ ложится в
`~/.hermes/kanban-webui/vapid-private.pem` (chmod 600) и остаётся на сервере;
в git и в задачи он не попадает.

```bash
cd ~/projects/hermes-kanban-webui
./.venv/bin/python scripts/make_vapid.py      # печатает public_key
systemctl --user restart hermes-kanban-webui  # чтобы /api/push/key увидел пару
```

Повторный запуск ключ не трогает. `--force` перегенерирует пару, после этого все
подписки недействительны (FCM отвечает 403) — на телефоне надо подписаться заново.

**2. Кнопка на телефоне.** Панель «Ещё» → «Включить уведомления»
(`static/push.js`). Подписка оформляется только по жесту: `Notification.requestPermission()`
из обработчика клика, затем `pushManager.subscribe({applicationServerKey})` с ключом
из `GET /api/push/key` и `POST /api/push/subscribe`. Состояние видно строкой рядом:

| состояние | что значит |
|---|---|
| уведомления включены | подписка есть в браузере и в `push.db` |
| уведомления выключены | разрешение есть, подписки нет — нажмите кнопку |
| запрещены в браузере | `Notification.permission === 'denied'`, кнопки нет: разрешение возвращается только в настройках сайта |
| не поддерживается | нет службы push / secure context |

**Важно:** Push API работает только в secure context. По `http://192.168.144.122:8790`
браузер честно скажет «не поддерживается» — уведомления включаются на
`https://ai.r1290z.ru` (или на `http://localhost`). Иконка с домашнего экрана
(PWA) для Chrome не обязательна, для iOS ≥16.4 — обязательна.

**3. Каталог состояния.** `~/.hermes/kanban-webui/`:

| файл | что |
|---|---|
| `push.db` | таблица `subscriptions` (`kanban.db` не трогаем — он общий с CLI) |
| `vapid-private.pem` | приватный ключ VAPID, chmod 600 |
| `push-cursor.json` | `{"last_event_id": N}` — докуда дочитали `task_events` |

**4. Отправитель.** Раз в 30 с читает `task_events` с `id > cursor` (база
открывается read-only) и шлёт пуш через `pywebpush`.

```bash
./.venv/bin/python scripts/push_notifier.py --dry-run   # печатает пейлоады, ничего не шлёт
./.venv/bin/python scripts/push_notifier.py             # реальная отправка
```

Первый настоящий прогон без курсора встаёт «на сейчас» и историю не отправляет:
иначе после установки прилетят сотни пушей разом. `--dry-run` без курсора
показывает окно истории (`--lookback`, по умолчанию 500 событий) и курсор не двигает.
Если отправка упала (сеть, 500), курсор остаётся перед этим событием — следующий
тик повторит. `410 Gone` / `404` от FCM означает мёртвую подписку: она удаляется
из `push.db`, остальные продолжают работать.

Заголовок задачи в тексте уведомления по умолчанию **не** попадает (он виден на
локскрине). Включается `PUSH_INCLUDE_TITLE=true` в
`~/.hermes/kanban-webui.env`. Там же можно задать `PUSH_VAPID_SUB`
(по умолчанию `mailto:hermes@localhost`) и `PUSH_TTL` (600 с).

**5. Установка таймера.**

```bash
cd ~/projects/hermes-kanban-webui
cp deploy/systemd/hermes-kanban-push.service deploy/systemd/hermes-kanban-push.timer \
   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hermes-kanban-push.timer
systemctl --user list-timers hermes-kanban-push.timer
journalctl --user -u hermes-kanban-push.service -n 20 --no-pager
```

Проверка без ожидания тика: `systemctl --user start hermes-kanban-push.service`.

## Снимок мобильного вида

```bash
./.venv/bin/python scripts/shot.py URL out.png 390 844
```

Chrome в режиме `--headless=new` игнорирует `--window-size` для вьюпорта (запрос
390×844 рендерится в 500×757, а кадр обрезается), поэтому скрипт ставит размеры
через CDP `Emulation.setDeviceMetricsOverride` и печатает фактическое переполнение.

## Запуск

```bash
systemctl --user status hermes-kanban-webui.service
```

Открыть: http://192.168.144.122:8790

Токен — в `~/.hermes/kanban-webui.env` (`HERMES_KANBAN_WEBUI_TOKEN`).
