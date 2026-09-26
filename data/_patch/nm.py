import shutil, os, sys, re, subprocess
P = '/home/ysc/mcp'
T = P + '/templates/frontend'
os.makedirs('/tmp/bak8', exist_ok=True)
for f in ['app.js.j2', 'layout.j2', 'style.css.j2']:
    shutil.copy(T + '/' + f, '/tmp/bak8/' + f)

# ---------------------------------------------------------------- app.js.j2
p = T + '/app.js.j2'
s = open(p, encoding='utf-8').read()
old = '    const rowsOf = name => lists.value[name] || [];'
new = '''    // 列表的数据：先看后端返回的 lists 里这个键有没有数据；没有就把键当成共享
    // 状态的路径去读。节点图详情浮层里的「列表 包含 绑 sel.points」读的就是
    // 选中节点身上的数组——那份数据跟着节点来，不走 lists。
    // lists 优先：两边都有时，接口明确给的那份算数。
    const rowsOf = name => {
      const v = lists.value[name];
      if (v && v.length) return v;
      if (typeof shared !== 'undefined') {
        const w = name.split('.').reduce((o, k) => (o == null ? o : o[k]), shared.value);
        if (Array.isArray(w)) return w;
      }
      return v || [];
    };'''
if 'typeof shared !== \'undefined\') {\n        const w = name.split' not in s:
    assert s.count(old) == 1, 'rowsOf 命中 %d' % s.count(old)
    s = s.replace(old, new)
    open(p, 'w', encoding='utf-8').write(s)
    print('app: rowsOf 支持共享路径')

# ---------------------------------------------------------------- layout.j2
p = T + '/layout.j2'
s = open(p, encoding='utf-8').read()
old = '<tr v-for="(row, i) in rowsOf(\'<%= node.bind or node.name %>\')" :key="i">'
new = '<tr v-for="(row, i) in rowsOf(\'<%= node.bind or node.name %>\')" :key="i" :class="row.state ? \'row-\' + row.state : \'\'">'
if "'row-' + row.state" not in s:
    assert s.count(old) == 1, 'layout 列表行命中 %d' % s.count(old)
    s = s.replace(old, new)
    open(p, 'w', encoding='utf-8').write(s)
    print('layout: 列表行按 state 加 class')

# ---------------------------------------------------------------- style.css.j2
p = T + '/style.css.j2'
s = open(p, encoding='utf-8').read()
if '.row-done' not in s:
    s = s.rstrip('\n') + '''

/* 列表行按 state 上色，跟节点图同一套状态：已掌握 / 可学 / 锁定 */
tr.row-done td { color:#4a7a8c; font-weight:600; }
tr.row-open td { color:var(--ink); }
tr.row-locked td { opacity:.55; }
.overlay-box table { margin:4px 0; }
'''
    open(p, 'w', encoding='utf-8').write(s)
    print('style: 行状态样式')

# ---------------------------------------------------------------- 验证
sys.path.insert(0, P)
from tools.ui import compile_ui
ok = True
UI = '''界面 自定义 学习路径
  分组 图区 竖排 占满
    节点图 kg 绑 graph 选中 sel 点开 节点详情 高 640px 方向 纵向
  结束
  浮层 节点详情 宽 480px
    显示 sel.label
    显示 sel.desc 当 shared.sel&&shared.sel.desc
    列表 包含 绑 sel.points 当 shared.sel&&shared.sel.points&&shared.sel.points.length
      列 label 知识点
      列 state 状态
    结束
    动作 收起 次要 关闭 收起
  结束
结束
'''
r = compile_ui(UI, backend='vue', options={'title': '学习路径'})
iss = [str(i) for i in r['issues']]
print('ISSUES:', iss or '无')
js = r['result']['files']['app.js']
os.makedirs('/tmp/g', exist_ok=True)
open('/tmp/g/l.js', 'w', encoding='utf-8').write(js)
c1 = "rowsOf('sel.points')" in js
c2 = 'const w = name.split' in js
c3 = "'row-' + row.state" in js
c4 = 'v-if="shared.sel&&shared.sel.points&&shared.sel.points.length"' in js
print("rowsOf('sel.points'):", c1, '| 共享回退:', c2, '| 行 class:', c3, '| 空时隐藏:', c4)
ok &= c1 and c2 and c3 and c4
rc = subprocess.run(['node', '--check', '/tmp/g/l.js'], capture_output=True, text=True)
print('node --check:', 'OK' if rc.returncode == 0 else rc.stderr[:300])
ok &= rc.returncode == 0

# 把生成的 rowsOf 抠出来单独跑：lists 为空时读共享路径，lists 有数据时优先 lists
m = re.search(r'(const rowsOf = name => \{.*?\n    \};)', js, re.S)
test = ('const lists = { value: {} };\n'
        'const shared = { value: { sel: { points: [{label:"五段动词",state:"done"},{label:"一段动词",state:"open"}] } } };\n'
        + m.group(1) + '\n'
        'console.log("A 读选中节点:", JSON.stringify(rowsOf("sel.points").map(r => r.label)));\n'
        'shared.value.sel = null;\n'
        'console.log("B 没选中:", JSON.stringify(rowsOf("sel.points")));\n'
        'lists.value["articles"] = [{t:1}];\n'
        'console.log("C lists 优先:", rowsOf("articles").length);\n'
        'console.log("D 都没有:", JSON.stringify(rowsOf("nothing")));\n')
open('/tmp/g/rows.js', 'w', encoding='utf-8').write(test)
rc = subprocess.run(['node', '/tmp/g/rows.js'], capture_output=True, text=True)
out = rc.stdout.strip() or rc.stderr[:300]
print(out)
ok &= '"五段动词","一段动词"' in out and 'B 没选中: []' in out and 'C lists 优先: 1' in out and 'D 都没有: []' in out

print('全部通过:', ok)
if ok:
    files = ['templates/frontend/app.js.j2', 'templates/frontend/layout.j2', 'templates/frontend/style.css.j2']
    subprocess.run(['git', 'add', '--', *files], cwd=P)
    msg = ('列表可读共享路径：节点详情里列出包含的知识点\n\n'
           '- rowsOf 先看 lists，没有数据就把键当共享状态路径读；'
           '「列表 包含 绑 sel.points」读选中节点身上的数组\n'
           '- 列表行按 state 上色（done / open / locked），跟节点图同一套')
    c = subprocess.run(['git', 'commit', '-m', msg], cwd=P, capture_output=True, text=True)
    print('commit:', c.returncode, (c.stdout + c.stderr).strip().splitlines()[:1])
else:
    for f in ['app.js.j2', 'layout.j2', 'style.css.j2']:
        shutil.copy('/tmp/bak8/' + f, T + '/' + f)
    print('有检查没过，已恢复，不提交')
