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
    # 交错记录写到临时目录，不进 data/submit_fails
    os.environ['WF_SUBMIT_FAILS'] = tempfile.mkdtemp(prefix='submit_fails_')
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

    # 交成数组里的一项（真跑：模块验收把 checked 里的一条当成整份结果，连交三次都是这样）
    ma = wf_submit.load_format(ROOT / 'workflow_demo', 'module_acceptance')
    hint = wf_submit.shape_hint(ma)
    check('整份结果' in hint and all(k in hint for k in ma['required']) and 'checked 是数组' in hint
          and 'evidence' in hint and '不要只把其中一项单独交上去' in hint,
          f'交之前的说明：最外层要带齐 {"、".join(ma["required"])}，checked 的每一项放进数组里')
    one = {'item': 'pytest', 'result': '满足', 'evidence': '243 passed'}
    w = wf_submit.wrong_level_hint(ma, one)
    check(w and 'checked 里的一项' in w and 'decide' in w and 'summary' in w, '交成 checked 里的一项：点明，说出最外层要什么')
    check(wf_submit.wrong_level_hint(ma, {'decide': '通过', 'item': 'x'}) is None
          and wf_submit.wrong_level_hint(ma, {'foo': 1}) is None and wf_submit.wrong_level_hint(ma, {}) is None,
          '最外层有顶层字段、或者是乱写的：不加这句（只有确实交成一项时才说）')
    s = Server(ma, max_tries=3)
    try:
        s.call('initialize')
        tools = s.call('tools/list')['result']['tools']
        check(hint in tools[0]['description'], 'submit 工具的说明里带上这句')
        err, text = s.submit(one)
        check(err and text.startswith(w) and "'decide' is a required property" in text, '交错时的回复：先点明交成了一项，再列逐条错误')
    finally:
        s.close()
    from tools import llm_router
    import inspect
    check('shape_hint(schema)' in inspect.getsource(llm_router.submit_call), 'submit_call 给模型的提交说明里也带上这句')
    check('一次 submit 里写完' in hint and '不要贴大段原文' in hint and '不要写成一段 JSON 字符串' in hint,
          '说明里还写了：一次交完、证据写短、数组不要写成字符串')

    # 数组写成了 JSON 字符串（Claude 调工具常见）：解开再校验，不算交错
    good = {'decide': '通过', 'summary': '好', 'checked': [one], 'not_verified': [], 'deviations': []}
    as_str = dict(good, checked=json.dumps([one], ensure_ascii=False))
    check(wf_submit.coerce(ma, as_str) == good and wf_submit.coerce(ma, good) == good, 'coerce：数组写成字符串的解开，本来对的不动')
    check(wf_submit.coerce(ma, dict(good, checked='不是 JSON'))['checked'] == '不是 JSON'
          and wf_submit.coerce(ma, dict(good, summary='[1]'))['summary'] == '[1]',
          'coerce：解不开的、格式本来就要字符串的：原样留着（照常报错 / 照常收）')
    nested = {'type': 'object', 'properties': {'rows': {'type': 'array', 'items': {
        'type': 'object', 'properties': {'tags': {'type': 'array', 'items': {'type': 'string'}}}}}}}
    check(wf_submit.coerce(nested, {'rows': [{'tags': '["a","b"]'}]}) == {'rows': [{'tags': ['a', 'b']}]},
          'coerce：数组里每一项的字段也解开')
    s = Server(ma, max_tries=3)
    try:
        s.call('initialize')
        err, text = s.submit(as_str)
        check(not err and json.loads(s.ch.out.read_text(encoding='utf-8')) == good and s.ch.errors() == [],
              'submit：checked 写成字符串也收下，结果文件里是解开的数组，不算交错')
    finally:
        s.close()

    # 交错过的：关闭时留一份每次交的参数和错误（data/submit_fails，测试里换成临时目录）
    kept = Path(os.environ['WF_SUBMIT_FAILS'])
    before = set(kept.glob('*.jsonl'))
    s = Server(ma, max_tries=3)
    try:
        s.call('initialize')
        s.submit(one)
        s.submit(good)
    finally:
        s.close()
    new = sorted(set(kept.glob('*.jsonl')) - before)
    rows = [json.loads(x) for x in new[0].read_text(encoding='utf-8').splitlines()] if new else []
    check(len(new) == 1 and len(rows) == 1 and rows[0]['arguments'] == one and rows[0]['submitted'] is True
          and any('decide' in e for e in rows[0]['errors']), '交错过的：留下交错那次的参数和错误（最后交对了也留，标 submitted）')
    before = set(kept.glob('*.jsonl'))
    s = Server(ma)
    try:
        s.call('initialize')
        s.submit(good)
    finally:
        s.close()
    check(set(kept.glob('*.jsonl')) == before, '一次就交对的：不留')

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
