"""HTN 排查机器人的薄包装：调 htnbot/planbot/diag（排序、探针、规则都在那边），以 small_model 身份跑指令机器人。

用法：
  diagnose(path, execute=True)  -> {'mode', 'report', 'calls', 'finding', 'summary'}
  diagnose(path, execute=True, brief=True) -> {'mode', 'status', 'summary', 'candidates', 'calls'}（给模型看，短）
  diagnose(path, detail=True)   -> {'mode', 'status', 'detail'}（10 分钟内跑过就读缓存）
  summarize(result)             -> 精简文本：失败用例各一行、前 3 个可疑行（各带上下一行代码和探针取值）
  detail(result)                -> 详细文本：所有失败用例、异常全文、测试报告和探针原文
命令行：python -m tools.htn_diag <测试文件> [--detail] [--full]
  --detail 10 分钟内跑过同一个测试就读缓存，不重跑。
"""
import argparse
import json
from pathlib import Path
import re
import sys
import time

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / 'htnbot'))
from planbot.diag.session import diagnose as _diagnose, summarize as _summary  # noqa: E402

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from tools import cmd  # noqa: E402

DOMAIN = str(_ROOT / 'htnbot/examples/diagnose/domain.json')
CACHE = _ROOT / 'data/tmp/htn_cache'
CACHE_SECONDS = 600


_HEADER = re.compile(r'跑了\s*(\d+)/(\d+)\s*个用例：通过\s*(\d+)，失败\s*(\d+)，出错\s*(\d+)')
_ALL_PASSED = re.compile(r'：全部通过（\w+，[1-9]\d* 个用例）')
_REPORT_CASE = re.compile(r'^\[\d+\]\s+(失败|出错)\s+([A-Za-z_]\w*)\.([A-Za-z_]\w*)', re.M)


def _norm(r):
    code = r.get('exit_code')
    return {'status': r.get('status'), 'exit_code': code if isinstance(code, int) and not isinstance(code, bool) else 1,
            'output': r.get('output') or ''}


def make_runner(caller='small_model', run=None, fast=True):
    """把 cmd.run_as 包成排查机器人要的 runner(name, args) -> {status, exit_code(int), output}。

    fast=True 时省掉重复跑测试（每跑一遍整个测试文件就是一遍完整耗时）：
      - run_test 改成直接跑 test_report，按报告开头的「通过/失败/出错」数判断红绿，报告留着给后面那一步用；
        报告开头认不出来（比如不是 unittest 的格式）就老老实实跑 run_test。
    探针（probe）不缩小范围：只跑失败用例所在的类时，通过的用例往往太少，排序要的「失败和通过时取值不同」就比不出来了。
    """
    call = run or cmd.run_as
    reports = {}

    def runner(name, args):
        path = args.get('path')
        if fast and name == 'run_test':
            rep = _norm(call(caller, 'test_report', {'path': path}))
            if rep['status'] == 'ok' and _ALL_PASSED.search(rep['output']):
                return {'status': 'ok', 'exit_code': 0, 'output': rep['output'] + 'OK\n'}
            m = _HEADER.search(rep['output'])
            red = bool(m) and (int(m.group(4)) + int(m.group(5)) > 0 or int(m.group(1)) == 0)
            if rep['status'] == 'ok' and m and (not red or _REPORT_CASE.search(rep['output'])):
                reports[path] = rep
                # 按 unittest 的格式写出失败用例（FAIL: 方法 (类.方法)），诊断模块从这里认失败用例
                heads = []
                for kind, cls, meth in _REPORT_CASE.findall(rep['output']):
                    line = '%s: %s (%s.%s)' % ('ERROR' if kind == '出错' else 'FAIL', meth, cls, meth)
                    if line not in heads:
                        heads.append(line)
                tail = 'FAILED (failures=%s, errors=%s)' % (m.group(4), m.group(5)) if red else 'OK'
                return {'status': 'failed' if red else 'ok', 'exit_code': 1 if red else 0,
                        'output': '\n'.join(heads + ['（由 test_report 得出，没有单独跑 run_test）', tail]) + '\n'}
            if rep['status'] != 'ok' and rep['exit_code'] != 0 and '测试跑不起来' in rep['output']:
                reports[path] = rep
                return {'status': 'failed', 'exit_code': 1, 'output': '测试跑不起来（由 test_report 得出）'}
            return _norm(call(caller, name, args))
        if fast and name == 'test_report' and path in reports and set(args) <= {'path'}:
            return reports[path]
        return _norm(call(caller, name, args))
    return runner


def diagnose(path: str, execute: bool = False, allow: list[str] | None = None, max_replans: int = 3,
             brief: bool = False, detail: bool = False) -> dict:
    """排查一个测试文件。execute=False 只空跑出计划，不调指令。

    brief=True 只返回给模型看的部分：{mode, status, summary, candidates:[{file, line}], calls:[指令名]}，
    不带规划过程和每条指令的原始输出。
    detail=True 返回 {mode, status, detail}：所有失败用例、异常全文、测试报告和探针原文；
    10 分钟内排查过同一个测试就读缓存，不重跑（命令行的 --detail 同样）。
    """
    if detail:
        result = _cached(path) or diagnose(path, execute=True, allow=allow, max_replans=max_replans)
        return {'mode': 'execute', 'status': (result.get('finding') or {}).get('status'), 'detail': _detail_text(result)}
    res = _diagnose(DOMAIN, path, make_runner(), execute=execute, allow=allow, max_replans=max_replans,
                    repo_root=str(_ROOT))
    out = {'mode': 'execute' if execute else 'dry_run', 'report': res.get('report'), 'calls': res.get('calls') or [],
           'finding': res.get('finding') if execute else None}
    if execute:
        out['summary'] = summarize(out)
        CACHE.mkdir(parents=True, exist_ok=True)
        _cache_file(path).write_text(json.dumps({'finding': out['finding'], 'calls': out['calls']}, ensure_ascii=False,
                                                default=str), encoding='utf-8')
    if brief:
        f = out['finding'] or {}
        report = out['report'] or {}
        return {'mode': out['mode'], 'status': f.get('status') if execute else report.get('status'),
                'summary': out.get('summary') or summarize(out),
                'candidates': [{'file': c.get('file'), 'line': c.get('line')} for c in f.get('candidates') or []],
                'calls': [c.get('name') for c in out['calls']]}
    return out


