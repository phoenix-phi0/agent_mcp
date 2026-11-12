import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""探针检索（tools/code_search.py）和 gsb_tools 的 search 工具：
切块、中文检索、增量更新、经验来源、密钥打码、凭证文件不进索引，以及 MCP 子集里 search 的暴露方式。"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def fresh(tmp):
    """每次换缓存目录、清模块里的索引，模拟新起的探针进程。"""
    os.environ['GSB_SEARCH_CACHE'] = str(tmp / 'cache')
    os.environ['GSB_SEARCH_EXP_DIRS'] = f"{tmp / 'jobs'}:{tmp / 'probes'}"
    for m in [k for k in sys.modules if k.endswith('code_search')]:
        del sys.modules[m]
    from tools import code_search
    return code_search


def run():
    tmp = Path(tempfile.mkdtemp(prefix='csearch-', dir='/tmp'))
    try:
        repo = tmp / 'repo'
        (repo / 'services').mkdir(parents=True)
        (repo / 'services' / 'kg.zs').write_text(
            '# 导入前先检查\n接口 导入预检\n    读JSONL 表 = content/kg.jsonl\n    遍历 行 于 {表}\n'
            '        如果 {行.id} 已存在\n            记 重复\n    返回 {结果}\n\n'
            '接口 列出条目\n    查询表 库 列出 {请求}\n    返回 {行}\n    设 a = 1\n    设 b = 2\n'
            '    设 c = 3\n    设 d = 4\n', encoding='utf-8')
        (repo / 'router.py').write_text(
            'import os\n\n\ndef submit_call(prompt, timeout=None):\n    """发给模型，超时就重试"""\n'
            '    return retry(prompt, timeout)\n\n\nclass ClaudeClient:\n    def run_claude(self):\n'
            '        return 1\n', encoding='utf-8')
        (repo / 'config.json').write_text('{"api_key": "zzzzzzzzzzzzzzzzzzzzzzzzzz"}', encoding='utf-8')
        (repo / 'notes.md').write_text('# 部署\n用 systemd 起服务\n\n# 密钥\napi_key = abcdefghijklmnopqrstuvw\n',
                                       encoding='utf-8')
        (tmp / 'jobs' / 'j1').mkdir(parents=True)
        (tmp / 'jobs' / 'j1' / 'job.json').write_text(json.dumps({'finished': '2026-11-10T10:00:00', 'tasks': [
            {'prompt': '查一下探针为什么超时', 'status': 'done',
             'output': 'goose 的 stdio 扩展单次调用固定 300 秒超时，所以 run_wait 最多阻塞 270 秒'}]},
            ensure_ascii=False), encoding='utf-8')
        (tmp / 'probes').mkdir()
        (tmp / 'probes' / 'probe_x_p1.prompt.txt').write_text('前言\n任务：\n找 kg 导入的重复检查在哪', encoding='utf-8')
        (tmp / 'probes' / 'probe_x_p1.reply.txt').write_text('在 services/kg.zs:5，按 id 判重', encoding='utf-8')

        cs = fresh(tmp)
        out = cs.search('导入时哪里检查重复', cwd=str(repo), scope='code')
        check('[1] services/kg.zs:1-' in out and '导入预检' in out, '中文按意思检索：导入预检那块排第一')
        check('列出条目' not in out.split('[2]')[0], '顶格的接口分成不同的块')
        out = cs.search('超时重试', cwd=str(repo), scope='code')
        check('router.py:' in out and 'submit_call' in out, 'py 按函数切块，docstring 里的中文能搜到')
        out = cs.search('ClaudeClient', cwd=str(repo), scope='code')
        check('router.py:9-' in out, '英文标识符：类名能定位到类那块')
        out = cs.search('claude client', cwd=str(repo), scope='code')
        check('router.py:9-' in out, '驼峰拆词：claude client 也能搜到 ClaudeClient')
        out = cs.search('api_key 密钥', cwd=str(repo), scope='all')
        check('config.json' not in out, 'config.json 不进索引')
        check('abcdefghijklmnopqrstuvw' not in out and 'api_key = ***' in out, '预览里的密钥打码')

        out = cs.search('探针 超时', cwd=str(repo), scope='exp')
        check('经验 gsbatch:j1#1' in out and '300 秒' in out and '2026-11-10' in out,
              '经验：批量任务的任务书和回复能搜到，带日期')
        out = cs.search('导入 重复检查', cwd=str(repo), scope='exp')
        check('经验 probe:probe_x_p1' in out and 'kg.zs:5' in out, '经验：探针的指令和结论能搜到，去掉了前言')

        # 增量：改一个文件只更新它；删掉的文件从结果里消失
        ix = cs._index(str(repo))
        check(ix.refresh_code() == 0, '没改动时不重建')
        time.sleep(0.01)
        (repo / 'router.py').write_text('def heartbeat():\n    """心跳检测"""\n', encoding='utf-8')
        os.utime(repo / 'router.py', (time.time() + 5, time.time() + 5))
        out = cs.search('心跳检测', cwd=str(repo), scope='code')
        check('更新 1 个来源' in out and 'router.py:1-' in out, '改了的文件增量重建，新内容能搜到')
        (repo / 'notes.md').unlink()
        out = cs.search('systemd 部署', cwd=str(repo), scope='code')
        check('notes.md' not in out, '删掉的文件不再出现')

        # 缓存：新进程直接用缓存，不重建
        cs = fresh(tmp)
        out = cs.search('导入预检', cwd=str(repo), scope='code')
        check('更新 0 个来源' in out, '新进程读缓存，没改动就不重建')

        try:
            cs.search('  ', cwd=str(repo))
            check(False, '空查询应该报错')
        except ValueError:
            check(True, '空查询报错')

        # MCP：探针子集 read_files,search 仍叫 gsb_read_files（Claude 的 --allowed-tools 靠这个名字）
        env = dict(os.environ, GSB_TOOLS_ONLY='read_files,search')
        msgs = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}},
                {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                 'params': {'name': 'search', 'arguments': {'query': '导入预检', 'scope': 'code', 'cwd': str(repo)}}}]
        p = subprocess.Popen([sys.executable, str(ROOT / 'tools' / 'gsb_tools_mcp.py')], env=env, cwd=str(repo),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for m in msgs:
            p.stdin.write(json.dumps(m, ensure_ascii=False) + '\n')
        p.stdin.flush()
        got = {}
        deadline = time.time() + 30
        while len(got) < 3 and time.time() < deadline:
            line = p.stdout.readline()
            if not line:
                break
            d = json.loads(line)
            if 'id' in d:
                got[d['id']] = d
        p.stdin.close()
        p.wait(timeout=10)
        check(got[1]['result']['serverInfo']['name'] == 'gsb_read_files', '子集 read_files,search 仍叫 gsb_read_files')
        check([t['name'] for t in got[2]['result']['tools']] == ['read_files', 'search'], '只暴露 read_files 和 search')
        check('services/kg.zs' in got[3]['result']['content'][0]['text'], '经 MCP 调 search 能用')

        sys.path.insert(0, str(ROOT / 'tools'))
        os.environ.pop('GSB_TOOLS_ONLY', None)
        import importlib
        g = importlib.import_module('gsb_tools_mcp')
        os.environ['GSB_PROBE_SEARCH'] = '0'
        check(g._probe_tools_only() == 'read_files', 'GSB_PROBE_SEARCH=0：探针只挂 read_files（对比用）')
        os.environ.pop('GSB_PROBE_SEARCH')
        check(g._probe_tools_only() == 'read_files,search', '默认探针挂 read_files 和 search')
        print('code search passed')
    finally:
        import shutil
        shutil.rmtree(tmp)


if __name__ == '__main__':
    run()
