import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.ui import compile_ui

js = (ROOT / 'templates/frontend/markdown.js.j2').read_text(encoding='utf-8')
probe = r'''
const assert = require('assert');
let x = markdown('# Heading\n\nParagraph **bold** `a < b & c`\n\n- one\n- two\n\n```python\n  print("<>&|")  \n```');
assert(x.includes('<h1>Heading</h1>'));
assert(x.includes('<strong>bold</strong>'));
assert(x.includes('<code>a &lt; b &amp; c</code>'));
assert(x.includes('<ul><li>one</li><li>two</li></ul>'));
assert(markdown('1. first\n2. second').includes('<ol><li>first</li><li>second</li></ol>'));
assert(x.includes('<pre><code>  print(&quot;&lt;&gt;&amp;|&quot;)  \n</code></pre>'));
x = markdown('<script>alert(1)</script>\n<img src=x onerror=alert(1)>\n[x](javascript:alert(1))');
assert(!x.includes('<script>') && !x.includes('<img') && !x.includes('<a '));
assert(x.includes('&lt;script&gt;') && x.includes('&lt;img'));
assert(markdown('```\n<script>\n```').includes('<pre><code>&lt;script&gt;\n</code></pre>'));
console.log('Markdown 9 assertions passed');
'''
subprocess.run(['node', '-e', js + probe], check=True)
r = compile_ui('界面 自定义 页面\n  显示 reading.explanation 正文 Markdown\n结束\n', options={'i18n_langs':['ja']})
files = r['result']['files']
assert 'v-html="markdown(' in files['app.js']
assert 'closest(".markdown code")' in files['app.js']
assert 'function markdown(value)' in files['app.js']
print('UI opt-in and i18n code exclusion: 3 assertions passed')
