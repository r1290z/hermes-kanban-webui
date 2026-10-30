import { api } from './api.js?v=20261030-9';
import { state, toast } from './state.js?v=20261030-9';
import { t } from './i18n.js?v=20261030-9';

// Moving a card is the one thing you do constantly on a phone, and drag-and-drop
// needs a mouse: touch never fires dragover, so the board had no working move at all.
// Long-press a card and pick the target column from a sheet instead of a text prompt.
const MOVE_STATUSES = ['scheduled', 'triage', 'todo', 'ready', 'blocked', 'done', 'archived'];
const PHONE_QUERY = '(max-width: 760px)';

export function isPhoneLayout() {
  return matchMedia(PHONE_QUERY).matches;
}

function closeSheet() {
  document.getElementById('moveSheet')?.remove();
}

function openMoveSheet(card) {
  closeSheet();
  const taskId = card.dataset.taskId;
  const current = (card.className.match(/\b(scheduled|triage|todo|ready|running|blocked|done|archived)\b/) || [])[1];

  const sheet = document.createElement('div');
  sheet.id = 'moveSheet';
  sheet.innerHTML = `
    <style>
      #moveSheet{position:fixed;inset:0;z-index:9998;display:flex;align-items:flex-end;
        background:rgba(8,10,18,.5)}
      #moveSheet .sheet{width:100%;background:var(--surface,#fff);border-radius:var(--r-md,8px) var(--r-md,8px) 0 0;
        padding:16px 14px calc(16px + env(safe-area-inset-bottom));
        font-family:inherit;color:var(--ink,#111);box-shadow:var(--shadow-overlay)}
      #moveSheet h4{margin:0 0 4px;font-size:15px}
      #moveSheet code{font-size:12px;opacity:.6}
      #moveSheet .grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0 10px}
      #moveSheet button{padding:12px 10px;border-radius:var(--r-sm,5px);border:1px solid var(--line,#ddd);
        background:var(--surface-2,#f6f7f9);color:var(--ink,inherit);font:inherit;font-weight:600;
        font-size:14px;cursor:pointer}
      #moveSheet button.is-current{outline:2px solid var(--run,#111);opacity:.55}
      #moveSheet .cancel{width:100%;background:transparent;font-weight:500}
    </style>
    <div class="sheet">
      <h4>${t('moveTask')}</h4>
      <code>${taskId}</code>
      <div class="grid">
        ${MOVE_STATUSES.map(s => `<button data-status="${s}" class="${s === current ? 'is-current' : ''}">${t(s)}</button>`).join('')}
      </div>
      <button class="cancel" data-cancel>${t('cancel')}</button>
    </div>`;

  sheet.addEventListener('click', async ev => {
    if (ev.target === sheet || ev.target.hasAttribute('data-cancel')) {
      closeSheet();
      return;
    }
    const button = ev.target.closest('button[data-status]');
    if (!button) return;
    const status = button.dataset.status;
    closeSheet();
    try {
      await api.updateTask(state.board, taskId, { status });
      toast(`${t('moved')} → ${t(status)}`);
      document.dispatchEvent(new CustomEvent('kanban:refresh'));
    } catch (err) {
      toast(err.message || String(err), 'error');
    }
  });

  document.body.appendChild(sheet);
}

// Телефонная раскладка включается классами, а не только медиазапросом: вкладки
// уезжают вниз фиксированной полосой, drawer становится полноэкранным листом.
// Классы снимаются при возврате к десктопной ширине, поэтому одна и та же
// страница обслуживает обе раскладки без перезагрузки.
function applyPhoneLayout() {
  const phone = isPhoneLayout();
  document.documentElement.classList.toggle('is-phone', phone);
  const tabs = document.querySelector('.tabs');
  if (tabs) tabs.classList.toggle('tabs-bottom', phone);
  const drawer = document.getElementById('drawer');
  if (drawer) drawer.classList.toggle('drawer-phone', phone && drawer.classList.contains('open'));
  if (!phone) document.body.classList.remove('drawer-open');
}

export function setupMobileShell() {
  applyPhoneLayout();
  const media = window.matchMedia(PHONE_QUERY);
  if (media.addEventListener) media.addEventListener('change', applyPhoneLayout);
  else media.addListener(applyPhoneLayout);
  window.addEventListener('orientationchange', applyPhoneLayout);
  window.addEventListener('resize', applyPhoneLayout);
  // Полноэкранный лист перекрывает страницу целиком: фон не должен скроллиться
  // под ним, иначе палец на карточке уводит саму карточку.
  document.addEventListener('kanban:drawer-open', () => {
    if (isPhoneLayout()) document.body.classList.add('drawer-open');
  });
  document.addEventListener('kanban:drawer-close', () => {
    document.body.classList.remove('drawer-open');
  });
}

export function setupMobileFallback() {
  // Long-press surfaces as contextmenu on touch; the mouse path keeps working too.
  document.addEventListener('contextmenu', ev => {
    const card = ev.target.closest?.('.task-card');
    if (!card || !isPhoneLayout()) return;
    ev.preventDefault();
    openMoveSheet(card);
  });
  document.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') closeSheet();
  });
}
