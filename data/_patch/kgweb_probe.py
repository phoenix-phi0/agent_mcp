import subprocess, os, time, re, sys
P = '/home/ysc/mcp'
def sh(c):
    return subprocess.run(c, shell=True, cwd=P, capture_output=True, text=True).stdout.strip()
def mt(f):
    return time.strftime('%m-%d %H:%M', time.localtime(os.path.getmtime(P + '/' + f))) if os.path.exists(P + '/' + f) else '不存在'
out = []
for f in ['kg/ui/node.ui', 'kg/web/index.html', 'kg/web/app.js', 'kg/web/style.css',
          'templates/frontend/app.js.j2', 'templates/frontend/graph.j2', 'tools/ui.py']:
    out.append('%-32s %s' % (f, mt(f)))
js = open(P + '/kg/web/app.js', encoding='utf-8').read() if os.path.exists(P + '/kg/web/app.js') else ''
marks = {'整页科技树(grow)': 'graph-wrap grow' in js, '邻域图(围绕)': "around: 'sel'" in js,
         '卡片(kg-head)': 'kg-head' in js, '压紧折行(MAXR)': 'MAXR' in js, '没有导航': '<nav>' not in js,
         '没有刷新按钮': '>刷新<' not in js}
out.append('kg/web/app.js 里：' + ' '.join('%s=%s' % (k, 'Y' if v else '-') for k, v in marks.items()))
out.append('== 谁负责生成 kg/web\n' + sh("grep -rIn -e 'kg/web' -e \"kg', 'web\" -e 'node.ui' --include='*.py' --include='*.zs' --include='*.sh' --include='*.toml' . | grep -v -e .venv -e node_modules -e data/_patch -e '^./data/' | head -12"))
out.append('== kg 目录\n' + sh('ls kg kg/web 2>&1 | head -30'))
open(P + '/data/_patch/kgweb_probe.txt', 'w', encoding='utf-8').write('\n'.join(out))
print('ok')
