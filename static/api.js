function tokenHeaders() {
  const token = localStorage.getItem('kanbanToken');
  return token ? { 'X-Kanban-Token': token } : {};
}

function errorMessage(data, fallback) {
  const message = data.detail || data.error || fallback;
  if (Array.isArray(message)) return message.map(x => x.msg || JSON.stringify(x)).join(', ');
  if (message && typeof message === 'object') return JSON.stringify(message);
  return message;
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
        justify-content:center;background:rgba(8,10,18,.82);backdrop-filter:blur(3px)}
      #tokenBar .box{background:var(--card,#151a26);border:1px solid var(--border,#2a3244);
        border-radius:14px;padding:26px 28px;max-width:420px;width:calc(100% - 40px);
        font-family:inherit;color:var(--foreground,#e8ecf4);box-shadow:0 24px 60px rgba(0,0,0,.45)}
      #tokenBar h3{margin:0 0 6px;font-size:17px}
      #tokenBar p{margin:0 0 16px;font-size:13px;opacity:.7;line-height:1.5}
      #tokenBar input{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:9px;
        border:1px solid var(--border,#2a3244);background:rgba(0,0,0,.25);
        color:inherit;font:inherit;font-size:14px}
      #tokenBar button{margin-top:12px;width:100%;padding:10px;border-radius:9px;border:0;
        background:#3b82f6;color:#fff;font:inherit;font-weight:600;cursor:pointer}
      #tokenBar .err{margin-top:10px;font-size:12px;color:#f87171;min-height:1em}
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

export async function request(path, options = {}) {
  let res = await send(path, options);
  if (res.status === 401) {
    askForToken();
    throw new Error('нужен токен доступа');
  }
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
  if (!res.ok) throw new Error(errorMessage(data, res.statusText));
  return data;
}

async function send(path, options) {
  const headers = { ...(options.headers || {}), ...tokenHeaders() };
  let body = options.body;
  if (body && typeof body !== 'string' && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(body);
  }
  return fetch(path, { ...options, headers, body });
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
  updateTask: (board, id, payload) => request(`/api/tasks/${encodeURIComponent(id)}?${new URLSearchParams({ board })}`, { method: 'PATCH', body: payload }),
  comment: (board, id, payload) => request(`/api/tasks/${encodeURIComponent(id)}/comments?${new URLSearchParams({ board })}`, { method: 'POST' , body: payload }),
  linkTask: (board, payload) => request(`/api/links?${new URLSearchParams({ board })}`, { method: 'POST', body: payload }),
  unlinkTask: (board, parentId, childId) => request(`/api/links?${new URLSearchParams({ board, parent_id: parentId, child_id: childId })}`, { method: 'DELETE' }),
  taskLog: (board, id, tail = 100000) => request(`/api/tasks/${encodeURIComponent(id)}/log?${new URLSearchParams({ board, tail })}`),
  homeChannels: (board, id) => request(`/api/home-channels?${new URLSearchParams({ board, task_id: id })}`),
  subscribeHome: (board, id, platform) => request(`/api/tasks/${encodeURIComponent(id)}/home-subscribe/${encodeURIComponent(platform)}?${new URLSearchParams({ board })}`, { method: 'POST' }),
  unsubscribeHome: (board, id, platform) => request(`/api/tasks/${encodeURIComponent(id)}/home-subscribe/${encodeURIComponent(platform)}?${new URLSearchParams({ board })}`, { method: 'DELETE' }),
  monitor: (board, id) => request(`/api/tasks/${encodeURIComponent(id)}/monitor?${new URLSearchParams({ board, tail: 65536 })}`),
  events: (board, since = 0) => request(`/api/events?${new URLSearchParams({ board, since })}`)
};
