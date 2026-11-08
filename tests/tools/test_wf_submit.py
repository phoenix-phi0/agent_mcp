import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""提交工具（tools/wf_submit_mcp.py）和格式（tools/wf_submit.py）。

直接起 MCP 服务、按 stdio JSON-RPC 跟它说话：交错格式回具体错误、交对写结果文件、
交错次数用完不再接受、条件规则（if/then）声明时去掉但校验照做。不调模型。
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from tools import wf_submit

ROOT = Path(__file__).resolve().parents[2]


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


class Server:
    def __init__(self, schema, max_tries=2):
        self.ch = wf_submit.SubmitChannel(schema, max_tries)
        env = dict(os.environ, **self.ch.env())
        self.p = subprocess.Popen([_sys.executable, str(wf_submit.SERVER)], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  encoding='utf-8', env=env)
        self.n = 0

    def call(self, method, params=None, notify=False):
        msg = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
        if not notify:
            self.n += 1
            msg['id'] = self.n
        self.p.stdin.write(json.dumps(msg, ensure_ascii=False) + '\n')
        self.p.stdin.flush()
        if notify:
            return None
        return json.loads(self.p.stdout.readline())

    def submit(self, args):
        r = self.call('tools/call', {'name': 'submit', 'arguments': args})['result']
        return r['isError'], r['content'][0]['text']

    def close(self):
        self.p.stdin.close()
        self.p.wait(5)
        self.ch.close()


GOOD = {'decide': '通过', 'summary': '好', 'checked': [{'item': 'a', 'result': '满足', 'evidence': 'e'}],
        'not_verified': []}


def run():
    schema = wf_submit.load_format(ROOT / 'workflow_demo', 'acceptance')
    s = Server(schema)
    try:
        r = s.call('initialize', {'protocolVersion': '2025-06-18'})
        check(r['result']['protocolVersion'] == '2025-06-18' and 'tools' in r['result']['capabilities'],
              'initialize 回协议版本和 tools 能力')
        s.call('notifications/initialized', notify=True)
        tools = s.call('tools/list')['result']['tools']
        check([t['name'] for t in tools] == ['submit'], '只有 submit 一个工具')
        check('if' not in tools[0]['inputSchema'] and tools[0]['inputSchema']['required'] == schema['required'],
              '声明给模型的参数格式去掉了顶层 if/then，其余照旧')

        err, text = s.submit({'decide': '需修改', 'summary': 'x', 'checked': [], 'not_verified': []})
        check(err and "'task' is a required property" in text and 'checked' in text and '还能再交 1 次' in text,
              '交错：条件规则（需修改必须带 task）照样校验，错误逐条回给模型')
        check(not s.ch.out.exists() and len(s.ch.errors()) == 1, '没写结果文件，错误记进日志')

        err, text = s.submit(GOOD)
        check(not err and '已提交' in text, '交对：回已提交')
        check(json.loads(s.ch.out.read_text(encoding='utf-8')) == GOOD, '结果文件就是交的参数')
        err, text = s.submit(GOOD)
        check(not err and '已经提交过' in text, '交过以后再交不覆盖')
        r = s.call('tools/call', {'name': 'other', 'arguments': {}})['result']
        check(r['isError'], '别的工具名报错')
        r = s.call('bogus')
        check(r['error']['code'] == -32601, '不认识的方法回 -32601')
    finally:
        s.close()

    s = Server(schema, max_tries=2)
    try:
        s.call('initialize')
        s.submit({'decide': '乱写'})
        err, text = s.submit({'decide': '乱写'})
        check(err and '次数用完' in text, '第 2 次还错：次数用完')
        err, text = s.submit(GOOD)
        check(err and not s.ch.out.exists(), '用完后交对的也不收')
    finally:
        s.close()

    # SubmitChannel.run：结果文件一出现就结束进程（假装是一个提交完还想继续说话的模型）
    ch = wf_submit.SubmitChannel(schema)
    try:
        script = (f"import json,time; open({str(ch.out)!r},'w').write(json.dumps({GOOD!r}, ensure_ascii=False));"
                  "time.sleep(60)")
        import time
        t0 = time.time()
        result, _ = ch.run([_sys.executable, '-c', script], ch.dir, dict(os.environ), None, 30, 'fake')
        check(result == GOOD and time.time() - t0 < 10, '提交后不等进程自己结束，马上收')
        ch.out.unlink()
        result, out = ch.run([_sys.executable, '-c', "print('只说话不提交')"], ch.dir, dict(os.environ), None, 30, 'fake')
        check(result is None and '只说话不提交' in out, '进程结束了还没提交：返回 None 和输出')
        try:
            ch.run([_sys.executable, '-c', 'import time; time.sleep(60)'], ch.dir, dict(os.environ), None, 1, 'fake')
            raise AssertionError('应当超时')
        except wf_submit.SubmitError as e:
            check('没有提交' in str(e), '超时报错')
    finally:
        ch.close()

    # 格式文件本身
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / 'formats').mkdir()
        (Path(d) / 'formats' / 'arr.json').write_text('{"type": "array"}', encoding='utf-8')
        (Path(d) / 'formats' / 'bad.json').write_text('{"type": 3}', encoding='utf-8')
        for name, text in (('arr', '顶层必须是 type: object'), ('bad', '不是合法的 JSON Schema'),
                           ('none', '没有格式文件'), ('../x', '格式名无效')):
            try:
                wf_submit.load_format(d, name)
                raise AssertionError(name)
            except wf_submit.FormatError as e:
                check(text in str(e), f'格式文件 {name}：{text}')
    for f in sorted((ROOT / 'workflow_demo' / 'formats').glob('*.json')):
        wf_submit.load_format(ROOT / 'workflow_demo', f.stem)
    print('  ✓ workflow_demo 的格式文件都合法')
    print('wf submit passed')


if __name__ == '__main__':
    run()
