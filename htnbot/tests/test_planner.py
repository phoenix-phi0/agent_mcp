import json

import pytest

from planbot import PlanbotError, load_domain
from planbot.core import Literal, bind, format_literal, parse_goal
from planbot.planner import allowed_actions, make_plan, plan


def _act(name, params=(), pre=(), add=(), delete=(), irreversible=False):
    return {'name': name, 'params': list(params), 'pre': list(pre), 'add': list(add),
            'del': list(delete), 'run': {'cmds': []}, 'irreversible': irreversible}


def _load(tmp_path, actions, derived=None, objects=None):
    data = {
        'name': 'mini',
        'predicates': {'s1': 0, 's2': 0, 'done': 0, 'm': 0, 'n': 0,
                       'blocked': 1, 'have': 1, 'shipped': 1},
        'derived': derived or [],
        'sensors': [],
        'actions': actions,
        'goals': ['done', 'shipped', 's1', 'blocked'] + (['ok'] if derived else []),
    }
    if objects:
        data['objects'] = objects
    path = tmp_path / 'domain.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return load_domain(str(path))


def _texts(result):
    return [step['text'] for step in result['steps']]


def test_tie_returns_lexicographically_smallest_and_is_repeatable(tmp_path):
    domain = _load(tmp_path, [
        _act('use_b', add=['n']), _act('use_a', add=['m']),
        _act('fin_b', pre=['n'], add=['done']), _act('fin_a', pre=['m'], add=['done']),
    ])
    goal = parse_goal(domain, ['done'])
    allowed = allowed_actions(domain, None, None)
    first = plan(domain, frozenset(), goal, allowed)
    assert first['found'] and first['source'] == 'search' and first['failure'] is None
    assert _texts(first) == ['use_a()', 'fin_a()']
    assert first['steps'][0] == {
        'action': 'use_a', 'args': [], 'text': 'use_a()', 'irreversible': False,
        'reasons': [{'literal': 'm()', 'for_step': 2, 'for_text': 'fin_a()'}],
    }
    assert plan(domain, frozenset(), goal, allowed) == first


def test_shortest_plan_preferred(tmp_path):
    domain = _load(tmp_path, [
        _act('step1', add=['s1']),
        _act('step2', pre=['s1'], add=['s2']),
        _act('step3', pre=['s2'], add=['done']),
        _act('zshortcut', pre=['s1'], add=['done']),
    ])
    result = plan(domain, frozenset(), parse_goal(domain, ['done']), allowed_actions(domain, None, None))
    assert _texts(result) == ['step1()', 'zshortcut()']


def test_derived_and_negated_literals(tmp_path):
    domain = _load(
        tmp_path,
        [
            _act('grab', ['x'], add=['have(?x)']),
            _act('unblock', ['x'], pre=['blocked(?x)'], delete=['blocked(?x)']),
            _act('ship', ['x'], pre=['ok(?x)'], add=['shipped(?x)']),
        ],
        derived=[{'head': 'ok(?x)', 'body': ['have(?x)', 'not blocked(?x)']}],
    )
    allowed = allowed_actions(domain, None, None)
    base = frozenset({('blocked', 'a')})
    goal = parse_goal(domain, ['shipped(a)', 'not blocked(a)'])
    result = plan(domain, base, goal, allowed)
    assert _texts(result) == ['grab(a)', 'unblock(a)', 'ship(a)']
    assert result['steps'][0]['args'] == ['a']
    derived_goal = parse_goal(domain, ['ok(a)'])
    assert _texts(plan(domain, base, derived_goal, allowed)) == ['grab(a)', 'unblock(a)']


def test_objects_are_part_of_the_universe(tmp_path):
    domain = _load(tmp_path, [
        _act('grab', ['x'], add=['have(?x)']),
        _act('fin', ['x'], pre=['have(?x)'], add=['done']),
    ], objects=['k'])
    result = plan(domain, frozenset(), parse_goal(domain, ['done']), frozenset({'grab', 'fin'}))
    assert _texts(result) == ['grab(k)', 'fin(k)']


def test_already_satisfied(tmp_path):
    domain = _load(tmp_path, [_act('step1', add=['s1'])])
    result = plan(domain, frozenset({('s1',)}), parse_goal(domain, ['s1']), frozenset({'step1'}))
    assert result['found'] is True and result['steps'] == [] and result['failure'] is None


