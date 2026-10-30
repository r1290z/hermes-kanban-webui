import { api } from './api.js?v=20261030-3';
import { t } from './i18n.js?v=20261030-3';
import { escapeHtml } from './markdown.js?v=20261030-3';
import { openTaskDrawer } from './drawer.js?v=20261030-3';
import { state } from './state.js?v=20261030-3';
import { formatDuration } from './duration.js?v=20261030-3';

const PAGE_SIZE = 50;

const logState = {
  mode: 'runs',
  assignee: '',
  outcome: '',
  since: 'all',
  kind: '',
  q: '',
  includeHeartbeat: false,
  before: null,
  beforeId: null,
  loading: false,
  profiles: [],
  outcomes: [],
  kinds: []
};

function outcomeLabel(outcome) {
  if (!outcome) return t('logRunning');
  const key = `outcome_${outcome}`;
  const label = t(key);
  // A missing translation falls back to the key itself — show the raw outcome then.
  return label === key ? outcome : label;
}

function runRowHtml(run) {
  const outcome = run.outcome || '';
  const error = run.error ? `<pre class="log-error">${escapeHtml(run.error)}</pre>` : '';
  const metadata = run.metadata
    ? `<pre class="log-metadata">${escapeHtml(typeof run.metadata === 'string' ? run.metadata : JSON.stringify(run.metadata, null, 2))}</pre>`
    : '';
  const summary = run.summary ? `<p class="log-summary">${escapeHtml(run.summary)}</p>` : '';
  const attachments = run.attachment_count
    ? `<span class="log-chip">${escapeHtml(t('attachments'))}: ${escapeHtml(String(run.attachment_count))}</span>`
    : '';
  const comments = run.comment_count
    ? `<span class="log-chip">${escapeHtml(t('comments'))}: ${escapeHtml(String(run.comment_count))}</span>`
    : '';
  return `<article class="log-row" data-run-id="${escapeHtml(String(run.id))}" data-task-id="${escapeHtml(run.task_id || '')}">
    <div class="log-row-main">
      <time class="log-time">${escapeHtml(run.started_at_label || '')}</time>
      <span class="log-profile">${escapeHtml(run.profile || t('unassigned'))}</span>
      <button type="button" class="log-title" data-open-task="${escapeHtml(run.task_id || '')}">${escapeHtml(run.title || run.task_id || '')}</button>
      <span class="log-duration">${escapeHtml(formatDuration(run.duration_sec))}</span>
      <span class="log-outcome is-${escapeHtml(outcome || 'running')}">${escapeHtml(outcomeLabel(outcome))}</span>
      <button type="button" class="button ghost log-toggle" data-log-toggle>${escapeHtml(t('logDetails'))}</button>
    </div>
    <div class="log-row-details" hidden>
      ${summary}${error}${metadata}
      <div class="log-row-actions">
        ${attachments}${comments}
        <button type="button" class="button ghost" data-open-task="${escapeHtml(run.task_id || '')}">${escapeHtml(t('logOpenTask'))}</button>
      </div>
    </div>
  </article>`;
}

function eventRowHtml(event) {
  let payload = '';
  if (event.payload) {
    const text = typeof event.payload === 'string' ? event.payload : JSON.stringify(event.payload, null, 2);
    payload = `<pre class="log-metadata">${escapeHtml(text)}</pre>`;
  }
  return `<article class="log-row log-event" data-event-id="${escapeHtml(String(event.id))}" data-task-id="${escapeHtml(event.task_id || '')}">
    <div class="log-row-main">
      <time class="log-time">${escapeHtml(event.created_at_label || '')}</time>
      <span class="log-kind">${escapeHtml(event.kind)}</span>
      <span class="log-profile">${escapeHtml(event.profile || '')}</span>
      <button type="button" class="log-title" data-open-task="${escapeHtml(event.task_id || '')}">${escapeHtml(event.title || event.task_id || '')}</button>
    </div>
    ${payload ? `<div class="log-row-details">${payload}</div>` : ''}
  </article>`;
}

function renderRuns(runs) {
  const host = document.getElementById('logList');
  if (!host) return;
  if (!runs.length) {
    host.innerHTML = `<p class="log-empty">${escapeHtml(t('logEmpty'))}</p>`;
    return;
  }
  host.innerHTML = runs.map(runRowHtml).join('');
}

function renderEvents(events) {
  const host = document.getElementById('logList');
  if (!host) return;
  if (!events.length) {
    host.innerHTML = `<p class="log-empty">${escapeHtml(t('logEmpty'))}</p>`;
    return;
  }
  host.innerHTML = events.map(eventRowHtml).join('');
}

