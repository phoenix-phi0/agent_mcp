import subprocess, os, re, glob
P = '/home/ysc/mcp'
out = []
def sh(c):
    r = subprocess.run(c, shell=True, cwd=P, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()
out.append('== HEAD\n' + sh('git log --oneline -6'))
out.append('== fd8f68a 改了哪些文件\n' + sh('git show --stat --format=%h fd8f68a | tail -12'))
out.append('== ui.py 里的 载入 / 带 / 进入时\n' + sh("grep -n -e '载入' -e '\"带\"' -e '进入时' -e 'carry' -e 'load' tools/ui.py | head -40"))
out.append('== app.js.j2 里的 载入 / carry / load / openOverlay\n' + sh("grep -n -e 'carry' -e 'loadOn' -e 'load' -e '载入' -e 'openOverlay' -e 'VueFlowCore' templates/frontend/app.js.j2 | head -60"))
out.append('== node_detail / node_list 在哪\n' + sh("grep -rln -e 'node_detail' -e 'node_list' --include='*.zs' --include='*.py' --include='*.json' . | grep -v -e __pycache__ -e node_modules -e '/data/' | head -20"))
open(P + '/data/_patch/probe1.txt', 'w', encoding='utf-8').write('\n\n'.join(out))
# 把后端路由原文拷出来
for f in re.findall(r'\S+', sh("grep -rln -e 'node_detail' -e 'node_list' --include='*.zs' . | grep -v -e node_modules -e '/data/'")):
    dst = P + '/data/_patch/route__' + f.strip('./').replace('/', '__') + '.txt'
    open(dst, 'w', encoding='utf-8').write(open(P + '/' + f.lstrip('./'), encoding='utf-8').read())
    print('拷出', f)
print('ok')
