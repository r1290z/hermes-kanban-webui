// Экран «Сейчас» — пульт прогонов. Агрегация целиком на клиенте поверх уже
// существующих эндпоинтов: /api/board (задачи и их статусы), /api/pulse
// (сколько идёт прогон, когда был heartbeat, просрочен ли он) и /api/log
// (завершённые прогоны за последние сутки). Серверный API не меняется.
//
// Четыре блока в фиксированном порядке: живые прогоны, требует внимания,
// очередь, завершено. Блоки рисуются всегда — при нуле прогонов, при ошибке
// сети и при 401 в них стоит осмысленный текст, пустого экрана не бывает.
// Пустая секция (кроме живых прогонов, у них своя строка простоя) сжимается в
// одну строку-статус «Требует внимания — нет»: заголовок-карточка с «Нет»
// внутри стоит дороже, чем нулевая информация в ней.
import { api, isOfflineError } from './api.js?v=20261030-9';
import { t } from './i18n.js?v=20261030-9';
import { escapeHtml } from './markdown.js?v=20261030-9';
import { state, toast } from './state.js?v=20261030-9';
import { openTaskDrawer } from './drawer.js?v=20261030-9';
import { schedulePulse } from './pulse.js?v=20261030-9';
import { formatClock, formatDuration, formatDurationCoarse } from './duration.js?v=20261030-9';

const QUEUE_STATUSES = ['scheduled', 'todo', 'ready', 'triage'];
const DAY_SECONDS = 86400;
const PREVIEW_ROWS = 6;
const PENDING = '—';

// Последние сутки прогонов (api.log), новые первыми: из блока «Завершено»
// берётся и «последний завершился N назад» для состояния простоя.
let logRuns = [];
let nowError = null;
let nowOffline = false;
let pulseNow = Math.floor(Date.now() / 1000);
let last = { data: null, pulse: null };
let expanded = { 'now-queue': false, 'now-done': false };

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

function outcomeLabel(outcome) {
  if (!outcome) return t('logRunning');
  const key = `outcome_${outcome}`;
  const label = t(key);
  return label === key ? outcome : label;
}

function visibleRows(key) {
  return expanded[key] ? Number.MAX_SAFE_INTEGER : PREVIEW_ROWS;
}

// Пустая секция — не карточка с заголовком и словом «нет», а одна строка-статус
// высотой в строку списка (40–44px, спека §4.1): на телефоне вертикаль дороже
// декора, а «Требует внимания — нет» читается быстрее, чем пустой блок.
function block(kind, label, count, body, status = '') {
  if (status) {
    return `<section class="now-block is-status ${kind}">
    <p class="now-status">${escapeHtml(status)}</p>
  </section>`;
  }
  return `<section class="now-block ${kind}">
    <div class="block-head"><span class="block-label">${escapeHtml(label)}</span><span class="count">${count}</span></div>
    ${body}
  </section>`;
}

function pendingBody(text) {
  return `<p class="now-pending">${escapeHtml(text)}</p>`;
}

function moreButton(kind) {
  return `<button type="button" class="button ghost now-more" data-now-more="${kind}">${escapeHtml(t('showAll'))}</button>`;
}

// Ошибка рисуется в каждом блоке: показывать «нет активных прогонов», когда
// ответ вообще не пришёл, — врать. «нет сети» вместо «не удалось загрузить»
// ставит метку api.js (обрыв fetch или 503 {"offline": true} от service worker).
function errorBlock({ alert = false } = {}) {
  const label = nowOffline ? t('noNetwork') : t('loadFailed');
  const role = alert ? ' role="alert"' : '';
  return `<div class="now-error"${role} title="${escapeHtml(nowError || '')}">
    <span>${escapeHtml(label)}</span>
    <span class="now-error-sep" aria-hidden="true">·</span>
    <button type="button" class="button ghost" data-now-retry>${escapeHtml(t('retry'))}</button>
  </div>`;
}

// ===== Живые прогоны =====

