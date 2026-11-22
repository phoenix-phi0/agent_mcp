"""Offline replay of recorded command outputs through the diagnose flow."""

import argparse
import json
import os
import sys
import tempfile

from planbot.core import PlanbotError, load_domain
from planbot.diag.parse import clean_text, norm_path
from planbot.diag.session import diagnose, summarize

_REPLAYED = ('run_test', 'test_report', 'locate', 'probe')
_MISSING = {'status': 'error', 'exit_code': 1, 'output': ''}


def _usage(message):
    return PlanbotError('USAGE', message)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _result(raw, where):
    if not isinstance(raw, dict):
        raise _usage('%s: result must be an object' % where)
    status, code, output = raw.get('status'), raw.get('exit_code'), raw.get('output')
    if not isinstance(status, str) or not _is_int(code) or not isinstance(output, str):
        raise _usage('%s: result needs str status, int exit_code, str output' % where)
    return {'status': status, 'exit_code': code, 'output': output}


def _sources(raw, case_id):
    if not isinstance(raw, dict):
        raise _usage('case %s: sources must be an object' % case_id)
    out = {}
    for key, text in raw.items():
        norm = norm_path(key)
        if norm is None:
            raise _usage('case %s: sources key %r is not a relative path inside the root' % (case_id, key))
        if norm in out:
            raise _usage('case %s: sources key %r duplicates another key after normalisation' % (case_id, key))
        if not isinstance(text, str):
            raise _usage('case %s: sources value for %r must be text' % (case_id, key))
        out[norm] = text
    return out


def _case(raw, index):
    if not isinstance(raw, dict):
        raise _usage('fixture case #%d must be an object' % index)
    case_id = raw.get('test')
    if not isinstance(case_id, str) or not case_id:
        raise _usage('fixture case #%d is missing "test"' % index)
    calls = raw.get('calls')
    if not isinstance(calls, dict):
        raise _usage('case %s: missing "calls"' % case_id)
    if 'run_test' not in calls:
        raise _usage('case %s: missing calls.run_test' % case_id)
    if 'sources' not in raw:
        raise _usage('case %s: missing "sources"' % case_id)
    outputs = {}
    for name in _REPLAYED:
        if name in calls:
            outputs[name] = _result(calls[name], 'case %s: calls.%s' % (case_id, name))
    return {'id': case_id, 'test_file': case_id, 'sources': _sources(raw['sources'], case_id),
            'outputs': outputs}


def load_cases(path):
    """Read the fixture file; return normalised cases in file order."""
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except FileNotFoundError:
        raise _usage('fixture not found: %s' % path)
    except (OSError, ValueError) as exc:
        raise _usage('cannot read fixture %s: %s' % (path, exc))
    raw_cases = data.get('cases') if isinstance(data, dict) else None
    if not isinstance(raw_cases, list):
        raise _usage('fixture must be an object with a "cases" list')
    cases = [_case(raw, i) for i, raw in enumerate(raw_cases, 1)]
    seen = set()
    for case in cases:
        if case['id'] in seen:
            raise _usage('duplicate case id %s' % case['id'])
        seen.add(case['id'])
    return cases


def _check_case(case):
    if not isinstance(case, dict):
        raise _usage('case must be an object')
    sources = case.get('sources')
    if not isinstance(sources, dict):
        raise _usage('case.sources must be an object')
    for key in sources:
        if norm_path(key) != key:
            raise _usage('case %s: sources key %r is not a canonical relative path' % (case.get('id'), key))
    outputs = case.get('outputs')
    if not isinstance(outputs, dict):
        raise _usage('case.outputs must be an object')
    return sources, outputs


def replay_case(case, domain_path, max_replans=3):
    """Run the diagnose flow on one case with recorded outputs; nothing real is executed."""
    sources, outputs = _check_case(case)

    def runner(name, args):
        if name in _REPLAYED and isinstance(outputs.get(name), dict):
            return dict(outputs[name])
        return dict(_MISSING)

    with tempfile.TemporaryDirectory() as root:
        for key, text in sources.items():
            target = os.path.join(root, *key.split('/'))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'w', encoding='utf-8', errors='replace', newline='') as handle:
                handle.write(text)
        return diagnose(domain_path, case.get('test_file'), runner, execute=True, allow=None,
                        max_replans=max_replans, repo_root=root)


DEFAULT_DOMAIN = 'examples/diagnose/domain.json'


class _Parser(argparse.ArgumentParser):
    """Argument errors become PlanbotError('USAGE', ...) instead of exiting."""

    def error(self, message):
        raise PlanbotError('USAGE', message)


