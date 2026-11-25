// Web-push на телефон (спека §10.2).
//
// Подписка — только по жесту: Notification.requestPermission() из обработчика
// клика. Браузер запоминает отказ навсегда, поэтому просить разрешение на
// загрузке страницы нельзя.
//
// Состояние показывается явно, тремя разными фразами:
//
//   включены            — подписка есть и на сервере, пуши придут;
//   запрещены в браузере — Notification.permission === 'denied', кнопки нет:
//                          разрешение возвращается только в настройках сайта;
//   не поддерживается    — нет PushManager / service worker / HTTPS.
//
// Кнопка живёт в панели «Ещё» рядом с «Установить».

import { request } from './api.js?v=20261125-1';
import { applyI18n, t } from './i18n.js?v=20261125-1';
import { toast } from './state.js?v=20261125-1';

const STATES = {
  on: 'pushOn',
  off: 'pushOff',
  denied: 'pushDenied',
  unsupported: 'pushUnsupported'
};

function supported() {
  return typeof window !== 'undefined'
    && window.isSecureContext
    && 'serviceWorker' in navigator
    && 'PushManager' in window
    && 'Notification' in window;
}

// applicationServerKey ждёт Uint8Array, сервер отдаёт base64url без паддинга.
function base64UrlToBytes(value) {
  const padded = value + '='.repeat((4 - (value.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

async function registration() {
  if (!('serviceWorker' in navigator)) return null;
  try {
    return await navigator.serviceWorker.ready;
  } catch {
    return null;
  }
}

async function currentSubscription() {
  const reg = await registration();
  if (!reg || !reg.pushManager) return null;
  return reg.pushManager.getSubscription();
}

async function postSubscription(subscription) {
  const json = subscription.toJSON();
  await request('/api/push/subscribe', {
    method: 'POST',
    body: { endpoint: json.endpoint, keys: json.keys, ua: navigator.userAgent }
  });
}

async function subscribe() {
  const permission = Notification.permission === 'granted'
    ? 'granted'
    : await Notification.requestPermission();
  if (permission !== 'granted') return null;

  const reg = await registration();
  if (!reg || !reg.pushManager) return null;

  const { public_key: publicKey } = await request('/api/push/key');
  // Старую подписку снимаем: после перегенерации VAPID-пары ключ в ней
  // не совпадает с серверным, и FCM отвечает 403 на каждую отправку.
  const existing = await reg.pushManager.getSubscription();
  if (existing) await existing.unsubscribe();

  const subscription = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: base64UrlToBytes(publicKey)
  });
  await postSubscription(subscription);
  return subscription;
}

async function unsubscribe(subscription) {
  const endpoint = subscription.endpoint;
  await subscription.unsubscribe();
  await request('/api/push/subscribe', { method: 'DELETE', body: { endpoint } });
}

function setState(stateEl, key) {
  stateEl.hidden = false;
  stateEl.dataset.i18n = key;
  stateEl.textContent = t(key);
}

async function render(button, stateEl) {
  if (!supported()) {
    button.hidden = true;
    setState(stateEl, STATES.unsupported);
    return;
  }
  if (Notification.permission === 'denied') {
    // Разрешение отсюда не вернуть: браузер запоминает отказ.
    button.hidden = true;
    setState(stateEl, STATES.denied);
    return;
  }
  const subscription = await currentSubscription();
  button.hidden = false;
  button.dataset.i18n = subscription ? 'pushDisable' : 'pushEnable';
  button.textContent = t(button.dataset.i18n);
  setState(stateEl, subscription ? STATES.on : STATES.off);
  applyI18n();
}

// Тихая сверка с сервером: если подписка в браузере есть (например, push.db
// пересоздали), отправляем её заново — иначе пуши молча не приходят.
async function syncExisting() {
  if (!supported() || Notification.permission !== 'granted') return;
  const subscription = await currentSubscription();
  if (!subscription) return;
  try {
    await postSubscription(subscription);
  } catch (err) {
    console.warn('[push] подписка не подтверждена на сервере', err);
  }
}

export function setupPush() {
  const button = document.getElementById('pushBtn');
  const stateEl = document.getElementById('pushState');
  if (!button || !stateEl) return;
  if (!supported()) {
    render(button, stateEl);
    return;
  }

  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const subscription = await currentSubscription();
      if (subscription) {
        await unsubscribe(subscription);
      } else {
        const created = await subscribe();
        if (!created) setState(stateEl, STATES.denied);
      }
    } catch (err) {
      toast(err && err.message ? err.message : String(err), 'error');
    } finally {
      button.disabled = false;
      await render(button, stateEl);
    }
  });

  render(button, stateEl);
  syncExisting();
}

// Экспорт для проб: в браузере состояние видно по data-i18n у #pushState.
export const _internals = { supported, base64UrlToBytes, currentSubscription };