def _one(value, limit):
    return ' '.join(str(value).split())[:limit]


def _report_text(result):
    return next((c.get('output') or '' for c in result.get('calls') or [] if c.get('name') == 'test_report'), '')


def summarize(result: dict, top: int = 3) -> str:
    f = (result or {}).get('finding') or {}
    if not f:
        return 'status: not_run（只空跑了计划，没有执行）'
    lines = ['status: %s' % f.get('status')]
    # 失败用例取自测试报告原文：用例名后面紧跟的那一行是断言或异常
    items = re.findall(r'^\[\d+\]\s+(?:失败|出错)\s+(.+)\n\s*(.+)', _report_text(result), re.M)
    if items:
        lines.append('失败用例（%d 个）:' % len(items))
        lines += ['  - %s: %s' % (_one(name, 120), _one(msg, 160)) for name, msg in items[:6]]
        if len(items) > 6:
            lines.append('  （还有 %d 个，见 --detail）' % (len(items) - 6))
    else:
        failed = [t for t in f.get('failed_tests') or [] if isinstance(t, str)]
        exc = f.get('exception') if isinstance(f.get('exception'), dict) else None
        lines.append('failed: %s' % (', '.join(failed[:3]) or '-'))
        if exc:
            lines.append('exception: %s: %s' % (exc.get('type'), _one(exc.get('message') or '', 300)))
    cands = [c for c in f.get('candidates') or [] if isinstance(c, dict)][:top]
    if cands:
        lines.append('可疑行（按可疑度排，可能是出现症状的行而不是根因）:')
    for i, c in enumerate(cands, 1):
        n = c.get('line')
        lines.append('  %d. %s:%s' % (i, c.get('file'), n))
        for row in c.get('snippet') or []:
            if isinstance(row, dict) and isinstance(n, int) and abs((row.get('line') or 0) - n) <= 1:
                lines.append('     %s %s | %s' % ('>>' if row.get('line') == n else '  ', row.get('line'),
                                                  _one(row.get('text') or '', 100)))
        # 探针在这一行取不到的名字（!NameError）不列，只留真正取到的值
        pairs = ['%s=%s' % (v.get('expr'), _one(v.get('value'), 40)) for v in c.get('probe') or []
                 if isinstance(v, dict) and not str(v.get('value')).startswith('!NameError')]
        if pairs:
            lines.append('     probe: ' + _one('; '.join(pairs), 120))
    if f.get('status') == 'passed':
        lines.append('测试通过。')
    else:
        if not cands:
            lines.append('没有定位到可疑行，请按异常和栈帧自己看。')
        lines.append('（要看所有失败用例、异常全文和栈帧：命令行加 --detail，htn.diagnose 传 detail=true；都不会重跑测试）')
    return '\n'.join(lines)


def detail(result: dict) -> str:
    f = (result or {}).get('finding') or {}
    exc = f.get('exception') if isinstance(f.get('exception'), dict) else None
    lines = ['status: %s' % f.get('status')]
    if exc:
        lines.append('异常: %s: %s' % (exc.get('type'), str(exc.get('message') or '')[:1500]))
    for call in result.get('calls') or []:
        if call.get('name') in ('test_report', 'probe'):
            out = (call.get('output') or '').strip()
            lines.append('\n== %s 原文%s ==' % (call.get('name'), '（截取前 6000 字）' if len(out) > 6000 else ''))
            lines.append(out[:6000])
    return '\n'.join(lines)


_detail_text = detail  # diagnose() 的参数也叫 detail，里面用这个名字


def _cache_file(path):
    return CACHE / (re.sub(r'[^A-Za-z0-9_.-]', '_', path) + '.json')


def _cached(path):
    """10 分钟内排查过同一个测试就返回上次的 {finding, calls}，否则 None。"""
    cache = _cache_file(path)
    try:
        if time.time() - cache.stat().st_mtime < CACHE_SECONDS:
            return json.loads(cache.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m tools.htn_diag', description='排查机器人：默认输出精简结论。')
    parser.add_argument('path')
    parser.add_argument('--detail', action='store_true',
                        help='详细信息（所有失败用例、异常全文、测试报告和探针原文）；10 分钟内跑过同一个测试就读缓存，不重跑')
    parser.add_argument('--full', action='store_true', help='调试用：完整摘要加每条指令的原始输出')
    args = parser.parse_args(argv)
    result = (_cached(args.path) if args.detail else None) or diagnose(args.path, execute=True)
    if args.detail:
        print(detail(result))
    elif args.full:
        print(_summary(result['finding']))
        for i, call in enumerate(result.get('calls') or [], 1):
            extra = {k: v for k, v in (call.get('args') or {}).items() if k != 'path'}
            print('\n[%d] %s %s -> %s (exit %s)' % (i, call.get('name'), extra or '', call.get('status'),
                                                   call.get('exit_code')))
            print((call.get('output') or '').strip()[-1500:])
    else:
        print(summarize(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
