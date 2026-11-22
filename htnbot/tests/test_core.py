import json

from planbot import PlanbotError, load_domain
from planbot.core import Action, Domain, Literal, Rule, Sensor, load_python
from planbot.core import bind, derive, format_atom, format_literal, holds, parse_literal
from planbot.core import parse_goal
import pytest


def test_planbot_error_attributes_and_string():
    error = PlanbotError('USAGE', 'x')
    assert error.code == 'USAGE'
    assert error.message == 'x'
    assert str(error) == 'USAGE: x'


def test_literal_equality_and_hash():
    literal = Literal(True, ('p', 'a'))
    assert literal == Literal(True, ('p', 'a'))
    assert Literal(True, ('p', 'a')) in {literal}


def test_zero_arity_forms_are_equal():
    assert parse_literal('q') == parse_literal('q()')


@pytest.mark.parametrize(('text', 'expected'), [
    ('not p(a,b)', 'not p(a,b)'), ('q()', 'q()'), ('q', 'q()'),
])
def test_literal_format_round_trip(text, expected):
    assert format_literal(parse_literal(text)) == expected


def test_parse_whitespace_and_variable():
    literal = parse_literal(' p( a , ?x ) ')
    assert literal.atom == ('p', 'a', '?x')
    assert literal.positive is True


def test_format_atom():
    assert format_atom(('p', 'a', 'b')) == 'p(a,b)'
    assert format_atom(('q',)) == 'q()'


@pytest.mark.parametrize('text', ['p(a', 'p(a,,b)', ''])
def test_invalid_literal(text):
    with pytest.raises(PlanbotError) as exc:
        parse_literal(text)
    assert exc.value.code == 'GOAL_INVALID'


def test_bind_preserves_constants_and_unbound_variables():
    assert bind(('p', '?x', 'b', '?y'), {'x': 'a'}) == ('p', 'a', 'b', '?y')


@pytest.mark.parametrize(('positive', 'atom', 'expected'), [
    (True, ('p', 'a'), True),
    (True, ('p', 'b'), False),
    (False, ('p', 'a'), False),
    (False, ('p', 'b'), True),
])
def test_holds(positive, atom, expected):
    facts = frozenset({('p', 'a')})
    assert holds(Literal(positive, atom), facts) is expected


def _domain(predicates, derived, *rules):
    return Domain('d', predicates, derived, list(rules), [], {}, frozenset(), (), {})


@pytest.fixture
def goal_domain():
    return Domain('d', {'p': 2, 'q': 0}, {'r': 1}, [], [], {},
                  frozenset({'p', 'r'}), (), {})


def test_parse_goal_deduplicates_and_sorts(goal_domain):
    assert parse_goal(goal_domain, ['r(a)', 'not p(a,b)', 'r(a)']) == (
        Literal(False, ('p', 'a', 'b')), Literal(True, ('r', 'a')),
    )


@pytest.mark.parametrize('texts', [[], ['r(?x)'], ['q()'], ['r(a,b)'], ['r(a']])
def test_parse_goal_invalid(goal_domain, texts):
    with pytest.raises(PlanbotError) as exc:
        parse_goal(goal_domain, texts)
    assert exc.value.code == 'GOAL_INVALID'


def test_core_has_no_domain_names():
    from pathlib import Path
    import planbot.core

    source = Path(planbot.core.__file__).read_text(encoding='utf-8').lower()
    assert all(word not in source for word in ('git', 'service', 'release'))


def test_derive_with_negation():
    rule = Rule(('r', '?x'), (Literal(False, ('q', '?x')), Literal(True, ('p', '?x'))))
    domain = _domain({'p': 1, 'q': 1}, {'r': 1}, rule)
    base = frozenset({('p', 'a'), ('p', 'b'), ('q', 'b')})

    assert derive(domain, base) == base | {('r', 'a')}
    assert derive(domain, frozenset()) == frozenset()


def test_derive_in_rule_order():
    first = Rule(('r', '?x'), (Literal(True, ('p', '?x')), Literal(False, ('q', '?x'))))
    second = Rule(('s', '?x'), (Literal(True, ('r', '?x')),))
    domain = _domain({'p': 1, 'q': 1}, {'r': 1, 's': 1}, first, second)
    base = frozenset({('p', 'a'), ('p', 'b'), ('q', 'b')})

    result = derive(domain, base)
    assert isinstance(result, frozenset)
    assert result == base | {('r', 'a'), ('s', 'a')}


