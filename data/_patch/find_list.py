import subprocess, os, glob, json, re
P = '/home/ysc/mcp'
def sh(c):
    r = subprocess.run(c, shell=True, cwd=P, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()
print('== 用到节点图的 .ui')
print(sh("grep -rn --include='*.ui' '节点图' . | grep -v node_modules | head -10"))
print('== 这些 .ui 里节点图附近的列表')
print(sh("grep -rn --include='*.ui' -e '^ *列表' . | grep -v node_modules | head -20"))
print('== 后端给图的地方（edges / nodes / from / to / 前置）')
print(sh("grep -rn --include='*.zs' --include='*.py' -e 'edges' kg | grep -v __pycache__ | head -20"))
print('== 服务日志里最近一次 graph 返回（如果有）')
for f in sorted(glob.glob(P + '/data/**/*.log', recursive=True))[-3:]:
    print(f)
