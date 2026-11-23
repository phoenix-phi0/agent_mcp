import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""外部交的结果只给交的那一步用。

运行 20261123-090353 出过的事：Muse 给第 10 步「模块返工」交了实现记录；之后记录回退重跑，
第 10 步变成了「模块任务分配」，旧的实现记录被它拿去用，格式不符，整个运行报错。
现在交的时候记下步骤名和行号，取用时对不上就不用（照常往下走）；旧控制文件没记的照旧只按步号。
"""
from tools import workflow_ctl as wc


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


REQ = {'step': 10, 'line': 37, 'name': '模块任务分配', 'role': 'ARCHITECT', 'task': '分配'}


def cfg_with(entry):
    return {'mode': 'auto', 'max_attempts': 4, 'roles': {}, 'models': {}, 'go': {}, 'notes': {},
            'submitted': {'10': {'status': '完成'}}, 'history': [entry]}


def decide(cfg, req=REQ):
    return wc._Control(cfg).decide(dict(req))


def run():
    stale = cfg_with({'op': 'submit', 'step': 10, 'name': '模块返工', 'line': 52, 'actor': 'mcp:muse', 'at': 'x'})
    d = decide(stale)
    check(d['action'] != 'result', f'交给旧第 10 步「模块返工」的结果，不给现在的第 10 步「模块任务分配」用（{d["action"]}）')

    same = cfg_with({'op': 'submit', 'step': 10, 'name': '模块任务分配', 'line': 37, 'actor': 'mcp:muse', 'at': 'x'})
    d = decide(same)
    check(d['action'] == 'result' and d['result'] == {'status': '完成'} and d['confirm'][0]['actor'] == 'mcp:muse',
          '名字和行号都对得上：照常用交来的结果，来源记 mcp:muse')

    moved = cfg_with({'op': 'submit', 'step': 10, 'name': '模块任务分配', 'line': 99, 'actor': 'x', 'at': 'x'})
    check(decide(moved)['action'] != 'result', '同名但行号不同（脚本里另一处同名步骤）：也不用')

    old = cfg_with({'op': 'submit', 'step': 10, 'actor': 'workflow_ctl', 'at': 'x'})
    check(decide(old)['action'] == 'result', '旧控制文件的 history 没记名字和行号：照旧按步号用')

    # submit 往 history 里记名字和行号
    logged = {'history': []}
    wc._log(logged, 'submit', step=10, actor='mcp:muse', name='模块返工', line=52)
    check(logged['history'][0]['name'] == '模块返工' and logged['history'][0]['line'] == 52, '_log 记下了名字和行号')
    src = (_pl.Path(wc.__file__)).read_text(encoding='utf-8')
    check('_log(cfg, "submit", step=pend["step"], actor=actor, name=pend.get("name"), line=pend.get("line"))' in src,
          'submit 交结果时把这一步的名字和行号写进 history')
    print('外部交的结果只给交的那一步用：全部通过')


if __name__ == '__main__':
    run()
