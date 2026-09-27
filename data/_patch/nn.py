import shutil, os, sys, re, subprocess
P = '/home/ysc/mcp'
T = P + '/templates/frontend'
os.makedirs('/tmp/bak9', exist_ok=True)
shutil.copy(P + '/tools/ui.py', '/tmp/bak9/ui.py')
shutil.copy(T + '/app.js.j2', '/tmp/bak9/app.js.j2')

def restore():
    shutil.copy('/tmp/bak9/ui.py', P + '/tools/ui.py')
    shutil.copy('/tmp/bak9/app.js.j2', T + '/app.js.j2')

# ------------------------------------------------------------------ ui.py
# 所有「选中」路径最后再压回 None。浮层里的节点图常常绑在选中节点身上
# （绑 sel.points），前面开槽时会把 sel 建成 {points:{...}}，「当 shared.sel」
# 就恒真了——跟当初「显示 sel.label」是同一个坑。
p = P + '/tools/ui.py'
L = open(p, encoding='utf-8').read().split('\n')
if not any('最后再把所有「选中」路径压回 None' in l for l in L):
    st = [k for k, l in enumerate(L) if l.startswith('def _shared_defaults(')]
    assert len(st) == 1, '_shared_defaults 命中 %d' % len(st)
    r = next(t for t in range(st[0], len(L)) if L[t].strip() == 'return shared')
    L[r:r] = [
        '    # 最后再把所有「选中」路径压回 None：浮层里的节点图常常绑在选中节点身上',
        '    # （绑 sel.points），上面开槽时会把 sel 建成对象，「当 shared.sel」就恒真了。',
        '    for s in screens:',
        '        for n in s.walk():',
        '            if n.kind == "节点图" and getattr(n, "selects", ""):',
        '                _box = shared',
        '                for _k in n.selects.split(".")[:-1]:',
        '                    _box = _box.setdefault(_k, {})',
        '                _box[n.selects.split(".")[-1]] = None',
    ]
    open(p, 'w', encoding='utf-8').write('\n'.join(L))
    print('ui: 选中路径最后压回 None')

# ------------------------------------------------------------------ app.js.j2
p = T + '/app.js.j2'
s = open(p, encoding='utf-8').read()
old1 = ("      const raw = _graphGet(shared.value, path) || {};\n"
        "      const src = raw.nodes || [], links = raw.edges || [];\n"
        "      const key = path + '|' + dir + '|' + JSON.stringify(raw);\n"
        "      if (_graphCache.has(key)) return _graphCache.get(key);")
new1 = ("      const raw0 = _graphGet(shared.value, path);\n"
        "      // 也收纯数组：没有连线的一组知识点（比如详情浮层里的 sel.points）直接给\n"
        "      // 数组就行，dagre 把它们排在同一层，看起来就是一排方块。有先后的就给\n"
        "      // {nodes, edges}，画法跟外面那张大图完全一样。\n"
        "      const raw = Array.isArray(raw0) ? { nodes: raw0 } : (raw0 || {});\n"
        "      // 没给 id 的用 label 顶上：手写的子知识点通常只有 label\n"
        "      const src = (raw.nodes || []).map((n, i) => n.id != null ? n : Object.assign({}, n, { id: n.label != null ? n.label : 'n' + i }));\n"
        "      const links = raw.edges || [];\n"
        "      const key = dir + '|' + JSON.stringify(raw);\n"
        "      // 按路径各缓存一份：页面上常同时有两张图（外面的大图、浮层里的小图），\n"
        "      // 只缓存一份的话两张来回挤掉对方，每次渲染都要重跑 dagre。\n"
        "      const hit = _graphCache.get(path);\n"
        "      if (hit && hit.key === key) return hit.out;")
old2 = "      _graphCache.clear(); _graphCache.set(key, out);\n      return out;"
new2 = "      _graphCache.set(path, { key, out });\n      return out;"
if 'Array.isArray(raw0)' not in s:
    if s.count(old1) != 1 or s.count(old2) != 1:
        restore()
        raise SystemExit('app 锚点命中 %d / %d，已恢复' % (s.count(old1), s.count(old2)))
    s = s.replace(old1, new1).replace(old2, new2)
    open(p, 'w', encoding='utf-8').write(s)
    print('app: graphOf 收数组、补 id、按路径缓存')

# ------------------------------------------------------------------ 验证
sys.path.insert(0, P)
for m in [k for k in list(sys.modules) if k.startswith('tools')]:
    del sys.modules[m]
