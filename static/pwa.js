// PWA-обвязка (спека §10): регистрация service worker, кнопка «Установить»
// по beforeinstallprompt и одноразовая подсказка на iOS.
//
// Регистрация асинхронная и «тихая»: если она не удалась (нет HTTPS, старый
// браузер), приложение продолжает работать как обычный сайт.

const IOS_HINT_KEY = 'kanbanIosInstallHintShown';
const UPDATE_CHECK_MS = 15 * 60 * 1000;

let installPrompt = null;

function isStandalone() {
  return window.matchMedia('(display-mode: standalone)').matches
    || window.navigator.standalone === true;
}

// На iOS установка только руками: «Поделиться → На экран „Домой“».
function isIos() {
  const ua = navigator.userAgent || '';
  return /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
}

function setupInstallButton() {
  const button = document.getElementById('installBtn');
  if (!button) return;
  window.addEventListener('beforeinstallprompt', event => {
    // Свой мини-баннер Chrome не показываем: кнопка живёт в панели «Ещё»,
    // чтобы не перекрывать интерфейс на телефоне.
    event.preventDefault();
    installPrompt = event;
    button.hidden = false;
  });
  button.addEventListener('click', async () => {
    if (!installPrompt) return;
    installPrompt.prompt();
    try {
      await installPrompt.userChoice;
    } catch {
      // Пользователь закрыл нативное окно — это не ошибка.
    }
    installPrompt = null;
    button.hidden = true;
  });
  window.addEventListener('appinstalled', () => {
    installPrompt = null;
    button.hidden = true;
  });
}

function maybeShowIosHint() {
  if (!isIos() || isStandalone()) return;
  if (localStorage.getItem(IOS_HINT_KEY)) return;
  const hint = document.getElementById('iosInstallHint');
  if (!hint) return;
  localStorage.setItem(IOS_HINT_KEY, '1');
  hint.hidden = false;
  hint.querySelector('[data-ios-hint-close]')?.addEventListener('click', () => {
    hint.hidden = true;
  });
}

function onNewWorkerAvailable(registration) {
  if (!navigator.serviceWorker.controller) return; // первая установка — не обновление
  if (registration.waiting || registration.installing) {
    document.dispatchEvent(new CustomEvent('kanban:sw-update'));
  }
}

function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  const start = () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(registration => {
      // Новая оболочка уже скачана и ждёт: сообщаем update.js, он показывает
      // баннер и по клику отправляет воркеру SKIP_WAITING.
      if (registration.waiting) {
        document.dispatchEvent(new CustomEvent('kanban:sw-update'));
        return;
      }
      registration.addEventListener('updatefound', () => {
        const installing = registration.installing;
        if (!installing) return;
        installing.addEventListener('statechange', () => {
          if (installing.state === 'installed') onNewWorkerAvailable(registration);
        });
      });
      // Телефон живёт с открытой вкладкой неделями: без этого новая версия не
      // найдётся до полного перезапуска браузера.
      setInterval(() => registration.update().catch(() => {}), UPDATE_CHECK_MS);
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') registration.update().catch(() => {});
      });
    }).catch(err => {
      console.warn('[pwa] service worker не зарегистрирован', err);
    });
  };
  if (document.readyState === 'complete') start();
  else window.addEventListener('load', start);
}

export function setupPwa() {
  setupInstallButton();
  maybeShowIosHint();
  registerServiceWorker();
}
