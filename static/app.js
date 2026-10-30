import { api, isOfflineError, offlineInfo } from './api.js?v=20261030-8';
import { applyI18n, setLang, nextLang, t } from './i18n.js?v=20261030-8';
import { setupThemeToggle, updateThemeToggleLabel } from './theme.js?v=20261030-8';
import { renderBoard } from './board.js?v=20261030-8';
import { setupDependencyControls } from './dependency-lines.js?v=20261030-8';
import { setupForms } from './forms.js?v=20261030-8';
import { setupMobileFallback, setupMobileShell } from './mobile.js?v=20261030-8';
import { setupAppUpdatePrompt, setupServiceWorkerUpdateBanner } from './update.js?v=20261030-8';
import { setupOperationsPanel, refreshOperationsPanel } from './operations.js?v=20261030-8';
import { closeDrawer, openTaskDrawer } from './drawer.js?v=20261030-8';
import { state, setBoard, toast } from './state.js?v=20261030-8';
import { createMultiSelect, loadList, setupListView } from './list.js?v=20261030-8';
import { loadLog, setupLogView } from './log.js?v=20261030-8';
import { schedulePulse } from './pulse.js?v=20261030-8';
import { loadNow } from './now.js?v=20261030-8';
import { loadFeed, refreshFeed, setupFeedView } from './feed.js?v=20261030-8';
import { setupPwa } from './pwa.js?v=20261030-8';

let boardStatusSelect = null;
let boardStatusFilter = [];

// Пять экранов, четыре вкладки: вид «Список» живёт внутри вкладки «Доска».
export const VIEWS = ['now', 'board', 'list', 'feed', 'log'];
export const TABS = ['now', 'board', 'feed', 'log'];
const PHONE_QUERY = '(max-width: 759px)';

function sectionFor(view) {
  return document.getElementById(`view${view[0].toUpperCase()}${view.slice(1)}`);
}

