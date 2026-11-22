import ast
import json
import re
import sys
from pathlib import Path

from planbot import core, executor, planner
from test_examples_diagnose import make_fake
from test_examples_release import repos as release_repos

ROOT = Path(__file__).resolve().parent.parent
SERVICES = ROOT / 'examples' / 'services'
RELEASE = ROOT / 'examples' / 'release'
DIAGNOSE = ROOT / 'examples' / 'diagnose'
IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def test_both_domains_dry_run_in_same_process(release_repos):
    tmp_path, _, work = release_repos
    core.load_python(str(SERVICES / 'sim.py')).reset({'db': [], 'web': ['db']})
    cases = (
        (SERVICES, 'running(web)', tmp_path),
        (RELEASE, 'published()', work),
    )
    results = []
    for directory, goal_text, cwd in cases:
        domain = core.load_domain(str(directory / 'domain.json'))
        goal = core.parse_goal(domain, [goal_text])
        allowed = planner.allowed_actions(domain, None, None)
        result = executor.dry_run(domain, goal, allowed, memory=None, cwd=str(cwd))
        assert isinstance(result, dict)
        assert {'goal', 'facts', 'satisfied', 'plan'} <= result.keys()
        results.append(result)

    services, release = results
    assert services['plan']['found'] is True
    assert release['satisfied'] is True

    runner, _ = make_fake({})
    domain = core.load_domain(str(DIAGNOSE / 'domain.json'), cmd_runner=runner)
    task = core.parse_task(domain, 'diagnose(t_a.py)')
    allowed = planner.allowed_actions(domain, None, None)
    diagnose = executor.dry_run_task(domain, task, allowed)
    assert diagnose['plan']['found'] is True
    assert [s['text'] for s in diagnose['plan']['steps']] == ['run_test(t_a.py)']


def test_engine_source_has_no_domain_vocabulary():
    words = {'git'}
    for directory in (SERVICES, RELEASE, DIAGNOSE):
        data = json.loads((directory / 'domain.json').read_text(encoding='utf-8'))
        words.add(data['name'])
        words.update(action['name'] for action in data['actions'])
        words.update(data['predicates'])
        words.update(rule['head'].partition('(')[0].strip() for rule in data.get('derived', []))
        words.update(task['name'] for task in data.get('tasks', []))
        words.update(method['name'] for method in data.get('methods', []))

    # Entry.start is a memory field, and 'blocked' is a failure kind.
    exemptions = {'start', 'blocked'}
    assert exemptions == {'start', 'blocked'}
    forbidden = {word.lower() for word in words} - exemptions
    patterns = [(word, re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE))
                for word in sorted(forbidden)]
    hits = []
    adapter = ROOT / 'planbot' / 'diag'
    for path in sorted((ROOT / 'planbot').rglob('*.py')):
        if adapter in path.parents:
            continue
        with path.open(encoding='utf-8') as source:
            for line_no, line in enumerate(source, 1):
                for word, pattern in patterns:
                    if pattern.search(line):
                        hits.append(f'{path.relative_to(ROOT)}:{line_no}: {word}')
    assert not hits, '\n'.join(hits)


FALLBACK_STDLIB = {
    'json', 're', 'subprocess', 'argparse', 'importlib', 'dataclasses', 'collections',
    'os', 'tempfile', 'hashlib', 'sys', 'types', 'typing', 'itertools', 'functools',
    'copy', 'pathlib', '__future__',
}


def test_engine_imports_only_stdlib_or_itself():
    stdlib = getattr(sys, 'stdlib_module_names', FALLBACK_STDLIB)
    bad = []
    for path in sorted((ROOT / 'planbot').rglob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                tops = [alias.name.partition('.')[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                tops = ['planbot'] if node.level > 0 else [(node.module or '').partition('.')[0]]
            else:
                continue
            for top in tops:
                if top != 'planbot' and top not in stdlib:
                    bad.append(f'{path.relative_to(ROOT)}:{node.lineno}: {top}')
    assert not bad, '\n'.join(bad)


def _line_count(paths):
    total = 0
    for path in paths:
        with path.open(encoding='utf-8') as source:
            total += sum(1 for _ in source)
    return total


def test_test_source_is_at_most_twice_the_implementation():
    test_lines = _line_count(
        p for p in (ROOT / 'tests').rglob('*.py') if p.name != 'test_cli_progress.py'
    )
    implementation_lines = _line_count((ROOT / 'planbot').rglob('*.py'))
    implementation_lines += _line_count([SERVICES / 'sim.py'])
    assert test_lines <= 2 * implementation_lines, (
        f'{test_lines} test lines, {implementation_lines} implementation lines'
    )
