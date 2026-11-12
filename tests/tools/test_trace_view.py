import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
"""查看器接入外部控制和格式提交：用离线假模型造三份受控记录，交给 trace_server.read_trace
（带上 _control、_formats），再用 jsdom 打开 trace_view.html 渲染，检查页面上看得到：

- 暂停在第几步、默认会怎么执行、提示词和格式定义（外部能照着自己执行）
- 外部交的结果、换卡换模型的步骤有标记
- 失败的尝试带原始回复、上次失败的原因
- 中止的状态

E：页面里「由我来做」。造一份停在第二次审查的记录，起真的 trace_server（本机地址，开放写接口）：
POST 不合格的结果被拒、带逐条字段错误；POST 合格的结果后运行往下走一步；--readonly 起的服务页面没有写标记、
POST 回 403。再用 jsdom（tests/e2e/trace_view_form_check.js）操作表单：enum 是下拉、数组可加删条目、
表单和 JSON 互相同步、页面先校验、服务端错误原样显示、中止要二次确认；只读页面没有写按钮。

jsdom 找的是 node_modules（项目根、或环境变量 NODE_PATH）；没装就只跑 Python 这一半，并说明跳过了。
"""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from dsl.client import ScriptClient
from tools import trace_server
from tools import workflow_ctl as wc
from wf_fixtures import REPLIES, acceptance, contract, impl, review, revision
from test_wf_refactor import analysis, assign, plan

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / 'tools' / 'trace_view.html'
CHECK = ROOT / 'tests' / 'e2e' / 'trace_view_check.js'
FORM_CHECK = ROOT / 'tests' / 'e2e' / 'trace_view_form_check.js'


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def client(replies):
    c = ScriptClient(list(replies))
    c.offline = True
    return c


def demo_copy(tmp, name):
    dst = tmp / name
    shutil.copytree(ROOT / 'workflow_demo', dst,
                    ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    return dst


def jsdom_env():
    env = dict(os.environ)
    paths = [p for p in (env.get('NODE_PATH', ''), str(ROOT / 'node_modules')) if p]
    env['NODE_PATH'] = os.pathsep.join(paths)
    node = shutil.which('node')
    if not node:
        return None, env
    r = subprocess.run([node, '-e', "require('jsdom')"], env=env, capture_output=True, text=True)
    return (node if r.returncode == 0 else None), env


def render(node, env, tmp, run, line=None):
    data = trace_server.read_trace(ROOT / run)
    f = tmp / (Path(run).stem + '.view.json')
    f.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding='utf-8')
    cmd = [node, str(CHECK), str(VIEW), str(f)] + ([str(line)] if line else [])
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError(f'node 出错：{r.stderr[-1500:]}')
    out = json.loads(r.stdout)
    if out['errors']:
        raise AssertionError(f'页面脚本报错：{out["errors"]}')
    return out


def cls(out, line):
    return dict(out['classes']).get(str(line), '')


