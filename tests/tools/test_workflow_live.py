import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""运行时状态：调用进行中时过程记录里就有 running 事件；查看服务的接口和 alive 判断。

在临时目录复制 workflow_demo 跑，不往真 demo 目录写东西。
"""
import json
import os
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from dsl.client import ScriptClient
from tools import trace_server
from tools.dsl import DSLEngine

ROOT = Path(__file__).resolve().parents[2]
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from wf_fixtures import REPLIES  # noqa: E402  每条都符合 workflow_demo 的节点格式


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


class Probe(ScriptClient):
    """每次被调用时，先看一眼磁盘上的过程记录：最后一条事件应该是进行中的这一步。"""

    def __init__(self, replies, runs):
        super().__init__(replies)
        self.runs = runs
        self.seen = []

    def chat_messages(self, messages, **kw):
        f = sorted(self.runs.glob('*.json'))[-1]
        t = json.loads(f.read_text(encoding='utf-8'))
        last = t['events'][-1]
        self.seen.append((t['status'], last['type'], last['status'], last.get('model'), last['role'],
                          'result' in last, t['pid'], t['updated']))
        return super().chat_messages(messages, **kw)


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')


def run():
    tmp = Path(tempfile.mkdtemp())
    try:
        demo = tmp / 'workflow_demo'
        shutil.copytree(ROOT / 'workflow_demo', demo,
                        ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
        (demo / 'runs').mkdir()
        client = Probe(list(REPLIES), demo / 'runs')
        client.offline = True
        engine = DSLEngine(client=client, workdir=demo, verbs_root=ROOT / 'verbs', verbose=False)
        engine.run_file('run.zs')

        # 1. 调用期间
        check(len(client.seen) == 10, '每次调用都看了一眼')
        check(all(s[0] == 'running' for s in client.seen), '调用期间整体状态是 running')
        check(all(s[1] == 'task' and s[2] == 'running' for s in client.seen), '调用期间最后一条是进行中的任务事件')
        check(all(s[3] for s in client.seen), '进行中的事件已经带上模型')
        check(not any(s[5] for s in client.seen), '进行中的事件还没有结果')
        check([s[4] for s in client.seen][7] == 'QA_ENGINEER', '第 8 次调用时停在 QA')
        check(all(s[6] == os.getpid() for s in client.seen), '记录里有进程号')
        check(all(s[7] for s in client.seen), '每次写盘都更新 updated')

        # 2. 跑完之后：没有残留的 running，事件数和以前一样（原地更新，不是追加）
        f = sorted((demo / 'runs').glob('*.json'))[-1]
        t = json.loads(f.read_text(encoding='utf-8'))
        tasks = [e for e in t['events'] if e['type'] == 'task']
        check(t['status'] == 'done', '结束后状态 done')
        check(len(tasks) == 10 and all(e['status'] == 'ok' for e in tasks), '10 条任务事件都从 running 改成 ok')
        check(len(t['events']) == 19, '事件总数不变（任务事件原地更新）')

        # 3. 查看服务
        runs = demo / 'runs'
        (runs / 'live-alive.json').write_text(json.dumps({'status': 'running', 'pid': os.getpid(), 'events': []}), encoding='utf-8')
        (runs / 'live-dead.json').write_text(json.dumps({'status': 'running', 'pid': 2 ** 22 + 12345, 'events': []}), encoding='utf-8')
        srv = ThreadingHTTPServer(('127.0.0.1', 0), trace_server.make_handler(runs))
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        base = f'http://127.0.0.1:{srv.server_address[1]}'
        try:
            code, body = get(base + '/')
            check(code == 200 and '编排过程查看器' in body, '首页返回查看器')
            code, body = get(base + '/api/runs')
            lst = json.loads(body)['runs']
            by = {r['name']: r for r in lst}
            check(code == 200 and f.name in by and by[f.name]['status'] == 'done' and by[f.name]['calls'] == 10, '列表里有这次运行')
            check(by['live-alive.json']['alive'] is True, '进程还在：alive=True')
            check(by['live-dead.json']['alive'] is False, '进程没了：alive=False')
            check(by[f.name]['alive'] is None, '已结束的不判断 alive')
            code, body = get(base + '/api/run?name=' + f.name)
            check(code == 200 and len(json.loads(body)['events']) == 19, '取单份记录')
            code, _ = get(base + '/api/run?name=../../etc/passwd')
            check(code == 400, '拒绝带路径的文件名')
            code, _ = get(base + '/api/run?name=nope.json')
            check(code == 404, '不存在的文件 404')
        finally:
            srv.shutdown()
            srv.server_close()
        print('workflow live passed')
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    run()
