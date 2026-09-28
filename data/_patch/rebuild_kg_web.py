import sys, os, time
from pathlib import Path
P = '/home/ysc/mcp'
sys.path.insert(0, P)
os.chdir(P)
from gen.project import build
proj = Path(P) / 'kg'
for line in build(proj):
    print('  build:', line)
js = open(P + '/kg/web/app.js', encoding='utf-8').read()
print('kg/web/app.js 生成于', time.strftime('%m-%d %H:%M:%S', time.localtime(os.path.getmtime(P + '/kg/web/app.js'))))
marks = {'整页撑满': 'graph-wrap grow' in js, '邻域图': "around: 'sel'" in js, '卡片': 'kg-head' in js,
         '压紧折行': 'MAXR' in js, '没有导航': '<nav>' not in js, '没有刷新按钮': '>刷新<' not in js,
         '进入时拉图': '"node_list"' in js}
print(' '.join('%s=%s' % (k, 'Y' if v else '-') for k, v in marks.items()))
