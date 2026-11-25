import { api } from './api.js?v=20261125-1';
import { lang, t } from './i18n.js?v=20261125-1';
import { escapeHtml } from './markdown.js?v=20261125-1';
import { openTaskDrawer } from './drawer.js?v=20261125-1';
import { state } from './state.js?v=20261125-1';
import { schedulePulse } from './pulse.js?v=20261125-1';

const PAGE_SIZE = 100;

const SORT_COLUMNS = new Set(['created', 'updated', 'priority', 'title', 'status']);

const listState = {
  assignee: [],
  status: [],
  q: '',
  archived: false,
  sort: 'created',
  dir: 'desc',
  offset: 0,
  loading: false
};

// A native <select multiple> is unusable on a phone (the OS picker allows a
// single choice), so the multiselect is a details/summary dropdown with
// checkboxes: one tap to open, works with touch, keeps the keyboard path.
export function createMultiSelect(host, config = {}) {
  const label = config.label || '';
  let options = config.options || [];
  let values = new Set(config.selected || []);

  host.classList.add('multiselect');
  host.replaceChildren();
  const details = document.createElement('details');
  details.className = 'multiselect-box';
  const summary = document.createElement('summary');
  summary.className = 'button ghost';
  const summaryText = document.createElement('span');
  summary.append(summaryText);
  const panel = document.createElement('div');
  panel.className = 'multiselect-panel';
  details.append(summary, panel);
  host.append(details);

  function summaryLabel() {
    if (!values.size) return `${label}: ${t('multiselectAll')}`;
    if (values.size === 1) return [...values][0];
    return `${label}: ${values.size}`;
  }

  function render() {
    summaryText.textContent = summaryLabel();
    panel.replaceChildren();
    for (const option of options) {
      const item = document.createElement('label');
      item.className = 'multiselect-item';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.value = option.value;
      input.checked = values.has(option.value);
      input.addEventListener('change', () => {
        if (input.checked) values.add(option.value);
        else values.delete(option.value);
        summaryText.textContent = summaryLabel();
        config.onChange?.([...values]);
      });
      const text = document.createElement('span');
      text.textContent = option.label;
      item.append(input, text);
      panel.append(item);
    }
  }

  function onOutside(ev) {
    if (!host.contains(ev.target)) details.open = false;
  }

  details.addEventListener('toggle', () => {
    if (details.open) document.addEventListener('click', onOutside, true);
    else document.removeEventListener('click', onOutside, true);
  });

  render();

  return {
    setOptions(next) {
      options = next || [];
      values = new Set([...values].filter(value => options.some(option => option.value === value)));
      render();
    },
    setSelected(next) {
      values = new Set(next || []);
      render();
    },
    getSelected() {
      return [...values];
    }
  };
}