function progressBar(entry, limit, overdue) {
  const elapsed = Math.max(0, Number(entry && entry.elapsed_sec) || 0);
  const percent = Math.max(0, Math.min(100, Math.round((elapsed / limit) * 100)));
  return `<span class="now-progress${overdue ? ' is-overdue' : ''}" role="progressbar"
    aria-valuemin="0" aria-valuemax="${limit}" aria-valuenow="${Math.round(elapsed)}"><i style="width:${percent}%"></i></span>`;
}

// Простой не должен быть безымянным: к «нет активных прогонов» добавляется,
// когда закончился последний (ещё идущий прогон ended_at не имеет — не он).
function emptyLiveText() {
  const text = t('noActiveRuns');
  const endedAt = logRuns.reduce((best, run) => {
    const value = Number(run.ended_at) || 0;
    return value > best ? value : best;
  }, 0);
  if (!endedAt) return text;
  const age = Math.max(0, pulseNow - endedAt);
  return `${text} · ${t('lastFinished')} ${formatDurationCoarse(age)} ${t('pulseAgo')}`;
}

function elapsedOf(entry) {
  if (!entry) return 0;
  const started = Number(entry.started_at) || 0;
  if (started && pulseNow > started) return Math.max(0, pulseNow - started);
  return Math.max(0, Number(entry.elapsed_sec) || 0);
}

// Строка прогона по спеке §4.1: заголовок → часы / лимит → пульс → @профиль →
// действия. Полоса прогресса стоит в той же строке метаданных сразу за своей
// подписью «13:50 / 180 мин» — отдельным блоком внизу она читалась как чужая.
// Часы, лимит и пульс держатся в отдельных элементах, чтобы 10-секундный poll из
// pulse.js обновлял их по отдельности.
function liveRow(task, entry) {
  const id = escapeHtml(task.id);
  const overdue = Boolean(entry && entry.overdue);
  const limit = Number(task.max_runtime_seconds) || 0;
  const clock = entry ? formatClock(elapsedOf(entry)) : PENDING;
  // Просроченный пульс (сервер: overdue > 300 с) — словом, а не только цветом.
  const heartbeat = !entry
    ? PENDING
    : overdue
      ? `${t('pulseOverdue')} ${formatDurationCoarse(Math.max(0, Number(entry.heartbeat_age_sec) || 0))}`
      : `${t('pulseHeartbeat')} ${formatDuration(Math.max(0, Number(entry.heartbeat_age_sec) || 0))}`;
  // Лимита нет — нет и полосы: процент считать не от чего.
  const bar = limit > 0 ? progressBar(entry, limit, overdue) : '';
  const limitPart = limit > 0
    ? `<span class="sep">/</span><span class="limit">${escapeHtml(`${Math.round(limit / 60)} ${t('unitMin')}`)}</span>`
    : '';
  const profile = (entry && entry.profile) || task.assignee;
  const profilePart = profile ? `<span class="profile">@${escapeHtml(profile)}</span>` : '';
  return `<article class="run-row" data-task-id="${id}">
    <button type="button" class="run-title" data-now-card="${id}">${escapeHtml(task.title)}</button>
    <div class="run-meta">
      <span class="clock" data-pulse-elapsed="${id}">${escapeHtml(clock)}</span>
      ${limitPart}
      ${bar}
      <span class="pulse${overdue ? ' is-overdue' : ''}" data-pulse-heartbeat="${id}">${escapeHtml(heartbeat)}</span>
      ${profilePart}
    </div>
    <div class="run-actions">
      <button type="button" class="button ghost" data-now-log="${id}">${escapeHtml(t('log'))}</button>
      <button type="button" class="button ghost" data-now-card="${id}">${escapeHtml(t('card'))}</button>
    </div>
  </article>`;
}

function liveBody(running, pulseMap) {
  if (nowError) return pendingBody(PENDING);
  if (!running.length) return `<p class="now-empty">${escapeHtml(emptyLiveText())}</p>`;
  return `<div class="now-list">${running.map(task => liveRow(task, pulseMap[task.id])).join('')}</div>`;
}

// ===== Требует внимания =====

