function tokenHeaders() {
  const token = localStorage.getItem('kanbanToken');
  return token ? { 'X-Kanban-Token': token } : {};
}

// A token in the query string would land in proxy logs and browser history, so the
// shareable link carries it in the fragment: the browser never sends that to the
// server. Read it once, keep it, then scrub it from the address bar and history.
function absorbFragmentToken() {
  const hash = location.hash || '';
  const match = hash.match(/(?:^#|&)token=([^&]+)/);
  if (!match) return;
  const token = decodeURIComponent(match[1]).trim();
  if (token) localStorage.setItem('kanbanToken', token);
  // Keep any other fragment state (e.g. #view=list) when scrubbing the token.
  const rest = hash.slice(1).split('&').filter(part => part && !part.startsWith('token=')).join('&');
  history.replaceState(null, '', location.pathname + location.search + (rest ? `#${rest}` : ''));
}

absorbFragmentToken();

function errorMessage(data, fallback) {
  const message = data.detail || data.error || fallback;
  if (Array.isArray(message)) return message.map(x => x.msg || JSON.stringify(x)).join(', ');
  if (message && typeof message === 'object') return JSON.stringify(message);
  return message;
}

// Обрыв сети — не ошибка сервера: вью показывает «нет сети · Повторить», а не
// «не удалось загрузить». Метка ставится и на упавший fetch, и на ответ
// 503 {"offline": true} от service worker (см. static/sw.js).
export function isOfflineError(error) {
  if (error && error.offline === true) return true;
  return typeof navigator !== 'undefined' && navigator.onLine === false;
}

function offlineError(message) {
  const error = new Error(message || 'нет сети');
  error.offline = true;
  return error;
}

// LAN mode: the server asks for a token and the browser has nowhere to enter it.
// A blocking window.prompt() here would freeze page load (the first API call fires
// during boot), so the ask is an inline bar that reloads once a token is saved.
function askForToken() {
  if (document.getElementById('tokenBar')) return;
  const bar = document.createElement('form');
  bar.id = 'tokenBar';
  bar.innerHTML = `
    <style>
      #tokenBar{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;
        justify-content:center;background:var(--bg,#080a12)}
      #tokenBar .box{background:var(--surface,#151a26);border:1px solid var(--line-strong,#2a3244);
        border-radius:var(--r-md,8px);padding:26px 28px;max-width:420px;width:calc(100% - 40px);
        font-family:inherit;color:var(--ink,#e8ecf4);box-shadow:var(--shadow-overlay)}
      #tokenBar h3{margin:0 0 6px;font-size:17px}
      #tokenBar p{margin:0 0 16px;font-size:13px;opacity:.7;line-height:1.5}
      #tokenBar input{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:var(--r-sm,5px);
        border:1px solid var(--line-strong,#2a3244);background:var(--surface-2,#111417);
        color:inherit;font:inherit;font-size:14px}
      #tokenBar button{margin-top:12px;width:100%;padding:10px;border-radius:var(--r-sm,5px);border:0;
        background:var(--run,#3b82f6);color:var(--on-accent,#fff);font:inherit;font-weight:600;cursor:pointer}
      #tokenBar .err{margin-top:10px;font-size:12px;color:var(--danger,#f87171);min-height:1em}
    </style>
    <div class="box">
      <h3>Нужен токен доступа</h3>
      <p>Эта доска открыта по сети и защищена токеном. Вставьте его — браузер запомнит значение.</p>
      <input name="token" type="password" autocomplete="off" placeholder="токен" autofocus />
      <button type="submit">Войти</button>
      <div class="err"></div>
    </div>`;
  document.body.appendChild(bar);
  const input = bar.querySelector('input');
  input.focus();
  bar.addEventListener('submit', ev => {
    ev.preventDefault();
    const value = input.value.trim();
    if (!value) return;
    localStorage.setItem('kanbanToken', value);
    location.reload();
  });
}

// Состояние связи по последнему ответу: офлайн с кэшем или живой ответ.
// Метку ставит service worker (X-Kanban-Offline), поэтому «данные показаны» и
// «данные свежие» — разные вещи, и разницу видно в интерфейсе.
let connectionState = { offline: false, cachedAt: '' };

export function offlineInfo() {
  return connectionState;
}

function trackConnection(res) {
  const stale = res.headers.get('X-Kanban-Offline') === '1';
  const next = { offline: stale, cachedAt: stale ? (res.headers.get('X-Kanban-Cached-At') || '') : '' };
  const changed = next.offline !== connectionState.offline || next.cachedAt !== connectionState.cachedAt;
  connectionState = next;
  if (changed) document.dispatchEvent(new CustomEvent('kanban:connection', { detail: next }));
  return res;
}

export async function request(path, options = {}) {
  let res = trackConnection(await send(path, options));
  if (res.status === 401) {
    askForToken();
    throw new Error('нужен токен доступа');
  }
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
  if (!res.ok) {
    if (data && data.offline) throw offlineError(errorMessage(data, res.statusText));
    throw new Error(errorMessage(data, res.statusText));
  }
  return data;
}

// Like request(), but returns the raw Response for blob/streams (attachment
// downloads and previews). The token must stay in a header — never the URL.
export async function requestRaw(path, options = {}) {
  let res = trackConnection(await send(path, options));
  if (res.status === 401) {
    askForToken();
    throw new Error('нужен токен доступа');
  }
  if (!res.ok) {
    const text = await res.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
    throw new Error(errorMessage(data, res.statusText));
  }
  return res;
}

async function send(path, options) {
  const headers = { ...(options.headers || {}), ...tokenHeaders() };
  let body = options.body;
  if (body && typeof body !== 'string' && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(body);
  }
  return fetch(path, { ...options, headers, body }).catch(err => {
    // fetch отклоняется только на сетевом уровне (обрыв, офлайн, DNS):
    // HTTP-статусы приходят обычным Response и разбираются выше.
    throw offlineError(err && err.message);
  });
}

function boardQuery(board, extra = {}) {
  const clean = { ...extra };
  if (board) clean.board = board;
  return new URLSearchParams(clean).toString();
}

export const api = {
  health: () => request('/health'),
  status: () => request('/api/service/status'),
  appUpdateStatus: () => request('/api/app/update-status'),
  applyAppUpdate: () => request('/api/app/update', { method: 'POST' }),
  config: () => request('/api/config'),
  opsSummary: (board, recentLimit = 20) => request(`/api/ops/summary?${boardQuery(board, { recent_limit: recentLimit })}`),
  boards: () => request('/api/boards'),
  createBoard: payload => request('/api/boards', { method: 'POST', body: payload }),
  switchBoard: slug => request(`/api/boards/${encodeURIComponent(slug)}/switch`, { method: 'POST' }),
  createWorkflowDraft: (board, payload) => request(`/api/workflows/drafts?${boardQuery(board)}`, { method: 'POST', body: payload }),
  getWorkflowDraft: (board, draftId) => request(`/api/workflows/drafts/${encodeURIComponent(draftId)}?${boardQuery(board)}`),
  reviseWorkflowDraft: (board, draftId, payload) => request(`/api/workflows/drafts/${encodeURIComponent(draftId)}/revise?${boardQuery(board)}`, { method: 'POST', body: payload }),
  instantiateWorkflowDraft: (board, draftId, payload = {}) => request(`/api/workflows/drafts/${encodeURIComponent(draftId)}/instantiate?${boardQuery(board)}`, { method: 'POST', body: payload }),
  workflowInstance: (board, instanceId) => request(`/api/workflows/instances/${encodeURIComponent(instanceId)}?${boardQuery(board)}`),
  list: params => {
    const clean = {};
    for (const [key, value] of Object.entries(params || {})) {
      if (value !== undefined && value !== null && value !== '') clean[key] = value;
    }
    const query = new URLSearchParams(clean).toString();
    return request(query ? `/api/list?${query}` : '/api/list');
  },
  log: params => {
    const clean = {};
    for (const [key, value] of Object.entries(params || {})) {
      if (value !== undefined && value !== null && value !== '') clean[key] = value;
    }
    const query = new URLSearchParams(clean).toString();
    return request(query ? `/api/log?${query}` : '/api/log');
  },
  logEvents: params => {
    const clean = {};
    for (const [key, value] of Object.entries(params || {})) {
      if (value !== undefined && value !== null && value !== '') clean[key] = value;
    }
    const query = new URLSearchParams(clean).toString();
    return request(query ? `/api/log/events?${query}` : '/api/log/events');
  },
  board: params => {
    const clean = {};
    for (const [key, value] of Object.entries(params || {})) {
      if (value !== undefined && value !== null && value !== '') clean[key] = value;
    }
    const query = new URLSearchParams(clean).toString();
    return request(query ? `/api/board?${query}` : '/api/board');
  },
  createTask: (board, payload) => request(`/api/tasks?${new URLSearchParams({ board })}`, { method: 'POST', body: payload }),
  bulkCreate: (board, payload) => request(`/api/tasks/bulk-create?${new URLSearchParams({ board })}`, { method: 'POST', body: payload }),
  task: (board, id) => request(`/api/tasks/${encodeURIComponent(id)}?${new URLSearchParams({ board })}`),
  attachments: (board, id) => request(`/api/tasks/${encodeURIComponent(id)}/attachments?${boardQuery(board)}`),
  attachmentRaw: (board, id, attachmentId) => requestRaw(`/api/tasks/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}?${boardQuery(board)}`),
  uploadAttachment: (board, id, formData) => request(`/api/tasks/${encodeURIComponent(id)}/attachments?${boardQuery(board)}`, { method: 'POST', body: formData }),
  updateTask: (board, id, payload) => request(`/api/tasks/${encodeURIComponent(id)}?${new URLSearchParams({ board })}`, { method: 'PATCH', body: payload }),
  comment: (board, id, payload) => request(`/api/tasks/${encodeURIComponent(id)}/comments?${new URLSearchParams({ board })}`, { method: 'POST' , body: payload }),
  linkTask: (board, payload) => request(`/api/links?${new URLSearchParams({ board })}`, { method: 'POST', body: payload }),
  unlinkTask: (board, parentId, childId) => request(`/api/links?${new URLSearchParams({ board, parent_id: parentId, child_id: childId })}`, { method: 'DELETE' }),
  taskLog: (board, id, tail = 100000) => request(`/api/tasks/${encodeURIComponent(id)}/log?${new URLSearchParams({ board, tail })}`),
  homeChannels: (board, id) => request(`/api/home-channels?${new URLSearchParams({ board, task_id: id })}`),
  subscribeHome: (board, id, platform) => request(`/api/tasks/${encodeURIComponent(id)}/home-subscribe/${encodeURIComponent(platform)}?${new URLSearchParams({ board })}`, { method: 'POST' }),
  unsubscribeHome: (board, id, platform) => request(`/api/tasks/${encodeURIComponent(id)}/home-subscribe/${encodeURIComponent(platform)}?${new URLSearchParams({ board })}`, { method: 'DELETE' }),
  monitor: (board, id) => request(`/api/tasks/${encodeURIComponent(id)}/monitor?${new URLSearchParams({ board, tail: 65536 })}`),
  events: (board, since = 0) => request(`/api/events?${new URLSearchParams({ board, since })}`),
  pulse: (board, tasks) => request(`/api/pulse?${new URLSearchParams({ board, tasks })}`)
};
