# KanbanWebUI UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переписать интерфейс KanbanWebUI на тёмный плотный «пульт + доска + лента» без glassmorphism, эмодзи и внешних шрифтов, не меняя серверный API.

**Architecture:** Статический фронтенд без сборки: `index.html` — оболочка с четырьмя вкладками и пятью секциями-вью (вкладка «Доска» содержит режимы «Секции» и «Таблица»), `app.js` — роутер по хэшу, `now.js`/`feed.js` — новые вью, `board.js`/`list.js`/`log.js`/`drawer.js` — переписанные, `design-tokens.css` — единственный источник цветов/радиусов/шрифтов. Данные берутся только из существующих эндпоинтов.

**Tech Stack:** vanilla ES-модули, CSS-переменные, Python 3.12 (FastAPI-статика), pytest + headless Chrome (CDP) для проб вёрстки.

**Spec:** `docs/superpowers/specs/2026-10-30-kanban-ui-redesign-design.md`

## Global Constraints

- Серверный API и `kanban_webui/*.py` не меняются (кроме `tests/`). Нужен серверный агрегат — остановиться и согласовать.
- Никаких новых зависимостей, сборки, CDN и внешних шрифтов. Иконки — только инлайновый SVG или текстовые глифы `＋ ⌕ ⋯`.
- Тёмная тема — основная; светлая — переопределение `:root[data-theme="light"]` тех же токенов.
- Токены и их значения — ровно как в спеке §5.1. Радиусы: контролы 5px, карточки/секции 8px.
- Запрещено (проверяется тестом): `linear-gradient`/`radial-gradient` в фоне, `backdrop-filter`, `border-radius: 999px`,
  эмодзи в подписях контролов, `fonts.googleapis.com`, `fonts.gstatic.com`.
- Вторичный текст ≥ 11.5px; `--mut`/`--faint` контраст ≥ 4.5:1 к своему фону.
- Сохраняются id: `boardSelect`, `taskCreateBtn`, `refreshBtn`, `newBoardBtn`, `themeToggle`, `langToggle`,
  `opsToggleBtn`, `workflowBtn`, `bulkBtn`, `searchInput`, `statusFilter`, `assigneeFilter`, `archivedToggle`.
- Сохраняются селекторы-контракты: `.board`, `.board-column`, `.cards`, `.task-card`, `.dependency-port`,
  `[data-task-id]`, `[data-parent-count]`, `[data-child-count]`, `[data-pulse-id]`, `[data-pulse-elapsed]`,
  `.list-table`, `#listBody`, `#listHead`.
- Токен кэша `?v=` один на релиз: меняется в `static/index.html` и во **всех** `import ... from './x.js?v='`
  одинаково; тест `assets_use_single_version_token` это проверяет.
- Все новые ключи i18n дублируются в `ru`/`en`; для `ko` допускается английский текст (машинный корейский не выдумывать).
- Каждый коммит — по одной задаче, сообщение по-русски, как в истории репозитория.

## Review Focus

1. Задача без `max_runtime_seconds` — строка «Сейчас» и карточка доски не рисуют полосу прогресса и не падают.
2. Просроченный пульс (heartbeat > 300 с) — помечен словом «пульс просрочен», а не только цветом.
3. Заголовок в 200 символов и id на 320px — карточка не выдавливает колонку (`min-width: 0` у грид-треков).
4. 42 задачи в «Готово» + 13 в архиве — на телефоне секция не рендерит всё сразу: свёрнута, «показать все».
5. Сетевая ошибка или 401 на любом вью — видно «не удалось загрузить · повторить», а не пустой экран.

---

### Task 1: Токены, база CSS и оболочка с вкладками

**Files:**
- Modify: `static/design-tokens.css` (перезапись)
- Modify: `static/style.css` (перезапись: база, топбар, табы, контролы, типографика)
- Modify: `static/index.html`
- Modify: `static/i18n.js`
- Modify: `static/app.js:19-65`
- Create: `scripts/probe_ui.py`
- Create: `tests/test_ui_shell.py`