def _build_parser():
    parser = _Parser(prog='planbot.diag')
    sub = parser.add_subparsers(dest='command', required=True)
    rp = sub.add_parser('replay', help='replay a recorded fixture offline')
    rp.add_argument('--fixture', required=True)
    rp.add_argument('--case', action='append', default=[])
    rp.add_argument('--domain', default=DEFAULT_DOMAIN)
    rp.add_argument('--max-replans', type=int, default=3)
    rp.add_argument('--summary', action='store_true')
    rp.add_argument('--json', action='store_true')
    return parser


def _line(value, limit=None):
    """One printable line: lone surrogates replaced, line breaks escaped."""
    text = clean_text(value).replace('\r', '\\r').replace('\n', '\\n')
    return clean_text(text, limit)


def _engine(report):
    report = report if isinstance(report, dict) else {}
    stuck = report.get('stuck') if isinstance(report.get('stuck'), dict) else None
    reason = stuck.get('reason') if stuck else None
    replans = report.get('replans')
    return {'status': report.get('status'), 'reason': reason if isinstance(reason, str) else None,
            'replans': replans if isinstance(replans, int) else 0}


def _case_text(case_id, result, with_summary):
    finding, engine = result['finding'], _engine(result['report'])
    exc = finding.get('exception')
    failed = finding.get('failed_tests') or []
    names = [c.get('name') for c in result['calls']]
    stuck_note = ' (%s)' % engine['reason'] if engine['status'] == 'stuck' and engine['reason'] else ''
    lines = ['case: %s' % _line(case_id),
             'status: %s (source: %s)' % (finding.get('status'), finding.get('source') or '-'),
             'failed: %s' % (', '.join(_line(t) for t in failed) or '-'),
             'exception: %s' % ('%s: %s' % (_line(exc.get('type')), _line(exc.get('message'), 120))
                                if isinstance(exc, dict) else '-'),
             'engine: %s%s' % (engine['status'], stuck_note),
             'calls: %s' % (' ; '.join(_line(n) for n in names) or '-'),
             'candidates:']
    cands = finding.get('candidates') or []
    for i, cand in enumerate(cands, 1):
        lines.append('  %d. %s:%s score=%.3f [%s]' % (
            i, _line(cand.get('file')), cand.get('line'), float(cand.get('score') or 0),
            ', '.join(_line(r) for r in cand.get('reasons') or [])))
    if not cands:
        lines.append('  (none)')
    if with_summary:
        lines.append('summary:')
        lines.extend('  ' + line for line in summarize(finding).split('\n'))
    return lines


def _dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def _render(results, with_summary, as_json):
    totals = {'cases': len(results), 'passed': 0, 'found': 0, 'not_found': 0}
    for _, result in results:
        status = result['finding'].get('status')
        if status in ('passed', 'found', 'not_found'):
            totals[status] += 1
    if as_json:
        cases = []
        for case_id, result in results:
            item = {'id': case_id, 'finding': result['finding'], 'engine': _engine(result['report']),
                    'calls': [{'name': c.get('name'), 'args': c.get('args'), 'exit_code': c.get('exit_code')}
                              for c in result['calls']]}
            if with_summary:
                item['summary'] = summarize(result['finding'])
            cases.append(item)
        return clean_text(_dumps({'cases': cases, 'totals': totals})) + '\n'
    lines = []
    for case_id, result in results:
        lines.extend(_case_text(case_id, result, with_summary))
    lines.append('cases: %d passed: %d found: %d not_found: %d' % (
        totals['cases'], totals['passed'], totals['found'], totals['not_found']))
    return clean_text('\n'.join(lines)) + '\n'


def _run(args):
    cases = load_cases(args.fixture)
    if args.case:
        known = {c['id'] for c in cases}
        for case_id in args.case:
            if case_id not in known:
                raise _usage('unknown case: %s' % case_id)
        wanted = set(args.case)
        cases = [c for c in cases if c['id'] in wanted]
    if args.max_replans < 0:
        raise _usage('--max-replans must not be negative')
    load_domain(args.domain)
    results = []
    for case in cases:
        try:
            results.append((case['id'], replay_case(case, args.domain, args.max_replans)))
        except PlanbotError as exc:
            raise PlanbotError(exc.code, 'case %s: %s' % (case['id'], exc.message))
    return _render(results, args.summary, args.json)


def main(argv=None):
    """Command entry; returns the exit code (0 ok, 2 any error). Output is written only on success."""
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = '--json' in argv
    try:
        text = _run(_build_parser().parse_args(argv))
    except PlanbotError as exc:
        if as_json:
            body = _dumps({'error': {'code': exc.code, 'message': clean_text(exc.message)}})
            sys.stdout.write(clean_text(body) + '\n')
        else:
            sys.stderr.write('error: %s: %s\n' % (exc.code, _line(exc.message)))
        return 2
    sys.stdout.write(text)
    return 0