function syncFacetOptions() {
  const profileSelect = document.getElementById('logAssignee');
  const outcomeSelect = document.getElementById('logOutcome');
  const kindSelect = document.getElementById('logKind');
  if (profileSelect) {
    const current = logState.assignee;
    profileSelect.innerHTML = `<option value="">${escapeHtml(t('logAllProfiles'))}</option>`
      + logState.profiles.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('');
    profileSelect.value = current;
  }
  if (outcomeSelect) {
    const current = logState.outcome;
    outcomeSelect.innerHTML = `<option value="">${escapeHtml(t('logAllOutcomes'))}</option>`
      + logState.outcomes.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(outcomeLabel(value))}</option>`).join('');
    outcomeSelect.value = current;
  }
  if (kindSelect) {
    const current = logState.kind;
    kindSelect.innerHTML = `<option value="">${escapeHtml(t('logAllKinds'))}</option>`
      + logState.kinds.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('');
    kindSelect.value = current;
  }
}

function updateFooter(hasMore, shown) {
  const moreBtn = document.getElementById('logMore');
  if (moreBtn) moreBtn.hidden = !hasMore;
  const counter = document.getElementById('logCount');
  if (counter) counter.textContent = `${t('logShown')}: ${shown}`;
}

export async function loadLog({ append = false } = {}) {
  if (logState.loading) return;
  logState.loading = true;
  const host = document.getElementById('logList');
  try {
    if (logState.mode === 'runs') {
      const data = await api.log({
        board: state.board,
        assignee: logState.assignee,
        outcome: logState.outcome,
        since: logState.since,
        q: logState.q,
        limit: PAGE_SIZE,
        before: append ? logState.before : null,
        before_id: append ? logState.beforeId : null
      });
      logState.profiles = data.profiles || [];
      logState.outcomes = data.outcomes || [];
      logState.before = data.next_before;
      logState.beforeId = data.next_before_id;
      syncFacetOptions();
      if (append && host) host.insertAdjacentHTML('beforeend', (data.runs || []).map(runRowHtml).join(''));
      else renderRuns(data.runs || []);
      const shown = host ? host.querySelectorAll('.log-row').length : 0;
      updateFooter(Boolean(data.has_more), shown);
    } else {
      const data = await api.logEvents({
        board: state.board,
        assignee: logState.assignee,
        outcome: logState.outcome,
        since: logState.since,
        kind: logState.kind,
        include_heartbeat: logState.includeHeartbeat ? 1 : 0,
        limit: PAGE_SIZE,
        before: append ? logState.before : null,
        before_id: append ? logState.beforeId : null
      });
      logState.profiles = logState.profiles.length ? logState.profiles : [];
      logState.kinds = data.kinds || [];
      logState.before = data.next_before;
      logState.beforeId = data.next_before_id;
      syncFacetOptions();
      if (append && host) host.insertAdjacentHTML('beforeend', (data.events || []).map(eventRowHtml).join(''));
      else renderEvents(data.events || []);
      const shown = host ? host.querySelectorAll('.log-row').length : 0;
      updateFooter(Boolean(data.has_more), shown);
    }
  } catch (err) {
    console.error(err);
    if (host && !host.children.length) {
      host.innerHTML = `<p class="log-empty">${escapeHtml(err.message || String(err))}</p>`;
    }
  } finally {
    logState.loading = false;
  }
}

function resetPaging() {
  logState.before = null;
  logState.beforeId = null;
}

export function setupLogView() {
  const host = document.getElementById('logList');
  if (!host) return;

  document.getElementById('logModeRuns')?.addEventListener('click', () => {
    logState.mode = 'runs';
    document.getElementById('logModeRuns')?.classList.add('is-active');
    document.getElementById('logModeEvents')?.classList.remove('is-active');
    document.getElementById('logKindFilter')?.setAttribute('hidden', '');
    resetPaging();
    loadLog();
  });

  document.getElementById('logModeEvents')?.addEventListener('click', () => {
    logState.mode = 'events';
    document.getElementById('logModeEvents')?.classList.add('is-active');
    document.getElementById('logModeRuns')?.classList.remove('is-active');
    document.getElementById('logKindFilter')?.removeAttribute('hidden');
    resetPaging();
    loadLog();
  });

  document.getElementById('logAssignee')?.addEventListener('change', ev => {
    logState.assignee = ev.target.value;
    resetPaging();
    loadLog();
  });

  document.getElementById('logOutcome')?.addEventListener('change', ev => {
    logState.outcome = ev.target.value;
    resetPaging();
    loadLog();
  });

  document.getElementById('logKind')?.addEventListener('change', ev => {
    logState.kind = ev.target.value;
    resetPaging();
    loadLog();
  });

  document.getElementById('logSince')?.addEventListener('change', ev => {
    logState.since = ev.target.value;
    resetPaging();
    loadLog();
  });

  document.getElementById('logHeartbeat')?.addEventListener('change', ev => {
    logState.includeHeartbeat = ev.target.checked;
    resetPaging();
    loadLog();
  });

  const search = document.getElementById('logSearch');
  search?.addEventListener('input', ev => {
    logState.q = ev.target.value;
    clearTimeout(ev.target._timer);
    ev.target._timer = setTimeout(() => {
      resetPaging();
      loadLog();
    }, 250);
  });

  document.getElementById('logMore')?.addEventListener('click', () => loadLog({ append: true }));

  host.addEventListener('click', ev => {
    const toggle = ev.target.closest('[data-log-toggle]');
    if (toggle) {
      const row = toggle.closest('.log-row');
      const details = row?.querySelector('.log-row-details');
      if (details) {
        details.hidden = !details.hidden;
        toggle.textContent = details.hidden ? t('logDetails') : t('logHideDetails');
      }
      return;
    }
    const open = ev.target.closest('[data-open-task]');
    if (open?.dataset.openTask) {
      openTaskDrawer(open.dataset.openTask);
    }
  });
}

export function refreshLog() {
  resetPaging();
  return loadLog();
}
