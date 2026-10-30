// Run-pulse: one batched /api/pulse poll every 10 s for all running tasks,
// rendered into [data-pulse-id] placeholders on board cards and list rows.
// Clock discipline: the server's `now` from each response is the base; between
// polls we interpolate with Date.now() only as a drift offset, so a browser
// with a wrong clock or timezone can never produce a negative elapsed time.
import { api } from './api.js?v=20261030-1';
import { t } from './i18n.js?v=20261030-1';
import { state } from './state.js?v=20261030-1';
import { formatDuration, formatDurationCoarse } from './duration.js?v=20261030-1';

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

function lineText(entry) {
  const now = serverNow();
  if (entry.overdue) {
    const age = formatDurationCoarse(Math.max(0, Number(entry.heartbeat_age_sec) || 0));
    return `⏱ ${t('pulseNoHeartbeat')} ${age}`;
  }
  const elapsed = now === null ? 0 : Math.max(0, now - entry.started_at);
  const heartbeat = formatDuration(Math.max(0, Number(entry.heartbeat_age_sec) || 0));
  return `⏱ ${t('pulseRunning')} ${formatDurationCoarse(elapsed)} · ${t('pulseHeartbeat')} ${heartbeat} ${t('pulseAgo')}`;
}

function elapsedText(entry) {
  const now = serverNow();
  const elapsed = now === null ? 0 : Math.max(0, now - entry.started_at);
  return formatDurationCoarse(elapsed);
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