def test_derive_joins_positive_literals():
    rule = Rule(('t', '?x', '?z'), (
        Literal(True, ('e', '?x', '?y')),
        Literal(True, ('e', '?y', '?z')),
    ))
    domain = _domain({'e': 2}, {'t': 2}, rule)
    base = frozenset({('e', 'a', 'b'), ('e', 'b', 'c'), ('e', 'b', 'd')})

    assert derive(domain, base) == base | {('t', 'a', 'c'), ('t', 'a', 'd')}


def test_derive_matches_constants_and_repeated_variables():
    rule = Rule(('r', '?x'), (Literal(True, ('p', '?x', '?x', 'a')),))
    domain = _domain({'p': 3}, {'r': 1}, rule)
    base = frozenset({('p', 'b', 'b', 'a'), ('p', 'c', 'd', 'a'), ('p', 'd', 'd', 'b')})

    assert derive(domain, base) == base | {('r', 'b')}


@pytest.fixture
def domain_data():
    return {
        'name': 'd',
        'objects': ['b', 'a'],
        'predicates': {'p': 1, 'q': 1},
        'derived': [
            {'head': 's(?x)', 'body': ['r(?x)']},
            {'head': 'r(?x)', 'body': ['p(?x)', 'not q(?x)']},
        ],
        'sensors': [{
            'name': 'read',
            'run': {'cmds': [['read', '{x}']]},
            'extract': [{'type': 'regex', 'pattern': '(.*)', 'facts': ['p({1})']}],
        }],
        'actions': [
            {
                'name': 'z', 'params': ['x'], 'pre': ['not q(?x)', 'r(?x)'],
                'add': ['q(?x)'], 'del': ['p(?x)'], 'run': {'cmds': [['write', '{x}']]},
                'irreversible': True,
            },
            {
                'name': 'a', 'params': [], 'pre': [], 'add': [], 'del': [],
                'run': {'cmds': [['write']]},
            },
        ],
        'goals': ['s', 'p', 's'],
    }


def _write_domain(tmp_path, data):
    path = tmp_path / 'domain.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return str(path)


def test_load_domain_fields(tmp_path, domain_data):
    domain = load_domain(_write_domain(tmp_path, domain_data))

    assert isinstance(domain, Domain)
    assert domain.name == 'd'
    assert domain.objects == ('b', 'a')
    assert domain.predicates == {'p': 1, 'q': 1}
    assert domain.derived == {'s': 1, 'r': 1}
    assert domain.rules == [
        Rule(('r', '?x'), (Literal(True, ('p', '?x')), Literal(False, ('q', '?x')))),
        Rule(('s', '?x'), (Literal(True, ('r', '?x')),)),
    ]
    assert domain.sensors == [
        Sensor('read', {'cmds': [['read', '{x}']]},
               ({'type': 'regex', 'pattern': '(.*)', 'facts': ['p({1})']},)),
    ]
    assert list(domain.actions) == ['z', 'a']
    assert domain.actions == {
        'z': Action(
            'z', ('x',), (Literal(False, ('q', '?x')), Literal(True, ('r', '?x'))),
            (('q', '?x'),), (('p', '?x'),), {'cmds': [['write', '{x}']]}, True,
        ),
        'a': Action('a', (), (), (), (), {'cmds': [['write']]}, False),
    }
    assert type(domain.goals) is frozenset
    assert domain.goals == frozenset({'p', 's'})
    assert domain.callbacks == {}


def test_load_domain_defaults(tmp_path):
    domain = load_domain(_write_domain(tmp_path, {
        'name': 'd', 'predicates': {}, 'sensors': [], 'actions': [], 'goals': [],
    }))
    assert domain == Domain(
        name='d', predicates={}, derived={}, rules=[], sensors=[], actions={},
        goals=frozenset(), objects=(), callbacks={},
    )


@pytest.mark.parametrize('key', ['name', 'predicates', 'sensors', 'actions', 'goals'])
def test_load_domain_missing_required_key(tmp_path, domain_data, key):
    del domain_data[key]
    with pytest.raises(PlanbotError, match=key) as exc:
        load_domain(_write_domain(tmp_path, domain_data))
    assert exc.value.code == 'DOMAIN_INVALID'


@pytest.mark.parametrize(('field', 'literal'), [
    ('pre', 'unknown(?x)'), ('pre', 'p()'), ('pre', 'p('),
    ('add', 'unknown(?x)'), ('add', 'q()'), ('add', 'not q(?x)'),
    ('del', 'unknown(?x)'), ('del', 'p()'), ('del', 'not p(?x)'),
    ('body', 'unknown(?x)'), ('body', 'p()'),
])
def test_load_domain_invalid_literal(tmp_path, domain_data, field, literal):
    item = domain_data['derived'][0] if field == 'body' else domain_data['actions'][0]
    item[field] = [literal]
    with pytest.raises(PlanbotError, match=field) as exc:
        load_domain(_write_domain(tmp_path, domain_data))
    assert exc.value.code == 'DOMAIN_INVALID'