**Interfaces:**
- Produces: CSS-токены из спеки §5.1; `applyView(view)` в `app.js` умеет `now|board|list|feed|log`;
  `probe_ui.py URL W H 'js-expr'` печатает JSON-результат выражения; `tests/test_ui_shell.py` — образец
  контрактных тестов для задач 2-5.

- [ ] **Step 1: Написать падающий тест** `tests/test_ui_shell.py`

```python
import re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

def test_tokens_have_spec_values():
    tokens = (STATIC / "design-tokens.css").read_text(encoding="utf-8")
    for pair in ["--bg: #0b0c0e", "--surface: #111417", "--line: #23272d", "--ink: #e6e8eb",
                 "--mut: #aab3c0", "--run: #5b9dff", "--blk: #e0a34a", "--ok: #4ec38a",
                 "--r-sm: 5px", "--r-md: 8px"]:
        assert pair in tokens, pair

def test_no_ai_style_markers():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "backdrop-filter" not in css
    assert "999px" not in css
    assert not re.search(r"background[^;{}]*gradient\\(", css), "градиенты в фоне"
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html

def test_shell_has_four_tabs_and_five_views():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for view in ["now", "board", "list", "feed", "log"]:
        assert f'id="view{view.capitalize()}"' in html, view
    tabs = re.findall(r'data-tab="(\\w+)"', html)
    assert tabs == ["now", "board", "feed", "log"]
    for control in ["boardSelect", "taskCreateBtn", "refreshBtn", "themeToggle", "langToggle", "searchInput"]:
        assert f'id="{control}"' in html, control

def test_assets_use_single_version_token():
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    token = re.search(r'app\\.js\\?v=([^"\\']+)', index).group(1)
    for path in STATIC.glob("*.js"):
        body = path.read_text(encoding="utf-8")
        for found in re.findall(r"\\?v=([\\w.-]+)", body):
            assert found == token, f"{path.name} uses ?v={found}, expected {token}"

def test_ready_status_renamed():
    i18n = (STATIC / "i18n.js").read_text(encoding="utf-8")
    assert "ready: 'На проверке'" in i18n
    assert "Готовы" not in i18n
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `./.venv/bin/python -m pytest tests/test_ui_shell.py -v`
Expected: FAIL (`--bg: #0b0c0e` отсутствует, `backdrop-filter` есть, вклад нет).

- [ ] **Step 3: Переписать `static/design-tokens.css`** — токены ровно из спеки §5.1, две области:
  `:root` (тёмная) и `:root[data-theme="light"]`. Больше в файле ничего нет.

- [ ] **Step 4: Переписать `static/index.html`** — оболочка:

```html
<header class="topbar">
  <div class="brand"><b>Hermes Kanban</b><span class="board-name" id="boardName">Default</span></div>
  <nav class="tabs" role="tablist">
    <button role="tab" data-tab="now" data-i18n="now">Сейчас</button>
    <button role="tab" data-tab="board" data-i18n="tabBoard">Доска</button>
    <button role="tab" data-tab="feed" data-i18n="feed">Лента</button>
    <button role="tab" data-tab="log" data-i18n="tabLog">Лог</button>
  </nav>
  <div class="top-actions">
    <button class="icon-btn" id="searchBtn" aria-label="Поиск"><svg…/></button>
    <button class="icon-btn" id="moreBtn" aria-label="Ещё">⋯</button>
    <button class="button primary" id="taskCreateBtn" data-i18n="taskCreate">Создать</button>
  </div>
</header>
```