def test_limit(tmp_path):
    domain = _load(tmp_path, [_act('step1', add=['s1']), _act('step2', pre=['s1'], add=['done'])])
    goal = parse_goal(domain, ['done'])
    allowed = frozenset({'step1', 'step2'})
    result = plan(domain, frozenset(), goal, allowed, max_nodes=1)
    assert result == {'found': False, 'source': 'search', 'steps': [],
                      'failure': {'kind': 'limit', 'details': [], 'max_nodes': 1}}
    assert plan(domain, frozenset(), goal, allowed, max_nodes=2)['found'] is True


def test_exhausted_search_reports_unreachable_goals(tmp_path):
    domain = _load(tmp_path, [_act('step1', add=['s1'])])
    goal = parse_goal(domain, ['done', 's1'])
    result = plan(domain, frozenset(), goal, frozenset({'step1'}))
    assert result['found'] is False and result['steps'] == []
    assert result['failure'] == {
        'kind': 'no_producer', 'details': [{'goal': 'done()', 'excluded': []}], 'max_nodes': 10000,
    }


def test_allowed_actions_irreversible_rules(tmp_path):
    domain = _load(tmp_path, [_act('safe', add=['m']), _act('risky', add=['n'], irreversible=True)])
    assert allowed_actions(domain, None, None) == frozenset({'safe'})
    assert allowed_actions(domain, None, ['risky']) == frozenset({'safe', 'risky'})
    assert allowed_actions(domain, ['risky'], None) == frozenset()
    assert allowed_actions(domain, [], ['risky']) == frozenset({'risky'})
    assert allowed_actions(domain, ['safe'], None) == frozenset({'safe'})


@pytest.mark.parametrize('allow, irreversible', [
    (['nope'], None), (None, ['nope']), (None, ['safe']),
])
def test_allowed_actions_usage_errors(tmp_path, allow, irreversible):
    domain = _load(tmp_path, [_act('safe', add=['m']), _act('risky', add=['n'], irreversible=True)])
    with pytest.raises(PlanbotError) as info:
        allowed_actions(domain, allow, irreversible)
    assert info.value.code == 'USAGE'


def test_plan_reasons_point_to_bound_preconditions_and_goals(tmp_path):
    domain = _load(tmp_path, [
        _act('a', ['x'], add=['have(?x)']),
        _act('b', ['x'], delete=['blocked(?x)']),
        _act('c', ['x'], pre=['ok(?x)'], add=['done']),
    ], derived=[{'head': 'ok(?x)', 'body': ['have(?x)', 'not blocked(?x)']}])
    goal = parse_goal(domain, ['done', 'not blocked(k)'])
    result = plan(domain, frozenset({('blocked', 'k')}), goal, frozenset(domain.actions))
    steps = result['steps']
    assert _texts(result) == ['a(k)', 'b(k)', 'c(k)']
    assert steps[0]['reasons'] == [{'literal': '', 'for_step': None, 'for_text': 'indirect'}]
    assert steps[1]['reasons'] == [
        {'literal': 'ok(k)', 'for_step': 3, 'for_text': 'c(k)'},
        {'literal': 'not blocked(k)', 'for_step': None, 'for_text': 'goal'},
    ]
    for index, step in enumerate(steps, 1):
        assert step['reasons']
        for reason in step['reasons']:
            target = reason['for_step']
            if target is not None:
                assert index < target <= len(steps)
                consumer = steps[target - 1]
                action = domain.actions[consumer['action']]
                binding = dict(zip(action.params, consumer['args']))
                preconditions = {
                    format_literal(Literal(lit.positive, bind(lit.atom, binding)))
                    for lit in action.pre
                }
                assert reason['literal'] in preconditions
                assert reason['for_text'] == consumer['text']
            elif reason['for_text'] == 'goal':
                assert reason['literal'] in {format_literal(lit) for lit in goal}


@pytest.fixture
def memory_domain(tmp_path):
    return _load(tmp_path, [
        _act('a', ['x'], delete=['have(?x)', 's1']),
        _act('b', ['x'], add=['have(?x)', 's1']),
        _act('c', ['x'], pre=['s1', 'have(?x)', 'have(?x)', 'not blocked(?x)'],
             add=['done'], irreversible=True),
    ])