function attentionRows(tasks, pulseMap) {
  const rows = new Map();
  for (const task of tasks) {
    const entry = pulseMap[task.id];
    if (task.status === 'running' && entry && entry.overdue) {
      rows.set(task.id, { task, reason: t('pulseOverdue'), action: 'log' });
    }
  }
  for (const task of tasks) {
    if (rows.has(task.id)) continue;
    if (task.status === 'blocked') rows.set(task.id, { task, reason: t('blocked'), action: 'unblock' });
  }
  for (const task of tasks) {
    if (rows.has(task.id)) continue;
    if (!task.assignee && QUEUE_STATUSES.includes(task.status)) {
      rows.set(task.id, { task, reason: t('noAssigneeTasks'), action: 'assign' });
    }
  }
  return [...rows.values()];
}

function attentionRow(row) {
  const id = escapeHtml(row.task.id);
  const attr = row.action === 'unblock' ? 'data-now-unblock' : row.action === 'assign' ? 'data-now-assign' : 'data-now-log';
  const label = row.action === 'unblock' ? t('unblock') : row.action === 'assign' ? t('assign') : t('log');
  return `<article class="attn-row" data-task-id="${id}">
    <button type="button" class="attn-title" data-now-card="${id}">${escapeHtml(row.task.title)}</button>
    <button type="button" class="button ghost attn-action" ${attr}="${id}">${escapeHtml(label)}</button>
    <span class="attn-reason">${escapeHtml(row.reason)}</span>
  </article>`;
}

function attentionBody(rows) {
  if (nowError) return pendingBody(PENDING);
  if (!rows.length) return `<p class="now-status">${escapeHtml(t('attentionNone'))}</p>`;
  return `<div class="now-list">${rows.map(attentionRow).join('')}</div>`;
}

// ===== Очередь =====

function queueTasks(tasks) {
  return tasks
    .filter(task => QUEUE_STATUSES.includes(task.status))
    .sort((a, b) => (Number(b.priority) || 0) - (Number(a.priority) || 0)
      || (Number(a.created_at) || 0) - (Number(b.created_at) || 0));
}

function queueRow(task) {
  const id = escapeHtml(task.id);
  const priority = Number(task.priority) || 0;
  const age = Math.max(0, pulseNow - (Number(task.created_at) || 0));
  // Приоритет — отдельный слот с табличными цифрами: в слитном тексте «P3» и «P2»
  // читаются одинаково. Возраст подписан словом, иначе «2 мин» — это что, когда?
  const slots = [
    `<span class="queue-status">${escapeHtml(t(task.status))}</span>`,
    `<span class="queue-priority">P${priority}</span>`,
    `<span class="queue-assignee">${task.assignee ? `@${escapeHtml(task.assignee)}` : escapeHtml(t('noAssigneeTasks'))}</span>`,
    age > 0 ? `<span class="queue-age">${escapeHtml(t('queueWaiting'))} ${escapeHtml(formatDurationCoarse(age))}</span>` : ''
  ].filter(Boolean);
  const sep = '<span class="sep" aria-hidden="true">·</span>';
  return `<article class="queue-row" data-task-id="${id}">
    <button type="button" class="queue-title" data-now-card="${id}">${escapeHtml(task.title)}</button>
    <span class="queue-meta">${slots.join(sep)}</span>
  </article>`;
}

function queueBody(queue) {
  if (nowError) return pendingBody(PENDING);
  if (!queue.length) return `<p class="now-status">${escapeHtml(t('queueNone'))}</p>`;
  const limit = visibleRows('now-queue');
  const rows = queue.slice(0, limit).map(queueRow).join('');
  const more = queue.length > limit ? moreButton('now-queue') : '';
  return `<div class="now-list">${rows}</div>${more}`;
}

// ===== Завершено =====