Плюс скрытая панель «Ещё» (`id="morePanel"`), внутри которой живут `boardSelect`, `refreshBtn`, `newBoardBtn`,
`themeToggle`, `langToggle`, `opsToggleBtn`, `workflowBtn`, `bulkBtn` и поле `searchInput` — так они остаются
в DOM, но не занимают главный экран. Пять секций: `#viewNow`, `#viewBoard`, `#viewFeed`, `#viewLog`
(`class="view"`), `#viewList` — существующая разметка таблицы без изменений. `hero-card`, `kpiRow` и
`toolbar`-карточка удаляются; `kpiRow` больше не нужен (его роль забрал «Сейчас»).
Angular-скобки `{{…}}` в этом плане — заполнители, писать реальный SVG.

- [ ] **Step 5: Переписать `static/style.css`** — только база: `*{box-sizing}`, `body` (токены, шрифт, фон
  `--bg`), `.topbar`, `.tabs` (активный таб — `box-shadow: inset 0 2px 0 var(--ink)`), `.button`,
  `.button.primary`, `.icon-btn`, `select/input/textarea` (радиус 5px, фон `--surface`, граница `--line-strong`),
  `.view[hidden]{display:none}`, `.muted`, `.mono`, `.num`. Блоки конкретных вью добавляются в задачах 2-5.

- [ ] **Step 6: Правки `app.js` и `i18n.js`.** `VIEWS = ['now','board','list','feed','log']`,
  `TABS = ['now','board','feed','log']`; `applyView` подсвечивает таб «Доска» и при `view === 'list'`;
  дефолт по `matchMedia('(max-width: 759px)')` → `now`, иначе `board`; роутер читает хэш как набор пар
  (`view`, `task`) и не теряет `task` при переключении вью.
  В `i18n.js`: `ready: 'На проверке'` (ru), плюс ключи `now`, `tabBoard`, `feed`, `tabLog`, `liveRuns`,
  `needsAttention`, `queue`, `completed`, `noActiveRuns`, `lastFinished`, `pulseOverdue`, `loadFailed`,
  `retry`, `modeSections`, `modeTable`, `toActive`, `showAll`, `noAssigneeTasks`, `more` — в `ru`, `en`
  (и `ko` = английский текст).

- [ ] **Step 7: Создать `scripts/probe_ui.py`** — копия CDP-обвязки из `scripts/shot.py` (Chrome
  `--headless=new`, `Emulation.setDeviceMetricsOverride`), но вместо скриншота печатает JSON:

```
python scripts/probe_ui.py URL 390 844 "document.documentElement.scrollWidth"
```

- [ ] **Step 8: Прогнать тесты**

Run: `./.venv/bin/python -m pytest tests/test_ui_shell.py -v`
Expected: PASS (5 тестов).

- [ ] **Step 9: Проверить в браузере**

Run: `./.venv/bin/python scripts/probe_ui.py "http://127.0.0.1:8790/#token=$HERMES_KANBAN_WEBUI_TOKEN" 390 844 "document.documentElement.scrollWidth"`
Expected: `390` (без горизонтального переполнения). Второй прогон с `"!!document.querySelector('#viewNow').hidden"` → `true`.

- [ ] **Step 10: Коммит**

```bash
cd ~/projects/hermes-kanban-webui
git add static/design-tokens.css static/style.css static/index.html static/app.js static/i18n.js scripts/probe_ui.py tests/test_ui_shell.py
git commit -m "UI: тёмные токены, оболочка с вкладками Сейчас/Доска/Лента/Лог, статус ready → «На проверке»"
```

---

### Task 2: Экран «Сейчас»

**Files:**
- Create: `static/now.js`
- Modify: `static/style.css` (блок `.now-*`)
- Modify: `static/app.js` (вызов `loadNow()` при активной вью `now`)
- Modify: `static/pulse.js:19-24` (убрать эмодзи `⏱`, использовать `t('pulseOverdue')`)
- Modify: `static/index.html` (токен `?v=`, подключение `now.js`)
- Create: `tests/test_now_view.py`

