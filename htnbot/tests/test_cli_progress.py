"""cli renders a no_progress stuck report generically (text and --json)."""
import json

from planbot.cli import main

_CB = '''
def sense(ctx):
    return ""

def act(binding, ctx):
    with open(COUNT_PATH, "a", encoding="utf-8") as handle:
        handle.write("x")

CALLBACKS = dict(sense=sense, act=act)
'''


def _setup(tmp_path):
    count = tmp_path / 'count.txt'
    code = 'COUNT_PATH = ' + repr(str(count)) + '\n' + _CB
    (tmp_path / 'callbacks.py').write_text(code, encoding='utf-8')
    data = {
        'name': 'mini', 'python': 'callbacks.py', 'predicates': {'p': 0}, 'goals': ['p'],
        'sensors': [{'name': 's', 'run': {'callback': 'sense'},
                     'extract': [{'type': 'regex', 'pattern': r'^(.+)$', 'facts': ['{1}']}]}],
        'actions': [{'name': 'a', 'params': [], 'pre': [], 'add': ['p()'], 'del': [],
                     'run': {'callback': 'act'}}],
        'tasks': [{'name': 'T', 'params': []}],
        'methods': [{'name': 'm', 'task': 'T', 'params': [], 'pre': [], 'subtasks': ['a()']}],
    }
    path = tmp_path / 'dom.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return str(path), count


def _calls(count):
    return len(count.read_text(encoding='utf-8')) if count.exists() else 0


def test_no_progress_text_renders_reason_verbatim(tmp_path, capsys):
    path, count = _setup(tmp_path)
    code = main(['task', '--domain', path, '--task', 'T()', '--execute', '--no-memory'])
    lines = capsys.readouterr().out.splitlines()
    assert code == 1
    assert 'replans: 1' in lines
    assert '  redo T()#0 after step 1 (mismatch: a()): a()' in lines
    assert 'status: stuck' in lines
    assert 'stuck at: a() (no_progress) in T()#0' in lines
    assert 'trigger: mismatch a()' in lines
    after = lines[lines.index('stuck at: a() (no_progress) in T()#0'):]
    assert not any('no decomposition' in line for line in after)
    assert lines[-1] == 'mode: execute'
    assert _calls(count) == 1


def test_no_progress_json_reason_and_null_failure(tmp_path, capsys):
    path, count = _setup(tmp_path)
    code = main(['task', '--domain', path, '--task', 'T()', '--execute', '--no-memory', '--json'])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out['stuck']['reason'] == 'no_progress'
    assert out['stuck']['failure'] is None
    assert out['mode'] == 'execute'
    assert len(out['executed']) == 1
    assert out['status'] == 'stuck'
    assert out['replans'] == 1
    assert _calls(count) == 1
