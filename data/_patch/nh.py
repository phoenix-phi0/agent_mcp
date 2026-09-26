import sys, os, re, subprocess, urllib.request
sys.path.insert(0, '/home/ysc/mcp')
from tools.ui import compile_ui
os.makedirs('/tmp/g', exist_ok=True)

UI = '''界面 自定义 图测
  分组 图区 竖排
    节点图 kg 绑 graph 选中 sel 高 520px 方向 纵向
    动作 详情 次要 当 shared.sel 查看
    显示 sel.label
  结束
  分组 图区2 竖排
    节点图 kg2 绑 graph2 高 300px 方向 横向
  结束
结束
'''
r = compile_ui(UI, backend='vue', options={'title': '图测'})
print('ISSUES:', [str(i) for i in r['issues']] or '无')
files = r['result']['files']
for n, t in files.items():
    open('/tmp/g/' + n, 'w', encoding='utf-8').write(t)
js = files['app.js']
print('slot #node-kg:', '#node-kg' in js, '| Handle 组件:', '<Handle' in js,
      '| 注册 Handle:', 'VueFlowCore.Handle' in js, '| :key:', ':key="graphOf(' in js)
print('_kgState:', '_kgState' in js, '| _kgSide:', '_kgSide' in js,
      '| sourcePosition:', 'sourcePosition' in js)
rc = subprocess.run(['node', '--check', '/tmp/g/app.js'], capture_output=True, text=True)
print('node --check:', 'OK' if rc.returncode == 0 else rc.stderr[:300])

# 模板字符串能不能被 Vue 编译器吃下：抽出 template 里的 VueFlow 片段，
# 检查标签是否配对（最常见的错误是插槽/Handle 没闭合）
m = re.search(r'template: `(.*)`', js, re.S)
tpl = m.group(1) if m else ''
for tag in ['VueFlow', 'template', 'div']:
    o = len(re.findall(r'<%s[\s>]' % tag, tpl)); c = tpl.count('</%s>' % tag)
    print('标签配对 %-8s 开 %d 闭 %d %s' % (tag, o, c, 'OK' if o == c else '!!'))

# VueFlowCore 里有没有 Handle 导出
try:
    src = urllib.request.urlopen(
        'https://unpkg.com/@vue-flow/core@1.48.2/dist/vue-flow-core.iife.js', timeout=20).read().decode('utf-8', 'ignore')
    print('iife 有 exports.Handle:', 'exports.Handle' in src or 'Handle:' in src[-4000:])
except Exception as e:
    print('下载 iife 失败:', e)

# 用 node 跑一遍 graphOf 的纯逻辑：把 app.js 里 graphOf 段抠出来，喂假数据
seg = re.search(r'(const _graphCache.*?function onGraphNode.*?\n)', js, re.S)
dag = urllib.request.urlopen('https://cdnjs.cloudflare.com/ajax/libs/dagre/0.8.5/dagre.min.js', timeout=20).read().decode()
open('/tmp/g/dagre.js', 'w').write(dag)
test = seg.group(1) + r'''
const shared = { value: { graph: {
  nodes: [
    {id:'a', label:'平假名', state:'done', badge:5},
    {id:'b', label:'片假名', state:'open'},
    {id:'c', label:'浊音', state:'locked'},
    {id:'d', label:'拗音'},
  ],
  edges: [ {from:'a',to:'b'}, {from:'a',to:'c'}, {from:'c',to:'d'}, {from:'b',to:'c',kind:'对照'} ]
}}};
for (const dir of ['纵向', '横向']) {
  const g = graphOf('graph', dir);
  console.log('==', dir);
  g.nodes.forEach(n => console.log(' node', n.id, JSON.stringify(n.position), n.class || '-', n.sourcePosition + '/' + n.targetPosition));
  g.edges.forEach(e => console.log(' edge', e.source + '->' + e.target, e.type, e.class || '-', e.sourceHandle + '/' + e.targetHandle));
}
// 给坐标就不跑布局
shared.value.graph = { nodes: [{id:'x',label:'X',x:697,y:36},{id:'y',label:'Y',x:547,y:140}], edges:[{from:'x',to:'y'}] };
const g2 = graphOf('graph', '纵向');
console.log('给坐标:', g2.nodes.map(n => n.id + JSON.stringify(n.position)).join(' '));
'''
open('/tmp/g/logic.js', 'w', encoding='utf-8').write(
    "const fs=require('fs');eval(fs.readFileSync('/tmp/g/dagre.js','utf8'));\n" + test)
rc = subprocess.run(['node', '/tmp/g/logic.js'], capture_output=True, text=True)
print(rc.stdout.strip() or rc.stderr[:600])
