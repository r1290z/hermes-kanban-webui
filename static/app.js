import { api } from './api.js?v=20261029-11';
import { applyI18n, lang, setLang, nextLang, t } from './i18n.js?v=20261029-11';
import { setupThemeToggle, updateThemeToggleLabel } from './theme.js?v=20261029-11';
import { renderBoard, renderKpis } from './board.js?v=20261029-11';
import { setupDependencyControls } from './dependency-lines.js?v=20261029-11';
import { setupForms } from './forms.js?v=20261029-11';
import { setupMobileFallback } from './mobile.js?v=20261029-11';
import { setupAppUpdatePrompt } from './update.js?v=20261029-11';
import { setupOperationsPanel, refreshOperationsPanel } from './operations.js?v=20261029-11';
import { closeDrawer } from './drawer.js?v=20261029-11';
import { state, setBoard, toast } from './state.js?v=20261029-11';
import { createMultiSelect, loadList, setupListView } from './list.js?v=20261029-11';

let boardStatusSelect = null;
let boardStatusFilter = [];

const VIEWS = ['board', 'list', 'log'];

function currentView() {
  const raw = (location.hash || '').replace(/^#/, '').trim();
  const [key, value] = raw.split('=');
  const view = key === 'view' ? value : raw;
  return VIEWS.includes(view) ? view : 'board';
}

function applyView(view, { updateHash = true } = {}) {
  const active = VIEWS.includes(view) ? view : 'board';
  VIEWS.forEach(name => {
    const section = document.getElementById(`view${name[0].toUpperCase()}${name.slice(1)}`);
    if (section) section.hidden = name !== active;
  });
  document.querySelectorAll('#viewSwitch [data-view]').forEach(btn => {
    btn.classList.toggle('is-active', btn.dataset.view === active);
    btn.setAttribute('aria-selected', String(btn.dataset.view === active));
  });
  if (updateHash && currentView() !== active) {
    history.replaceState(null, '', `#view=${active}`);
  }
  if (active === 'list') loadList();
  return active;
}

function setupViewSwitch() {
  document.getElementById('viewSwitch')?.addEventListener('click', ev => {
    const btn = ev.target.closest('[data-view]');
    if (!btn) return;
    const view = btn.dataset.view;
    history.replaceState(null, '', `#view=${view}`);
    applyView(view, { updateHash: false });
  });
  window.addEventListener('hashchange', () => applyView(currentView(), { updateHash: false }));
  applyView(currentView(), { updateHash: false });
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
  select.replaceChildren();
  for (const b of data.boards) {
    const option = document.createElement('option');
    option.value = b.slug;
    option.textContent = `${b.icon || ''} ${b.name || b.slug} (${b.total || 0})`;
    select.appendChild(option);
  }
  if (!data.boards.find(b => b.slug === state.board)) setBoard(data.current || 'default');
  select.value = state.board;
}

async function loadStatus() {
  const status = await api.status();
  document.getElementById('healthDot').classList.toggle('ok', status.ok);
  document.getElementById('healthText').textContent = status.ok ? 'OK' : 'Error';
  document.getElementById('dbPath').textContent = status.db_path || '';
  const serverLabel = document.getElementById('serverLabel');
  if (serverLabel) serverLabel.textContent = `${status.service || 'kanban-webui'} · ${window.location.host}`;
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
  const previousTaskAssignee = taskAssignee.value || localStorage.getItem('lastAssignee') || '';
  taskAssignee.replaceChildren();
  appendOption(taskAssignee, '', t('unassigned'));
  for (const assignee of profileAssignees) appendOption(taskAssignee, assignee.name, assigneeOptionLabel(assignee));
  taskAssignee.value = profileAssignees.some(item => item.name === previousTaskAssignee) ? previousTaskAssignee : '';

  const filter = document.getElementById('assigneeFilter');
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

export async function load() {
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
  document.getElementById('boardTitle').textContent = data.board_meta.name || data.board;
  document.getElementById('boardDescription').textContent = data.board_meta.description || t('boardDescription');
  renderKpis(data);
  renderBoardColumns();
  if (boardStatusSelect) {
    boardStatusSelect.setOptions((data.column_order || []).map(status => ({ value: status, label: t(status) })));
  }
  await refreshOperationsPanel();
  await loadStatus();
  if (currentView() === 'list') loadList();
}

function setupControls() {
  document.getElementById('refreshBtn').addEventListener('click', load);
  const toolbarToggle = document.getElementById('toolbarToggle');
  if (toolbarToggle) {
    toolbarToggle.addEventListener('click', () => {
      const open = toolbarToggle.closest('.toolbar').classList.toggle('is-open');
      toolbarToggle.setAttribute('aria-expanded', String(open));
    });
  }
  document.getElementById('langToggle').addEventListener('click', () => { setLang(nextLang()); updateThemeToggleLabel(); load(); });
  document.getElementById('boardSelect').addEventListener('change', async ev => {
    setBoard(ev.target.value);
    await api.switchBoard(state.board);
    await load();
  });
  document.getElementById('archivedToggle').addEventListener('change', ev => { state.includeArchived = ev.target.checked; load(); });
  document.getElementById('searchInput').addEventListener('input', ev => { state.query = ev.target.value; clearTimeout(ev.target._timer); ev.target._timer = setTimeout(load, 250); });
  document.getElementById('assigneeFilter').addEventListener('change', ev => { state.assignee = ev.target.value; load(); });
  document.getElementById('overlay').addEventListener('click', closeDrawer);
  document.addEventListener('kanban:refresh', load);
  document.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') closeDrawer();
    const tagName = ev.target?.tagName?.toLowerCase();
    const isTyping = ['input', 'select', 'textarea'].includes(tagName) || ev.target?.isContentEditable;
    if (!isTyping && ev.key === '/') { ev.preventDefault(); document.getElementById('searchInput').focus(); }
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
  setupViewSwitch();
  setupBoardStatusFilter();
  setupListView();
  setupDependencyControls();
  setupForms(load);
  setupMobileFallback();
  setupAppUpdatePrompt();
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
