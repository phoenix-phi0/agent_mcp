import subprocess
from pathlib import Path

import pytest

from planbot.core import load_domain, parse_goal
from planbot.executor import dry_run, execute
from planbot.planner import allowed_actions

DOMAIN = str(Path(__file__).resolve().parent.parent / 'examples' / 'release' / 'domain.json')
MESSAGE = 'planbot: publish changes'


def git(cwd, *args):
    done = subprocess.run(['git', *args], cwd=str(cwd), capture_output=True, text=True, check=True)
    return done.stdout


def clone(remote, target):
    git(target.parent, 'clone', '-q', str(remote), str(target))
    git(target, 'config', 'user.name', 'tester')
    git(target, 'config', 'user.email', 'tester@example.com')
    return target


@pytest.fixture
def repos(tmp_path):
    remote = tmp_path / 'remote.git'
    git(tmp_path, 'init', '-q', '--bare', str(remote))
    work = clone(remote, tmp_path / 'work')
    (work / 'base.txt').write_text('base\n')
    git(work, 'add', '-A')
    git(work, 'commit', '-q', '-m', 'initial')
    git(work, 'push', '-q', '-u', 'origin', 'HEAD')
    return tmp_path, remote, work


def count(repo):
    return int(git(repo, 'rev-list', '--all', '--count').strip())


def setup(allow_irreversible):
    domain = load_domain(DOMAIN)
    goal = parse_goal(domain, ['published()'])
    allowed = allowed_actions(domain, None, allow_irreversible)
    return domain, goal, allowed


def test_commit_and_push(repos):
    _, remote, work = repos
    (work / 'new.txt').write_text('new\n')
    domain, goal, allowed = setup(['push'])
    report = execute(domain, goal, allowed, cwd=str(work))
    assert [s['text'] for s in report['plan']['steps']] == ['commit()', 'push()']
    assert report['status'] == 'done'
    assert MESSAGE in git(remote, 'log', '--format=%s')
    assert 'published()' in report['final_facts']


def test_sync_before_push(repos):
    tmp_path, remote, work = repos
    other = clone(remote, tmp_path / 'other')
    (other / 'other.txt').write_text('other\n')
    git(other, 'add', '-A')
    git(other, 'commit', '-q', '-m', 'from other')
    git(other, 'push', '-q')
    (work / 'mine.txt').write_text('mine\n')
    domain, goal, allowed = setup(['push'])
    report = execute(domain, goal, allowed, cwd=str(work))
    assert [s['text'] for s in report['plan']['steps']] == ['commit()', 'sync()', 'push()']
    assert report['status'] == 'done'
    log = git(remote, 'log', '--format=%s')
    assert MESSAGE in log and 'from other' in log


def test_push_not_allowed(repos):
    _, remote, work = repos
    (work / 'new.txt').write_text('new\n')
    before = (count(work), count(remote))
    domain, goal, allowed = setup([])
    result = dry_run(domain, goal, allowed, cwd=str(work))
    plan = result['plan']
    assert plan['found'] is False
    assert plan['failure']['kind'] == 'no_producer'
    assert plan['steps'] == []
    assert plan['failure']['details'] == [{'goal': 'published()', 'excluded': ['push']}]
    assert (count(work), count(remote)) == before


def test_already_satisfied(repos):
    _, remote, work = repos
    before = (count(work), count(remote))
    domain, goal, allowed = setup(['push'])
    report = execute(domain, goal, allowed, cwd=str(work))
    assert report['status'] == 'already_satisfied'
    assert (count(work), count(remote)) == before


def test_conflict_cleanup(repos):
    from planbot.cli import _report_lines
    tmp_path, remote, work = repos
    other = clone(remote, tmp_path / 'other')
    (other / 'base.txt').write_text('remote\n')
    git(other, 'add', '-A')
    git(other, 'commit', '-q', '-m', 'remote change')
    git(other, 'push', '-q')
    remote_head = git(remote, 'rev-parse', 'HEAD')
    (work / 'base.txt').write_text('local\n')
    domain, goal, allowed = setup(['push'])
    report = execute(domain, goal, allowed, cwd=str(work))
    assert report['status'] == 'stuck' and report['stuck']['step'] == 'sync()'
    assert report['executed'][-1]['cleanup'] == {'ok': True}
    assert any(line.startswith('  last output: ') for line in _report_lines(report))
    assert not any((work / '.git' / name).exists() for name in ('rebase-merge', 'rebase-apply', 'MERGE_HEAD'))
    assert git(work, 'show', 'HEAD:base.txt') == 'local\n'
    assert git(remote, 'rev-parse', 'HEAD') == remote_head
