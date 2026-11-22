"""Translate command results into diagnostic facts and a compact finding."""
import builtins
import json
import keyword
from pathlib import Path
import re
import sys

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / 'htnbot'))
from planbot import core, executor, planner  # noqa: E402
from tools import cmd  # noqa: E402

_LOC = re.compile(r'([A-Za-z0-9_./-]+\.py):(\d+)')
_ROW = re.compile(r'^\s*(\d+)\.\s+([A-Za-z0-9_./-]+\.py):(\d+)\s+([\d.]+)\b', re.M)


def _location(file, line):
    try:
        p = (_ROOT / file).resolve()
        return p.relative_to(_ROOT).as_posix(), int(line)
    except (ValueError, OSError):
        return None


def _candidate(file, line, score=None, trace=()):
    code = []
    try:
        lines = (_ROOT / file).read_text(encoding='utf-8', errors='replace').splitlines()
        code = [{'line': i, 'text': lines[i - 1]} for i in range(max(1, line - 2), min(len(lines), line + 2) + 1)]
    except OSError:
        pass
    return {'file': file, 'line': line, 'score': score, 'in_traceback': (file, line) in trace,
            'code': code, 'values': []}


def make_runner(caller='small_model', run=None):
    """Create an isolated diagnostic session; run has the run_as signature."""
    run = cmd.run_as if run is None else run
    state, calls = {}, []

    def runner(name, args):
        if name == 'diag_state':
            keys = ('ran', 'result', 'report', 'locate', 'probe', 'cause')
            files = [dict(file=p, **{k: e[k] for k in keys}) for p, e in sorted(state.items())]
            return {'status': 'ok', 'exit_code': 0, 'output': json.dumps({'files': files})}
        path = args.get('path')
        entry = state.setdefault(path, {'ran': 'no', 'result': '', 'report': 'no', 'locate': 'no',
                                        'probe': 'no', 'cause': 'no', 'trace': set(), 'candidates': [],
                                        'report_at': None, 'failing': [], 'error': '', 'kind': 'report_only'})
        actual_args = {'path': path}
        if name == 'probe':
            targets = entry['candidates'][:3]
            if not targets and entry['report_at']:
                targets = [_candidate(*entry['report_at'], trace=entry['trace'])]
            if not targets:
                return {'status': 'failed', 'exit_code': 2, 'output': 'no location to probe'}
            source = ' '.join(next((row['text'] for row in c['code'] if row['line'] == c['line']), '') for c in targets)
            names = [w for w in dict.fromkeys(re.findall(r'(?<![\w.])[A-Za-z_]\w*', source))
                     if not keyword.iskeyword(w) and w not in dir(builtins) and w != 'self'][:8]
            actual_args.update(at=['%s:%s' % (c['file'], c['line']) for c in targets], exprs=names or ['type(self)'])
        result = run(caller, name, actual_args)
        output = result.get('output') or ''
        exit_code = result.get('exit_code')
        exit_code = int(exit_code) if isinstance(exit_code, int) else 1
        status = result['status']
        calls.append({'name': name, 'args': actual_args.copy(), 'status': status, 'exit_code': exit_code, 'output': output})
        if name == 'run_test':
            entry['ran'], entry['result'] = 'yes', 'green' if exit_code == 0 else 'red'
        elif name == 'test_report':
            locations = [p for f, n in _LOC.findall(output) if (p := _location(f, n))]
            entry['trace'] = set(locations)
            match = re.search(r'(?:最内层仓库内帧|位置)\s+([A-Za-z0-9_./-]+\.py):(\d+)', output)
            entry['report_at'] = _location(*match.groups()) if match else (locations[0] if locations else None)
            entry['failing'] = re.findall(r'^\[\d+\]\s+(?:失败|出错)\s+(.+)$', output, re.M)
            error = re.search(r'^\s*((?:[\w.]+(?:Error|Exception)|AssertionError|Failed|Error)(?::[^\n]*)?)', output, re.M)
            fatal = re.search(r'测试跑不起来——([^\n]+)', output)
            entry['error'] = (fatal.group(1) if fatal else error.group(1) if error else '')[:400]
            if status == 'ok' or entry['report_at']:
                entry['report'] = 'yes'
            if exit_code != 0 and entry['report_at']:
                entry['cause'], entry['kind'] = 'yes', 'cannot_run'
                entry['candidates'] = [_candidate(*entry['report_at'], trace=entry['trace'])]
        elif name == 'locate':
            entry['locate'] = 'yes'
            rows = []
            if status == 'ok':
                for rank, file, line, score in _ROW.findall(output):
                    pos = _location(file, line)
                    if pos:
                        rows.append((pos, float(score), int(rank)))
            # Python's stable sort preserves the original order for equal keys.
            rows.sort(key=lambda row: (-row[1], row[0] not in entry['trace']))
            if rows:
                count = min(5, max(3, sum(row[1] == rows[0][1] for row in rows)))
                entry['candidates'] = [_candidate(*pos, score=score, trace=entry['trace']) for pos, score, rank in rows[:count]]
                entry['cause'], entry['kind'] = 'yes', 'locate'
        elif name == 'probe':
            entry['probe'] = 'yes'
            entry['cause'] = 'yes' if status == 'ok' else 'no'
            if not entry['candidates'] and entry['report_at']:
                entry['candidates'] = [_candidate(*entry['report_at'], trace=entry['trace'])]
            for c in entry['candidates']:
                m = re.search(r'^== ' + re.escape('%s:%s' % (c['file'], c['line'])) + r'\s*\|[^\n]*\n(.*?)(?=^== |\Z)', output, re.M | re.S)
                if m:
                    c['values'] = [line.strip() for line in m.group(1).splitlines() if re.match(r'\s*#\d+\s', line)]
            if status == 'ok':
                entry['kind'] = 'probe'
        return {'status': status, 'exit_code': exit_code, 'output': output}

    def finding():
        if not state:
            return {'status': 'not_found', 'kind': 'report_only', 'failing': [], 'error': '', 'candidates': [], 'note': '尚未取得诊断结果。'}
        entry = next(reversed(state.values()))
        if entry['result'] == 'green':
            status, kind, note = 'pass', 'pass', '测试通过。'
        elif entry['cause'] == 'yes':
            status, kind = 'found', entry['kind']
            note = '候选是可疑位置；同分时症状行和根因行可能不同，请结合源码和调用栈判断。' if kind == 'locate' else '结合异常和源码确认原因。'
        else:
            status, kind, note = 'not_found', 'report_only', '尚未定位原因；请结合测试报告继续排查。'
        candidates = entry['candidates'] or ([_candidate(*entry['report_at'], trace=entry['trace'])] if entry['report_at'] else [])
        return {'status': status, 'kind': kind, 'failing': entry['failing'], 'error': entry['error'], 'candidates': candidates, 'note': note}

    runner.calls = calls
    runner.finding = finding
    return runner


