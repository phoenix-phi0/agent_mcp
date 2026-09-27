import subprocess, sys
P = '/home/ysc/mcp'
def sh(c):
    r = subprocess.run(c, shell=True, cwd=P, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()

TARGET = 'f8b7e4c'
print('HEAD:', sh('git log --oneline -1')[1])
rc, t = sh('git cat-file -t %s' % TARGET)
print('目标提交存在:', rc == 0, t)
if rc != 0:
    sys.exit('目标提交不在对象库里，只能重写')
rc, _ = sh('git merge-base --is-ancestor HEAD %s' % TARGET)
print('HEAD 是目标的祖先（可以快进）:', rc == 0)
print('中间的提交:'); print(sh('git log --oneline HEAD..%s' % TARGET)[1])
rc, st = sh('git status --porcelain -- tools templates')
print('工作区干净:', st == '', st[:200])
if st:
    sys.exit('工作区有改动，不动')
rc, out = sh('git merge --ff-only %s' % TARGET)
print('快进:', rc, out.splitlines()[-1] if out else '')
print('现在:', sh('git log --oneline -1')[1])

# 快进后自检
sys.path.insert(0, P)
from tools.ui import compile_ui
r = compile_ui('界面 自定义 T\n  分组 a 竖排\n    节点图 kg 绑 graph 选中 sel 图例 高 600px\n  结束\n结束\n',
               backend='vue', options={'title': 't'})
js = r['result']['files']['app.js']
open('/tmp/ff.js', 'w', encoding='utf-8').write(js)
print('ISSUES:', [str(i) for i in r['issues']] or '无')
print('科技树卡片:', 'kg-head' in js, '| 直角线:', "type: 'smoothstep'" in js, '| minlen:', 'minlen' in js,
      '| 层带:', '#node-kglayer' in js, '| 图例:', '.legend' in js)
print('node --check:', sh('node --check /tmp/ff.js')[0] == 0)
