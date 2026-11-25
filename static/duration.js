// Single home for human-readable duration formatting ("12 с", "4 мин 05 с",
// "2 ч 05 мин"). Units come from i18n so the same function reads naturally in
// RU/EN/KO — no per-view copies.
import { t } from './i18n.js?v=20261125-1';

export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return '—';
  const total = Math.max(0, Math.round(Number(seconds)));
  if (total < 60) return `${total} ${t('unitSec')}`;
  if (total < 3600) {
    const minutes = Math.floor(total / 60);
    const rest = total % 60;
    return `${minutes} ${t('unitMin')} ${String(rest).padStart(2, '0')} ${t('unitSec')}`;
  }
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return `${hours} ${t('unitHour')} ${String(minutes).padStart(2, '0')} ${t('unitMin')}`;
}

// Coarse variant for the "going for X" pulse line: "12 с", "4 мин", "2 ч 05 мин".
export function formatDurationCoarse(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return '—';
  const total = Math.max(0, Math.round(Number(seconds)));
  if (total < 60) return `${total} ${t('unitSec')}`;
  if (total < 3600) return `${Math.floor(total / 60)} ${t('unitMin')}`;
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return `${hours} ${t('unitHour')} ${String(minutes).padStart(2, '0')} ${t('unitMin')}`;
}

// Clock for the run pult: "27:14", "1:05:07" — the elapsed column must line up
// under the limit ("60 мин") the way the spec draws it, so no unit words here.
export function formatClock(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return '—';
  const total = Math.max(0, Math.floor(Number(seconds)));
  const pad = value => String(value).padStart(2, '0');
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(rest)}` : `${pad(minutes)}:${pad(rest)}`;
}
