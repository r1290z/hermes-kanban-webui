// Экран «Лента» — поток событий доски, сгруппированный по дням. Новых серверных
// полей не нужно: страница собирается из /api/log/events (курсор before/before_id,
// как у «Лога») и /api/board (контекст задач: статус, исполнитель, пульс).
//
// Чипы: «Требует меня» (по умолчанию) — события, где решение ждали от человека;
// «Всё» — весь поток; «Блокировки» — только блокировки. Инлайн-действия есть
// только под «Требует меня» и только там, где действие действительно доступно
// сейчас: разблокировать, назначить, посмотреть лог просроченного прогона.
import { api, isOfflineError } from './api.js?v=20261030-8';
import { t, lang } from './i18n.js?v=20261030-8';
import { escapeHtml } from './markdown.js?v=20261030-8';
import { state, toast } from './state.js?v=20261030-8';
import { openTaskDrawer } from './drawer.js?v=20261030-8';

// Событий внимания мало (одно на десятки heartbeat'ов и spawn'ов), поэтому первая
// страница широкая: узкое окно оставило бы дефолтный чип пустым при живых данных.
const PAGE_SIZE = 200;
const OVERDUE_SECONDS = 300;
const DAY_SECONDS = 86400;
const QUEUE_STATUSES = ['scheduled', 'todo', 'ready', 'triage'];

// Решение ждут от человека: агент встал, прогон упал или не уложился в лимит,
// планировщик задал вопросы. Остальные kind — ход машины, они живут под «Всё».
const ATTENTION_KINDS = ['blocked', 'specified', 'crashed', 'timed_out', 'gave_up'];

const KIND_LABELS = {
  created: 'kindCreated',
  edited: 'kindEdited',
  commented: 'kindCommented',
  attached: 'kindAttached',
  blocked: 'kindBlocked',
  unblocked: 'kindUnblocked',
  completed: 'kindCompleted',
  crashed: 'kindCrashed',
  timed_out: 'kindTimedOut',
  gave_up: 'kindGaveUp',
  specified: 'kindSpecified',
  worker_result: 'kindWorkerResult',
  spawned: 'kindSpawned',
  claimed: 'kindClaimed',
  assigned: 'kindAssigned',
  status: 'kindStatus',
  archived: 'kindArchived',
  promoted: 'kindPromoted',
  scheduled: 'kindScheduled'
};

// Цвет — по смыслу события, а не по его названию: блокировка и вопросы ждут
// человека, авария — плохо, завершение и снятие блокировки — хорошо.
const KIND_TONES = {
  blocked: 'is-blocked',
  specified: 'is-blocked',
  crashed: 'is-bad',
  timed_out: 'is-bad',
  gave_up: 'is-bad',
  completed: 'is-ok',
  unblocked: 'is-ok',
  spawned: 'is-run',
  claimed: 'is-run'
};

const feed = {
  chip: 'mine',
  events: [],
  tasks: new Map(),
  before: null,
  beforeId: null,
  hasMore: false,
  paged: false,
  loading: false,
  error: null,
  offline: false,
  now: Math.floor(Date.now() / 1000)
};

function flatTasks(data) {
  if (!data) return [];
  const seen = new Set();
  const out = [];
  const columns = data.columns || {};
  const order = Array.isArray(data.column_order) ? data.column_order : Object.keys(columns);
  for (const status of order) {
    for (const task of columns[status] || []) {
      if (!task || !task.id || seen.has(task.id)) continue;
      seen.add(task.id);
      out.push(task);
    }
  }
  for (const task of data.tasks || []) {
    if (!task || !task.id || seen.has(task.id)) continue;
    seen.add(task.id);
    out.push(task);
  }
  return out;
}

function taskMap(data) {
  return new Map(flatTasks(data).map(task => [task.id, task]));
}

function pad2(value) {
  return String(value).padStart(2, '0');
}

function toDate(ts) {
  return new Date((Number(ts) || 0) * 1000);
}