@pytest.mark.parametrize('head', ['p(?x)', 'r()', 'not r(?x)'])
def test_load_domain_invalid_head(tmp_path, domain_data, head):
    domain_data['derived'].append({'head': head, 'body': []})
    with pytest.raises(PlanbotError, match='head') as exc:
        load_domain(_write_domain(tmp_path, domain_data))
    assert exc.value.code == 'DOMAIN_INVALID'


def test_load_domain_repeated_head_with_same_arity(tmp_path, domain_data):
    domain_data['derived'].append({'head': 'r(?x)', 'body': ['q(?x)']})
    domain = load_domain(_write_domain(tmp_path, domain_data))
    assert domain.derived == {'s': 1, 'r': 1}
    assert domain.rules[1] == Rule(('r', '?x'), (Literal(True, ('q', '?x')),))
    assert domain.rules[-1].head == ('s', '?x')


@pytest.mark.parametrize('field', ['actions', 'sensors'])
def test_load_domain_duplicate_names(tmp_path, domain_data, field):
    domain_data[field].append(domain_data[field][0])
    with pytest.raises(PlanbotError, match=field) as exc:
        load_domain(_write_domain(tmp_path, domain_data))
    assert exc.value.code == 'DOMAIN_INVALID'


@pytest.mark.parametrize(('field', 'value'), [
    ('goals', ['unknown']), ('predicates', {'p': True}), ('objects', ['a', 1]),
])
def test_load_domain_invalid_field(tmp_path, domain_data, field, value):
    domain_data[field] = value
    with pytest.raises(PlanbotError, match=field) as exc:
        load_domain(_write_domain(tmp_path, domain_data))
    assert exc.value.code == 'DOMAIN_INVALID'


@pytest.mark.parametrize('run', [
    {}, {'cmds': ['read']}, {'cmds': [[1]]}, {'callback': []},
    {'callback': 'unknown'}, {'cmds': [], 'callback': 'read'},
])
def test_load_domain_invalid_run(tmp_path, domain_data, run):
    domain_data['sensors'][0]['run'] = run
    with pytest.raises(PlanbotError, match='run') as exc:
        load_domain(_write_domain(tmp_path, domain_data))
    assert exc.value.code == 'DOMAIN_INVALID'


@pytest.mark.parametrize('content', [None, '{', '[]', '{"extra": NaN}'])
def test_load_domain_invalid_file(tmp_path, content):
    path = tmp_path / 'domain.json'
    if content is not None:
        path.write_text(content, encoding='utf-8')
    with pytest.raises(PlanbotError, match='domain.json') as exc:
        load_domain(str(path))
    assert exc.value.code == 'DOMAIN_INVALID'


@pytest.mark.parametrize('loader', [load_domain, load_python])
def test_loader_invalid_unicode_path(loader):
    with pytest.raises(PlanbotError, match='path') as exc:
        loader('\ud800')
    assert exc.value.code == 'DOMAIN_INVALID'


