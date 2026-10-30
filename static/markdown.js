// Мини-markdown для тела задачи: заголовки, списки, код, ссылки, абзацы.
// Вход всегда экранируется ПЕРВЫМ (escapeHtml), поэтому разметку строит только
// этот модуль, а пользовательский текст не может протащить свой HTML.

export function escapeHtml(value = '') {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

// Открывающий/закрывающий тег на каждый уровень: `#` — самый крупный (h2),
// дальше по одному уровню вниз; поле задачи — не документ, h1 не нужен.
const HEADINGS = [
  ['<h2>', '</h2>'],
  ['<h3>', '</h3>'],
  ['<h4>', '</h4>'],
  ['<h5>', '</h5>'],
  ['<h6>', '</h6>'],
];

const CODE_TOKEN = '\u0000';
const FENCE = /^\s*```/;
const HEADING = /^(#{1,6})\s+(.*)$/;
const BULLET = /^\s*[-*+]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;

// Инлайн-разметка. Код вынимается в плейсхолдеры, иначе `**` внутри
// `code` превратился бы в <strong> и содержимое команды было бы испорчено.
function inline(value) {
  const codes = [];
  let out = value.replace(/`([^`]+)`/g, (_, code) => {
    codes.push(`<code>${code}</code>`);
    return `${CODE_TOKEN}${codes.length - 1}${CODE_TOKEN}`;
  });
  out = out
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2" rel="noopener" target="_blank">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
  return out.replace(new RegExp(`${CODE_TOKEN}(\\d+)${CODE_TOKEN}`, 'g'), (_, index) => codes[Number(index)]);
}

export function renderMarkdown(value = '') {
  const lines = escapeHtml(value).split(/\r?\n/);
  const out = [];
  let list = null;
  let fence = null;

  const closeList = () => {
    if (!list) return;
    out.push(`</${list}>`);
    list = null;
  };
  const openList = kind => {
    if (list === kind) return;
    closeList();
    out.push(`<${kind}>`);
    list = kind;
  };

  for (const line of lines) {
    if (fence) {
      if (FENCE.test(line)) {
        out.push(`<pre><code>${fence.join('\n')}</code></pre>`);
        fence = null;
      } else {
        fence.push(line);
      }
      continue;
    }
    if (FENCE.test(line)) {
      closeList();
      fence = [];
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      closeList();
      const level = Math.min(heading[1].length, HEADINGS.length) - 1;
      const [open, close] = HEADINGS[level];
      out.push(`${open}${inline(heading[2].trim())}${close}`);
      continue;
    }
    const bullet = BULLET.exec(line);
    if (bullet) {
      openList('ul');
      out.push(`<li>${inline(bullet[1])}</li>`);
      continue;
    }
    const numbered = NUMBERED.exec(line);
    if (numbered) {
      openList('ol');
      out.push(`<li>${inline(numbered[1])}</li>`);
      continue;
    }
    if (!line.trim()) {
      closeList();
      continue;
    }
    closeList();
    out.push(`<p>${inline(line)}</p>`);
  }

  closeList();
  if (fence) out.push(`<pre><code>${fence.join('\n')}</code></pre>`);
  return out.join('\n');
}