function doneRow(run) {
  const id = escapeHtml(run.task_id || '');
  // Внутри секции «Завершено» слово «Завершено» в каждой строке — дубль заголовка.
  // Остаются длительность и когда это было: «30 мин · 25 ч назад».
  const ended = Number(run.ended_at) || 0;
  const age = ended && pulseNow > ended ? pulseNow - ended : 0;
  const ago = age > 0
    ? `<span class="done-ago">${escapeHtml(formatDurationCoarse(age))} ${escapeHtml(t('pulseAgo'))}</span>`
    : '';
  return `<article class="done-row" data-task-id="${id}">
    <time class="done-time">${escapeHtml(run.started_at_label || '')}</time>
    <button type="button" class="done-title" data-now-card="${id}">${escapeHtml(run.title || run.task_id || '')}</button>
    <span class="done-meta">
      <span class="done-profile">@${escapeHtml(run.profile || t('unassigned'))}</span>
      <span class="done-duration">${escapeHtml(formatDuration(run.duration_sec))}</span>
      ${ago}
    </span>
  </article>`;
}

function doneSummary(all) {
  const errors = all.filter(run => run.outcome && run.outcome !== 'completed').length;
  const durations = all.map(run => Number(run.duration_sec)).filter(value => Number.isFinite(value) && value >= 0);
  const average = durations.length ? durations.reduce((sum, value) => sum + value, 0) / durations.length : 0;
  // Ошибки — акцент, а не серый текст рядом с «средн. 12 мин»: их надо замечать.
  const errorPart = `<span class="sum-errors${errors ? '' : ' is-zero'}">${errors} ${escapeHtml(t('summaryErrors'))}</span>`;
  return `<p class="now-summary">${all.length} ${escapeHtml(t('summaryRuns'))} ${escapeHtml(t('summaryWindow'))} · ${errorPart} · ${escapeHtml(t('summaryAvg'))} ${escapeHtml(formatDurationCoarse(average))}</p>`;
}

function doneBody() {
  if (nowError) return pendingBody(PENDING);
  const completed = logRuns.filter(run => run.outcome === 'completed');
  const summary = logRuns.length ? doneSummary(logRuns) : '';
  if (!completed.length) return `${summary}<p class="now-status">${escapeHtml(t('doneNone'))}</p>`;
  const limit = visibleRows('now-done');
  const rows = completed.slice(0, limit).map(doneRow).join('');
  const more = completed.length > limit ? moreButton('now-done') : '';
  return `${summary}<div class="now-list">${rows}</div>${more}`;
}

// ===== Сборка экрана =====

export function renderNow(data, pulse) {
  const root = document.getElementById('viewNow');
  if (!root) return;
  last = { data, pulse };
  const pult = pulse && pulse.pulse ? pulse.pulse : {};
  pulseNow = Number(pulse && pulse.now) || Math.floor(Date.now() / 1000);
  const tasks = flatTasks(data);
  const running = tasks.filter(task => task.status === 'running');
  const attention = attentionRows(tasks, pult);
  const queue = queueTasks(tasks);
  const completed = logRuns.filter(run => run.outcome === 'completed');
  // При ошибке счётчики не показываются цифрами: их не из чего взять.
  const failed = Boolean(nowError);
  const count = value => (failed ? PENDING : value);
  const body = (rendered, first) => (failed ? errorBlock({ alert: first }) : rendered);
  // Пустая секция сворачивается в одну строку-статус: заголовок-карточка с «Нет»
  // внутри съедал пол-экрана телефона ради нуля информации.
  const idle = (size, text) => (failed || size > 0 ? '' : text);
  root.innerHTML = [
    block('now-live', t('liveRuns'), count(running.length), body(liveBody(running, pult), true)),
    block('now-attention', t('needsAttention'), count(attention.length), body(attentionBody(attention), false), idle(attention.length, t('attentionNone'))),
    block('now-queue', t('queue'), count(queue.length), body(queueBody(queue), false), idle(queue.length, t('queueNone'))),
    block('now-done', t('completed'), count(completed.length), body(doneBody(), false), idle(logRuns.length, t('doneNone')))
  ].join('');
  bind(root);
  // Дальше пульс обновляют существующие [data-pulse-id] каждые 10 секунд.
  schedulePulse(running.map(task => task.id));
}