**Interfaces:**
- Consumes: `api.board({board})`, `api.pulse(board, ids)`, `api.log({board, outcome, since})`, `schedulePulse(ids)`
  из `pulse.js`, `openTaskDrawer(id)` из `drawer.js`.
- Produces: `export async function loadNow()` и `export function renderNow(data, pulse)`, рисующие в `#viewNow`.

- [ ] **Step 1: Написать падающий тест** `tests/test_now_view.py`

```python
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

def test_now_module_contract():
    now = (STATIC / "now.js").read_text(encoding="utf-8")
    assert "export async function loadNow" in now
    assert "export function renderNow" in now
    for marker in ["api.board", "api.pulse", "api.log"]:
        assert marker in now, marker
    for section in ["now-live", "now-attention", "now-queue", "now-done"]:
        assert section in now, section

def test_now_has_idle_and_error_states():
    now = (STATIC / "now.js").read_text(encoding="utf-8")
    assert "t('noActiveRuns')" in now
    assert "t('loadFailed')" in now
    assert "t('retry')" in now

def test_no_emoji_in_pulse_and_now():
    for name in ["pulse.js", "now.js"]:
        body = (STATIC / name).read_text(encoding="utf-8")
        assert "⏱" not in body, name
        assert not re.search(r"[\\U0001F300-\\U0001FAFF]", body), name

def test_progress_bar_only_with_limit():
    now = (STATIC / "now.js").read_text(encoding="utf-8")
    assert "max_runtime_seconds" in now
    assert "now-progress" in now
```

- [ ] **Step 2: Прогнать — падает**

Run: `./.venv/bin/python -m pytest tests/test_now_view.py -v`
Expected: FAIL (`No such file: static/now.js`).

- [ ] **Step 3: Реализовать `static/now.js`**

`loadNow()`: `const data = await api.board({ board: state.board })`; собрать `running = плоский список задач со
status==='running'`; `await schedulePulse(running.map(t => t.id))` не нужен — вызвать `api.pulse(state.board, ids)`
напрямую и рисовать из ответа, а `schedulePulse` использовать для обновления после первого рендера (он уже
умеет обновлять `[data-pulse-id]`).

`renderNow(data, pulse)` строит в `#viewNow`:

```
<section class="now-block now-live">
  <div class="block-head"><span class="block-label">Живые прогоны</span><span class="count">2</span></div>
  <a class="run-row" data-task-id="t_x">
     <span class="run-title">…</span>
     <span class="run-meta"><span class="pulse" data-pulse-id="t_x"><span class="elapsed" data-pulse-elapsed>27:14</span></span>
       <span class="sep">/</span><span class="limit">60 мин</span><span class="profile">@coder</span>
       <span class="hb">пульс 24 с</span></span>
     <span class="run-progress"><i style="width:45%"></i></span>
  </a>
</section>
```

Правила: полоса `.run-progress` рисуется только если `task.max_runtime_seconds > 0`; пустой список живых
прогонов → `<p class="now-empty">нет активных прогонов · последний завершился {age}</p>` (возраст берётся
из самого свежего прогона в блоке «Завершено», иначе текст без возраста); ошибка любого из запросов →
`.now-error` с кнопкой «Повторить», вызывающей `loadNow()`; просроченный пульс → класс `is-overdue` и слово
`t('pulseOverdue')`.
Блоки «Требует внимания», «Очередь», «Завершено» — как в спеке §4.1; у строк внимания одна кнопка действия
(`blocked` → «Разблокировать» через `api.updateTask(board, id, {status:'todo'})`, без исполнителя →
«Назначить» через открытие drawer, overdue → «Лог»).

- [ ] **Step 4: Стили `.now-*`** в `style.css`: секционные метки 11px uppercase `--faint`, `.run-row` —
  сетка `minmax(0,1fr) auto`, `border-top: 1px solid var(--line)`, плотность 11px/13.5px, полоса 2px `--run`,
  `.is-overdue` — текст `--blk`.

