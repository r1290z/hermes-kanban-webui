import { t } from './i18n.js?v=20261125-1';
import { escapeHtml } from './markdown.js?v=20261125-1';
import { openTaskDrawer } from './drawer.js?v=20261125-1';
import { attachDragHandlers } from './dragdrop.js?v=20261125-1';
import { clearDependencyFocus, focusDependencyTask, refreshDependencyOverlay, renderDependencyOverlay, selectDependencyTask } from './dependency-lines.js?v=20261125-1';
import { schedulePulse } from './pulse.js?v=20261125-1';

// Один DOM — две раскладки (колонки на десктопе, секции на телефоне, CSS).
// Плотная карточка: id не переносится, метаданные одной строкой, нулевые
// счётчики не рисуются, предупреждение об отсутствии профиля — одно.
const PHONE_QUERY = '(max-width: 759px)';
// Телефон не рендерит всю секцию сразу: длинный «Готово» раскрывается кнопкой.
const MOBILE_LIMIT = 8;
// Куда автоскроллить на десктопе: первый значимый статус в этом порядке.
const SIGNIFICANT_ORDER = ['running', 'blocked', 'ready'];

const expandedStatuses = new Set();
let lastData = null;
let lastScrollTarget = null;
let hintBound = false;

function isPhone() { return window.matchMedia(PHONE_QUERY).matches; }

// Markdown в карточке не печатается: превью — плоский текст без fence-блоков,
// заголовков, списков, жирного/курсива, таблиц и плейсхолдеров <|-- ... --|>.
function plainPreview(value) {
  return String(value || '')
    .replace(/<\|[\s\S]*?\|>/g, ' ')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s{0,3}[-*+]\s+/gm, '')
    .replace(/^\s{0,3}\d+\.\s+/gm, '')
    .replace(/\*\*|__|~~/g, '')
    .replace(/\*([^*\n]+)\*/g, '$1')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\|/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function progressBar(taskId, limit) {
  if (!(limit > 0)) return '';
  return `<span class="card-progress" data-pulse-progress="${taskId}" data-pulse-limit="${limit}" role="progressbar" aria-valuemin="0" aria-valuemax="${limit}" aria-valuenow="0"><i></i></span>`;
}

function card(task) {
  const isUnassigned = !task.assignee;
  const assigneeHint = escapeHtml(t('profileMissing'));
  const taskId = escapeHtml(task.id);
  const parents = Number(task.link_counts?.parents || 0);
  const children = Number(task.link_counts?.children || 0);
  const childPortHint = escapeHtml(t('childPortHint'));
  const parentPortHint = escapeHtml(t('parentPortHint'));
  const limit = Number(task.max_runtime_seconds) || 0;

  const meta = [];
  if (task.assignee) meta.push(`<span class="chip-profile">@${escapeHtml(task.assignee)}</span>`);
  if (task.tenant) meta.push(`<span class="chip-tenant">${escapeHtml(task.tenant)}</span>`);
  if (task.priority) meta.push(`<span class="num" title="${escapeHtml(t('priority'))}">P${escapeHtml(String(task.priority))}</span>`);
  const total = Number(task.progress?.total || 0);
  if (total) meta.push(`<span class="num" title="${escapeHtml(t('runs'))}">${Number(task.progress?.done || 0)}/${total}</span>`);
  const comments = Number(task.comment_count || 0);
  if (comments) meta.push(`<span class="chip-count" title="${escapeHtml(t('comments'))}">${escapeHtml(t('comments'))}: <b class="num">${comments}</b></span>`);
  const attachments = Number(task.attachment_count || 0);
  if (attachments) meta.push(`<span class="chip-count" title="${escapeHtml(t('attachments'))}">${escapeHtml(t('attachments'))}: <b class="num">${attachments}</b></span>`);
  if (parents) meta.push(`<span class="chip-count" title="${escapeHtml(t('parents'))}">${escapeHtml(t('parents'))}: <b class="num">${parents}</b></span>`);
  if (children) meta.push(`<span class="chip-count" title="${escapeHtml(t('children'))}">${escapeHtml(t('children'))}: <b class="num">${children}</b></span>`);
  const workflowKey = task.current_step_key || task.workflow_template_id;
  if (workflowKey) meta.push(`<span class="workflow-chip" title="${escapeHtml(task.workflow_template_id || '')}">${escapeHtml(t('workflow'))}: ${escapeHtml(task.current_step_key || task.workflow_template_id)}</span>`);

  const preview = plainPreview(task.body_preview);

  return `<article class="task-card ${task.status}${isUnassigned ? ' is-unassigned' : ''}" data-task-id="${taskId}" data-parent-count="${parents}" data-child-count="${children}" data-assignee-state="${isUnassigned ? 'missing' : 'assigned'}" tabindex="0">
    <button type="button" class="dependency-port child-port" data-link-role="child" data-link-task-id="${taskId}" title="${childPortHint}" aria-label="${childPortHint}"><span>${escapeHtml(t('child'))}</span></button>
    <button type="button" class="dependency-port parent-port" data-link-role="parent" data-link-task-id="${taskId}" title="${parentPortHint}" aria-label="${parentPortHint}"><span>${escapeHtml(t('parent'))}</span></button>
    <div class="card-head"><span class="id mono">${taskId}</span>${isUnassigned ? `<span class="profile-missing-badge" title="${assigneeHint}" aria-label="${assigneeHint}">${escapeHtml(t('profileMissingShort'))}</span>` : ''}<span class="status-dot ${task.status}"></span></div>
    <h3 class="card-title">${escapeHtml(task.title)}</h3>
    ${preview ? `<p class="card-preview">${escapeHtml(preview)}</p>` : ''}
    ${task.status === 'running' ? `<div class="card-live pulse-line" data-pulse-id="${taskId}"></div>${progressBar(taskId, limit)}` : ''}
    ${meta.length ? `<div class="card-meta">${meta.join('')}</div>` : ''}
  </article>`;
}