from tools.ui import compile_ui, parse, _shared_defaults
ok = True
UI = '''界面 自定义 学习路径
  分组 图区 竖排 占满
    节点图 kg 绑 graph 选中 sel 点开 节点详情 高 640px 方向 纵向
  结束
  浮层 节点详情 宽 560px
    显示 sel.label
    显示 sel.desc 当 shared.sel&&shared.sel.desc
    节点图 包含 绑 sel.points 高 220px 当 shared.sel&&shared.sel.points&&shared.sel.points.length
    动作 收起 次要 关闭 收起
  结束
结束
'''
sh = _shared_defaults(parse(UI))
print('shared 初值:', sh)
ok &= sh.get('sel', 'x') is None

r = compile_ui(UI, backend='vue', options={'title': '学习路径'})
iss = [str(i) for i in r['issues']]
print('ISSUES:', iss or '无')
ok &= not iss
js = r['result']['files']['app.js']
os.makedirs('/tmp/g', exist_ok=True)
open('/tmp/g/q.js', 'w', encoding='utf-8').write(js)
c1 = "graphOf('sel.points'" in js
c2 = js.count('<VueFlow') == 2
print("浮层里的小图读 sel.points:", c1, '| 两张 VueFlow:', c2)
ok &= c1 and c2
rc = subprocess.run(['node', '--check', '/tmp/g/q.js'], capture_output=True, text=True)
print('node --check:', 'OK' if rc.returncode == 0 else rc.stderr[:300])
ok &= rc.returncode == 0

# graphOf 逻辑：纯数组 / 带边 / 两张图交替不互相挤掉
m = re.search(r'(const _graphCache.*?function onGraphNode)', js, re.S)
seg = m.group(1).rsplit('function onGraphNode', 1)[0]
seg = re.sub(r'<%.*?%>', '', seg)
test = ("globalThis.dagre = require('/tmp/g/dagre.js');\n" + seg + r'''
const shared = { value: {
  graph: { nodes: [{id:'a',label:'A'},{id:'b',label:'B'}], edges: [{from:'a',to:'b'}] },
  sel: { points: [ {label:'五段动词',state:'done'}, {label:'一段动词',state:'open'}, {label:'カ变・サ变',state:'locked'} ] },
  sel2: { points: { nodes:[{id:'x',label:'う结尾'},{id:'y',label:'く结尾'}], edges:[{from:'x',to:'y'}] } }
}};
const p = graphOf('sel.points', '纵向');
console.log('数组:', p.nodes.map(n => n.id + '@' + n.position.x + ',' + n.position.y + ' ' + n.class).join(' | '));
const q = graphOf('sel2.points', '纵向');
console.log('带边:', q.nodes.map(n => n.id + '@' + n.position.x + ',' + n.position.y).join(' | '), '边', q.edges.length);
const g1 = graphOf('graph', '纵向'); graphOf('sel.points', '纵向'); const g2 = graphOf('graph', '纵向');
console.log('交替后仍命中缓存:', g1 === g2);
''')
open('/tmp/g/inner.js', 'w', encoding='utf-8').write(test)
rc = subprocess.run(['node', '/tmp/g/inner.js'], capture_output=True, text=True)
out = rc.stdout.strip() or rc.stderr[:500]
print(out)
ok &= '五段动词@' in out and 'kg-done' in out and '交替后仍命中缓存: true' in out and '边 1' in out
# 纯数组时三个方块应在同一层（y 相同）
ys = re.findall(r'@-?[\d.]+,(-?[\d.]+) kg', out)
print('数组各项 y:', ys)
ok &= len(set(ys)) == 1 and len(ys) == 3

print('全部通过:', ok)
if ok:
    files = ['tools/ui.py', 'templates/frontend/app.js.j2']
    subprocess.run(['git', 'add', '--', *files], cwd=P)
    msg = ('节点详情里的知识点改用节点图画，跟外面那张图一个样式\n\n'
           '- graphOf 也收纯数组（没有连线的一组知识点排成一层方块），没给 id 用 label\n'
           '- 按路径缓存：外面的大图和浮层里的小图不再互相挤掉缓存\n'
           '- 所有「选中」路径最后压回 None：浮层里的图绑 sel.points 时，'
           '开槽会把 sel 建成对象，「当 shared.sel」就恒真了')
    c = subprocess.run(['git', 'commit', '-m', msg], cwd=P, capture_output=True, text=True)
    print('commit:', c.returncode, (c.stdout + c.stderr).strip().splitlines()[:1])
else:
    restore()
    print('有检查没过，已恢复，不提交')
