// Проверка темы без браузера: theme.js разбирается как классический скрипт
// (единственный импорт — i18n — заменяется заглушкой), localStorage и
// matchMedia подменяются. Печатает JSON с результатом resolveTheme()/applyTheme().
//
// Использование: node tests/helpers/theme_probe.js static/theme.js
const fs = require('fs');
const vm = require('vm');

const file = process.argv[2];
if (!file) {
  process.stderr.write('usage: node theme_probe.js <static/theme.js>\n');
  process.exit(2);
}

let src = fs.readFileSync(file, 'utf8');
src = src.replace(/^import .*$/gm, 'const t = (key) => key;').replace(/^export /gm, '');

const store = {};
const ctx = {
  localStorage: {
    getItem: (key) => (key in store ? store[key] : null),
    setItem: (key, value) => { store[key] = String(value); },
  },
  // Светлая системная схема: дефолт всё равно обязан быть тёмным.
  window: { matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }) },
  document: { documentElement: { dataset: {}, style: {} }, getElementById: () => null },
  console,
};
vm.createContext(ctx);
vm.runInContext(src, ctx, { filename: file });

const result = {
  resolved: vm.runInContext('resolveTheme()', ctx),
  applied: vm.runInContext('applyTheme()', ctx),
  dataset: vm.runInContext('document.documentElement.dataset.theme', ctx),
  colorScheme: vm.runInContext('document.documentElement.style.colorScheme', ctx),
};
// Сохранённый выбор остаётся главнее дефолта.
store.kanbanTheme = 'light';
result.storedLight = vm.runInContext('applyTheme()', ctx);
store.kanbanTheme = 'system';
result.systemChoice = vm.runInContext('resolveTheme()', ctx);

process.stdout.write(JSON.stringify(result));