import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""会议页要的后端：启动时传入口参数（vars），查看器挂会议页（<前缀>/meeting/）。离线，不调真模型。

1. workflow_ctl.start 带 vars 启动 meeting.zs：议题进了提示词；每次回放都带着（人交完发言后接着跑，议题还在）；
   status 里看得到 vars。缺必填参数、多给参数、参数名不对、值不是字符串：启动时就报 ControlError。
2. 查看器：入口列表带上 meeting.zs 的参数声明；POST /api/start 带 vars 开一场全是人的会，GET /api/run 看得到停在人那里；
   不带 vars 启动报 400 说缺什么。
4. 会后「交给流程」：run_project / run_frontend / run_refactor 声明了 content（重构是 goal）和 project，
   传了用传的、不传用脚本里的默认值，入口列表报出默认值；没声明的参数不能传。
3. 会议页静态文件：/meeting 跳 /meeting/，/meeting/ 给 index.html（加上实时、可写标记），js/css 带对的类型，
   越出目录、不存在、不认识的后缀都 404；只读服务不加可写标记。
"""
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from dsl.client import ScriptClient
from tools import trace_server as ts
from tools import workflow_ctl as wc

ROOT = Path(__file__).resolve().parents[2]


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def speech(text, agree=False):
    return {'speech': text, 'agree': agree, 'ask': '', 'question': ''}


def copy(tmp):
    demo = tmp / 'm'
    shutil.copytree(ROOT / 'workflow_demo', demo, ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    human_b = demo / 'agents/HUMAN_B'
    human_b.mkdir()
    (human_b / 'agent.json').write_text(json.dumps({'model': 'human', 'cost': 1, 'description': '第二个人'}), encoding='utf-8')
    (human_b / 'SOUL.md').write_text('第二个参会的人。', encoding='utf-8')
    return demo


def raises(fn, words, msg):
    try:
        fn()
    except wc.ControlError as e:
        check(all(w in str(e) for w in words), f'{msg}（{e}）')
        return
    raise AssertionError(msg + '：没有报错')


def test_ctl(tmp):
    demo = copy(tmp)
    c = ScriptClient([speech('我主张纯 HTML/JS'),
                      {'done': '是', 'disagreements': [], 'summary': '一致'},
                      {'decision': '用纯 HTML/JS', 'reasons': ['简单'], 'dissent': [], 'todo': [], 'summary': '定了'}])
    c.offline = True
    v = {'topic': '会议页用什么技术做', 'attendees': 'ARCHITECT,HUMAN'}
    s = wc.start(demo, entry='meeting.zs', mode='auto', wait=True, client=c, vars=v)
    check(s['status'] == 'waiting' and s['pending']['role'] == 'HUMAN', '带 vars 启动：ARCHITECT 发言后轮到人')
    check('会议页用什么技术做' in c.calls[0]['prompt'], '议题从 vars 进了提示词')
    check(s['vars'] == v, 'status 里有 vars')
    s = wc.submit(s['run'], speech('同意', agree=True), wait=True, client=c)
    check(s['status'] == 'done' and '会议页用什么技术做' in c.calls[-1]['prompt'],
          '人交完以后接着回放跑到底，议题还在（每次回放都带 vars）')
    check('背景' not in c.calls[0]['prompt'] or '无' in c.calls[0]['prompt'], '没传 background 用声明里的默认值')
    raises(lambda: wc.start(demo, entry='meeting.zs', vars={'attendees': 'HUMAN'}), ['topic'], '缺必填参数：启动时报')
    raises(lambda: wc.start(demo, entry='meeting.zs', vars={'topic': 'x', 'attendees': 'HUMAN', 'agenda': 'y'}),
           ['agenda'], '多给了声明里没有的参数：启动时报')
    raises(lambda: wc.start(demo, entry='meeting.zs', vars={'议题': 'x'}), ['变量名'], '参数名不是英文变量名：报')
    raises(lambda: wc.start(demo, entry='meeting.zs', vars={'topic': 1, 'attendees': 'HUMAN'}), ['字符串'], '值不是字符串：报')
    raises(lambda: wc.start(demo, entry='meeting.zs', vars=['topic']), ['对象'], 'vars 不是对象：报')
    c2 = ScriptClient([])
    c2.offline = True
    s = wc.start(demo, entry='run_meeting.zs', mode='step', client=c2)
    check(s['status'] == 'waiting' and s['vars'] == {}, '没声明参数的老入口不传 vars 照常启动')


def test_handoff_entries(tmp):
    """会后「交给流程」：常用入口声明了可传参数，传了就用、不传用「或」后面的默认值；入口列表报出默认值。"""
    demo = copy(tmp)
    entries = {e['entry']: e for e in ts.list_entries(demo)}
    for entry, var in (('run_project.zs', 'content'), ('run_frontend.zs', 'content'), ('run_refactor.zs', 'goal')):
        params = {p['name']: p for p in entries[entry]['params']}
        check({var, 'project'} <= set(params) and not any(p['required'] for p in params.values())
              and params[var]['default'] and params['project']['default'],
              f'{entry}：{var}、project 可选，入口列表报出脚本里的默认值')
        c = ScriptClient([])
        c.offline = True
        s = wc.start(demo, entry=entry, mode='step', client=c,
                     vars={var: '会议结论：只做列表页\n理由：先跑通', 'project': 'from_meeting1'})
        task = json.dumps(s['pending'], ensure_ascii=False)
        check('会议结论：只做列表页' in task and 'from_meeting1' in task and not c.calls,
              f'{entry}：传的需求和项目名进了第一步（多行也行），停在第一步前没调模型')
        s = wc.start(demo, entry=entry, mode='step', client=c)
        check(params[var]['default'][:20] in json.dumps(s['pending'], ensure_ascii=False),
              f'{entry}：不传就用默认值，和改之前一样')
    raises(lambda: wc.start(demo, entry='run_project.zs', vars={'budget': '3'}), ['budget'],
           '没声明的参数不能传（预算、角色这些照旧写在脚本里）')


def test_submit_while_worker_exits(tmp):
    """记录刚变成 waiting、后台进程还没退出的那一刻交结果：等它退出再收，不报「后台还在跑」。"""
    import subprocess
    import sys
    demo = copy(tmp)
    c = ScriptClient([])
    c.offline = True
    s = wc.start(demo, entry='meeting.zs', mode='auto', wait=True, client=c,
                 vars={'topic': '收尾', 'attendees': 'HUMAN', 'moderator': 'HUMAN'})
    run = Path(s['run']) if Path(s['run']).is_absolute() else ROOT / s['run']
    cf = run.with_suffix('.ctl')
    # 假的后台进程：命令行里带 workflow_ctl，0.8 秒后退出（模拟正在收尾的 advance）
    fake = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(0.8)', 'workflow_ctl', 'advance'])
    try:
        cfg = json.loads(cf.read_text(encoding='utf-8'))
        cfg['worker'] = fake.pid
        cf.write_text(json.dumps(cfg, ensure_ascii=False), encoding='utf-8')
        t0 = time.time()
        s = wc.submit(run, speech('收尾时交的'), wait=True, client=c)
        check(s['status'] == 'waiting' and s['pending']['name'] == '主持判断' and time.time() - t0 >= 0.5,
              '后台进程还在收尾时交：等它退出后收下，会议接着走到主持判断')
    finally:
        fake.kill()
        fake.wait()


def test_embedded_meeting(tmp):
    """流程里的会：前端流程入口能传评审会名单和主持人；人进了名单，评审会轮到人就停下；运行清单标出这是有会议的运行。"""
    sys_path = str(Path(__file__).resolve().parent)
    import sys
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from test_wf_frontend import design
    demo = copy(tmp)
    params = {p['name']: p for p in {e['entry']: e for e in ts.list_entries(demo)}['run_frontend.zs']['params']}
    check(params['review_attendees']['default'] == 'DESIGNER,ARCHITECT,REVIEWER_GPT' and 'moderator' in params,
          'run_frontend.zs：评审会名单和主持人可传，名单默认值照旧')
    c = ScriptClient([design('v1')])
    c.offline = True
    s = wc.start(demo, entry='run_frontend.zs', mode='auto', wait=True, client=c,
                 vars={'review_attendees': 'HUMAN,REVIEWER_GPT', 'moderator': 'HUMAN', 'project': 'fe_embed1'})
    check(s['status'] == 'waiting' and s['pending']['role'] == 'HUMAN' and s['pending']['name'] == '评审发言',
          '设计交出来以后，评审会第一个轮到人：停下等')
    rows = {r['name']: r for r in ts.list_runs(demo / 'runs')}
    run = Path(s['run']).name
    check(rows[run]['meeting'] == 'embedded', '运行清单把它标成「流程里有会」（meeting=embedded）')
    c2 = ScriptClient([])
    c2.offline = True
    s2 = wc.start(demo, entry='meeting.zs', mode='auto', wait=True, client=c2,
                  vars={'topic': '单独的会', 'attendees': 'HUMAN', 'moderator': 'HUMAN'})
    s3 = wc.start(demo, entry='run_project.zs', mode='step', client=c2)
    rows = {r['name']: r for r in ts.list_runs(demo / 'runs')}
    check(rows[Path(s2['run']).name]['meeting'] == 'standalone' and rows[Path(s3['run']).name]['meeting'] is None,
          '单独开的会是 standalone；没有会议步骤的运行是 None')


def call(runs, method, path, body=None, write=True):
    data = json.dumps(body).encode() if body is not None else b''
    headers = {'Content-Type': 'application/json', 'Content-Length': str(len(data)),
               'Origin': 'http://127.0.0.1', 'Host': '127.0.0.1'}
    code, head, out = ts.route(runs, method, path, '', headers, data, write=write)
    return code, head, out


def wait_for(fn, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.2)
    raise AssertionError('等超时')


def test_server(tmp):
    demo = copy(tmp)
    runs = demo / 'runs'
    runs.mkdir(exist_ok=True)
    entries = {e['entry']: e for e in ts.list_entries(demo)}
    check(entries['meeting.zs']['params'] == [
        {'name': 'topic', 'required': True, 'default': None}, {'name': 'attendees', 'required': True, 'default': None},
        {'name': 'background', 'required': False, 'default': '无'}, {'name': 'moderator', 'required': False, 'default': 'MODERATOR'}],
        '入口列表带上 meeting.zs 的参数声明（必填、默认值）')
    check(entries['run_meeting.zs']['params'] == [], '没声明参数的入口 params 为空')
    code, _, out = call(runs, 'POST', '/api/start', {'entry': 'meeting.zs', 'mode': 'auto'})
    check(code == 400 and 'topic' in json.loads(out)['error'], '不带 vars 启动：400，说缺 topic')
    code, _, out = call(runs, 'POST', '/api/start', {'entry': 'meeting.zs', 'mode': 'auto', 'vars': 'x'})
    check(code == 400, 'vars 不是对象：400')
    code, _, out = call(runs, 'POST', '/api/start', {'entry': 'meeting.zs', 'mode': 'auto',
                                                     'vars': {'topic': '周会', 'attendees': 'HUMAN,HUMAN_B', 'moderator': 'HUMAN'}})
    body = json.loads(out)
    check(code == 200 and body['ok'], f'带 vars 开一场全是人的会（{body.get("error")}）')
    name = body['name']
    t = wait_for(lambda: (lambda d: d if d.get('status') == 'waiting' else None)(ts.read_trace(runs / name)))
    check(t['pending']['role'] == 'HUMAN' and t['pending']['name'] == '发言', '停在第一个人发言，不调模型')
    check(t['_control']['vars'] == {'topic': '周会', 'attendees': 'HUMAN,HUMAN_B', 'moderator': 'HUMAN'},
          '运行记录的 _control 里带着启动参数（页面显示议题、参会名单用）')
    code, _, out = call(runs, 'POST', '/api/submit', {'name': name, 'result': speech('先说我的看法')})
    check(code == 200, '人交了发言')
    t = wait_for(lambda: (lambda d: d if d.get('status') == 'waiting' and d['pending']['role'] == 'HUMAN_B' else None)(
        ts.read_trace(runs / name)))
    check('周会' in json.dumps(t['pending'], ensure_ascii=False) and '先说我的看法' in json.dumps(t['pending'], ensure_ascii=False),
          '轮到第二个人：待办里看得到议题和前面的发言')


def test_static(tmp):
    web = tmp / 'web'
    (web / 'js').mkdir(parents=True)
    (web / 'index.html').write_text('<html><head><title>会议</title></head><body>会议页</body></html>', encoding='utf-8')
    (web / 'js/app.js').write_text('export const x = 1;', encoding='utf-8')
    (web / 'notes.txt').write_text('不给', encoding='utf-8')
    (tmp / 'secret.html').write_text('<head></head>外面', encoding='utf-8')
    runs = tmp / 'runs'
    runs.mkdir()
    old = os.environ.get('TRACE_MEETING_DIR')
    os.environ['TRACE_MEETING_DIR'] = str(web)
    try:
        code, head, _ = ts.route(runs, 'GET', '/t0k/meeting', '', {}, b'', token='t0k')
        check(code == 301 and head['Location'] == '/t0k/meeting/', '/meeting 跳到 /meeting/（带前缀和口令）')
        code, head, out = ts.route(runs, 'GET', '/t0k/meeting/', '', {}, b'', token='t0k', write=True)
        check(code == 200 and b'trace-write' in out and b'trace-live' in out and head['Content-Type'].startswith('text/html'),
              '/meeting/ 给 index.html，加上实时、可写标记')
        code, _, out = ts.route(runs, 'GET', '/t0k/meeting/', '', {}, b'', token='t0k', write=False)
        check(b'trace-live' in out and b'trace-write' not in out, '只读服务不加可写标记')
        code, head, _ = ts.route(runs, 'GET', '/t0k/meeting/js/app.js', '', {}, b'', token='t0k')
        check(code == 200 and head['Content-Type'].startswith('text/javascript'), 'js 带对的类型')
        for bad in ('/t0k/meeting/../secret.html', '/t0k/meeting/%2e%2e/secret.html', '/t0k/meeting/nope.js',
                    '/t0k/meeting/notes.txt'):
            code, _, _ = ts.route(runs, 'GET', bad, '', {}, b'', token='t0k')
            check(code == 404, f'{bad} → 404')
        code, head, _ = ts.route(runs, 'GET', '/meeting/index.html', '', {}, b'', token='t0k')
        check(code == 302 and head['Location'].startswith('/login?next='), '不带口令、没登录：/meeting/index.html 跳登录页')
    finally:
        if old is None:
            os.environ.pop('TRACE_MEETING_DIR', None)
        else:
            os.environ['TRACE_MEETING_DIR'] = old


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mstart-', dir=ROOT / 'data/tmp') as folder:
        for case in (test_ctl, test_server, test_static, test_handoff_entries, test_submit_while_worker_exits,
                     test_embedded_meeting):
            tmp = Path(folder) / case.__name__
            tmp.mkdir()
            print(case.__name__)
            case(tmp)
    print('会议启动和会议页：全部通过')


if __name__ == '__main__':
    run()
