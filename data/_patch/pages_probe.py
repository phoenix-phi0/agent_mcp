import subprocess, os
P = '/home/ysc/mcp'
def sh(c):
    return subprocess.run(c, shell=True, cwd=P, capture_output=True, text=True).stdout.strip()
out = []
out.append('== .ui 文件\n' + sh("find . -name '*.ui' -not -path './.venv/*' -not -path '*/node_modules/*' -not -path './data/_patch/*' | sort"))
out.append('== 各 .ui 里的界面名\n' + sh("for f in $(find . -name '*.ui' -not -path './.venv/*' -not -path '*/node_modules/*' -not -path './data/_patch/*' | sort); do echo \"$f: $(grep -h '^界面' $f | sed 's/^界面 *//' | tr '\\n' '|')\"; done"))
out.append('== 手写的 html（不在生成目录里的）\n' + sh("find . \\( -name '*.html' -o -name '*.htm' \\) -not -path './.venv/*' -not -path '*/node_modules/*' -not -path './data/_patch/*' -not -path './.git/*' | sort | head -40"))
out.append('== 生成出来的前端目录（有 app.js 的）\n' + sh("find . -name app.js -not -path './.venv/*' -not -path '*/node_modules/*' -not -path './data/_patch/*' | sort | head -20"))
out.append('== 服务端直接吐 HTML 的地方（python 里的 <html / PAGE =）\n' + sh("grep -rIln -e '<!doctype html' -e '<html' -e 'PAGE = ' --include='*.py' --include='*.zs' . | grep -v -e .venv -e node_modules -e data/_patch -e templates/ | head -20"))
open(P + '/data/_patch/pages_probe.txt', 'w', encoding='utf-8').write('\n\n'.join(out))
print('ok')