- [ ] **Step 5: Подключить вью** — в `index.html` импорт `now.js` с тем же `?v=`, в `app.js` в `applyView`
  вызов `loadNow()` при `active === 'now'` и при старте, если вью по умолчанию — `now`.

- [ ] **Step 6: Прогнать тесты**

Run: `./.venv/bin/python -m pytest tests/test_now_view.py tests/test_ui_shell.py -v`
Expected: PASS.

- [ ] **Step 7: Проверить на живых данных**

Run: `./.venv/bin/python scripts/probe_ui.py "http://127.0.0.1:8790/#view=now&token=$HERMES_KANBAN_WEBUI_TOKEN" 390 844 "JSON.stringify({blocks:[...document.querySelectorAll('.now-block')].map(e=>e.className), empty:!!document.querySelector('.now-empty'), overflow:document.documentElement.scrollWidth})"`
Expected: 4 блока (`now-live`, `now-attention`, `now-queue`, `now-done`), `overflow: 390`. При нуле живых
прогонов `empty: true` — это нормальное состояние базы.

- [ ] **Step 8: Коммит**

```bash
git add static/now.js static/style.css static/app.js static/pulse.js static/index.html tests/test_now_view.py
git commit -m "UI: экран «Сейчас» — живые прогоны, внимание, очередь, завершённые"
```

---

### Task 3: Экран «Доска» (секции на телефоне, колонки на десктопе)

**Files:**
- Modify: `static/board.js` (перезапись `renderBoard` и `card`)
- Modify: `static/style.css` (блок `.board-*`)
- Modify: `static/index.html` (каркас `#viewBoard`: строка фильтров, переключатель режима, `#board`)
- Modify: `static/app.js` (фильтры доски, переключение режима «Секции/Таблица»)
- Modify: `static/list.js:235-310` (режим «Таблица» внутри `#viewBoard`)
- Create: `tests/test_board_view.py`

**Interfaces:**
- Consumes: `data.column_order`, `data.columns[status][]`, `data.stats.by_status`, `attachDragHandlers(root)`,
  `renderDependencyOverlay(data)`, `schedulePulse(ids)` — без изменения их сигнатур.
- Produces: `renderBoard(data)` рисует `.board > .board-column[data-status] > .cards > .task-card[data-task-id]`
  на всех ширинах (раскладка — CSS); `.board-column.is-empty` для пустых; `.board-rail` — свёрнутый вид.

- [ ] **Step 1: Написать падающий тест** `tests/test_board_view.py`

```python
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"

def test_card_template_has_no_zero_noise():
    board = (STATIC / "board.js").read_text(encoding="utf-8")
    assert "💬" not in board
    assert "↑ ${parents} ↓ ${children}" not in board
    assert "profile-missing-badge" in board and "missing-assignee-chip" not in board

def test_card_contract_selectors_preserved():
    board = (STATIC / "board.js").read_text(encoding="utf-8")
    for attr in ["data-task-id", "data-parent-count", "data-child-count", "data-pulse-id"]:
        assert attr in board, attr
    assert "dependency-port" in board

def test_empty_columns_render_rail():
    board = (STATIC / "board.js").read_text(encoding="utf-8")
    assert "is-empty" in board and "board-rail" in board

def test_board_responsive_rules():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert ".board-column{min-width:0" in css.replace(" ", "") or "min-width: 0" in css
    assert "@media (max-width: 759px)" in css
```

- [ ] **Step 2: Прогнать — падает**

Run: `./.venv/bin/python -m pytest tests/test_board_view.py -v`
Expected: FAIL (эмодзи 💬 в `board.js`, нет `is-empty`).

- [ ] **Step 3: Переписать карточку в `board.js`**