def diagnose(path: str, execute: bool = False, allow: list[str] | None = None,
             max_replans: int = 3) -> dict:
    runner = make_runner()
    domain = core.load_domain(str(_ROOT / 'htnbot/examples/diagnose/domain.json'), cmd_runner=runner)
    task = core.parse_task(domain, f'diagnose({path})')
    allowed = planner.allowed_actions(domain, allow, None)
    if execute:
        report = executor.execute_task(domain, task, allowed, max_replans=max_replans, cwd=str(_ROOT))
    else:
        report = executor.dry_run_task(domain, task, allowed, cwd=str(_ROOT))
    return {'mode': 'execute' if execute else 'dry_run', 'report': report, 'calls': runner.calls,
            'finding': runner.finding() if execute else None}


def summarize(result: dict) -> str:
    f = result.get('finding') or {'status': 'not_found', 'kind': 'report_only', 'failing': [], 'error': '', 'candidates': [], 'note': '未执行诊断。'}
    def cut(value, limit):
        value = str(value).replace('\n', ' ')
        return value if len(value) <= limit else value[:limit - 1] + '…'
    lines = ['%s（%s）；指令：%s' % ({'pass': '通过', 'found': '找到', 'not_found': '没找到'}[f['status']], f['kind'], ' → '.join(c['name'] for c in result['calls']) or '无')]
    if f['failing']:
        lines.append('失败用例：' + cut('、'.join(f['failing']), 250))
    if f['error']:
        lines.append('异常：' + cut(f['error'], 250))
    for c in f['candidates']:
        lines.append('%s:%s 可疑度 %s 调用栈：%s' % (c['file'], c['line'], c['score'] if c['score'] is not None else '无', '是' if c['in_traceback'] else '否'))
        lines.extend('  %s%s %s' % ('>' if row['line'] == c['line'] else ' ', row['line'], cut(row['text'], 55)) for row in c['code'])
        if c['values']:
            lines.append('  探针值：' + cut('；'.join(c['values']), 100))
    note = cut(f['note'], 200)
    body = '\n'.join(lines)
    if len(body) + len(note) + 1 > 2500:
        body = body[:2498 - len(note)] + '…'
    return body + '\n' + note