// Пустые статусы на телефоне не занимают экран: они уезжают в ряд чипов внизу,
// тап по чипу разворачивает секцию (в ней есть «＋», чтобы завести задачу).
function renderRail(rail, emptyStatuses) {
  if (!rail) return;
  rail.classList.add('board-rail');
  rail.innerHTML = emptyStatuses
    .map(status => `<button type="button" data-status="${escapeHtml(status)}" aria-label="${escapeHtml(t(status))}">${escapeHtml(t(status))}</button>`)
    .join('');
}

// Десктоп: доска занимает остаток вьюпорта, поэтому набор карточек растягивал
// страницу не она, а колонки — они скроллятся внутри себя. Высоту считаем по
// фактическому верху доски: панель фильтров переносится и её высота не константа.
function fitBoardHeight(root) {
  if (!root) return;
  if (isPhone()) {
    root.style.removeProperty('height');
    return;
  }
  const top = root.getBoundingClientRect().top;
  const next = `${Math.max(320, Math.round(window.innerHeight - top - 16))}px`;
  if (root.style.height !== next) root.style.height = next;
}

function bindColumnScroll(root) {
  // Карточки скроллятся внутри колонки — линии связей обязаны перерисоваться,
  // иначе стрелки остаются на прежних местах.
  root.querySelectorAll('.cards').forEach(el => {
    el.addEventListener('scroll', refreshDependencyOverlay, { passive: true });
  });
}

function updateScrollHint(root) {
  if (!root) return;
  const canScroll = root.scrollWidth - root.clientWidth - root.scrollLeft > 4;
  root.classList.toggle('can-scroll-right', canScroll);
  const toActive = document.getElementById('boardToActive');
  if (toActive) toActive.hidden = !canScroll;
}

function scrollToSignificant(root, force = false) {
  if (!root || isPhone()) return;
  // Сначала «живые» статусы. Если их нет (например, всё в «Готово»), едем к
  // первой непустой колонке: иначе при горизонтальном скролле на 900px экран
  // открывается одними пустыми дорожками.
  const target = SIGNIFICANT_ORDER
    .map(status => root.querySelector(`.board-column[data-status="${status}"]:not(.is-empty)`))
    .find(Boolean)
    || root.querySelector('.board-column:not(.is-empty)');
  if (!target) return;
  const key = target.dataset.status || '';
  if (!force && key === lastScrollTarget) return;
  lastScrollTarget = key;
  root.scrollLeft = Math.max(0, target.offsetLeft);
  updateScrollHint(root);
}

