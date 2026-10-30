"""Карточка задачи: markdown-рендер, порядок блоков, одно предупреждение, deep links.

Проверки markdown не строковые: `markdown.js` реально исполняется в node и
сравнивается разметка, которую он выдаёт. Строковые ассерты по style.css не
держатся здесь специально — контракты раскладки живут в test_static_smoke.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / 'static'

# markdown.js — ES-модуль без package.json type=module, поэтому грузим его через
# data:-URL: node разбирает такой импорт как ESM независимо от окружения.
RUNNER = """
import fs from 'node:fs';
const src = fs.readFileSync(process.argv[1], 'utf8');
const mod = await import('data:text/javascript;base64,' + Buffer.from(src).toString('base64'));
const cases = JSON.parse(process.argv[2]);
const out = {};
for (const [name, input] of Object.entries(cases)) out[name] = mod.renderMarkdown(input);
out.__escape = mod.escapeHtml(`<b>"x"&'y'</b>`);
console.log(JSON.stringify(out));
"""

CASES = {
    'html': '<b>x</b>',
    'headings': '# Один\n## Два\n### Три\n##### Пять\n###### Шесть',
    'bullets': '- один\n- два',
    'numbered': '1. один\n2. два',
    'fence': '```\nls -la <dir>\n```',
    'inline_code': 'запусти `git **status**` сейчас',
    'emphasis': '**жирно** и *курсив*',
    'link': 'см. [доки](https://example.test/a?b=1)',
    'paragraphs': 'первый\n\nвторой',
    'mixed': '## Итог\n\n- `ok`\n- **важно**',
}


@pytest.fixture(scope='module')
def rendered():
    node = shutil.which('node')
    if not node:
        pytest.skip('node is required to execute markdown.js')
    proc = subprocess.run(
        [node, '--input-type=module', '-e', RUNNER, str(STATIC / 'markdown.js'), json.dumps(CASES)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_markdown_escapes_html_first(rendered):
    # текст задачи не может протащить свой тег: сначала escapeHtml, потом разметка
    assert rendered['html'] == '<p>&lt;b&gt;x&lt;/b&gt;</p>'
    assert rendered['__escape'] == '&lt;b&gt;&quot;x&quot;&amp;&#039;y&#039;&lt;/b&gt;'


def test_markdown_supports_headings(rendered):
    """`#`…`#####` сдвигаются на уровень вниз (h2…h6): тело задачи — не документ,
    свой h1 ему не нужен, а шестой уровень упирается в h6."""
    md = rendered['headings']
    assert '<h2>Один</h2>' in md
    assert '<h3>Два</h3>' in md
    assert '<h4>Три</h4>' in md
    assert '<h6>Пять</h6>' in md
    assert '<h6>Шесть</h6>' in md, 'шестой уровень не вылезает за h6'


def test_markdown_supports_lists_and_code_blocks(rendered):
    md = rendered['bullets']
    assert '<ul>' in md and md.count('<li>') == 2
    assert '<ol>' in rendered['numbered'] and rendered['numbered'].count('<li>') == 2
    assert rendered['fence'] == '<pre><code>ls -la &lt;dir&gt;</code></pre>'


def test_inline_code_wins_over_emphasis(rendered):
    md = rendered['inline_code']
    assert '<code>git **status**</code>' in md
    assert '<strong>' not in md


def test_markdown_supports_emphasis_links_paragraphs(rendered):
    md = rendered['emphasis']
    assert '<strong>жирно</strong>' in md and '<em>курсив</em>' in md
    link = rendered['link']
    assert '<a href="https://example.test/a?b=1" rel="noopener" target="_blank">доки</a>' in link
    assert rendered['paragraphs'] == '<p>первый</p>\n<p>второй</p>'
    mixed = rendered['mixed']
    assert mixed.startswith('<h3>Итог</h3>')
    assert '<li><code>ok</code></li>' in mixed and '<li><strong>важно</strong></li>' in mixed


def test_drawer_renders_body_as_markdown():
    drawer = (STATIC / 'drawer.js').read_text(encoding='utf-8')
    assert "import { renderMarkdown, escapeHtml } from './markdown.js" in drawer
    # тело показывается отрендеренным, а в редакторе остаётся исходник
    assert 'renderMarkdown(task.body)' in drawer
    assert 'escapeHtml(task.body ||' in drawer


def test_drawer_single_warning_badge():
    drawer = (STATIC / 'drawer.js').read_text(encoding='utf-8')
    assert drawer.count('profile-missing-badge') == 1


def test_drawer_section_order_matches_spec():
    """Спека §4.5: состояние и исполнитель → заголовок → markdown → действия →
    зависимости → комментарии → вложения → прогоны и события."""
    drawer = (STATIC / 'drawer.js').read_text(encoding='utf-8')
    markers = [
        'id="taskMetaForm"',
        'class="drawer-header drawer-title"',
        'renderMarkdown(task.body)',
        'class="drawer-actions"',
        'data-action="triage"',
        'addParentSelect',
        'id="commentForm"',
        'id="attachmentForm"',
        'id="workerLogContent"',
    ]
    positions = [drawer.index(marker) for marker in markers]
    assert positions == sorted(positions), dict(zip(markers, positions))


def test_deep_link_contract():
    """#task=<id> пишется при открытии карточки и снимается при закрытии."""
    drawer = (STATIC / 'drawer.js').read_text(encoding='utf-8')
    app = (STATIC / 'app.js').read_text(encoding='utf-8')

    assert 'function syncTaskHash(' in drawer
    assert 'history.replaceState(null, \'\', url)' in drawer
    assert "next.push(['task', taskId])" in drawer
    assert 'syncTaskHash(taskId);' in drawer            # openTaskDrawer
    assert 'syncTaskHash(null);' in drawer              # closeDrawer
    # якоря нет — панель сама не открывается; есть — открывается на загрузке
    assert 'function currentTask()' in app
    assert 'openTaskDrawer(task)' in app
    assert "addEventListener('hashchange'" in app


def test_mobile_shell_bottom_tabs_and_fullscreen_drawer():
    mobile = (STATIC / 'mobile.js').read_text(encoding='utf-8')
    app = (STATIC / 'app.js').read_text(encoding='utf-8')
    style = (STATIC / 'style.css').read_text(encoding='utf-8')

    assert 'export function setupMobileShell' in mobile
    assert 'tabs-bottom' in mobile and 'drawer-phone' in mobile
    assert 'setupMobileShell()' in app
    # раскладка включается классами, поэтому правила живут вне медиазапроса
    assert '.tabs.tabs-bottom' in style
    assert '.drawer.drawer-phone' in style
    assert 'env(safe-area-inset-bottom)' in style
    for banned in ['backdrop-filter', 'border-radius: 999px']:
        assert banned not in style