```
<article class="task-card" data-task-id data-parent-count data-child-count tabindex="0">
  <button class="dependency-port child-port" data-link-role="child" …> </button>
  <button class="dependency-port parent-port" data-link-role="parent" …> </button>
  <div class="card-head">
    <span class="id mono">t_4f464521</span>
    <span class="status-dot"></span>
  </div>
  <h3 class="card-title">…</h3>
  <div class="card-live" data-pulse-id><!-- только для running --></div>
  <div class="card-meta">
    <span class="chip-profile">@coder</span> | <span class="chip-warn">нет исполнителя</span>
    <span class="num">P2</span> <span class="num">5/8</span>
  </div>
</article>
```

Правила: `.id` — `white-space: nowrap`; превью тела — только текст без markdown-разметки (`body_preview`
чистить регэкспом от `#`, `**`, `|`, `<|--`); счётчики комментариев/связей рисуются только при `> 0`;
предупреждение одно — `.chip-warn` (никакого второго бейджа); прогресс/пульс — только для `running`.

- [ ] **Step 4: Раскладка доски.** Один DOM, две раскладки:
  - `@media (min-width: 760px)`: `.board { display: grid; grid-auto-flow: column; grid-auto-columns: 320px;
    overflow-x: auto; gap: 12px; }`, `.board-column` со `min-width: 0`, sticky-шапка, `.board-column.is-empty`
    → ширина 40px, вертикальная подпись (`writing-mode: vertical-rl`), крестик-разворот по тапу;
    тень-подсказка `.board.can-scroll-right::after`; кнопка `#boardToActive`.
  - `@media (max-width: 759px)`: `.board { display: block }`, `.board-column` — секция с sticky-заголовком,
    `.board-rail` — ряд чипов для пустых статусов (`.board-rail [data-status]`), тап → `scrollIntoView`.
  - Автоскролл к первой значимой колонке: `running` → `blocked` → `ready` (на десктопе, один раз за загрузку).

- [ ] **Step 5: Строка фильтров и режим «Таблица».** В `#viewBoard` сверху одна строка: поле поиска,
  чипы-мультиселекты статуса и исполнителя (переиспользовать `createMultiSelect` из `list.js`), чекбокс архива,
  переключатель `Секции | Таблица`. «Таблица» показывает `#viewList` внутри `#viewBoard` (переключение
  `hidden`), вкладка «Доска» остаётся активной.

- [ ] **Step 6: Прогнать тесты**

Run: `./.venv/bin/python -m pytest tests/test_board_view.py tests/test_ui_shell.py -v`
Expected: PASS.

- [ ] **Step 7: Проба вёрстки на двух ширинах**

Run: `./.venv/bin/python scripts/probe_ui.py "http://127.0.0.1:8790/#view=board&token=$HERMES_KANBAN_WEBUI_TOKEN" 390 844 "JSON.stringify({overflow:document.documentElement.scrollWidth, cards:document.querySelectorAll('.task-card').length, rail:document.querySelectorAll('.board-rail [data-status]').length})"`
Expected: `overflow: 390`, `rail ≥ 3` (пустые статусы), `cards` не 0.
Повторить на 1440×900: `overflow: 1440`, `board.scrollWidth > board.clientWidth` (есть горизонтальный скролл колонок).

- [ ] **Step 8: Коммит**

```bash
git add static/board.js static/style.css static/index.html static/app.js static/list.js tests/test_board_view.py
git commit -m "UI: доска — секции на телефоне, колонки 320px на десктопе, пустые статусы в рейл"
```

---

### Task 4: Экраны «Лента» и «Лог»

**Files:**
- Create: `static/feed.js`
- Modify: `static/log.js` (скин под общие токены, строка фильтров)
- Modify: `static/style.css` (блоки `.feed-*`, `.log-*`)
- Modify: `static/index.html`, `static/app.js` (вью `feed`)
- Create: `tests/test_feed_view.py`

