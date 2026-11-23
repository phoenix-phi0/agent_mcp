import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""Muse 当模型用（tools/muse_backend.py，模型名 cli:muse）和工程师卡 ENGINEER_MUSE。不连真 Muse：
mbatch 的任务目录换成临时目录，「等一轮轮询」换成一个假 Muse（认领、写回预设的回复）。

1. run_job：投任务 → 被认领 → 写回 → 取回回复和用量；没人认领超时取消；认领后不写回超时取消；做失败、回复为空、被取消都报错。
2. submit：最后的回复里取 JSON 按格式校验；不合格带着错误重投；JSON 套在围栏里、前后有话也取得出；
   agentic 时任务的 cwd 是项目目录，提示词里写明目录和虚拟环境；用完次数还不合格报错。
3. 接入：config 认 cli:muse（不能选模型）；submit_call 和普通问答都分派到 Muse；
   cli:muse 的卡能加载、走按格式交；写 allowed_tools / sandbox / effort 报错。
（ENGINEER_MUSE 现在是 model=muse，流程停给 Muse 自己交：见 test_muse_flow.py）
"""
import json
import shutil
import tempfile
from pathlib import Path

from tools import mbatch, muse_backend as mb

ROOT = Path(__file__).resolve().parents[2]
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_wf_project import impl  # noqa: E402  合格的实现记录


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def raises(fn, words, msg, exc=mb.MuseError):
    try:
        fn()
    except exc as e:
        check(all(w in str(e) for w in words), f'{msg}（{e}）')
        return
    raise AssertionError(msg + '：没有报错')


class FakeMuse:
    """替换 muse_backend._sleep：每「睡」一次，按剧本处理队列里的任务。
    replies 里每项是 str（写回 done）、('fail', 错误) 或 None（认领了不写回）。claim=False 时一直不认领。"""

    def __init__(self, replies=(), claim=True):
        self.replies = list(replies)
        self.claim = claim
        self.prompts = []
        self.cwds = []
        self.sleeps = 0

    def __call__(self, seconds):
        self.sleeps += 1
        if not self.claim:
            return
        for q in mbatch.queued():
            d = mbatch.claim(q['job_id'])
            self.prompts.append(d['tasks'][0]['prompt'])
            self.cwds.append(d['cwd'])
            r = self.replies.pop(0) if self.replies else None
            if r is None:
                continue
            if isinstance(r, tuple):
                mbatch.set_task(d['id'], 0, error=r[1], status='failed')
            else:
                mbatch.set_task(d['id'], 0, output=r)
            mbatch.finish(d['id'])


def use(fake):
    mb._sleep = fake
    return fake


def test_run_job(tmp):
    work = tmp / 'w'
    work.mkdir()
    f = use(FakeMuse(['你好，我是 Muse']))
    out, u = mb.run_job('打个招呼', cwd=work, timeout=60, poll=0)
    check(out == '你好，我是 Muse' and u['backend'] == 'muse' and u['job'] and f.prompts == ['打个招呼']
          and f.cwds == [str(work.resolve())], '投任务 → 认领 → 写回：拿到回复，任务在指定目录做')
    check(mbatch.status(u['job'])['status'] == 'done', 'mbatch 里这条是 done')
    use(FakeMuse(claim=False))
    raises(lambda: mb.run_job('没人接', cwd=work, claim_wait=0, poll=0), ['没有认领', '已取消'], '一直没人认领：超时取消并报错')
    check(mbatch.jobs(1)[0]['status'] == 'cancelled', '没认领的那条在 mbatch 里是 cancelled（Muse 之后看到就不做）')
    use(FakeMuse([None]))
    raises(lambda: mb.run_job('认领了不写回', cwd=work, timeout=0, poll=0), ['没写回', '已取消'], '认领后不写回：超时取消并报错')
    use(FakeMuse([('fail', '跑测试时机器没空间了')]))
    raises(lambda: mb.run_job('会失败', cwd=work, poll=0), ['没做成', '机器没空间了'], 'Muse 报失败：错误原文带出来')
    use(FakeMuse(['   ']))
    raises(lambda: mb.run_job('空回复', cwd=work, poll=0), ['回复是空的'], '回复为空：报错')


def test_last_json():
    j = {'a': 1, 'b': {'c': [1, 2]}}
    check(mb.last_json(json.dumps(j)) == j, '整条就是 JSON')
    check(mb.last_json('做完了，结果如下：\n```json\n' + json.dumps(j) + '\n```\n以上。') == j, '围栏里、前后有话：取得出')
    check(mb.last_json('先 {"x": 1} 后 ' + json.dumps(j)) == j, '有几个 JSON 对象：取最后一个')
    check(mb.last_json('没有 JSON') is None and mb.last_json('{坏的') is None, '没有 JSON：None')


def test_submit(tmp):
    schema = json.loads((ROOT / 'workflow_demo/formats/implementation.json').read_text(encoding='utf-8'))
    proj = tmp / 'proj'
    proj.mkdir()
    good = impl('muse_core')
    f = use(FakeMuse(['我写完了，但是忘了按格式', '交结果：\n```json\n' + json.dumps(good, ensure_ascii=False) + '\n```']))
    r, u = mb.submit('任务：实现 core', '你是工程师', schema,
                     agentic={'cwd': proj, 'timeout': 60, 'venv': True})
    check(r == good and u['tries'] == 2 and len(u['jobs']) == 2, '第一次回复里没有 JSON → 带着错误重投 → 第二次合格')
    p1, p2 = f.prompts
    check(str(proj) in p1 and str(proj / '.venv/bin/python') in p1 and '你是工程师' in p1 and '任务：实现 core' in p1
          and '只写一个 JSON 对象' in p1 and '"verification"' in p1, '提示词里有角色说明、工作目录、虚拟环境、任务和格式')
    check('上一次交的不合格' in p2 and '找不到 JSON' in p2 and '忘了按格式' in p2, '重投时带上上一次的回复和问题')
    check(f.cwds == [str(proj.resolve())] * 2, 'agentic：任务的 cwd 是项目目录')
    bad = dict(good)
    del bad['verification']
    use(FakeMuse([json.dumps(bad), json.dumps(bad)]))
    raises(lambda: mb.submit('任务', '', schema, agentic={'cwd': proj}), ['2 次', 'verification'],
           '两次都缺字段：报错，说出缺了什么')


def test_wiring(tmp):
    from tools import config, llm_router
    spec = config.parse_model('cli:muse')
    check(spec.provider == 'muse' and spec.backend.ready, 'config 认 cli:muse')
    try:
        config.parse_model('cli:muse/opus')
    except config.ModelNameError as e:
        check('不能选模型' in str(e), f'cli:muse 不能选模型（{e}）')
    else:
        raise AssertionError('cli:muse/opus 应报错')
    calls = []
    real_submit, real_complete = mb.submit, mb.complete
    try:
        mb.submit = lambda prompt, system, schema, agentic=None, timeout=None, **kw: (
            calls.append(('submit', prompt, agentic)) or ({'ok': True}, {'backend': 'muse', 'tries': 1}))
        r = llm_router.submit_call('做吧', '系统', 'cli:muse', {'type': 'object'}, agentic={'cwd': tmp})
        check(r == {'ok': True} and calls[-1][0] == 'submit' and llm_router.LAST_USAGE['value']['backend'] == 'muse',
              'submit_call 遇到 cli:muse 交给 Muse，用量记上')
        mb.submit = lambda *a, **k: (_ for _ in ()).throw(mb.MuseError('15 分钟没认领'))
        raises(lambda: llm_router.submit_call('做吧', '', 'cli:muse', {}), ['muse', '没认领'], 'Muse 出错：转成后端错误',
               exc=llm_router.BackendError)
        mb.complete = lambda prompt, system, timeout=None: f'回复：{prompt}'
        check(llm_router._BACKENDS['muse'].complete('你好', None, '') == '回复：你好', '普通问答（问 … 用 cli:muse）也分派到 Muse')
    finally:
        mb.submit, mb.complete = real_submit, real_complete


def test_card(tmp):
    from verbs.workflow import _agents as ag
    from tools.dsl import DSLEngine
    from dsl.client import ScriptClient
    from tools.dsl_core import DSLError
    demo = tmp / 'd'
    shutil.copytree(ROOT / 'workflow_demo', demo, ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    # cli:muse（把 Muse 当慢模型、经 mbatch 问答）的卡：拿 ENGINEER_MUSE 改一张临时的。
    # ENGINEER_MUSE 本身是 model=muse（流程停给 Muse），见 test_muse_flow.py
    src = demo / 'agents/ENGINEER_MUSE'
    shutil.copytree(src, demo / 'agents/MUSE_CLI')
    card = demo / 'agents/MUSE_CLI/agent.json'
    base = json.loads(card.read_text(encoding='utf-8'))
    base.update(model='cli:muse', agentic=dict(base['agentic'], timeout=2400))
    card.write_text(json.dumps(base, ensure_ascii=False), encoding='utf-8')
    e = DSLEngine(client=ScriptClient([]), workdir=demo, verbs_root=ROOT / 'verbs', verbose=False)
    e.vars['project'] = 'muse_proj'
    prof = ag.load_agent(e, 'MUSE_CLI')
    check(prof['model'] == 'cli:muse' and prof['agentic']['cwd'] == (demo / 'work/muse_proj').resolve()
          and prof['agentic']['venv'] is True and prof['agentic']['allowed_tools'] == []
          and prof['agentic']['timeout'] == 2400,
          'cli:muse 的卡能加载：在 work/{project} 里干活，用项目 venv')
    online = DSLEngine(client=ScriptClient([]), workdir=demo, verbs_root=ROOT / 'verbs', verbose=False)
    online.client.offline = False
    check(ag._uses_submit(online, prof, ('implementation', {})) is True, '真跑时走按格式交（submit_call → Muse）')
    for extra, words, msg in (({'agentic': dict(base['agentic'], allowed_tools=['Read'])}, ['allowed_tools'], '写 allowed_tools'),
                              ({'agentic': dict(base['agentic'], sandbox='workspace-write')}, ['sandbox'], '写 sandbox'),
                              ({'effort': 'high'}, ['effort'], '写 effort')):
        card.write_text(json.dumps(dict(base, **extra), ensure_ascii=False), encoding='utf-8')
        try:
            ag.load_agent(e, 'MUSE_CLI')
        except DSLError as err:
            check(all(w in str(err) for w in words), f'cli:muse 的卡{msg}：报错（{err}）')
        else:
            raise AssertionError(f'cli:muse 的卡{msg}应报错')
    card.write_text(json.dumps(base, ensure_ascii=False), encoding='utf-8')


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='muse-', dir=ROOT / 'data/tmp'))
    old_jobs, old_sleep = mbatch.JOBS, mb._sleep
    mbatch.JOBS = folder / 'jobs'          # 不碰真队列：真 Muse 不会认领这些
    try:
        for case in (test_run_job, test_submit, test_wiring, test_card):
            tmp = folder / case.__name__
            tmp.mkdir()
            print(case.__name__)
            case(tmp)
        print('test_last_json')
        test_last_json()
    finally:
        mbatch.JOBS, mb._sleep = old_jobs, old_sleep
        shutil.rmtree(folder, ignore_errors=True)
    print('Muse 后端：全部通过')


if __name__ == '__main__':
    run()