function bind(root) {
  root.querySelectorAll('[data-now-card]').forEach(btn => {
    btn.addEventListener('click', () => openTaskDrawer(btn.dataset.nowCard));
  });
  root.querySelectorAll('[data-now-log]').forEach(btn => {
    btn.addEventListener('click', () => toggleRunLog(btn));
  });
  root.querySelectorAll('[data-now-unblock]').forEach(btn => {
    btn.addEventListener('click', () => unblockTask(btn));
  });
  root.querySelectorAll('[data-now-assign]').forEach(btn => {
    btn.addEventListener('click', () => openTaskDrawer(btn.dataset.nowAssign));
  });
  root.querySelectorAll('[data-now-more]').forEach(btn => {
    btn.addEventListener('click', () => {
      expanded[btn.dataset.nowMore] = true;
      renderNow(last.data, last.pulse);
    });
  });
  root.querySelectorAll('[data-now-retry]').forEach(btn => {
    btn.addEventListener('click', () => loadNow());
  });
}

async function toggleRunLog(btn) {
  const row = btn.closest('.run-row, .attn-row');
  if (!row) return;
  const existing = row.querySelector('.run-log');
  if (existing) {
    existing.remove();
    return;
  }
  const id = btn.dataset.nowLog;
  let html;
  try {
    const data = await api.log({ board: state.board, task: id, limit: 5 });
    const runs = Array.isArray(data.runs) ? data.runs : [];
    html = runs.length
      ? runs.map(run => `<div class="run-log-row">
          <time>${escapeHtml(run.started_at_label || PENDING)}</time>
          <span>${escapeHtml(outcomeLabel(run.outcome))}</span>
          <span>${escapeHtml(formatDuration(run.duration_sec))}</span>
          <span class="mono">@${escapeHtml(run.profile || PENDING)}</span>
        </div>`).join('')
      : `<div class="run-log-row">${escapeHtml(t('logEmpty'))}</div>`;
  } catch (err) {
    html = `<div class="run-log-row">${escapeHtml(t('loadFailed'))}</div>`;
  }
  row.insertAdjacentHTML('beforeend', `<div class="run-log">${html}</div>`);
}

async function unblockTask(btn) {
  const id = btn.dataset.nowUnblock;
  btn.disabled = true;
  try {
    await api.updateTask(state.board, id, { status: 'todo' });
    document.dispatchEvent(new CustomEvent('kanban:refresh'));
  } catch (err) {
    btn.disabled = false;
    toast(err.message || String(err), 'error');
  }
}

// Роутер и load() зовут экран почти одновременно: второй вызов
// присоединяется к уже идущему запросу, а не дублирует его.
let inflight = null;

export async function loadNow() {
  if (!document.getElementById('viewNow')) return;
  if (inflight) return inflight;
  inflight = fetchAndRender().finally(() => { inflight = null; });
  return inflight;
}

async function fetchAndRender() {
  const board = state.board;
  try {
    const data = await api.board({ board });
    const runningIds = flatTasks(data)
      .filter(task => task.status === 'running')
      .map(task => task.id);
    const [pulse, log] = await Promise.all([
      runningIds.length
        ? api.pulse(board, runningIds.join(','))
        : Promise.resolve({ now: Math.floor(Date.now() / 1000), pulse: {} }),
      // Окна «ровно сутки» у /api/log нет: берём неделю и сужаем на клиенте.
      api.log({ board, since: '7d', limit: 200 })
    ]);
    const serverNow = Number(log.server_now) || Number(pulse.now) || Math.floor(Date.now() / 1000);
    logRuns = (Array.isArray(log.runs) ? log.runs : [])
      .filter(run => !run.started_at || Number(run.started_at) >= serverNow - DAY_SECONDS)
      .sort((a, b) => (Number(b.started_at) || 0) - (Number(a.started_at) || 0));
    nowError = null;
    nowOffline = false;
    renderNow(data, pulse);
  } catch (err) {
    nowError = err && err.message ? err.message : String(err);
    nowOffline = isOfflineError(err);
    logRuns = [];
    renderNow(null, null);
  }
}