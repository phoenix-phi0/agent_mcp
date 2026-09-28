import subprocess, os, re, json, glob, sqlite3
P = '/home/ysc/mcp'
def sh(c):
    r = subprocess.run(c, shell=True, cwd=P, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()
print('== db 文件'); print(sh("find . -name '*.db' -not -path './.venv/*' -not -path '*/node_modules/*' | head"))
print('== 查询定义'); print(sh("grep -rn -e 'kg_graph_nodes' -e 'kg_graph_edges' --include='*.sql' --include='*.zs' --include='*.py' --include='*.yaml' --include='*.toml' --include='*.json' . | grep -v -e .venv -e node_modules -e data/_patch | head"))