export function renderBoard(data) {
  const root = document.getElementById('board');
  if (!root) return;
  lastData = data;
  const statuses = data.column_order || [];
  root.style.setProperty('--kanban-column-count', String(Math.max(1, statuses.length)));
  const phone = isPhone();
  const runningIds = [];
  const emptyStatuses = [];

  root.innerHTML = statuses.map(status => {
    const tasks = data.columns[status] || [];
    tasks.forEach(task => { if (task.status === 'running') runningIds.push(task.id); });
    if (!tasks.length) emptyStatuses.push(status);
    const expanded = expandedStatuses.has(status);
    const clipped = phone && tasks.length > MOBILE_LIMIT && !expanded;
    const shown = clipped ? tasks.slice(0, MOBILE_LIMIT) : tasks;
    const more = clipped
      ? `<button type="button" class="button ghost section-more" data-status="${escapeHtml(status)}">${escapeHtml(t('showAll'))} · ${tasks.length}</button>`
      : '';
    // Развёрнутая пустая секция (тап по чипу) переживает перерисовку по poll'у.
    const classes = ['board-column'];
    if (!tasks.length) classes.push('is-empty');
    if (!tasks.length && expanded) classes.push('is-expanded');
    return `<section class="${classes.join(' ')}" data-status="${escapeHtml(status)}">
      <header><div><h2>${escapeHtml(t(status))}</h2><small class="num">${tasks.length}</small></div><button type="button" class="mini-add" data-status="${escapeHtml(status)}" aria-label="${escapeHtml(t('taskCreate'))}">＋</button></header>
      <div class="drop-placeholder"></div>
      ${!tasks.length ? '<div class="column-empty" aria-hidden="true"></div>' : ''}
      <div class="cards">${shown.map(card).join('')}</div>
      ${more}
    </section>`;
  }).join('');

  renderRail(document.getElementById('boardRail'), emptyStatuses);

  schedulePulse(runningIds);

  root.querySelectorAll('.task-card').forEach(el => {
    const open = () => {
      selectDependencyTask(el.dataset.taskId);
      openTaskDrawer(el.dataset.taskId);
    };
    el.addEventListener('mouseenter', () => focusDependencyTask(el.dataset.taskId));
    el.addEventListener('mouseleave', () => clearDependencyFocus(el.dataset.taskId));
    el.addEventListener('focus', () => focusDependencyTask(el.dataset.taskId));
    el.addEventListener('blur', () => clearDependencyFocus(el.dataset.taskId));
    el.addEventListener('click', open);
    el.addEventListener('keydown', ev => { if (ev.key === 'Enter') open(); });
  });
  root.querySelectorAll('.mini-add').forEach(btn => btn.addEventListener('click', ev => {
    ev.stopPropagation();
    document.dispatchEvent(new CustomEvent('kanban:open-task-create', { detail: { status: btn.dataset.status } }));
  }));
  // Телефон: «Показать все» перерисовывает доску с раскрытой секцией, чтобы
  // скрытые карточки не висели в DOM пустыми прямоугольниками для линий связей.
  root.querySelectorAll('.section-more').forEach(btn => btn.addEventListener('click', () => {
    expandedStatuses.add(btn.dataset.status);
    if (lastData) renderBoard(lastData);
  }));
  const rail = document.getElementById('boardRail');
  rail?.querySelectorAll('[data-status]').forEach(btn => btn.addEventListener('click', () => {
    const column = root.querySelector(`.board-column[data-status="${btn.dataset.status}"]`);
    if (!column) return;
    expandedStatuses.add(btn.dataset.status);
    column.classList.add('is-expanded');
    column.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }));

  if (!hintBound) {
    hintBound = true;
    root.addEventListener('scroll', () => updateScrollHint(root), { passive: true });
    window.addEventListener('resize', () => { fitBoardHeight(root); updateScrollHint(root); });
    document.getElementById('boardToActive')?.addEventListener('click', () => scrollToSignificant(root, true));
  }

  fitBoardHeight(root);
  bindColumnScroll(root);
  attachDragHandlers(root);
  renderDependencyOverlay(data);
  scrollToSignificant(root);
  updateScrollHint(root);
}