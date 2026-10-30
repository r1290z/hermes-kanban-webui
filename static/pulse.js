// Run-pulse: one batched /api/pulse poll every 10 s for all running tasks,
// rendered into [data-pulse-id] placeholders on board cards and list rows.
// Clock discipline: the server's `now` from each response is the base; between
// polls we interpolate with Date.now() only as a drift offset, so a browser
// with a wrong clock or timezone can never produce a negative elapsed time.
import { api } from './api.js?v=20261030-2';
import { t } from './i18n.js?v=20261030-2';
import { state } from './state.js?v=20261030-2';
import { formatClock, formatDuration, formatDurationCoarse } from './duration.js?v=20261030-2';

const POLL_MS = 10000;

let timer = null;
let ids = [];
let sync = { now: 0, at: 0 };
let pulse = {};
let inFlight = false;

function serverNow() {
  if (!sync.now) return null;
  return sync.now + Math.floor((Date.now() - sync.at) / 1000);
}

// Single source of the pulse wording: the "Сейчас" screen paints its first frame
// with the same function, so the board card, the list column and the run pult
// can never drift apart in format.
export function pulseLine(entry, nowSec = null) {
  if (!entry) return '';
  if (entry.overdue) {
    const age = formatDurationCoarse(Math.max(0, Number(entry.heartbeat_age_sec) || 0));
    return `${t('pulseOverdue')} ${age}`;
  }
  const now = nowSec === null ? serverNow() : nowSec;
  const elapsed = now === null
    ? Math.max(0, Number(entry.elapsed_sec) || 0)
    : Math.max(0, now - Number(entry.started_at || 0));
  const heartbeat = formatDuration(Math.max(0, Number(entry.heartbeat_age_sec) || 0));
  return `${t('pulseRunning')} ${formatDurationCoarse(elapsed)} · ${t('pulseHeartbeat')} ${heartbeat} ${t('pulseAgo')}`;
}

function lineText(entry) {
  return pulseLine(entry);
}

function elapsedSeconds(entry, nowSec = null) {
  const now = nowSec === null ? serverNow() : nowSec;
  return now === null ? 0 : Math.max(0, now - (Number(entry.started_at) || 0));
}

function elapsedText(entry) {
  return formatDurationCoarse(elapsedSeconds(entry));
}

// Missing entries are left as-is on purpose: a run that just finished drops out
// of the payload, but the card itself disappears on the next board render —
// clearing text here would blank lines on the hidden view after a view switch.
function apply() {
  document.querySelectorAll('[data-pulse-id]').forEach(el => {
    const entry = pulse[el.dataset.pulseId];
    if (!entry) return;
    const text = el.dataset.pulseElapsed !== undefined ? elapsedText(entry) : lineText(entry);
    el.classList.toggle('is-overdue', Boolean(entry.overdue));
    if (el.textContent !== text) el.textContent = text;
  });
  // Пульт прогонов держит части строки раздельно: часы, лимит и heartbeat
  // обновляются по отдельности, чтобы «/ 60 мин» не перерисовывался зря.
  document.querySelectorAll('[data-pulse-elapsed]:not([data-pulse-id])').forEach(el => {
    const entry = pulse[el.dataset.pulseElapsed];
    if (!entry) return;
    el.classList.toggle('is-overdue', Boolean(entry.overdue));
    const text = formatClock(elapsedSeconds(entry));
    if (el.textContent !== text) el.textContent = text;
  });
  document.querySelectorAll('[data-pulse-heartbeat]').forEach(el => {
    const entry = pulse[el.dataset.pulseHeartbeat];
    if (!entry) return;
    // Просроченный пульс (сервер: overdue > 300 с) помечается словом, а не только цветом.
    const text = entry.overdue
      ? `${t('pulseOverdue')} ${formatDurationCoarse(Math.max(0, Number(entry.heartbeat_age_sec) || 0))}`
      : `${t('pulseHeartbeat')} ${formatDuration(Math.max(0, Number(entry.heartbeat_age_sec) || 0))}`;
    el.classList.toggle('is-overdue', Boolean(entry.overdue));
    if (el.textContent !== text) el.textContent = text;
  });
}

async function fetchPulse() {
  if (!ids.length || document.hidden || inFlight) return;
  inFlight = true;
  try {
    const data = await api.pulse(state.board, ids.join(','));
    sync = { now: Number(data.now) || 0, at: Date.now() };
    pulse = data.pulse || {};
    apply();
  } catch (err) {
    console.warn('pulse poll failed', err);
  } finally {
    inFlight = false;
  }
}

function stopTimer() {
  if (timer) { clearInterval(timer); timer = null; }
}

export function schedulePulse(runningIds) {
  const next = [...new Set(runningIds || [])].filter(Boolean).sort();
  const changed = next.length !== ids.length || next.some((value, index) => value !== ids[index]);
  ids = next;
  if (!ids.length) {
    stopTimer();
    pulse = {};
    sync = { now: 0, at: 0 };
    return;
  }
  // Same id set + re-rendered DOM (board reload): re-apply the cached payload
  // without burning a request; changed ids need fresh data right away.
  if (changed) fetchPulse();
  else apply();
  if (!timer) timer = setInterval(fetchPulse, POLL_MS);
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    stopTimer();
    return;
  }
  if (ids.length) {
    fetchPulse();
    if (!timer) timer = setInterval(fetchPulse, POLL_MS);
  }
});
