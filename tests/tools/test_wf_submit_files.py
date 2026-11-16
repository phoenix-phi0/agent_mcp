import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""人工交代码（workflow_ctl.workfiles / submit_files）：

实现步骤停着时，人把文件交上来 → 写进这一步的工作目录 → 跑这次流程的测试命令 →
按实际改动生成实现记录 → 开始前走 submit、结束后走 approve。
路径越界、符号链接、密钥文件、测试没过、没有改动都要拒，并且工作目录保持原样。

离线假模型，不起后台进程；ENGINEER 卡改成不用 venv，测试命令是 <python> check.py。
"""
import json
import os
import shutil
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools import workflow_ctl as wc

ROOT = Path(__file__).resolve().parents[2]
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from wf_fixtures import REPLIES, impl  # noqa: E402

PASS = 'import user\nassert user.create_user("a") == 1\nprint("1 passed")\n'
FAIL = 'import sys\nprint("1 failed")\nsys.exit(1)\n'
CMD = f'{_sys.executable} check.py'   # 绝对路径开头：DSL 里以词+空格开头的右值会被当成动词调用
USER = 'def create_user(name):\n    return 1\n'


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def raises(fn, text):
    try:
        fn()
    except wc.ControlError as e:
        if text not in str(e):
            raise AssertionError(f'报错内容不对：{e}')
        return str(e)
    raise AssertionError(f'应当报错（{text}）')


def client(replies):
    c = ScriptClient(list(replies))
    c.offline = True
    return c


def snapshot(d):
    if not d.is_dir():
        return {}
    return {f.relative_to(d).as_posix(): f.read_bytes() for f in d.rglob('*') if f.is_file()}


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='wffiles-', dir=ROOT / 'data/tmp'))
    try:
        demo = tmp / 'a'
        shutil.copytree(ROOT / 'workflow_demo', demo,
                        ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
        card = demo / 'agents/ENGINEER/agent.json'
        data = json.loads(card.read_text(encoding='utf-8'))
        data['agentic']['venv'] = False
        card.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        zs = demo / 'run.zs'
        zs.write_text(zs.read_text(encoding='utf-8').replace(
            '设 project = demo', f'设 project = demo\n设 test_cmd = {CMD}'), encoding='utf-8')
        work = demo / 'work/demo'

        c = client([])
        s = wc.start(demo, client=c)
        run_id = s['run']
        for r in REPLIES[:5]:
            s = wc.submit(run_id, r, client=c)
        pend = wc.status(run_id, detail=True)['pending']
        check(pend['step'] == 6 and pend['role'] == 'ENGINEER' and pend['format'] == 'implementation',
              '前 5 步交完，停在第 6 步 ENGINEER 实现')
        check(pend['cwd'] == 'work/demo' and pend['venv'] is False and pend['test_cmd'] == CMD,
              'pending 带工作目录、venv 开关、测试命令')

        w = wc.workfiles(run_id)
        check(w['cwd'] == 'work/demo' and w['step'] == 6 and w['phase'] == 'before' and w['files'] == [],
              '拉取工作目录：一开始是空的')

        # ---- 不合格的请求：全都拒，工作目录不动
        before = snapshot(work)
        for path, text in (('../x.py', '不能有空段'), ('/etc/x', '相对路径'), ('a\\b.py', '相对路径'),
                           ('.git/config', '不能改这个目录'), ('.venv/bin/x', '不能改这个目录'),
                           ('.env', '密钥'), ('keys/server.pem', '密钥'), ('a//b.py', '空段')):
            raises(lambda: wc.submit_files(run_id, [{'path': path, 'content': 'x'}], '摘要', client=c), text)
        raises(lambda: wc.submit_files(run_id, [], '摘要', client=c), '没有要交的文件')
        raises(lambda: wc.submit_files(run_id, [{'path': 'a.py', 'content': 'x'}], '  ', client=c), '摘要要写')
        raises(lambda: wc.submit_files(run_id, [{'path': 'a.py', 'content': 1}], '摘要', client=c), '要是文本')
        raises(lambda: wc.submit_files(run_id, [{'path': 'a.py', 'content': None}], '摘要', client=c),
               '要删的文件不存在')
        raises(lambda: wc.submit_files(run_id, [{'path': 'a.py', 'content': 'x'}] * 2, '摘要', client=c), '重复')
        raises(lambda: wc.submit_files(run_id, [{'path': 'a.py', 'content': 'x'}], '摘要', step=5, client=c),
               '停在第 6 步')
        raises(lambda: wc.submit_files(run_id, [{'path': 'a.py', 'content': 'x'}], '摘要', status='做完了',
                                       client=c), '状态只能是')
        outside = tmp / 'outside'
        outside.mkdir()
        work.mkdir(parents=True, exist_ok=True)
        os.symlink(outside, work / 'link')
        raises(lambda: wc.submit_files(run_id, [{'path': 'link/x.py', 'content': 'x'}], '摘要', client=c),
               '符号链接')
        (work / 'link').unlink()
        check(snapshot(work) == before and not list(outside.iterdir()), '被拒的请求一个文件都没写')

        # ---- 测试没过：撤回，不提交
        err = raises(lambda: wc.submit_files(run_id, [{'path': 'user.py', 'content': USER},
                                                      {'path': 'check.py', 'content': FAIL}], '实现了', client=c),
                     '测试没过')
        check('1 failed' in err and '文件已撤回' in err, '报错带测试输出尾部')
        check(snapshot(work) == before, '测试没过：文件撤回，工作目录原样')
        check(wc.status(run_id)['pending']['step'] == 6, '测试没过：还停在第 6 步')
        hist = json.loads((demo / 'runs' / (Path(run_id).name[:-5] + '.ctl')).read_text(encoding='utf-8'))['history']
        check(not any(h['op'] == 'submit_files' for h in hist), '测试没过：控制文件里不留交代码的记录')

        # ---- 测试通过：写进去、生成记录、走 submit
        s = wc.submit_files(run_id, [{'path': 'user.py', 'content': USER},
                                     {'path': 'check.py', 'content': PASS},
                                     {'path': 'docs/notes.md', 'content': '说明\n'}], '实现了 create_user',
                            open_issues=['没做用户名校验'], client=c)
        rec = s['submitted_files']['record']
        check((work / 'user.py').read_text() == USER and (work / 'docs/notes.md').is_file(),
              '文件写进工作目录（含子目录）')
        check([(x['target'], x['action'], x['detail']) for x in rec['changes']]
              == [('user.py', '新增', '新文件 2 行'), ('check.py', '新增', '新文件 3 行'), ('docs/notes.md', '新增', '新文件 1 行')],
              '改动由服务器按实际文件算：三个新增，带行数')
        check(rec['verification'] == {'executed': True, 'method': CMD,
                                      'result': '通过（退出码 0）：1 passed'},
              '验证栏是服务器真跑的结果')
        check(rec['status'] == '完成' and rec['summary'] == '人工提交：实现了 create_user'
              and rec['open_issues'] == ['没做用户名校验'], '状态、摘要（标明人工提交）、遗留问题')
        st6 = s['steps'][5]
        check(st6['status'] == 'ok' and st6['source'] == 'external', '第 6 步记成外部结果')
        check(s['pending']['step'] == 7, '往下走，停在第 7 步')
        hist = json.loads((demo / 'runs' / (Path(run_id).name[:-5] + '.ctl')).read_text(encoding='utf-8'))['history']
        h = [x for x in hist if x['op'] == 'submit_files']
        check(len(h) == 1 and h[0]['files'] == ['user.py', 'check.py', 'docs/notes.md'] and h[0]['test']['rc'] == 0,
              '控制文件历史记下交了哪些文件和测试结果')

        w = wc.workfiles(run_id)
        check(sorted(x['path'] for x in w['files']) == ['check.py', 'docs/notes.md', 'user.py'], '拉取能看到交上去的文件')
        (work / '.env').write_text('SECRET=1')
        (work / 'blob.bin').write_bytes(b'\x00\x01')
        (work / '__pycache__').mkdir(exist_ok=True)
        (work / '__pycache__/x.pyc').write_bytes(b'\x00')
        w = wc.workfiles(run_id)
        check(sorted(x['path'] for x in w['files']) == ['check.py', 'docs/notes.md', 'user.py']
              and {x['path']: x['reason'] for x in w['skipped']} == {'.env': '密钥类文件', 'blob.bin': '二进制'},
              '拉取跳过密钥、二进制和缓存目录')

        # ---- 一样的内容：没有改动
        raises(lambda: wc.submit_files(run_id, [{'path': 'user.py', 'content': USER}], '摘要', client=c), '没有改动')

        # ---- 测试没过但 allow_fail：照样交，状态降为部分完成
        # （第 7 步先这样交；第 8 步再演示结束后确认）
        s = wc.submit_files(run_id, [{'path': 'check.py', 'content': FAIL}], '先交一半', allow_fail=True, client=c)
        rec = s['submitted_files']['record']
        check(rec['status'] == '部分完成' and rec['verification']['result'].startswith('失败（退出码 1）')
              and rec['changes'] == [{'target': 'check.py', 'action': '修改', 'detail': '+3 −3 行'}],
              'allow_fail：照样交，状态降为部分完成，验证写失败，改动是修改')
        check(s['pending']['step'] == 8 and s['pending']['role'] == 'QA_ENGINEER', '停在第 8 步 QA')

        # ---- 不是实现记录的步骤不能交
        raises(lambda: wc.submit_files(run_id, [{'path': 'x.py', 'content': 'x'}], '摘要', client=c), '不是实现记录')

        # ---- 结束后确认：模型交了结果，人在上面再改，approve 时保留模型的改动
        wc.configure(run_id, confirm_after=['ENGINEER'])
        c2 = client([{'decide': '需修改', 'summary': '要修', 'task': '修边界', 'checked': [
            {'item': 'x', 'result': '不满足', 'evidence': 'e'}], 'not_verified': []},
            impl('边界', fix_for='修边界')])
        s = wc.execute(run_id, wait=True, client=c2)              # 第 8 步 QA 需修改
        s = wc.execute(run_id, wait=True, client=c2)              # 第 9 步 ENGINEER 修改 → 停在结束后确认
        pend = wc.status(run_id, detail=True)['pending']
        check(pend['step'] == 9 and pend['phase'] == 'after' and pend['cwd'] == 'work/demo', '第 9 步停在结束后确认')
        raises(lambda: wc.submit_files(run_id, [{'path': 'check.py', 'content': PASS}], '修好', attempt=2,
                                       client=c2), '结果已经换了')
        s = wc.submit_files(run_id, [{'path': 'check.py', 'content': PASS},
                                     {'path': 'docs/notes.md', 'content': None}], '修好了边界', attempt=1,
                            note='模型漏了测试', client=client([]))
        rec = s['submitted_files']['record']
        check([(x['target'], x['action']) for x in rec['changes']]
              == [('边界.py', '新增'), ('check.py', '修改'), ('docs/notes.md', '删除')]
              and rec['changes'][2]['detail'] == '删掉整个文件（1 行）',
              '结束后确认：保留模型那次的改动，加上人的修改和删除')
        check(rec['fix_for'] == '修边界' and rec['verification']['result'].startswith('通过'), '带上 fix_for，测试通过')
        check(not (work / 'docs/notes.md').exists(), '删除的文件真删了')
        st9 = s['steps'][8]
        check(st9['status'] == 'ok' and s['pending']['step'] == 10, '第 9 步通过，往下到第 10 步')
        t = json.loads((ROOT / run_id).read_text(encoding='utf-8'))
        ev = [e for e in t['events'] if e.get('step') == 9 and e.get('status') == 'ok'][-1]
        check(ev['result']['summary'] == '人工提交：修好了边界', '记录里第 9 步的结果是人工改过的版本')
        run_http(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('交代码：全部通过')


def setup(tmp, name):
    demo = tmp / name
    shutil.copytree(ROOT / 'workflow_demo', demo,
                    ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    card = demo / 'agents/ENGINEER/agent.json'
    data = json.loads(card.read_text(encoding='utf-8'))
    data['agentic']['venv'] = False
    card.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    zs = demo / 'run.zs'
    zs.write_text(zs.read_text(encoding='utf-8').replace(
        '设 project = demo', f'设 project = demo\n设 test_cmd = {CMD}'), encoding='utf-8')
    c = client([])
    run_id = wc.start(demo, client=c)['run']
    for r in REPLIES[:5]:
        wc.submit(run_id, r, client=c)
    return demo, run_id


def run_http(tmp):
    """查看器的接口：GET /api/workfiles、POST /api/submit_files（同一套校验，只读服务不给）。"""
    from tools import trace_server as ts
    demo, run_id = setup(tmp, 'h')
    runs = demo / 'runs'
    name = Path(run_id).name

    def get(write):
        code, _, body = ts.route(runs, 'GET', '/api/workfiles', f'name={name}', {'host': '127.0.0.1:1'}, b'',
                                 write=write)
        return code, json.loads(body)

    def post(obj, write=True):
        raw = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        code, _, body = ts.route(runs, 'POST', '/api/submit_files', '',
                                 {'host': '127.0.0.1:1', 'content-type': 'application/json',
                                  'content-length': str(len(raw))}, raw, write=write)
        return code, json.loads(body)

    code, out = get(False)
    check(code == 403, '只读的查看服务不给拉工作目录')
    code, out = get(True)
    check(code == 200 and out['cwd'] == 'work/demo' and out['step'] == 6, '能写的查看服务：拉取工作目录')
    code, out = post({'name': name, 'files': [{'path': 'user.py', 'content': USER}]}, write=False)
    check(code == 403, '只读的查看服务不收代码')
    code, out = post({'name': name, 'files': [{'path': '../x.py', 'content': 'x'}], 'summary': 's'})
    check(code == 400 and '不能有空段' in out['error'], '越界路径：400')
    code, out = post({'name': name, 'files': [{'path': 'user.py', 'content': USER},
                                              {'path': 'check.py', 'content': PASS}], 'summary': '网页交的',
                      'test_cmd': 'rm -rf /'})
    rec = out['status']['submitted_files']['record']
    check(code == 200 and out['ok'] and rec['verification']['method'] == CMD,
          '交代码成功；请求里夹带的 test_cmd 不起作用，用的是流程自己的测试命令')
    hist = json.loads((runs / (name[:-5] + '.ctl')).read_text(encoding='utf-8'))['history']
    check([h['actor'] for h in hist if h['op'] == 'submit_files'] == ['viewer'], '来源记成 viewer')


if __name__ == '__main__':
    run()