// Дата в списке — короткая и на языке интерфейса: раньше toLocaleString() без
// локали печатал секунды и следовал языку браузера, а не переключателю RU/EN.
function formatDate(value) {
  if (!value) return '—';
  const date = new Date(Number(value) * 1000);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(lang(), {
    day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

function statusCell(task) {
  return `<span class="list-status"><span class="status-dot ${escapeHtml(task.status || '')}"></span><span>${escapeHtml(t(task.status || ''))}</span></span>`;
}

// Три счётчика в одной ячейке: прогоны · комментарии · вложения. Отдельными
// колонками они съедали по 4-8% ширины, и заголовку задачи оставалось 16%.
function countsCell(task) {
  const pairs = [['runs', task.run_count], ['comments', task.comment_count], ['attachments', task.attachment_count]];
  return pairs.map(([key, value]) => `<span title="${escapeHtml(t(key))}" class="list-count-num">${escapeHtml(String(Number(value) || 0))}</span>`).join('');
}

function rowHtml(task) {
  const assignee = task.assignee
    ? `<span class="list-assignee">@${escapeHtml(task.assignee)}</span>`
    : `<span class="muted">${escapeHtml(t('unassigned'))}</span>`;
  return `<tr class="list-row" data-task-id="${escapeHtml(task.id)}" tabindex="0">
    <td data-label="${escapeHtml(t('status'))}">${statusCell(task)}</td>
    <td data-label="${escapeHtml(t('listAssignee'))}">${assignee}</td>
    <td data-label="${escapeHtml(t('priority'))}"><span class="list-priority">${escapeHtml(String(task.priority ?? 0))}</span></td>
    <td data-label="${escapeHtml(t('title'))}">
      <code class="list-id">${escapeHtml(task.id)}</code>
      <span class="list-title">${escapeHtml(task.title || '')}</span>
    </td>
    <td data-label="${escapeHtml(t('tenant'))}">${task.tenant ? escapeHtml(task.tenant) : '<span class="muted">—</span>'}</td>
    <td data-label="${escapeHtml(t('created'))}"><span class="list-date">${escapeHtml(formatDate(task.created_at))}</span></td>
    <td data-label="${escapeHtml(t('listUpdated'))}"><span class="list-date">${escapeHtml(formatDate(task.updated_at))}</span></td>
    <td data-label="${escapeHtml(t('listCounts'))}" class="list-counts">${countsCell(task)}</td>
    <td data-label="${escapeHtml(t('listElapsed'))}" class="list-pulse">${task.status === 'running' ? `<span class="pulse-short" data-pulse-id="${escapeHtml(task.id)}" data-pulse-elapsed></span><span class="pulse-full" data-pulse-id="${escapeHtml(task.id)}"></span>` : ''}</td>
  </tr>`;
}

function headerHtml(sort, dir) {
  const cell = (key, label) => {
    const active = sort === key;
    const arrow = active ? (dir === 'asc' ? ' ↑' : ' ↓') : '';
    const ariaSort = active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none';
    return `<th class="list-th${active ? ' is-active' : ''}" data-sort="${key}" aria-sort="${ariaSort}"><button type="button" class="list-sort">${escapeHtml(label)}${arrow}</button></th>`;
  };
  return `<tr>
    ${cell('status', t('status'))}
    <th class="list-th">${escapeHtml(t('listAssignee'))}</th>
    ${cell('priority', t('priority'))}
    ${cell('title', t('title'))}
    <th class="list-th">${escapeHtml(t('tenant'))}</th>
    ${cell('created', t('created'))}
    ${cell('updated', t('listUpdated'))}
    <th class="list-th">${escapeHtml(t('listCounts'))}</th>
    <th class="list-th">${escapeHtml(t('listElapsed'))}</th>
  </tr>`;
}

function renderRows(tasks, append) {
  const body = document.getElementById('listBody');
  if (!body) return;
  if (!append) body.innerHTML = '';
  const empty = body.querySelector('.list-empty-row');
  if (empty) empty.remove();
  if (!tasks.length && !body.children.length) {
    body.innerHTML = `<tr class="list-empty-row"><td colspan="9">${escapeHtml(t('listEmpty'))}</td></tr>`;
    return;
  }
  body.insertAdjacentHTML('beforeend', tasks.map(rowHtml).join(''));
}

function updateFooter(data) {
  const total = Number(data.total || 0);
  const shown = document.getElementById('listBody')?.querySelectorAll('.list-row').length || 0;
  const totalEl = document.getElementById('listTotal');
  if (totalEl) totalEl.textContent = `${t('listTotal')}: ${shown} / ${total}`;
  const moreBtn = document.getElementById('listMore');
  if (moreBtn) moreBtn.hidden = shown >= total;
  const sortSel = document.getElementById('listSort');
  if (sortSel) sortSel.value = listState.sort;
  const dirBtn = document.getElementById('listSortDir');
  if (dirBtn) dirBtn.textContent = listState.dir === 'asc' ? t('listSortAsc') : t('listSortDesc');
}

export async function loadList({ append = false } = {}) {
  if (listState.loading) return;
  listState.loading = true;
  try {
    const data = await api.list({
      board: state.board,
      assignee: listState.assignee.join(','),
      status: listState.status.join(','),
      q: listState.q,
      archived: listState.archived ? 1 : 0,
      sort: listState.sort,
      dir: listState.dir,
      limit: PAGE_SIZE,
      offset: append ? listState.offset : 0
    });
    listState.offset = append ? listState.offset + data.tasks.length : data.tasks.length;
    const head = document.getElementById('listHead');
    if (head) head.innerHTML = headerHtml(listState.sort, listState.dir);
    renderRows(data.tasks, append);
    updateFooter(data);
    populateFacets(data);
    schedulePulse(data.tasks.filter(task => task.status === 'running').map(task => task.id));
  } catch (err) {
    console.error(err);
    const body = document.getElementById('listBody');
    if (body && !body.children.length) {
      body.innerHTML = `<tr class="list-empty-row"><td colspan="9">${escapeHtml(err.message || String(err))}</td></tr>`;
    }
  } finally {
    listState.loading = false;
  }
}

let assigneeSelect = null;
let statusSelect = null;

function populateFacets(data) {
  if (!assigneeSelect || !statusSelect) return;
  assigneeSelect.setOptions((data.assignees || []).map(value => ({ value, label: value })));
  statusSelect.setOptions((data.statuses || []).map(value => ({ value, label: t(value) })));
}

function applySort(key) {
  if (!SORT_COLUMNS.has(key)) return;
  if (listState.sort === key) listState.dir = listState.dir === 'asc' ? 'desc' : 'asc';
  else {
    listState.sort = key;
    listState.dir = key === 'title' || key === 'status' ? 'asc' : 'desc';
  }
  listState.offset = 0;
  loadList();
}

export function setupListView() {
  const table = document.getElementById('listTable');
  if (!table) return;

  assigneeSelect = createMultiSelect(document.getElementById('listAssigneeFilter'), {
    label: t('listAssignee'),
    options: [],
    onChange: values => {
      listState.assignee = values;
      listState.offset = 0;
      loadList();
    }
  });

  statusSelect = createMultiSelect(document.getElementById('listStatusFilter'), {
    label: t('status'),
    options: [],
    onChange: values => {
      listState.status = values;
      listState.offset = 0;
      loadList();
    }
  });

  const search = document.getElementById('listSearch');
  search?.addEventListener('input', ev => {
    listState.q = ev.target.value;
    clearTimeout(ev.target._timer);
    ev.target._timer = setTimeout(() => {
      listState.offset = 0;
      loadList();
    }, 250);
  });

  document.getElementById('listArchived')?.addEventListener('change', ev => {
    listState.archived = ev.target.checked;
    listState.offset = 0;
    loadList();
  });

  document.getElementById('listSort')?.addEventListener('change', ev => {
    if (!SORT_COLUMNS.has(ev.target.value)) return;
    listState.sort = ev.target.value;
    listState.offset = 0;
    loadList();
  });

  document.getElementById('listSortDir')?.addEventListener('click', () => {
    listState.dir = listState.dir === 'asc' ? 'desc' : 'asc';
    listState.offset = 0;
    loadList();
  });

  document.getElementById('listMore')?.addEventListener('click', () => loadList({ append: true }));

  table.addEventListener('click', ev => {
    const th = ev.target.closest('th[data-sort]');
    if (th) {
      applySort(th.dataset.sort);
      return;
    }
    const row = ev.target.closest('.list-row');
    if (row?.dataset.taskId) openTaskDrawer(row.dataset.taskId);
  });

  table.addEventListener('keydown', ev => {
    if (ev.key !== 'Enter') return;
    const row = ev.target.closest('.list-row');
    if (row?.dataset.taskId) openTaskDrawer(row.dataset.taskId);
  });
}

export function refreshList() {
  listState.offset = 0;
  return loadList();
}