def form_check(node, env, view_json, readonly=False):
    cmd = [node, str(FORM_CHECK), str(VIEW), str(view_json)] + (['readonly'] if readonly else [])
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError(f'node 出错：{r.stderr[-1500:]}')
    out = json.loads(r.stdout)
    if out['errors']:
        raise AssertionError(f'页面脚本报错：{out["errors"]}')
    return out


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Server:
    """起一个 trace_server：单独的进程组（setsid），记 PID，结束时按进程组杀；输出写日志文件。"""

    def __init__(self, workdir, log, *extra):
        self.port = free_port()
        self.log = open(log, 'w', encoding='utf-8')
        self.proc = subprocess.Popen(
            [sys.executable, '-m', 'tools.trace_server', str(workdir), '--port', str(self.port), *extra],
            cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT)), stdin=subprocess.DEVNULL,
            stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        self.base = f'http://127.0.0.1:{self.port}'
        for _ in range(100):
            if self.proc.poll() is not None:
                raise AssertionError(f'trace_server 没起来（退出码 {self.proc.returncode}），日志 {log}')
            try:
                socket.create_connection(('127.0.0.1', self.port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.1)
        self.stop()
        raise AssertionError('trace_server 10 秒没监听端口')

    def stop(self):
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait(timeout=5)
            except ProcessLookupError:
                pass
        self.log.close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return r.read().decode('utf-8')

    def post(self, op, body, ctype='application/json', headers=None):
        req = urllib.request.Request(f'{self.base}/api/{op}', data=json.dumps(body).encode('utf-8'),
                                     headers={'Content-Type': ctype, **(headers or {})}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode('utf-8'))


def server_checks(tmp, e, re_):
    """E 的服务端一半：真的起服务，POST 写接口。"""
    name = Path(re_).name
    srv = Server(e, tmp / 'server-e.log')
    try:
        check('<meta name="trace-write"' in srv.get('/') and '<meta name="trace-live"' in srv.get('/'),
              '本机地址起的服务：页面带写标记（显示「由我来做」）')
        d = json.loads(srv.get(f'/api/run?name={name}'))
        check(d['status'] == 'waiting' and d['pending']['step'] == 4 and d['pending']['format'] == 'review'
              and any(a['name'] == 'ARCHITECT_GLM' for a in d['_agents']),
              '/api/run：停在第 4 步（格式 review），带角色卡清单')

        bad = {'summary': '少了 decide', 'issues': [{'location': 'a', 'problem': '', 'suggestion': 's', 'severity': '很严重'}]}
        code, out = srv.post('submit', {'name': name, 'result': bad})
        errs = out.get('errors') or []
        check(code == 400 and out['ok'] is False and '不符合格式 review' in out['error']
              and any('decide' in x for x in errs) and any(x.startswith('issues[0].severity') for x in errs),
              f'POST 不合格的结果：400，带逐条字段错误（{len(errs)} 条）')
        d = json.loads(srv.get(f'/api/run?name={name}'))
        check(d['status'] == 'waiting' and d['pending']['step'] == 4, '被拒后运行没动，还停在第 4 步')

        code, out = srv.post('submit', {'name': name, 'result': review('通过'), 'step': 3})
        check(code == 400 and '第 4 步' in out['error'], 'step 对不上：400，说明现在停在哪一步')
        code, out = srv.post('submit', {'name': name, 'result': review('通过')}, ctype='text/plain')
        check(code == 415, 'Content-Type 不是 application/json：415')
        code, out = srv.post('submit', {'name': name, 'result': review('通过')}, headers={'Origin': 'http://evil.example'})
        check(code == 403 and out['ok'] is False, '跨站 Origin（和 Host 不一致）：403')
        code, out = srv.post('submit', {'name': name, 'result': review('通过'), 'step': 3}, headers={'Origin': srv.base})
        check(code == 400, 'Origin 和 Host 一致不被拦（走到步号检查，400）')
        d = json.loads(srv.get(f'/api/run?name={name}'))
        check(d['status'] == 'waiting' and d['pending']['step'] == 4, '被 403 拦下的请求没让运行往下走')
        code, out = srv.post('submit', {'name': '../x.json', 'result': {}})
        check(code == 400, '文件名不对：400')
        code, out = srv.post('nothing', {'name': name})
        check(code == 404, '没有的写接口：404')

        code, out = srv.post('submit', {'name': name, 'result': review('通过'), 'step': 4})
        check(code == 200 and out['ok'] is True and out['status']['run'].endswith(name), 'POST 合格的结果：200')
        for _ in range(300):
            d = json.loads(srv.get(f'/api/run?name={name}'))
            if d['status'] == 'waiting' and d['pending']['step'] == 5:
                break
            time.sleep(0.2)
        step4 = [x for x in d['events'] if x.get('type') == 'task' and x.get('step') == 4]
        check(d['status'] == 'waiting' and d['pending']['step'] == 5 and step4 and step4[-1]['status'] == 'ok'
              and step4[-1]['result']['decide'] == '通过',
              '运行往下走：第 4 步用了交的结果，停到第 5 步')

        code, out = srv.post('abort', {'name': name})
        d = json.loads(srv.get(f'/api/run?name={name}'))
        check(code == 200 and out['status']['status'] == 'aborted' and d['status'] == 'aborted', 'POST abort：运行中止')
    finally:
        srv.stop()

    ro = Server(e, tmp / 'server-ro.log', '--readonly')
    try:
        page = ro.get('/')
        check('<meta name="trace-live"' in page and '<meta name="trace-write"' not in page, '--readonly 起的服务：页面没有写标记')
        code, out = ro.post('resume', {'name': name})
        check(code == 403 and out['ok'] is False, '--readonly：POST 回 403')
    finally:
        ro.stop()
    check(not trace_server.writable('0.0.0.0') and not trace_server.writable('192.168.1.5')
          and trace_server.writable('127.0.0.1') and trace_server.writable('::1') and trace_server.writable('localhost'),
          '只有本机地址才开放写接口')


def page_checks(node, env, view_json):
    """E 的页面一半：jsdom 里操作「由我来做」。"""
    f = form_check(node, env, view_json)
    check(f['hasAct'] and f['title'].startswith('由我来做（扮演') and f['below'],
          f'暂停节点详情最下面有「{f["title"]}」')
    check(f['order'][0] == 'decide' and set(f['order']) == {'decide', 'summary', 'issues'}, 'decide 排在表单最上')
    check(f['decideTag'] == 'SELECT' and {'通过', '需修改'} <= set(f['decideOptions']), 'enum（decide）是下拉')
    check(f['summaryTag'] in ('INPUT', 'TEXTAREA') and 'decide' in f['stars'], '字符串是输入框，必填的标星')
    check([m for m in f['modes']] == ['表单', 'JSON'], '有 表单 / JSON 切换')
    check(all(any(k in a for a in f['actions']) for k in ('提交结果', '按默认执行', '按所选执行', '继续自动跑', '中止'))
          and 'ARCHITECT_GLM' in f['cards'], '同一块里有提交、按默认执行、换卡/换模型执行、继续自动跑、中止')
    check(f['hasCopy'] and f['copied'] == {'decide': '需修改', 'summary': '审查结论：需修改', 'items': 1, 'severity': '一般'},
          '从上次这个节点的结果预填')
    check(f['cleared'] == {'decide': '', 'summary': '', 'items': 0}, '清空重填')
    check((f['items1'], f['items2'], f['items3']) == (1, 2, 1), '数组可加条目、删条目')
    check('issues[0].severity:SELECT' in f['itemFields'] and any(x.startswith('issues[0].problem:') for x in f['itemFields']),
          '数组里的对象是一组子字段，其中的 enum 也是下拉')
    check(f['postsAfterInvalid'] == 0 and 'issues[0].severity' in f['clientBad'] and f['clientMsg'],
          f'没填全就提交：页面先拦下不发请求，缺的字段标出（{f["clientMsg"][:40]}）')
    j = f['jsonFromForm']
    check(j['decide'] == '需修改' and j['summary'] == '人工审查：缺错误码' and j['issues'][0]['severity'] == '一般',
          '切到 JSON：内容就是表单里填的')
    check(f['badJsonStays'] and f['badJsonMsg'], 'JSON 写坏了切不回表单，有提示')
    check(f['formFromJson'] == {'summary': '从 JSON 改的', 'items': 2, 'severity1': '轻微'}, '改 JSON 再切回表单：表单跟着变')
    check("issues[0].problem: '' should be non-empty" in f['serverMsg'] and 'issues[0].problem' in f['serverBad']
          and f['canRetry'], '服务端拒绝：原样显示字段错误，对应字段标出，可以接着改')
    p = f['posts']
    check([x['url'] for x in p] == ['api/submit', 'api/submit', 'api/execute', 'api/abort']
          and all(x['type'] == 'application/json' for x in p), f'发出的写请求：{[x["url"] for x in p]}')
    check(p[1]['body']['result']['summary'] == '人工审查：缺错误码' and len(p[1]['body']['result']['issues']) == 2
          and p[1]['body']['step'] == 4 and f['busyWhileSending'], '提交的是表单里的结果，带步号；发送中按钮不可点')
    check(f['noteAfterSubmit'] != f['note'] or f['formResetAfterSubmit'], '提交成功后有提示并刷新')
    check(f['execNeedsChoice'] and p[2]['body'].get('role') == 'ARCHITECT_GLM' and p[2]['body'].get('model') == 'cli:goose/glm-5.3',
          '换卡 / 换模型执行：没选时提示，选了带上卡和模型')
    check('确定中止' in f['abortConfirm'] and f['postsBeforeAbortYes'] == 3 and f['abortBack'],
          '中止在页面内二次确认（没用 alert/confirm），点「不中止」退回')

    r = form_check(node, env, view_json, readonly=True)
    check(not r['hasAct'] and r['writeButtons'] == 0, '查看服务只读时：页面没有「由我来做」和写按钮')


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='wfview-', dir=ROOT / 'data/tmp'))
    try:
        # A：外部交第 1 步、内置跑第 2 步、换卡换模型跑第 3 步，停在第 4 步
        a = demo_copy(tmp, 'a')
        ca = client(REPLIES[1:])
        ra = wc.start(a, client=ca)['run']
        wc.submit(ra, REPLIES[0], client=ca)
        wc.execute(ra, wait=True, client=ca)
        wc.execute(ra, model='cli:goose/glm-5.3', role='ARCHITECT_GLM', wait=True, client=ca)
        data = trace_server.read_trace(ROOT / ra)
        check(data['_control']['mode'] == 'step' and [h['op'] for h in data['_control']['history']]
              == ['start', 'submit', 'execute', 'execute'], 'read_trace 带上控制文件：模式、操作记录')
        check(sorted(data['_formats']) == ['acceptance', 'assignment', 'contract', 'contract_revision',
                                           'implementation', 'review'], 'read_trace 带上脚本里用到的 6 个格式定义')
        runs = trace_server.list_runs(a / 'runs')
        check(runs[0]['status'] == 'waiting' and runs[0]['waiting_step'] == 4 and runs[0]['controlled']
              and runs[0]['calls'] == 3, '运行列表：暂停在第 4 步、受控、3 次执行（停住那条不算）')

        # B：第 1 步模型回的不是 JSON，停在第 1 步
        b = demo_copy(tmp, 'b')
        cb = client(['这不是 JSON'])
        rb = wc.start(b, client=cb)['run']
        wc.execute(rb, wait=True, client=cb)

        # C：中止
        c = demo_copy(tmp, 'c')
        rc = wc.start(c, client=client([]))['run']
        wc.submit(rc, contract('v1'), client=client([]))
        wc.abort(rc)

        # D：重构流程，启动时把架构师长期换成 Fable 卡，逐步跑完
        d = demo_copy(tmp, 'd')
        cd = client([analysis(), plan('v1'), review('通过'), assign('ENGINEER_LITE'), impl('抽函数'),
                     acceptance('通过')])
        rd = wc.start(d, entry='run_refactor.zs', roles={'ARCHITECT': 'ARCHITECT_FABLE'}, client=cd)['run']
        for _ in range(6):
            wc.execute(rd, wait=True, client=cd)
        runs = trace_server.list_runs(d / 'runs')
        check(runs[0]['status'] == 'done' and len(cd.calls) == 6, f'重构流程换卡后逐步跑完（{runs[0]["status"]}，{len(cd.calls)} 次调用）')

        # E：停在第二次审查（第 4 步，这个节点上次有过结果）；先存一份给页面检查用，再起服务打写接口
        e = demo_copy(tmp, 'e')
        ce = client([])
        re_ = wc.start(e, client=ce)['run']
        for r in (contract('v1'), review('需修改'), revision('v2')):
            wc.submit(re_, r, client=ce)
        view_e = tmp / 'e.view.json'
        view_e.write_text(json.dumps(trace_server.read_trace(ROOT / re_), ensure_ascii=False, default=str),
                          encoding='utf-8')
        server_checks(tmp, e, re_)

        node, env = jsdom_env()
        if not node:
            print('  - 跳过页面渲染：没有 node 或 jsdom（装到项目 node_modules，或设 NODE_PATH）')
            print('trace view passed（只跑了 Python 部分）')
            return

        o = render(node, env, tmp, ra)
        check('暂停 · 等外部决定' in o['summary'] and '停在' in o['summary'] and '第 4 步' in o['summary'],
              '概况：暂停 · 等外部决定，停在第 4 步')
        check('外部控制' in o['summary'] and '逐步，每步停' in o['summary'], '概况：外部控制的模式')
        check('workflow.submit' in o['note'], '提示里写了外部能做什么')
        check('格式 contract' in o['flow'] and '格式 review' in o['flow'], '流程图节点上有格式名')
        check('暂停 · 第 4 步等外部' in o['flow'] and 'waiting' in cls(o, 7), '停住的节点（任务研讨）标成暂停')
        check('外部交' in o['flow'] and '换卡 · 换模型' in o['flow'], '外部交过、换过卡和模型的节点有标记')
        check(o['bars'] == 3, '耗时条只画 3 次执行，停住的不算')
        check(o['act'] is False and o['writeButtons'] == 0, '只读打开 html（没有服务）：没有「由我来做」和写按钮')
        check('第 4 步 · 暂停' in o['detail'] and '默认会这样执行' in o['detail']
              and '提示词（外部自己执行时照这个发）' in o['detail'] and '系统提示（角色卡）' in o['detail'],
              '默认选中停住的节点：摊开默认执行方式、提示词、角色卡')
        check('格式定义' in o['detail'] and 'decide' in o['detail'], '详情里能看格式定义')

        o = render(node, env, tmp, ra, line=14)
        check(o['head'].startswith('接口修改') and '换卡 ARCHITECT → ARCHITECT_GLM' in o['detail']
              and '换模型 cli:goose/glm-5.3' in o['detail'] and '外部指定执行' in o['detail'],
              '点「接口修改」：看得到换卡、换模型、来源')
        o = render(node, env, tmp, ra, line=1)
        check('外部提交结果' in o['detail'], '点「接口约定」：看得到是外部交的结果')

        o = render(node, env, tmp, rb)
        check('err' in cls(o, 1) and 'waiting' in cls(o, 1), '失败后停住的节点同时标出错和暂停')
        check('模型的原始回复' in o['detail'] and '这不是 JSON' in o['detail'] and '上次失败的原因' in o['detail'],
              '失败那次带原始回复，暂停那条带上次失败的原因')
        check('这一步上次失败' in o['note'], '概况提示里也写了上次失败')

        o = render(node, env, tmp, rc)
        check('已中止' in o['summary'] and '已中止' in o['flow'], '中止的运行：概况和结束节点都写已中止')
        o = render(node, env, tmp, rc, line=-2)
        check('外部控制的操作' in o['detail'] and 'abort' in o['detail'], '结束节点详情里列出外部控制的操作')

        o = render(node, env, tmp, rd)
        check('已完成' in o['summary'], '重构流程：概况已完成')
        check(all(k in o['flow'] for k in ('现状分析', '重构方案', '方案审查', '方案修改', '任务分配')),
              '流程图画的是 refactor_workflow.wf 的节点')
        check('现状分析员' in o['flow'] and 'REFACTOR_ANALYST' not in o['flow'], '新角色显示中文名')
        check('架构师（换 架构师·Fable）' in o['flow'], '换卡的节点写出原角色和换成的卡')
        o = render(node, env, tmp, rd, line=1)
        check(o['head'].startswith('现状分析'), '点第一个节点是现状分析')

        page_checks(node, env, view_e)
        print('trace view passed')
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    run()
