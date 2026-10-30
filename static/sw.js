// Service worker KanbanWebUI: офлайн-оболочка и фундамент под web-push.
//
// Оболочка (index.html, ES-модули, стили, иконки) лежит в кэше, в имени
// которого стоит токен версии. Новая версия — новый кэш, старый удаляется на
// activate. Токен общий с index.html (?v=…): если разъедутся, браузер будет
// искать в кэше другие URL и офлайн покажет пустоту, поэтому равенство
// проверяет tests/test_pwa.py.
//
// Стратегии:
//   /api/*       network-first: свежие данные важнее, при обрыве — кэш, иначе
//                503 {"offline": true} (страница рисует «нет сети · Повторить»)
//   /static/*    cache-first: ассеты неизменяемы в пределах версии
//   навигация    network-first, при обрыве — оболочка из кэша
//
// skipWaiting только по сообщению со страницы: обновление не должно
// перезагружать интерфейс из-под пальца, баннер показывает update.js.

const VERSION = '20261030-9';
const CACHE = `kanban-${VERSION}`;
const ASSET_QUERY = `?v=${VERSION}`;

// Весь ES-модульный граф приложения: без любого из файлов SPA не загрузится
// офлайн. Список должен совпадать с static/*.js — это проверяет test_pwa.py.
const MODULES = [
  'api.js',
  'app.js',
  'board.js',
  'dependency-lines.js',
  'dragdrop.js',
  'drawer.js',
  'duration.js',
  'feed.js',
  'forms.js',
  'i18n.js',
  'list.js',
  'log.js',
  'markdown.js',
  'mobile.js',
  'monitor.js',
  'now.js',
  'operations.js',
  'pulse.js',
  'pwa.js',
  'push.js',
  'state.js',
  'theme.js',
  'update.js'
];

const STYLES = ['design-tokens.css', 'style.css'];

const ICONS = [
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon-maskable-512.png',
  '/static/icons/apple-touch-icon-180.png'
];

const SHELL = [
  '/',
  '/manifest.webmanifest',
  ...STYLES.map(name => `/static/${name}${ASSET_QUERY}`),
  ...MODULES.map(name => `/static/${name}${ASSET_QUERY}`),
  ...ICONS
];

const OFFLINE_HTML = '<!doctype html><html lang="ru"><meta charset="utf-8">'
  + '<title>Hermes Kanban</title><body style="background:#0b0c0e;color:#e6e8eb;'
  + 'font:14px system-ui,sans-serif;padding:24px">Оболочка не в кэше. '
  + 'Откройте страницу при связи с сервером.</body></html>';

self.addEventListener('install', event => {
  event.waitUntil(precache());
});

async function precache() {
  const cache = await caches.open(CACHE);
  // По одному: cache.addAll падает целиком, если хоть один ассет отдал не 200,
  // и тогда офлайн-оболочка не соберётся вообще.
  await Promise.all(SHELL.map(async url => {
    try {
      await cache.add(new Request(url, { cache: 'reload' }));
    } catch (err) {
      console.warn('[sw] ассет не попал в кэш', url, err);
    }
  }));
}

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener('message', event => {
  const data = event.data || {};
  if (data.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.cache === 'only-if-cached' && request.mode !== 'same-origin') return;

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstApi(request));
    return;
  }
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(request));
    return;
  }
  if (request.mode === 'navigate') {
    event.respondWith(networkFirstShell(request));
  }
});

function offlineJson() {
  return new Response(JSON.stringify({ offline: true }), {
    status: 503,
    statusText: 'Offline',
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }
  });
}

async function networkFirstApi(request) {
  const cache = await caches.open(CACHE);
  try {
    const response = await fetch(request);
    if (response && response.ok && response.type === 'basic') {
      await cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    // Кэш — не замена правде: отдаём последний ответ, но помечаем его
    // заголовком X-Kanban-Offline, и страница показывает «нет сети · данные от
    // HH:MM · Повторить» (см. api.js). Молча отдать вчерашнюю доску как
    // свежую — ровно та ложь, которую этот экран не должен говорить.
    const cached = await cache.match(request);
    if (cached) return markedStale(cached);
    // Пустой кэш (первый заход был офлайн) — честный 503, а не пустой JSON.
    return offlineJson();
  }
}

// Копия закэшированного ответа с меткой «это из кэша» и исходным временем.
async function markedStale(response) {
  const headers = new Headers(response.headers);
  headers.set('X-Kanban-Offline', '1');
  headers.set('X-Kanban-Cached-At', response.headers.get('date') || '');
  const body = await response.blob();
  return new Response(body, { status: response.status, statusText: response.statusText, headers });
}

async function cacheFirst(request) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response && response.ok && response.type === 'basic') {
      await cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    return new Response('', { status: 504, statusText: 'Offline' });
  }
}

async function networkFirstShell(request) {
  try {
    return await fetch(request);
  } catch (err) {
    const cache = await caches.open(CACHE);
    const cached = await cache.match('/');
    if (cached) return cached;
    return new Response(OFFLINE_HTML, {
      status: 503,
      headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' }
    });
  }
}

// web-push (§10.1–10.2): пейлоад собирает scripts/push_notifier.py — заголовок
// задачи в тексте по умолчанию не идёт (виден на локскрине), тап открывает
// карточку по /#task=<id>.
self.addEventListener('push', event => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (err) {
    payload = { body: event.data ? event.data.text() : '' };
  }
  const taskId = payload.task_id || '';
  const target = payload.url || (taskId ? `/#task=${taskId}` : '/#view=now');
  event.waitUntil(self.registration.showNotification(payload.title || 'Kanban', {
    body: payload.body || '',
    tag: payload.tag || (taskId ? `task:${taskId}` : undefined),
    icon: '/static/icons/icon-192.png',
    data: { url: target, task_id: taskId }
  }));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const data = event.notification.data || {};
  const target = new URL(data.url || (data.task_id ? `/#task=${data.task_id}` : '/#view=now'),
                         self.location.origin).href;
  event.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    const focused = all.find(client => client.url.startsWith(self.location.origin + '/'));
    if (focused) {
      await focused.focus();
      if ('navigate' in focused) await focused.navigate(target);
      return;
    }
    await self.clients.openWindow(target);
  })());
});