// Хэш — набор пар (view=..., task=...): роутер не теряет карточку при смене вью.
function parseHash() {
  const pairs = {};
  for (const part of (location.hash || '').replace(/^#/, '').split('&')) {
    if (!part) continue;
    const idx = part.indexOf('=');
    const key = idx === -1 ? part : part.slice(0, idx);
    const value = idx === -1 ? '' : part.slice(idx + 1);
    try { pairs[decodeURIComponent(key)] = decodeURIComponent(value); }
    catch { pairs[key] = value; }
  }
  return pairs;
}

export function isPhone() { return window.matchMedia(PHONE_QUERY).matches; }
export function defaultView() { return isPhone() ? 'now' : 'board'; }
export function currentView() {
  const view = parseHash().view;
  return VIEWS.includes(view) ? view : defaultView();
}
export function currentTask() { return parseHash().task || null; }
export function viewUrl(view = currentView(), task = currentTask()) {
  const parts = [`view=${view}`];
  if (task) parts.push(`task=${task}`);
  return `#${parts.join('&')}`;
}

function writeHash(url) {
  if (location.hash !== url) history.replaceState(null, '', url);
}

export function applyView(view, { updateHash = true } = {}) {
  const active = VIEWS.includes(view) ? view : defaultView();
  // «Список» живёт внутри вкладки «Доска» переключателем «Секции | Таблица»:
  // обе секции видны, переключается только начинка — колонки/секции или таблица.
  const host = active === 'list' ? 'board' : active;
  VIEWS.forEach(name => {
    const section = sectionFor(name);
    if (section) section.hidden = name !== active && name !== host;
  });
  const sections = document.getElementById('boardSections');
  if (sections) sections.hidden = active === 'list';
  if (active === 'list') {
    const toActive = document.getElementById('boardToActive');
    if (toActive) toActive.hidden = true;
  }
  const tabFor = active === 'list' ? 'board' : active;
  document.querySelectorAll('.tabs [data-tab]').forEach(btn => {
    const on = btn.dataset.tab === tabFor;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-selected', String(on));
  });
  document.querySelectorAll('[data-board-mode]').forEach(btn => {
    const on = btn.dataset.boardMode === (active === 'list' ? 'table' : 'sections');
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-pressed', String(on));
  });
  if (updateHash) writeHash(viewUrl(active));
  // Пульс обслуживает один список id за раз: вид «Список» сужает его до своих строк,
  // поэтому возврат на доску пересобирает полный набор.
  // Доска без данных — не «нет задач»: либо ответ ещё не пришёл, либо не пришёл
  // вовсе. Ошибку рисует load(), сюда доходит уже готовый блок с «Повторить».
  if (active === 'board' && boardError) renderBoardError();
  if (active === 'board' && state.data) {
    const runningIds = [];
    (state.data.column_order || []).forEach(status => {
      (state.data.columns[status] || []).forEach(task => { if (task.status === 'running') runningIds.push(task.id); });
    });
    schedulePulse(runningIds);
  }
  if (active === 'list') loadList();
  if (active === 'log') loadLog();
  if (active === 'feed') loadFeed();
  // Экран «Сейчас» грузит себя сам и показывает состояние ошибки, если API
  // недоступен: load() при 401 падает раньше и до вью бы не дошёл.
  if (active === 'now') loadNow();
  return active;
}

function setupTabs() {
  document.querySelector('.tabs')?.addEventListener('click', ev => {
    const btn = ev.target.closest('[data-tab]');
    if (!btn) return;
    const view = btn.dataset.tab;
    writeHash(viewUrl(view));
    applyView(view, { updateHash: false });
  });
  window.addEventListener('hashchange', () => {
    applyView(currentView(), { updateHash: false });
    const task = currentTask();
    if (task) openTaskDrawer(task);
    else if (document.getElementById('drawer')?.classList.contains('open')) closeDrawer();
  });
  applyView(currentView(), { updateHash: false });
  const task = currentTask();
  if (task) openTaskDrawer(task);
}

function setupMorePanel() {
  const panel = document.getElementById('morePanel');
  const moreBtn = document.getElementById('moreBtn');
  const searchBtn = document.getElementById('searchBtn');
  if (!panel) return;
  const setOpen = open => {
    panel.hidden = !open;
    moreBtn?.setAttribute('aria-expanded', String(open));
    searchBtn?.setAttribute('aria-expanded', String(open));
  };
  moreBtn?.addEventListener('click', () => setOpen(panel.hidden));
  searchBtn?.addEventListener('click', () => {
    setOpen(true);
    document.getElementById('searchInput')?.focus();
  });
  document.addEventListener('keydown', ev => {
    if (ev.key === 'Escape' && !panel.hidden) setOpen(false);
  });
}

// Переключатель «Секции | Таблица» и строка фильтров — внутри вкладки «Доска».
function setupBoardMode() {
  const bar = document.getElementById('boardBar');
  if (!bar) return;
  bar.addEventListener('click', ev => {
    const btn = ev.target.closest('[data-board-mode]');
    if (!btn) return;
    applyView(btn.dataset.boardMode === 'table' ? 'list' : 'board');
  });
  // Фильтры строки принадлежат таблице: в режиме секций их ввод иначе не виден,
  // поэтому первое же изменение переключает на «Таблицу».
  const toTable = ev => {
    if (ev.target.closest?.('.mode-switch')) return;
    if (currentView() === 'board') applyView('list');
  };
  bar.addEventListener('change', toTable);
  bar.addEventListener('input', toTable);
}

function setupBoardStatusFilter() {
  const host = document.getElementById('statusFilter');
  if (!host) return;
  boardStatusSelect = createMultiSelect(host, {
    label: t('status'),
    options: [],
    onChange: values => {
      boardStatusFilter = values;
      renderBoardColumns();
    }
  });
}

function renderBoardColumns() {
  const data = state.data;
  if (!data) return;
  const filtered = boardStatusFilter.length
    ? { ...data, column_order: (data.column_order || []).filter(status => boardStatusFilter.includes(status)) }
    : data;
  renderBoard(filtered);
}

async function loadBoards() {
  const data = await api.boards();
  const select = document.getElementById('boardSelect');
  if (!select) return;
  select.replaceChildren();
  for (const b of data.boards) {
    const option = document.createElement('option');
    option.value = b.slug;
    option.textContent = `${b.name || b.slug} (${b.total || 0})`;
    select.appendChild(option);
  }
  if (!data.boards.find(b => b.slug === state.board)) setBoard(data.current || 'default');
  select.value = state.board;
}

function countAssigneeTasks(assignee) {
  return Object.values(assignee.counts || {}).reduce((sum, count) => sum + Number(count || 0), 0);
}

function assigneeOptionLabel(assignee) {
  const count = countAssigneeTasks(assignee);
  const kind = assignee.on_disk ? t('agentProfile') : t('manualAssignee');
  return `${assignee.name} · ${kind}${count ? ` (${count})` : ''}`;
}

function appendOption(select, value, label) {
  const option = document.createElement('option');
  option.value = value;
  option.textContent = label;
  select.appendChild(option);
}

function renderAssigneeControls(data) {
  const assignees = Array.isArray(data.assignees) ? data.assignees : [];
  const profileAssignees = assignees.filter(item => item && item.on_disk);

  const taskAssignee = document.getElementById('taskAssignee');
  if (taskAssignee) {
    const previousTaskAssignee = taskAssignee.value || localStorage.getItem('lastAssignee') || '';
    taskAssignee.replaceChildren();
    appendOption(taskAssignee, '', t('unassigned'));
    for (const assignee of profileAssignees) appendOption(taskAssignee, assignee.name, assigneeOptionLabel(assignee));
    taskAssignee.value = profileAssignees.some(item => item.name === previousTaskAssignee) ? previousTaskAssignee : '';
  }

  const filter = document.getElementById('assigneeFilter');
  if (!filter) return;
  const previousFilter = state.assignee || filter.value || '';
  filter.replaceChildren();
  appendOption(filter, '', t('allAssignees'));
  for (const assignee of assignees) appendOption(filter, assignee.name, assigneeOptionLabel(assignee));
  if (assignees.some(item => item.name === previousFilter)) {
    filter.value = previousFilter;
  } else {
    filter.value = '';
    state.assignee = '';
  }
}

// Последняя ошибка загрузки доски: null, пока данные приходят. Отдельная
// переменная, потому что пустая доска и недоступная доска выглядят одинаково —
// без неё офлайн рисовал бы «задач нет», то есть врал про содержимое.
let boardError = null;

export async function load() {
  try {
    await fetchBoard();
    boardError = null;
  } catch (err) {
    // Токен спрашивает сам api.js (модальная полоса), остальное — сюда:
    // обрыв сети подписываем «нет сети», серверную ошибку — «не удалось загрузить».
    boardError = { message: err && err.message ? err.message : String(err), offline: isOfflineError(err) };
    renderBoardError();
    // Доска уже показана — колонки не трогаем, но человек должен знать, что
    // цифры в них не свежие: полоса «нет сети · Повторить» поверх.
    if (state.data && boardError.offline) showOfflineNotice();
    console.warn('board load failed:', err);
  }
}

// Блок ошибки на месте колонок: текст + «Повторить». Рисуется только когда
// данных ещё нет (первая загрузка, пустая оболочка в офлайне). Если доска уже
// показана и упал очередной poll — колонки не трогаем: устаревшая доска полезнее
// пустого экрана, а про обрыв скажет полоса #offlineBar.
function renderBoardError() {
  const board = document.getElementById('board');
  if (!board || !boardError || state.data) return;
  const label = boardError.offline ? t('noNetwork') : t('loadFailed');
  board.innerHTML = `<p class="view-placeholder board-error" role="alert" title="${String(boardError.message).replace(/"/g, '&quot;')}">
    <span>${label}</span>
    <span class="now-error-sep" aria-hidden="true">·</span>
    <button type="button" class="button ghost" data-board-retry>${t('retry')}</button>
  </p>`;
  board.querySelector('[data-board-retry]')?.addEventListener('click', () => load());
}

async function fetchBoard() {
  await api.config().then(cfg => { state.config = cfg; });
  await loadBoards();
  const params = {
    board: state.board,
    include_archived: state.includeArchived,
    q: state.query,
    assignee: state.assignee
  };
  const data = await api.board(params);
  state.data = data;
  state.latestEventId = data.latest_event_id;
  renderAssigneeControls(data);
  // На телефоне имя доски из топбара убрано (там оно резалось до «D…») — полное
  // имя стоит первой строкой панели «Ещё», рядом с выбором доски.
  const name = (data.board_meta || {}).name || data.board;
  const boardName = document.getElementById('boardName');
  if (boardName) boardName.textContent = name;
  const boardNameFull = document.getElementById('boardNameFull');
  if (boardNameFull) boardNameFull.textContent = name;
  renderBoardColumns();
  if (boardStatusSelect) {
    boardStatusSelect.setOptions((data.column_order || []).map(status => ({ value: status, label: t(status) })));
  }
  await refreshOperationsPanel();
  renderOfflineBar();
  if (currentView() === 'list') loadList();
  if (currentView() === 'log') loadLog();
  if (currentView() === 'now') loadNow();
  // Лента обновляется только пока открыта её первая страница: иначе poll
  // сбрасывал бы подгрузку «Показать ещё» (см. refreshFeed).
  if (currentView() === 'feed') refreshFeed();
}

// Полоса «нет сети · данные от HH:MM · Повторить»: показывается, когда ответ
// пришёл из кэша service worker'а. Час берём из заголовка Date закэшированного
// ответа, чтобы человек видел, насколько данные старые.
function renderOfflineBar() {
  const bar = document.getElementById('offlineBar');
  const text = document.getElementById('offlineBarText');
  if (!bar || !text) return;
  const info = offlineInfo();
  if (!info.offline) {
    bar.hidden = true;
    return;
  }
  let clock = '';
  const stamp = Date.parse(info.cachedAt || '');
  if (!Number.isNaN(stamp)) {
    clock = new Date(stamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  text.textContent = clock ? `${t('noNetwork')} · ${clock}` : t('noNetwork');
  bar.hidden = false;
}

function setupOfflineBar() {
  document.addEventListener('kanban:connection', renderOfflineBar);
  window.addEventListener('online', renderOfflineBar);
  window.addEventListener('offline', showOfflineNotice);
  document.getElementById('offlineRetry')?.addEventListener('click', () => {
    document.dispatchEvent(new CustomEvent('kanban:refresh'));
  });
}

// Полоса без времени: сеть пропала, но кэша под рукой может и не быть (тогда
// время брать не откуда). «Повторить» уже стоит в самой полосе.
function showOfflineNotice() {
  const bar = document.getElementById('offlineBar');
  const text = document.getElementById('offlineBarText');
  if (!bar || !text) return;
  text.textContent = t('noNetwork');
  bar.hidden = false;
}

function setupControls() {
  const on = (id, event, handler) => document.getElementById(id)?.addEventListener(event, handler);
  on('refreshBtn', 'click', load);
  on('langToggle', 'click', () => { setLang(nextLang()); updateThemeToggleLabel(); load(); });
  on('boardSelect', 'change', async ev => {
    setBoard(ev.target.value);
    await api.switchBoard(state.board);
    await load();
  });
  on('archivedToggle', 'change', ev => { state.includeArchived = ev.target.checked; load(); });
  on('searchInput', 'input', ev => { state.query = ev.target.value; clearTimeout(ev.target._timer); ev.target._timer = setTimeout(load, 250); });
  on('assigneeFilter', 'change', ev => { state.assignee = ev.target.value; load(); });
  on('overlay', 'click', closeDrawer);
  document.addEventListener('kanban:refresh', load);
  document.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') closeDrawer();
    const tagName = ev.target?.tagName?.toLowerCase();
    const isTyping = ['input', 'select', 'textarea'].includes(tagName) || ev.target?.isContentEditable;
    if (!isTyping && ev.key === '/') {
      ev.preventDefault();
      document.getElementById('moreBtn')?.click();
      document.getElementById('searchInput')?.focus();
    }
    if (!isTyping && ev.key.toLowerCase() === 'n') document.getElementById('taskCreateBtn').click();
  });
}

async function pollEvents() {
  try {
    const data = await api.events(state.board, state.latestEventId || 0);
    if (data.events.length) await load();
  } catch (err) {
    console.warn(err);
  } finally {
    state.refreshTimer = setTimeout(pollEvents, 2500);
  }
}

async function main() {
  applyI18n();
  setupThemeToggle();
  setupControls();
  setupMorePanel();
  // Раскладка телефона (нижние вкладки, полноэкранный drawer) — до первого рендера,
  // иначе табы успевают мигнуть наверху.
  setupMobileShell();
  setupTabs();
  setupBoardMode();
  setupBoardStatusFilter();
  setupListView();
  setupLogView();
  setupFeedView();
  setupDependencyControls();
  setupForms(load);
  setupMobileFallback();
  setupAppUpdatePrompt();
  setupServiceWorkerUpdateBanner();
  setupOfflineBar();
  setupPwa();
  setupOperationsPanel();
  const storedAssignee = localStorage.getItem('lastAssignee') || '';
  const taskAssignee = document.getElementById('taskAssignee');
  if (taskAssignee) taskAssignee.value = storedAssignee;
  try {
    await load();
    pollEvents();
  } catch (err) {
    console.error(err);
    toast(err.message || String(err), 'error');
  }
}

main();