def test_load_python_caches_absolute_path(tmp_path, monkeypatch):
    path = tmp_path / 'callbacks.py'
    path.write_text('CALLBACKS = {}\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    assert load_python(str(path)) is load_python('callbacks.py')


@pytest.mark.parametrize('source', [None, 'raise RuntimeError("failed")\n', 'def (\n'])
def test_load_python_import_failure(tmp_path, source):
    path = tmp_path / 'callbacks.py'
    if source is not None:
        path.write_text(source, encoding='utf-8')
    with pytest.raises(PlanbotError, match='callbacks.py') as exc:
        load_python(str(path))
    assert exc.value.code == 'DOMAIN_INVALID'


def test_load_python_can_retry_failed_import(tmp_path):
    path = tmp_path / 'callbacks.py'
    path.write_text('raise RuntimeError("failed")\n', encoding='utf-8')
    with pytest.raises(PlanbotError, match='callbacks.py') as exc:
        load_python(str(path))
    assert exc.value.code == 'DOMAIN_INVALID'

    path.write_text('CALLBACKS = {}\n', encoding='utf-8')
    assert load_python(str(path)).CALLBACKS == {}


@pytest.mark.parametrize('source', ['', 'CALLBACKS = []\n', 'CALLBACKS = {"read": 1}\n'])
def test_load_domain_invalid_file_callbacks(tmp_path, domain_data, source):
    (tmp_path / 'callbacks.py').write_text(source, encoding='utf-8')
    domain_data['python'] = 'callbacks.py'
    with pytest.raises(PlanbotError, match='CALLBACKS') as exc:
        load_domain(_write_domain(tmp_path, domain_data))
    assert exc.value.code == 'DOMAIN_INVALID'


def test_load_domain_callbacks_parameter_overrides_python(tmp_path, domain_data):
    path = tmp_path / 'callbacks.py'
    path.write_text(
        'def read():\n    raise AssertionError("called during load")\n'
        'CALLBACKS = {"read": read, "extra": read}\n',
        encoding='utf-8',
    )
    domain_data['python'] = path.name
    domain_data['sensors'][0]['run'] = {'callback': 'read'}
    domain_data['actions'][0]['run'] = {'callback': 'write'}

    def override():
        pytest.fail('called during load')

    callbacks = {'read': override, 'write': override}
    domain = load_domain(_write_domain(tmp_path, domain_data), callbacks=callbacks)
    file_callbacks = load_python(str(path)).CALLBACKS

    assert domain.callbacks == {'read': override, 'write': override,
                                'extra': file_callbacks['extra']}
    assert file_callbacks['read'] is file_callbacks['extra']
    assert set(callbacks) == {'read', 'write'}
    assert domain.sensors[0].run == {'callback': 'read'}
    assert domain.actions['z'].run == {'callback': 'write'}


def _invalid(tmp_path, data, *fragments):
    with pytest.raises(PlanbotError) as exc:
        load_domain(_write_domain(tmp_path, data))
    assert exc.value.code == 'DOMAIN_INVALID'
    for fragment in fragments:
        assert fragment in exc.value.message


@pytest.mark.parametrize('field', ['add', 'del'])
def test_load_domain_action_effect_derived(tmp_path, domain_data, field):
    domain_data['actions'][0][field] = ['r(?x)']
    _invalid(tmp_path, domain_data, 'r')


def test_load_domain_rule_cycle(tmp_path, domain_data):
    domain_data['derived'] = [
        {'head': 'a(?x)', 'body': ['b(?x)']}, {'head': 'b(?x)', 'body': ['a(?x)']},
    ]
    domain_data['goals'] = ['p']
    domain_data['actions'][0]['pre'] = []
    _invalid(tmp_path, domain_data, 'cyclic')


def test_load_domain_rule_self_dependency(tmp_path, domain_data):
    domain_data['derived'].append({'head': 'r(?x)', 'body': ['s(?x)']})
    _invalid(tmp_path, domain_data, 'cyclic')


@pytest.mark.parametrize('rule', [
    {'head': 'r(?x)', 'body': ['p(?y)']},
    {'head': 'r(?x)', 'body': ['p(?x)', 'not q(?y)']},
    {'head': 'r(?x)', 'body': ['not q(?x)']},
])
def test_load_domain_rule_unbound_variable(tmp_path, domain_data, rule):
    domain_data['derived'] = [rule]
    domain_data['actions'][0]['pre'] = []
    _invalid(tmp_path, domain_data, '?')


def test_load_domain_action_variable_not_in_params(tmp_path, domain_data):
    domain_data['actions'][0]['pre'] = ['p(?y)']
    _invalid(tmp_path, domain_data, '?y')


def test_load_domain_action_placeholder_not_in_params(tmp_path, domain_data):
    domain_data['actions'][0]['run'] = {'cmds': [['write', '{x}'], ['tag', 'a-{x}-{x2}']]}
    _invalid(tmp_path, domain_data, 'z', 'x2')


def test_load_domain_action_placeholders_in_params(tmp_path, domain_data):
    domain_data['actions'][0]['params'] = ['x', 'x2']
    domain_data['actions'][0]['run'] = {'cmds': [['write', 'a-{x}-{x2}'], ['x', '{ }', '{1}']]}
    assert load_domain(_write_domain(tmp_path, domain_data)).actions['z'].params == ('x', 'x2')


def test_load_domain_sensor_braces_not_checked(tmp_path, domain_data):
    domain_data['sensors'][0]['run'] = {'cmds': [['read', '{x}', '{y}']]}
    domain_data['sensors'][0]['extract'][0]['facts'] = ['p({nothing})']
    domain = load_domain(_write_domain(tmp_path, domain_data))
    assert domain.sensors[0].run == {'cmds': [['read', '{x}', '{y}']]}


def test_load_domain_orders_rules_by_dependency(tmp_path, domain_data):
    domain_data['derived'] = [
        {'head': 'top(?x)', 'body': ['mid(?x)']},
        {'head': 'free(?x)', 'body': ['p(?x)']},
        {'head': 'mid(?x)', 'body': ['low(?x)']},
        {'head': 'low(?x)', 'body': ['p(?x)', 'not q(?x)']},
        {'head': 'low(?x)', 'body': ['q(?x)', 'not p(?x)']},
    ]
    domain_data['goals'] = ['top']
    domain_data['actions'][0]['pre'] = []
    domain = load_domain(_write_domain(tmp_path, domain_data))

    assert [rule.head[0] for rule in domain.rules] == ['free', 'low', 'low', 'mid', 'top']
    base = frozenset({('p', 'a'), ('q', 'b'), ('p', 'c'), ('q', 'c')})
    assert derive(domain, base) == base | {
        ('free', 'a'), ('free', 'c'), ('low', 'a'), ('low', 'b'),
        ('mid', 'a'), ('mid', 'b'), ('top', 'a'), ('top', 'b'),
    }


def _rule_domain(tmp_path, domain_data, rules):
    domain_data['derived'] = rules
    domain_data['goals'] = ['p']
    domain_data['actions'][0]['pre'] = []
    return load_domain(_write_domain(tmp_path, domain_data))


def _r(head, *body):
    return {'head': head + '(?x)', 'body': list(body)}


def test_sort_rules_dependency_before_dependent(tmp_path, domain_data):
    domain = _rule_domain(tmp_path, domain_data, [_r('s', 'r(?x)'), _r('r', 'p(?x)')])
    assert domain.rules == [
        Rule(('r', '?x'), (Literal(True, ('p', '?x')),)),
        Rule(('s', '?x'), (Literal(True, ('r', '?x')),)),
    ]


def test_sort_rules_groups_dependency_rules_before_dependent(tmp_path, domain_data):
    domain = _rule_domain(
        tmp_path, domain_data, [_r('r', 'p(?x)'), _r('s', 'r(?x)'), _r('r', 'q(?x)')],
    )
    assert domain.rules == [
        Rule(('r', '?x'), (Literal(True, ('p', '?x')),)),
        Rule(('r', '?x'), (Literal(True, ('q', '?x')),)),
        Rule(('s', '?x'), (Literal(True, ('r', '?x')),)),
    ]


def test_sort_rules_negated_dependency_counts(tmp_path, domain_data):
    domain = _rule_domain(
        tmp_path, domain_data, [_r('s', 'p(?x)', 'not r(?x)'), _r('r', 'q(?x)')],
    )
    assert [rule.head[0] for rule in domain.rules] == ['r', 's']


def test_sort_rules_groups_independent_predicates(tmp_path, domain_data):
    domain = _rule_domain(
        tmp_path, domain_data, [_r('a', 'p(?x)'), _r('b', 'q(?x)'), _r('a', 'q(?x)')],
    )
    assert domain.rules == [
        Rule(('a', '?x'), (Literal(True, ('p', '?x')),)),
        Rule(('a', '?x'), (Literal(True, ('q', '?x')),)),
        Rule(('b', '?x'), (Literal(True, ('q', '?x')),)),
    ]


def test_sort_rules_tie_uses_first_rule_position(tmp_path, domain_data):
    domain = _rule_domain(
        tmp_path, domain_data,
        [_r('c', 'a(?x)', 'b(?x)'), _r('b', 'p(?x)'), _r('a', 'q(?x)')],
    )
    assert [rule.head[0] for rule in domain.rules] == ['b', 'a', 'c']


def test_derive_two_layers_single_pass(tmp_path, domain_data):
    domain = _rule_domain(tmp_path, domain_data, [
        _r('t', 's(?x)', 'not q(?x)'), _r('s', 'r(?x)'), _r('r', 'p(?x)'), _r('r', 'q(?x)'),
    ])
    base = frozenset({('p', 'a'), ('q', 'b')})
    assert derive(domain, base) == base | {
        ('r', 'a'), ('r', 'b'), ('s', 'a'), ('s', 'b'), ('t', 'a'),
    }

@pytest.mark.parametrize('on_fail', [{'cmds': [['do', '{missing}']]}, {'callback': 'absent'}])
def test_invalid_on_fail(tmp_path, domain_data, on_fail):
    domain_data['actions'][0]['on_fail'] = on_fail
    _invalid(tmp_path, domain_data, 'on_fail')