def test_make_plan_annotates_latest_establishment(memory_domain):
    goal = parse_goal(memory_domain, ['done', 's1', 'not blocked(k)'])
    sequence = [['b', ['k']], ['a', ['k']], ['b', ['k']], ['c', ['k']]]
    result = make_plan(memory_domain, frozenset(), goal + goal, sequence,
                       frozenset(memory_domain.actions))
    assert result['found'] is True and result['source'] == 'memory' and result['failure'] is None
    assert _texts(result) == ['b(k)', 'a(k)', 'b(k)', 'c(k)']
    assert result['steps'][0]['reasons'] == [{'literal': '', 'for_step': None, 'for_text': 'indirect'}]
    assert result['steps'][1]['reasons'] == [{'literal': '', 'for_step': None, 'for_text': 'indirect'}]
    assert result['steps'][2]['reasons'] == [
        {'literal': 'have(k)', 'for_step': 4, 'for_text': 'c(k)'},
        {'literal': 's1()', 'for_step': 4, 'for_text': 'c(k)'},
        {'literal': 's1()', 'for_step': None, 'for_text': 'goal'},
    ]
    assert result['steps'][3] == {
        'action': 'c', 'args': ['k'], 'text': 'c(k)', 'irreversible': True,
        'reasons': [{'literal': 'done()', 'for_step': None, 'for_text': 'goal'}],
    }


@pytest.mark.parametrize('steps, allowed, target', [
    ([['c', ['k']]], {'c'}, 'done'),
    ([['b', ['k']], ['c', ['k']]], {'b'}, 'done'),
    ([['b', ['k']]], {'b'}, 'done'),
    ([['missing', []]], {'missing'}, 'done'),
    ([['b', []]], {'b'}, 's1'),
    ([['b', 'k'], ['c', ['k']]], {'b', 'c'}, 'done'),
    ([['b', ['\ud800']]], {'b'}, 's1'),
], ids=['precondition', 'permission', 'goal', 'unknown', 'arity', 'argument_list', 'argument_format'])
def test_make_plan_returns_none_for_invalid_sequence(memory_domain, steps, allowed, target):
    goal = parse_goal(memory_domain, [target])
    assert make_plan(memory_domain, frozenset(), goal, steps, frozenset(allowed)) is None


def test_make_plan_accepts_empty_sequence_for_satisfied_goal(memory_domain):
    goal = parse_goal(memory_domain, ['done'])
    assert make_plan(memory_domain, frozenset({('done',)}), goal, [], frozenset()) == {
        'found': True, 'source': 'memory', 'steps': [], 'failure': None,
    }


def test_no_producer_unifies_effects_and_precedes_blocked(tmp_path):
    path = tmp_path / 'domain.json'
    path.write_text(json.dumps({
        'name': 'mini', 'predicates': {'p': 2, 'q': 0, 'r': 0}, 'derived': [],
        'sensors': [], 'goals': ['p', 'q'],
        'actions': [
            _act('a', ['x'], add=['p(?x,?x)']), _act('b', ['x'], add=['p(c,?x)']),
            _act('c', ['x'], add=['p(?x,b)']), _act('d', ['x'], delete=['p(?x,b)']),
            _act('e', pre=['r'], add=['q']),
        ],
    }), encoding='utf-8')
    domain = load_domain(str(path))
    goal = parse_goal(domain, ['q', 'p(a,b)', 'not p(c,b)'])
    result = plan(domain, frozenset({('p', 'c', 'b')}), goal, frozenset({'a', 'b', 'e'}))
    assert result == {
        'found': False, 'source': 'search', 'steps': [],
        'failure': {'kind': 'no_producer', 'max_nodes': 10000, 'details': [
            {'goal': 'not p(c,b)', 'excluded': ['d']}, {'goal': 'p(a,b)', 'excluded': ['c']},
        ]},
    }


def test_blocked_checks_bound_literals_across_reachable_states(tmp_path):
    domain = _load(tmp_path, [
        _act('a', ['x'], pre=['not s2', 'ok(?x)', 'm', 'not s1'], delete=['blocked(?x)']),
        _act('b', add=['have(b)'], delete=['s1']),
    ], derived=[{'head': 'ok(?x)', 'body': ['have(?x)']}], objects=['a'])
    base = frozenset({('blocked', 'b'), ('s1',), ('s2',)})
    result = plan(domain, base, parse_goal(domain, ['not blocked(b)']), frozenset(domain.actions))
    assert result['failure'] == {'kind': 'blocked', 'max_nodes': 10000, 'details': [
        {'goal': 'not blocked(b)', 'action': 'a(b)', 'missing': ['m()', 'not s2()']},
    ]}
    assert result['found'] is False and result['steps'] == []


@pytest.mark.parametrize('base,target', [(frozenset(), 'ok(a)'), (frozenset({('m',)}), 'not ok(a)')])
def test_no_producer_expands_all_derived_rules(tmp_path, base, target):
    domain = _load(tmp_path, [
        _act('z', add=['have(b)']), _act('a', delete=['m']), _act('b', add=['blocked(b)']),
        _act('other', add=['s1']),
    ], derived=[
        {'head': 'ok(?x)', 'body': ['mid(?x)']},
        {'head': 'mid(?x)', 'body': ['have(?x)', 'not blocked(?x)']},
        {'head': 'mid(a)', 'body': ['m']},
    ])
    result = plan(domain, base, parse_goal(domain, [target]), frozenset({'other'}))
    assert result['failure'] == {'kind': 'no_producer', 'max_nodes': 10000, 'details': [
        {'goal': target, 'excluded': ['a', 'b', 'z']},
    ]}