**Interfaces:**
- Consumes: `api.logEvents({board, since_id, kind})`, `api.board({board})`, `api.updateTask`, `openTaskDrawer`.
- Produces: `export async function loadFeed({append})`, `export function renderFeed(events)`.

- [ ] **Step 1: Написать падающий тест** `tests/test_feed_view.py`

```python
from pathlib import Path
STATIC = Path(__file__).resolve().parents[1] / "static"

def test_feed_module_contract():
    feed = (STATIC / "feed.js").read_text(encoding="utf-8")
    assert "export async function loadFeed" in feed
    assert "export function renderFeed" in feed
    assert "api.logEvents" in feed
    for part in ["feed-day", "feed-event", "feed-chips"]:
        assert part in feed, part

def test_feed_day_grouping():
    feed = (STATIC / "feed.js").read_text(encoding="utf-8")
    assert "toDateString" in feed or "dayKey" in feed

def test_log_view_uses_tokens():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert ".log-row" in css and "var(--line)" in css
```

- [ ] **Step 2: Прогнать — падает** (`static/feed.js` отсутствует).

- [ ] **Step 3: Реализовать `feed.js`** — поток: `api.logEvents` (курсор `since_id`, пагинация вниз по
  «Показать ещё»), группировка по дням (`СЕГОДНЯ · 30 ОКТЯБРЯ`, `ВЧЕРА · 29 ОКТЯБРЯ`, далее `dd.mm`),
  под каждой группой — сводка дня (кол-во событий, сколько прогонов, сколько требует внимания).
  Чипы-фильтры `Требует меня` (дефолт: `blocked`, без исполнителя, overdue) / `Всё` / `Блокировки`.
  Строка события: время `HH:MM` (mono, 11.5px) → тип (uppercase, 11px, цвет по типу) → заголовок задачи →
  мета. Инлайн-действия только для «требует меня».

- [ ] **Step 4: Скин `log.js`** — те же токены, одна строка фильтров вместо панели-карточки, моно-таймстемпы,
  плотность 40-44px. Логика `loadLog`/пагинация не меняется.

- [ ] **Step 5: Прогнать тесты** — `pytest tests/test_feed_view.py tests/test_ui_shell.py -v` → PASS.

- [ ] **Step 6: Проба** — 390px, `#view=feed`: нет переполнения, есть `.feed-day` и `.feed-event`.

- [ ] **Step 7: Коммит** — `UI: экраны «Лента» и «Лог» на общих токенах`.

---

### Task 5: Карточка задачи, markdown, deep links, приёмка

**Files:**
- Modify: `static/markdown.js`
- Modify: `static/drawer.js`
- Modify: `static/mobile.js`
- Modify: `static/app.js` (хэш `#task=`), `static/index.html` (токен `?v=`)
- Modify: `tests/test_static_smoke.py` (удалить ассерты точных CSS-строк, оставить контракты)
- Create: `tests/test_drawer_markdown.py`

**Interfaces:**
- Consumes: всё предыдущее.
- Produces: `renderMarkdown(text)` с поддержкой заголовков, списков, `**bold**`, `*italic*`, `` `code` ``,
  блоков ``` ``` ```, ссылок и абзацев; `openTaskDrawer(taskId)` пишет `#task=<id>` в хэш, `closeDrawer()` убирает.

- [ ] **Step 1: Написать падающий тест** `tests/test_drawer_markdown.py`

```python
from pathlib import Path
STATIC = Path(__file__).resolve().parents[1] / "static"

def test_markdown_supports_lists_and_code_blocks():
    md = (STATIC / "markdown.js").read_text(encoding="utf-8")
    for marker in ["<ul>", "<li>", "<pre>", "<code>", "<a href"]:
        assert marker in md, marker

def test_markdown_escapes_html_first():
    md = (STATIC / "markdown.js").read_text(encoding="utf-8")
    assert md.index("escapeHtml") < md.index("<h3>")

def test_drawer_single_warning_badge():
    drawer = (STATIC / "drawer.js").read_text(encoding="utf-8")
    assert drawer.count("profile-missing-badge") <= 1

def test_deep_link_contract():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "task=" in app
    assert "openTaskDrawer" in app
```