// Ключ дня — локальная дата: события приходят с серверным timestamp, а читает их
// человек в своём часовом поясе.
function dayKey(ts) {
  const date = toDate(ts);
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function longDate(date) {
  try {
    return date.toLocaleDateString(lang(), { day: 'numeric', month: 'long' }).toLocaleUpperCase(lang());
  } catch (err) {
    return `${pad2(date.getDate())}.${pad2(date.getMonth() + 1)}`;
  }
}

// «СЕГОДНЯ · 30 ОКТЯБРЯ», «ВЧЕРА · 29 ОКТЯБРЯ», дальше — просто «28.10».
function dayLabel(ts) {
  const date = toDate(ts);
  const key = dayKey(ts);
  const today = Math.floor(Date.now() / 1000);
  if (key === dayKey(today)) return `${t('feedToday')} · ${longDate(date)}`;
  if (key === dayKey(today - DAY_SECONDS)) return `${t('feedYesterday')} · ${longDate(date)}`;
  return `${pad2(date.getDate())}.${pad2(date.getMonth() + 1)}`;
}

function timeLabel(ts) {
  const date = toDate(ts);
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function isoStamp(ts) {
  try {
    return toDate(ts).toISOString();
  } catch (err) {
    return '';
  }
}

function kindLabel(kind) {
  const key = KIND_LABELS[kind];
  const label = key ? t(key) : '';
  if (label && label !== key) return label;
  // Без перевода показываем сам kind, но по-человечески: worker_result → WORKER RESULT.
  return String(kind || '').replace(/[_-]+/g, ' ').toUpperCase();
}

function outcomeLabel(outcome) {
  if (!outcome) return '';
  const key = `outcome_${outcome}`;
  const label = t(key);
  return label === key ? outcome : label;
}

function pulseAge(task) {
  const beat = Number(task.last_heartbeat_at) || Number(task.started_at) || Number(task.created_at) || 0;
  if (!beat) return 0;
  return Math.max(0, feed.now - beat);
}

function isOverdue(task) {
  return task.status === 'running' && pulseAge(task) > OVERDUE_SECONDS;
}

// «Сейчас от меня что-то нужно»: задача заблокирована, лежит в очереди без
// исполнителя или идёт с просроченным пульсом. Только эти три причины дают
// инлайн-действие — остальные строки ленты читаются, но ничего не требуют.
function needsNow(task) {
  if (!task) return false;
  if (task.status === 'blocked') return true;
  if (!task.assignee && QUEUE_STATUSES.includes(task.status)) return true;
  return isOverdue(task);
}

function isAttention(event) {
  if (needsNow(feed.tasks.get(event.task_id))) return true;
  return ATTENTION_KINDS.includes(event.kind);
}

function isBlockedEvent(event) {
  const task = feed.tasks.get(event.task_id);
  return event.kind === 'blocked' || Boolean(task && task.status === 'blocked');
}

function visibleEvents(events) {
  if (feed.chip === 'all') return events;
  if (feed.chip === 'blocked') return events.filter(isBlockedEvent);
  return events.filter(isAttention);
}

function chipCount(chip) {
  if (chip === 'all') return feed.events.length;
  if (chip === 'blocked') return feed.events.filter(isBlockedEvent).length;
  return feed.events.filter(isAttention).length;
}

function chipsHtml() {
  const chips = [
    ['mine', t('feedMine')],
    ['all', t('feedAll')],
    ['blocked', t('feedBlocked')]
  ];
  const buttons = chips.map(([value, label]) => {
    const on = feed.chip === value;
    return `<button type="button" class="feed-chip${on ? ' is-active' : ''}" data-feed-chip="${value}" aria-pressed="${on}">`
      + `<span class="feed-chip-label">${escapeHtml(label)}</span>`
      + `<span class="feed-chip-count">${chipCount(value)}</span></button>`;
  });
  return `<div class="feed-chips" role="group" aria-label="${escapeHtml(t('feed'))}">${buttons.join('')}</div>`;
}

function actionHtml(task) {
  if (feed.chip !== 'mine' || !task) return '';
  const id = escapeHtml(task.id);
  if (task.status === 'blocked') {
    return `<div class="feed-actions"><button type="button" class="button ghost" data-feed-unblock="${id}">${escapeHtml(t('unblock'))}</button></div>`;
  }
  if (!task.assignee && QUEUE_STATUSES.includes(task.status)) {
    return `<div class="feed-actions"><button type="button" class="button ghost" data-feed-assign="${id}">${escapeHtml(t('assign'))}</button></div>`;
  }
  if (isOverdue(task)) {
    return `<div class="feed-actions"><button type="button" class="button ghost" data-feed-log="${id}">${escapeHtml(t('log'))}</button></div>`;
  }
  return '';
}

function metaHtml(event, task) {
  const parts = [];
  if (event.profile) parts.push(`@${escapeHtml(event.profile)}`);
  if (task) parts.push(escapeHtml(t(task.status)));
  // outcome прогона дублирует kind события (blocked/blocked) — второй раз не пишем.
  if (event.outcome && event.outcome !== event.kind) parts.push(escapeHtml(outcomeLabel(event.outcome)));
  // Событие внимания, которое больше ничего не ждёт, помечаем явно: чип не врёт
  // про «требует меня», но и не прячет историю решений.
  if (ATTENTION_KINDS.includes(event.kind) && task && !needsNow(task)) {
    parts.push(`<span class="feed-state">${escapeHtml(t('feedResolved'))}</span>`);
  }
  if (!parts.length) return '';
  return `<div class="feed-meta">${parts.join('<span class="feed-sep">·</span>')}</div>`;
}

function eventRow(event) {
  const task = feed.tasks.get(event.task_id) || null;
  const id = escapeHtml(event.task_id || '');
  const title = escapeHtml(event.title || event.task_id || '');
  const titleTag = id
    ? `<button type="button" class="feed-title" data-feed-card="${id}">${title}</button>`
    : `<span class="feed-title">${title}</span>`;
  const tone = KIND_TONES[event.kind] || '';
  return `<article class="feed-event" data-event-id="${escapeHtml(String(event.id))}" data-task-id="${id}">
    <time class="feed-time" datetime="${escapeHtml(isoStamp(event.created_at))}">${escapeHtml(timeLabel(event.created_at))}</time>
    <div class="feed-body">
      <div class="feed-line"><span class="feed-kind ${tone}">${escapeHtml(kindLabel(event.kind))}</span>${titleTag}</div>
      ${metaHtml(event, task)}
      ${actionHtml(task)}
    </div>
  </article>`;
}

function daySummary(day) {
  const runs = day.events.filter(event => event.run_id).length;
  const attention = day.events.filter(isAttention).length;
  // Подпись перед числом: «событий 12» читается при любом числе, «12 событий» — нет.
  return `${t('feedEvents')} ${day.events.length} · ${t('summaryRuns')} ${runs} · ${t('feedAttention')} ${attention}`;
}

function dayHtml(day) {
  return `<section class="feed-day" data-day="${escapeHtml(day.key)}">
    <header class="feed-day-head">
      <span class="feed-day-label">${escapeHtml(day.label)}</span>
      <span class="feed-day-sum">${escapeHtml(daySummary(day))}</span>
    </header>
    ${day.events.map(eventRow).join('')}
  </section>`;
}

// События приходят новыми первыми, поэтому группы дней идут сверху вниз от
// сегодняшнего дня к прошлому — без пересортировки.
function groupByDay(events) {
  const days = [];
  let current = null;
  for (const event of events) {
    const key = dayKey(event.created_at);
    if (!current || current.key !== key) {
      current = { key, label: dayLabel(event.created_at), events: [] };
      days.push(current);
    }
    current.events.push(event);
  }
  return days;
}

function emptyText() {
  if (feed.chip === 'blocked') return t('feedEmptyBlocked');
  if (feed.chip === 'mine') return t('feedEmptyMine');
  return t('logEmpty');
}

// «нет сети» вместо «не удалось загрузить», когда пропала связь: метку ставит
// api.js (упавший fetch или 503 {"offline": true} от service worker).
function errorHtml() {
  const label = feed.offline ? t('noNetwork') : t('loadFailed');
  return `<div class="feed-error" role="alert" title="${escapeHtml(feed.error || '')}">
    <span class="feed-error-text">${escapeHtml(label)}</span>
    <span class="feed-error-sep" aria-hidden="true">·</span>
    <button type="button" class="button ghost" data-feed-retry>${escapeHtml(t('retry'))}</button>
  </div>`;
}

export function renderFeed(events = feed.events) {
  const root = document.getElementById('viewFeed');
  if (!root) return;
  const source = Array.isArray(events) ? events : [];
  const days = groupByDay(visibleEvents(source));
  const more = feed.hasMore && !feed.error
    ? `<div class="feed-more"><button type="button" class="button ghost" data-feed-more>${escapeHtml(t('listShowMore'))}</button></div>`
    : '';
  root.innerHTML = [
    chipsHtml(),
    feed.error ? errorHtml() : '',
    // Пустое состояние при ошибке не рисуем: «ничего не ждёт решения» рядом с
    // «нет сети» — это утверждение о данных, которых мы не получили.
    days.length ? days.map(dayHtml).join('') : (feed.error ? '' : `<p class="feed-empty">${escapeHtml(emptyText())}</p>`),
    more
  ].join('');
  bind(root);
}

function bind(root) {
  root.querySelectorAll('[data-feed-chip]').forEach(btn => {
    btn.addEventListener('click', () => {
      feed.chip = btn.dataset.feedChip;
      renderFeed();
    });
  });
  root.querySelectorAll('[data-feed-card]').forEach(btn => {
    btn.addEventListener('click', () => openTaskDrawer(btn.dataset.feedCard));
  });
  root.querySelectorAll('[data-feed-unblock]').forEach(btn => {
    btn.addEventListener('click', () => unblockTask(btn));
  });
  root.querySelectorAll('[data-feed-assign]').forEach(btn => {
    btn.addEventListener('click', () => openTaskDrawer(btn.dataset.feedAssign));
  });
  root.querySelectorAll('[data-feed-log]').forEach(btn => {
    btn.addEventListener('click', () => { location.hash = '#view=log'; });
  });
  root.querySelector('[data-feed-more]')?.addEventListener('click', () => loadFeed({ append: true }));
  root.querySelector('[data-feed-retry]')?.addEventListener('click', () => loadFeed());
}

async function unblockTask(btn) {
  const id = btn.dataset.feedUnblock;
  btn.disabled = true;
  try {
    await api.updateTask(state.board, id, { status: 'todo' });
    document.dispatchEvent(new CustomEvent('kanban:refresh'));
    await loadFeed();
  } catch (err) {
    btn.disabled = false;
    toast(err.message || String(err), 'error');
  }
}

export async function loadFeed({ append = false } = {}) {
  const root = document.getElementById('viewFeed');
  if (!root) return;
  if (feed.loading) return;
  feed.loading = true;
  try {
    const [page, board] = await Promise.all([
      api.logEvents({
        board: state.board,
        limit: PAGE_SIZE,
        before: append ? feed.before : null,
        before_id: append ? feed.beforeId : null
      }),
      // Контекст задач нужен только для первой страницы: статус, исполнитель и
      // пульс от номера страницы не зависят. Архив тоже берём: без него старая
      // блокировка выглядела бы как действующая, а не как снятая.
      append ? Promise.resolve(null) : api.board({ board: state.board, include_archived: 1 })
    ]);
    if (board) feed.tasks = taskMap(board);
    feed.now = Number(page.server_now) || Math.floor(Date.now() / 1000);
    const events = Array.isArray(page.events) ? page.events : [];
    if (append) {
      const seen = new Set(feed.events.map(item => item.id));
      feed.events = feed.events.concat(events.filter(item => !seen.has(item.id)));
    } else {
      feed.events = events;
    }
    feed.before = page.next_before;
    feed.beforeId = page.next_before_id;
    feed.hasMore = Boolean(page.has_more);
    feed.paged = append;
    feed.error = null;
    feed.offline = false;
  } catch (err) {
    feed.error = err && err.message ? err.message : String(err);
    feed.offline = isOfflineError(err);
    if (!append) {
      feed.events = [];
      feed.hasMore = false;
    }
  } finally {
    feed.loading = false;
  }
  renderFeed();
}

// Poll и «Обновить» перерисовывают ленту только пока открыта первая страница:
// иначе подгрузка «Показать ещё» сбрасывалась бы каждые 2.5 секунды.
export function refreshFeed() {
  if (feed.paged) return Promise.resolve();
  return loadFeed();
}

export function setupFeedView() {
  // Лента целиком рисуется из JS. Если экран открыт напрямую по #view=feed,
  // роутер уже запустил loadFeed(); здесь только страховка от пустого экрана.
  const root = document.getElementById('viewFeed');
  if (root && root.hidden === false && !feed.loading && !root.querySelector('.feed-chips')) loadFeed();
}