def test_derived_goal_counts_all_producer_instances(tmp_path):
    domain = _load(tmp_path, [
        _act('a', ['x'], pre=['blocked(?x)'], add=['have(?x)']),
        _act('b', add=['have(b)']),
    ], derived=[{'head': 'ok(?x)', 'body': ['have(?x)']}], objects=['b', 'a'])
    goal = parse_goal(domain, ['ok(a)'])
    result = plan(domain, frozenset(), goal, frozenset(domain.actions))
    assert result['failure'] == {'kind': 'blocked', 'max_nodes': 10000, 'details': [
        {'goal': 'ok(a)', 'action': 'a(a)', 'missing': ['blocked(a)']},
        {'goal': 'ok(a)', 'action': 'a(b)', 'missing': ['blocked(b)']},
    ]}


def test_unreachable_when_preconditions_hold_in_different_states(tmp_path):
    domain = _load(tmp_path, [
        _act('a', add=['m'], delete=['n']), _act('b', add=['n'], delete=['m']),
        _act('c', pre=['m', 'n'], add=['done', 's1']),
    ], derived=[{'head': 'ok', 'body': ['s2']}])
    goal = tuple(reversed(parse_goal(domain, ['s1', 'ok', 'done'])))
    base = frozenset({('s2',)})
    result = plan(domain, base, goal, frozenset(domain.actions), max_nodes=3)
    assert result == {
        'found': False, 'source': 'search', 'steps': [],
        'failure': {'kind': 'unreachable', 'max_nodes': 3,
                    'details': [{'goal': 'done()'}, {'goal': 's1()'}]},
    }


def test_producer_with_no_ground_instances(tmp_path):
    domain = _load(tmp_path, [_act('a', ['x'], pre=['have(?x)'], add=['done'])])
    result = plan(domain, frozenset(), parse_goal(domain, ['done']), frozenset({'a'}))
    assert result['failure'] == {'kind': 'unreachable', 'details': [{'goal': 'done()'}],
                                 'max_nodes': 10000}


def _excluded_domain(tmp_path, extra=()):
    data = {
        'name': 'mini',
        'predicates': {'a': 0, 'b': 0, 'm': 0},
        'derived': [{'head': 'g()', 'body': ['not a()', 'not b()']}],
        'sensors': [],
        'actions': [
            _act('x', pre=['a()'], delete=['a()'], add=['b()']),
            _act('y', pre=['b()'], delete=['b()']),
            *extra,
        ],
        'goals': ['g'],
    }
    path = tmp_path / 'domain.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return load_domain(str(path))


def test_excluded_action_unlocks_plan_reports_no_producer(tmp_path):
    domain = _excluded_domain(tmp_path)
    goal = parse_goal(domain, ['g()'])
    base = frozenset({('a',)})
    result = plan(domain, base, goal, frozenset({'x'}))
    assert result['found'] is False and result['steps'] == [] and result['source'] == 'search'
    assert result['failure'] == {
        'kind': 'no_producer', 'max_nodes': 10000,
        'details': [{'goal': 'g()', 'excluded': ['y']}],
    }
    full = plan(domain, base, goal, frozenset({'x', 'y'}))
    assert full['found'] is True and _texts(full) == ['x()', 'y()']


def test_first_search_limit_stays_limit(tmp_path):
    domain = _excluded_domain(tmp_path)
    goal = parse_goal(domain, ['g()'])
    result = plan(domain, frozenset({('a',)}), goal, frozenset({'x'}), max_nodes=1)
    assert result['failure'] == {'kind': 'limit', 'details': [], 'max_nodes': 1}


def test_second_search_limit_falls_back_to_unreachable(tmp_path):
    # Restricted search exhausts in 2 expansions; the full search needs a third.
    domain = _excluded_domain(tmp_path, [_act('z', pre=['a()'], add=['m()'])])
    goal = parse_goal(domain, ['g()'])
    base = frozenset({('a',)})
    result = plan(domain, base, goal, frozenset({'x'}), max_nodes=2)
    assert result['failure'] == {
        'kind': 'unreachable', 'max_nodes': 2, 'details': [{'goal': 'g()'}],
    }
    big = plan(domain, base, goal, frozenset({'x'}))
    assert big['failure']['details'] == [{'goal': 'g()', 'excluded': ['y']}]