- [ ] **Step 2: Прогнать — падает.**

- [ ] **Step 3: Доработать `renderMarkdown`** — сначала `escapeHtml`, затем построчный разбор: `#`…`######`
  → `h2..h6`; `- ` / `* ` → `<ul><li>`; `1. ` → `<ol>`; пустая строка → закрыть список, начать `<p>`;
  ``` ``` ``` → `<pre><code>`; инлайн: `` ` ``, `**`, `*`, `[text](url)` → `<a href>` с `rel="noopener"`.

- [ ] **Step 4: Перестроить `drawer.js`** — порядок из спеки §4.5, одно предупреждение, тело через
  `renderMarkdown`, действия строкой кнопок 5px радиус, зависимости компактным списком. `openTaskDrawer`
  пишет `history.replaceState(null,'','#task='+id+'&view='+currentView())`, `closeDrawer` убирает `task`.

- [ ] **Step 5: `mobile.js`** — нижние табы (fixed, `padding-bottom: env(safe-area-inset-bottom)`), drawer
  на весь экран при `<760px`, лист перемещения задачи остаётся.

- [ ] **Step 6: Почистить `tests/test_static_smoke.py`** — удалить ассерты вида
  `assert '.button.ghost { background: var(--ghost-bg); color: var(--ink); }' in style` и все проверки
  удалённых классов (`.hero-card`, `.kpi`, `.toolbar`); оставить контракты вью, i18n, id контролов, парсинг JS.

- [ ] **Step 7: Полный прогон**

Run: `./.venv/bin/python -m pytest -q`
Expected: все тесты PASS.

- [ ] **Step 8: Скриншоты и живая проверка**

```bash
./.venv/bin/python scripts/shot.py "http://127.0.0.1:8790/#view=now&token=$TOKEN"  screenshots/redesign_now_390.png 390 844
./.venv/bin/python scripts/shot.py "http://127.0.0.1:8790/#view=board&token=$TOKEN" screenshots/redesign_board_1440.png 1440 900
./.venv/bin/python scripts/probe_ui.py "http://127.0.0.1:8790/#task=t_4f464521&token=$TOKEN" 390 844 "!!document.querySelector('.drawer.open')"
```
Expected: скриншоты созданы, drawer открыт (`true`).

- [ ] **Step 9: Коммит**

```bash
git add -A static tests scripts screenshots
git commit -m "UI: карточка задачи, markdown-рендер, deep links, чистка контрактных тестов"
```

---

## Self-Review

- Покрытие спеки: §4.1 → Task 2, §4.2 → Task 3, §4.3/§4.4 → Task 4, §4.5 → Task 5, §5 → Task 1 (+точечно 2-5),
  §6 → Tasks 2/4, §7 → Tasks 3/5, §8 → Steps «проба»/«полный прогон» в каждой задаче.
- Review Focus: (1) Task 2 Step 3 (`max_runtime_seconds`), (2) Tasks 2/3 (`pulseOverdue`, `is-overdue`),
  (3) Task 3 Step 4 (`min-width: 0`) + Task 3 Step 7, (4) Task 3 Step 4 (`.board-column.is-empty`, кнопка
  «показать все»), (5) Task 2 Step 3 (`.now-error`).
- Имена: `loadNow`/`renderNow` (Task 2), `renderBoard` (Task 3, сигнатура не меняется), `loadFeed`/`renderFeed`
  (Task 4), `renderMarkdown`/`openTaskDrawer` (Task 5) — используются согласованно.
- Вне рамок спеки: правки `kanban_webui/*.py`, новые эндпоинты, мультидосковость — не требуются.