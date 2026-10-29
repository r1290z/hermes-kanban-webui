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
