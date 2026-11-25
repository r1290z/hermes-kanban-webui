import { t } from './i18n.js?v=20261125-1';

export const THEME_STORAGE_KEY = 'kanbanTheme';
const DARK_QUERY = '(prefers-color-scheme: dark)';
const VALID_THEMES = new Set(['light', 'dark']);
// Зарезервировано под будущий пункт «как в системе»: в интерфейсе его пока нет,
// но сохранённое значение уже понимается — иначе ветка ниже была бы мертвой.
const SYSTEM_THEME = 'system';
const STORED_THEMES = new Set([...VALID_THEMES, SYSTEM_THEME]);

function mediaQuery() {
  return typeof window.matchMedia === 'function' ? window.matchMedia(DARK_QUERY) : null;
}

export function storedTheme() {
  const value = localStorage.getItem(THEME_STORAGE_KEY);
  return STORED_THEMES.has(value) ? value : null;
}

export function resolveTheme(preference = storedTheme()) {
  if (VALID_THEMES.has(preference)) return preference;
  // Системная схема участвует только при явном выборе «как в системе» (в MVP
  // такого пункта нет). Спека §5.1: основная тема — тёмная, поэтому без
  // сохранённого выбора всегда dark, даже если система светлая.
  if (preference === SYSTEM_THEME) return mediaQuery()?.matches ? 'dark' : 'light';
  return 'dark';
}

export function applyTheme(preference = storedTheme()) {
  const theme = resolveTheme(preference);
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  updateThemeToggleLabel(theme);
  return theme;
}

export function updateThemeToggleLabel(theme = resolveTheme()) {
  const toggle = document.getElementById('themeToggle');
  if (!toggle) return;
  const nextIsDark = theme !== 'dark';
  toggle.textContent = nextIsDark ? t('themeDark') : t('themeLight');
  toggle.setAttribute('aria-label', nextIsDark ? t('themeDark') : t('themeLight'));
  toggle.setAttribute('aria-pressed', String(theme === 'dark'));
}

export function toggleTheme() {
  const current = resolveTheme();
  const next = current === 'dark' ? 'light' : 'dark';
  localStorage.setItem(THEME_STORAGE_KEY, next);
  return applyTheme(next);
}

export function setupThemeToggle() {
  applyTheme();
  const toggle = document.getElementById('themeToggle');
  if (toggle) toggle.addEventListener('click', toggleTheme);

  const query = mediaQuery();
  const onSystemThemeChange = () => {
    // По умолчанию тема фиксирована (dark), поэтому смена системной схемы
    // перерисовывает приложение только при явном выборе «как в системе».
    if (storedTheme() === SYSTEM_THEME) applyTheme();
  };
  if (query?.addEventListener) {
    query.addEventListener('change', onSystemThemeChange);
  } else if (query?.addListener) {
    query.addListener(onSystemThemeChange);
  }
}
