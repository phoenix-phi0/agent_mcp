from dataclasses import dataclass, field as _field
from hashlib import sha256
from importlib import util
import json
import os
import re
import sys
import types
from typing import Callable


class PlanbotError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f'{code}: {message}')


@dataclass(frozen=True)
class Literal:
    positive: bool
    atom: tuple[str, ...]


def parse_literal(text: str) -> Literal:
    text = text.strip()
    positive = not text.startswith('not ')
    if not positive:
        text = text[4:].strip()
    match = re.fullmatch(r'([\w./-]+)(?:\(([^()]*)\))?', text)
    if match is None:
        raise PlanbotError('GOAL_INVALID', 'Invalid literal syntax')
    name, args = match.groups()
    if args is None or not args.strip():
        return Literal(positive, (name,))
    parts = tuple(part.strip() for part in args.split(','))
    if any(re.fullmatch(r'\??[\w./-]+', part) is None for part in parts):
        raise PlanbotError('GOAL_INVALID', 'Invalid literal argument')
    return Literal(positive, (name, *parts))


def format_atom(atom: tuple[str, ...]) -> str:
    return f'{atom[0]}({",".join(atom[1:])})'


def format_literal(lit: Literal) -> str:
    return ('' if lit.positive else 'not ') + format_atom(lit.atom)


@dataclass
class Rule:
    head: tuple[str, ...]
    body: tuple[Literal, ...]


@dataclass
class Sensor:
    name: str
    run: dict
    extract: tuple[dict, ...]


@dataclass
class Action:
    name: str
    params: tuple[str, ...]
    pre: tuple[Literal, ...]
    add: tuple[tuple[str, ...], ...]
    delete: tuple[tuple[str, ...], ...]
    run: dict
    irreversible: bool
    on_fail: dict | None = None


@dataclass(frozen=True)
class Subtask:
    kind: str
    name: str
    args: tuple[str, ...]
    goal: tuple[Literal, ...]


@dataclass(frozen=True)
class Method:
    name: str
    task: str
    params: tuple[str, ...]
    pre: tuple[Literal, ...]
    subtasks: tuple[Subtask, ...]


@dataclass
class Domain:
    name: str
    predicates: dict[str, int]
    derived: dict[str, int]
    rules: list[Rule]
    sensors: list[Sensor]
    actions: dict[str, Action]
    goals: frozenset[str]
    objects: tuple[str, ...]
    callbacks: dict[str, Callable]
    tasks: dict[str, tuple[str, ...]] = _field(default_factory=dict)
    methods: list[Method] = _field(default_factory=list)
    cmd_runner: Callable | None = None
    digest: str = _field(default='', compare=False)


def parse_goal(domain: Domain, texts: list[str]) -> tuple[Literal, ...]:
    if not texts:
        raise PlanbotError('GOAL_INVALID', 'Goal must not be empty')
    literals = set()
    for text in texts:
        literal = parse_literal(text)
        name, *args = literal.atom
        if any(arg.startswith('?') for arg in args):
            raise PlanbotError('GOAL_INVALID', 'Goal must not contain variables')
        if name not in domain.goals:
            raise PlanbotError('GOAL_INVALID', f'Predicate {name!r} is not allowed in goals')
        arities = domain.predicates | domain.derived
        if name not in arities or len(args) != arities[name]:
            raise PlanbotError('GOAL_INVALID', f'Invalid arity for predicate {name!r}')
        literals.add(literal)
    return tuple(sorted(literals, key=format_literal))


_python_modules: dict[str, types.ModuleType] = {}


def _absolute_path(path: str) -> str:
    try:
        path = os.fspath(path)
        if not isinstance(path, str) or not path or '\0' in path:
            raise ValueError('expected a nonempty text path without NUL characters')
        path.encode('utf-8')
        return os.path.abspath(path)
    except (OSError, TypeError, ValueError) as exc:
        raise PlanbotError('DOMAIN_INVALID', f'Invalid path {path!r}: {exc}') from exc


def load_python(path: str) -> types.ModuleType:
    path = _absolute_path(path)
    if path in _python_modules:
        return _python_modules[path]

    try:
        name = '_planbot_domain_' + sha256(os.fsencode(path)).hexdigest()
        spec = util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError('no loader for this path')
        module = util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    except (Exception, SystemExit) as exc:
        raise PlanbotError('DOMAIN_INVALID', f'Cannot import python file {path!r}: {exc}') from exc

    _python_modules[path] = module
    return module


def _reject_json_constant(value: str) -> None:
    raise ValueError(f'{value} is not a JSON constant')


def _expect(value, expected: type, field: str):
    if not isinstance(value, expected):
        raise PlanbotError('DOMAIN_INVALID', f'{field} must be a {expected.__name__}')
    return value


def _list_of(value, expected: type, field: str) -> list:
    items = _expect(value, list, field)
    for index, item in enumerate(items):
        _expect(item, expected, f'{field}[{index}]')
    return items


def _domain_literal(text, field: str, arities: dict[str, int] | None = None) -> Literal:
    _expect(text, str, field)
    try:
        literal = parse_literal(text)
    except PlanbotError as exc:
        raise PlanbotError('DOMAIN_INVALID', f'{field}: {exc.message}') from exc

    if arities is not None:
        predicate = literal.atom[0]
        if predicate not in arities:
            raise PlanbotError('DOMAIN_INVALID', f'{field}: undeclared predicate {predicate!r}')
        if len(literal.atom) - 1 != arities[predicate]:
            raise PlanbotError(
                'DOMAIN_INVALID',
                f'{field}: predicate {predicate!r} expects {arities[predicate]} arguments',
            )
    return literal


def _domain_atom(text, field: str, arities: dict[str, int] | None = None) -> tuple[str, ...]:
    literal = _domain_literal(text, field, arities)
    if not literal.positive:
        raise PlanbotError('DOMAIN_INVALID', f'{field} must be a positive atom')
    return literal.atom


def _domain_callbacks(data: dict, path: str, callbacks: dict | None) -> dict[str, Callable]:
    result = {}
    if 'python' in data:
        source = _expect(data['python'], str, 'python')
        if os.path.isabs(source) or not source.endswith('.py'):
            raise PlanbotError('DOMAIN_INVALID', 'python must be a relative .py path')
        try:
            module = load_python(os.path.join(os.path.dirname(path), source))
        except PlanbotError as exc:
            raise PlanbotError('DOMAIN_INVALID', f'python: {exc.message}') from exc
        result.update(_callback_table(vars(module).get('CALLBACKS'), 'python.CALLBACKS'))
    if callbacks is not None:
        result.update(_callback_table(callbacks, 'callbacks'))
    return result


def _callback_table(value, field: str) -> dict[str, Callable]:
    table = _expect(value, dict, field)
    for name, callback in table.items():
        if not isinstance(name, str) or not callable(callback):
            raise PlanbotError('DOMAIN_INVALID', f'{field} must map names to callable objects')
    return table


def _domain_run(value, callbacks: dict[str, Callable], field: str, owner: str = '') -> dict:
    run = _expect(value, dict, field)
    if run.keys() == {'callback'}:
        name = _expect(run['callback'], str, f'{field}.callback')
        if name not in callbacks:
            raise PlanbotError('DOMAIN_INVALID', f'{field}: unknown callback {name!r}')
    elif run.keys() == {'cmds'}:
        for index, argv in enumerate(_expect(run['cmds'], list, f'{field}.cmds')):
            _list_of(argv, str, f'{field}.cmds[{index}]')
    elif run.keys() == {'cmd'}:
        cmd = _expect(run['cmd'], dict, f'{field}.cmd')
        cmd_name = cmd.get('name')
        if not isinstance(cmd_name, str) or not cmd_name:
            raise PlanbotError('DOMAIN_INVALID', f'{field}{owner}.cmd.name must be a nonempty string')
        _expect(cmd.setdefault('args', {}), dict, f'{field}{owner}.cmd.args')
    else:
        raise PlanbotError(
            'DOMAIN_INVALID', f'{field}{owner} must contain exactly one of cmds, callback or cmd',
        )
    return run


def _domain_rules(data: dict, predicates: dict[str, int]) -> tuple[dict[str, int], list[Rule]]:
    entries = _list_of(data.get('derived', []), dict, 'derived')
    derived = {}
    heads = []
    for index, entry in enumerate(entries):
        field = f'derived[{index}].head'
        head = _domain_atom(entry.get('head'), field)
        predicate = head[0]
        arity = len(head) - 1
        if predicate in predicates:
            raise PlanbotError('DOMAIN_INVALID', f'{field}: {predicate!r} is a basic predicate')
        if derived.setdefault(predicate, arity) != arity:
            raise PlanbotError(
                'DOMAIN_INVALID', f'{field}: predicate {predicate!r} expects {derived[predicate]} arguments',
            )
        heads.append(head)

    arities = predicates | derived
    rules = []
    for index, (head, entry) in enumerate(zip(heads, entries)):
        field = f'derived[{index}].body'
        body = _list_of(entry.get('body'), str, field)
        literals = tuple(_domain_literal(text, field, arities) for text in body)
        bound = {arg for lit in literals if lit.positive for arg in lit.atom[1:] if arg.startswith('?')}
        unbound = sorted({
            arg for atom in [head, *(lit.atom for lit in literals if not lit.positive)]
            for arg in atom[1:] if arg.startswith('?') and arg not in bound
        })
        if unbound:
            raise PlanbotError(
                'DOMAIN_INVALID',
                f'derived[{index}]: variables {unbound} of the head or a negated literal '
                'do not appear in a positive literal',
            )
        rules.append(Rule(head, literals))
    return derived, _sort_rules(rules, derived)


def _sort_rules(rules: list[Rule], derived: dict[str, int]) -> list[Rule]:
    """Order rules by the topological order of their head predicates.

    A predicate relies on every derived predicate used in the bodies of its
    rules (positive or negated). Among predicates that can be placed, the one
    whose first rule comes first in the file goes first. The rules of one
    predicate are emitted together, in file order. A cycle (including a
    self-dependency) is an error.
    """
    order: list[str] = []
    for rule in rules:
        if rule.head[0] not in order:
            order.append(rule.head[0])
    needs: dict[str, set[str]] = {name: set() for name in order}
    for rule in rules:
        needs[rule.head[0]].update(lit.atom[0] for lit in rule.body if lit.atom[0] in derived)

    placed: list[str] = []
    pending = list(order)
    while pending:
        for name in pending:
            if all(need in placed for need in needs[name]):
                break
        else:
            raise PlanbotError(
                'DOMAIN_INVALID', f'derived predicates have a cyclic dependency (involving {sorted(pending)})',
            )
        pending.remove(name)
        placed.append(name)
    return [rule for name in placed for rule in rules if rule.head[0] == name]


def _domain_sensors(entries: list[dict], callbacks: dict[str, Callable]) -> list[Sensor]:
    sensors = []
    names = set()
    for index, entry in enumerate(entries):
        field = f'sensors[{index}]'
        name = _expect(entry.get('name'), str, f'{field}.name')
        if name in names:
            raise PlanbotError('DOMAIN_INVALID', f'{field}.name: duplicate sensor {name!r}')
        names.add(name)
        run = _domain_run(entry.get('run'), callbacks, f'{field}.run', f' (sensor {name!r})')
        extract = tuple(_list_of(entry.get('extract'), dict, f'{field}.extract'))
        sensors.append(Sensor(name, run, extract))
    return sensors


_PLACEHOLDER = re.compile(r'\{([A-Za-z_][A-Za-z0-9_]*)\}')


def _strings_in(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings_in(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings_in(item)


def _check_action(name: str, field: str, action: Action, derived: dict[str, int]) -> None:
    atoms = [('pre', lit.atom) for lit in action.pre]
    atoms += [('add', atom) for atom in action.add] + [('del', atom) for atom in action.delete]
    for part, atom in atoms:
        if part != 'pre' and atom[0] in derived:
            raise PlanbotError(
                'DOMAIN_INVALID', f'{field}.{part}: action {name!r} changes derived predicate {atom[0]!r}',
            )
        for arg in atom[1:]:
            if arg.startswith('?') and arg[1:] not in action.params:
                raise PlanbotError(
                    'DOMAIN_INVALID', f'{field}.{part}: action {name!r} uses variable {arg!r} not in params',
                )
    for part, run in (('run', action.run), ('on_fail', action.on_fail or {})):
        for argv in run.get('cmds', ()):
            for item in argv:
                for placeholder in _PLACEHOLDER.findall(item):
                    if placeholder not in action.params:
                        raise PlanbotError(
                            'DOMAIN_INVALID',
                            f'{field}.{part}: action {name!r} uses placeholder {{{placeholder}}} not in params',
                        )
        for text in _strings_in(run['cmd']['args']) if 'cmd' in run else ():
            for placeholder in _PLACEHOLDER.findall(text):
                if placeholder not in action.params:
                    raise PlanbotError(
                        'DOMAIN_INVALID',
                        f'{field}.{part}: action {name!r} uses placeholder {{{placeholder}}} not in params',
                    )


def _domain_actions(
    entries: list[dict], arities: dict[str, int], callbacks: dict[str, Callable],
    derived: dict[str, int],
) -> dict[str, Action]:
    actions = {}
    for index, entry in enumerate(entries):
        field = f'actions[{index}]'
        name = _expect(entry.get('name'), str, f'{field}.name')
        if name in actions:
            raise PlanbotError('DOMAIN_INVALID', f'{field}.name: duplicate action {name!r}')
        params = tuple(_list_of(entry.get('params'), str, f'{field}.params'))
        pre = _list_of(entry.get('pre'), str, f'{field}.pre')
        add = _list_of(entry.get('add'), str, f'{field}.add')
        delete = _list_of(entry.get('del'), str, f'{field}.del')
        run = _domain_run(entry.get('run'), callbacks, f'{field}.run', f' (action {name!r})')
        irreversible = _expect(entry.get('irreversible', False), bool, f'{field}.irreversible')
        action = Action(
            name=name,
            params=params,
            pre=tuple(_domain_literal(text, f'{field}.pre', arities) for text in pre),
            add=tuple(_domain_atom(text, f'{field}.add', arities) for text in add),
            delete=tuple(_domain_atom(text, f'{field}.del', arities) for text in delete),
            run=run,
            irreversible=irreversible,
            on_fail=_domain_run(entry['on_fail'], callbacks, f'{field}.on_fail')
            if 'on_fail' in entry else None,
        )
        _check_action(name, field, action, derived)
        actions[name] = action
    return actions


def _domain_tasks(data: dict, actions: dict[str, Action]) -> dict[str, tuple[str, ...]]:
    tasks = {}
    for index, entry in enumerate(_list_of(data.get('tasks', []), dict, 'tasks')):
        field = f'tasks[{index}]'
        name = _expect(entry.get('name'), str, f'{field}.name')
        if name in tasks:
            raise PlanbotError('DOMAIN_INVALID', f'{field}.name: duplicate task {name!r}')
        if name in actions:
            raise PlanbotError('DOMAIN_INVALID', f'{field}.name: task {name!r} has the same name as an action')
        params = tuple(_list_of(entry.get('params'), str, f'{field}.params'))
        if len(set(params)) != len(params):
            raise PlanbotError('DOMAIN_INVALID', f'{field}.params: task {name!r} has duplicate params')
        tasks[name] = params
    return tasks


def _check_variables(atom: tuple[str, ...], usable: set[str], field: str, owner: str) -> None:
    for arg in atom[1:]:
        if arg.startswith('?') and arg[1:] not in usable:
            raise PlanbotError('DOMAIN_INVALID', f'{field}: method {owner!r} uses unavailable variable {arg!r}')


def _domain_subtask(
    value, field: str, owner: str, usable: set[str], arities: dict[str, int],
    actions: dict[str, Action], tasks: dict[str, tuple[str, ...]],
) -> Subtask:
    if isinstance(value, dict):
        if value.keys() != {'goal'}:
            raise PlanbotError('DOMAIN_INVALID', f'{field}: method {owner!r} goal subtask must have only the key goal')
        texts = _list_of(value['goal'], str, f'{field}.goal')
        if not texts:
            raise PlanbotError('DOMAIN_INVALID', f'{field}.goal: method {owner!r} has an empty goal subtask')
        literals = tuple(_domain_literal(text, f'{field}.goal', arities) for text in texts)
        for literal in literals:
            _check_variables(literal.atom, usable, f'{field}.goal', owner)
        return Subtask('goal', '', (), literals)
    literal = _domain_literal(value, field, None)
    if not literal.positive:
        raise PlanbotError('DOMAIN_INVALID', f'{field}: method {owner!r} subtask must not use not')
    name, *args = literal.atom
    if name in actions:
        kind, params = 'action', actions[name].params
    elif name in tasks:
        kind, params = 'task', tasks[name]
    else:
        raise PlanbotError('DOMAIN_INVALID', f'{field}: method {owner!r} refers to unknown action or task {name!r}')
    if len(args) != len(params):
        raise PlanbotError(
            'DOMAIN_INVALID', f'{field}: method {owner!r} calls {name!r} with {len(args)} arguments, expects {len(params)}',
        )
    _check_variables(literal.atom, usable, field, owner)
    return Subtask(kind, name, tuple(args), ())


def _domain_methods(
    data: dict, arities: dict[str, int], actions: dict[str, Action], tasks: dict[str, tuple[str, ...]],
) -> list[Method]:
    methods = []
    names = set()
    for index, entry in enumerate(_list_of(data.get('methods', []), dict, 'methods')):
        field = f'methods[{index}]'
        name = _expect(entry.get('name'), str, f'{field}.name')
        field = f'{field} (method {name!r})'
        if name in names:
            raise PlanbotError('DOMAIN_INVALID', f'{field}.name: duplicate method {name!r}')
        names.add(name)
        task = _expect(entry.get('task'), str, f'{field}.task')
        if task not in tasks:
            raise PlanbotError('DOMAIN_INVALID', f'{field}.task: method {name!r} refers to undeclared task {task!r}')
        params = tuple(_list_of(entry.get('params'), str, f'{field}.params'))
        if len(params) != len(tasks[task]):
            raise PlanbotError(
                'DOMAIN_INVALID',
                f'{field}.params: method {name!r} has {len(params)} params, task {task!r} has {len(tasks[task])}',
            )
        if len(set(params)) != len(params):
            raise PlanbotError('DOMAIN_INVALID', f'{field}.params: method {name!r} has duplicate params')
        pre = tuple(
            _domain_literal(text, f'{field}.pre', arities)
            for text in _list_of(entry.get('pre', []), str, f'{field}.pre')
        )
        usable = set(params) | {
            arg[1:] for lit in pre if lit.positive for arg in lit.atom[1:] if arg.startswith('?')
        }
        for lit in pre:
            if not lit.positive:
                _check_variables(lit.atom, usable, f'{field}.pre', name)
        subtasks = tuple(
            _domain_subtask(value, f'{field}.subtasks[{position}]', name, usable, arities, actions, tasks)
            for position, value in enumerate(_expect(entry.get('subtasks'), list, f'{field}.subtasks'))
        )
        methods.append(Method(name, task, params, pre, subtasks))
    return methods


def load_domain(path: str, callbacks: dict | None = None, cmd_runner: Callable | None = None) -> Domain:
    path = _absolute_path(path)
    try:
        with open(path, encoding='utf-8') as source:
            data = json.load(source, parse_constant=_reject_json_constant)
    except (OSError, ValueError, RecursionError) as exc:
        raise PlanbotError('DOMAIN_INVALID', f'Cannot read domain file {path!r}: {exc}') from exc

    _expect(data, dict, f'Domain file {path!r}')
    digest = sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('ascii')
    ).hexdigest()
    name = _expect(data.get('name'), str, 'name')
    predicates = _expect(data.get('predicates'), dict, 'predicates')
    for predicate, arity in predicates.items():
        if re.fullmatch(r'[\w./-]+', predicate) is None or type(arity) is not int or arity < 0:
            raise PlanbotError(
                'DOMAIN_INVALID', f'predicates[{predicate!r}] must name a predicate with a nonnegative integer arity',
            )
    sensor_entries = _list_of(data.get('sensors'), dict, 'sensors')
    action_entries = _list_of(data.get('actions'), dict, 'actions')
    goals = frozenset(_list_of(data.get('goals'), str, 'goals'))
    objects = tuple(_list_of(data.get('objects', []), str, 'objects'))
    derived, rules = _domain_rules(data, predicates)
    arities = predicates | derived
    for goal in sorted(goals):
        if goal not in arities:
            raise PlanbotError('DOMAIN_INVALID', f'goals: undeclared predicate {goal!r}')
    callback_table = _domain_callbacks(data, path, callbacks)
    sensors = _domain_sensors(sensor_entries, callback_table)
    actions = _domain_actions(action_entries, arities, callback_table, derived)
    tasks = _domain_tasks(data, actions)
    methods = _domain_methods(data, arities, actions, tasks)
    return Domain(
        name=name,
        predicates=predicates,
        derived=derived,
        rules=rules,
        sensors=sensors,
        actions=actions,
        goals=goals,
        objects=objects,
        callbacks=callback_table,
        tasks=tasks,
        methods=methods,
        cmd_runner=cmd_runner,
        digest=digest,
    )


def bind(atom: tuple[str, ...], binding: dict[str, str]) -> tuple[str, ...]:
    return (atom[0], *(
        binding.get(arg[1:], arg) if arg.startswith('?') else arg
        for arg in atom[1:]
    ))


def holds(lit: Literal, facts: frozenset) -> bool:
    return (lit.atom in facts) == lit.positive


def _match_atom(
    atom: tuple[str, ...], fact: tuple[str, ...], binding: dict[str, str]
) -> dict[str, str] | None:
    matched = binding.copy()
    for arg, value in zip(atom[1:], fact[1:]):
        if arg.startswith('?'):
            if matched.setdefault(arg[1:], value) != value:
                return None
        elif arg != value:
            return None
    return matched


def derive(domain: Domain, base: frozenset) -> frozenset:
    facts = set(base)
    fact_index: dict[tuple[str, int], set[tuple[str, ...]]] = {}
    for fact in facts:
        fact_index.setdefault((fact[0], len(fact)), set()).add(fact)

    for rule in domain.rules:
        bindings: list[dict[str, str]] = [{}]
        for lit in rule.body:
            if not lit.positive:
                continue
            candidates = fact_index.get((lit.atom[0], len(lit.atom)), ())
            matches = []
            for binding in bindings:
                for fact in candidates:
                    matched = _match_atom(lit.atom, fact, binding)
                    if matched is not None:
                        matches.append(matched)
            bindings = matches
            if not bindings:
                break

        negative_atoms = [lit.atom for lit in rule.body if not lit.positive]
        derived = {
            bind(rule.head, binding)
            for binding in bindings
            if all(bind(atom, binding) not in facts for atom in negative_atoms)
        }
        facts.update(derived)
        for fact in derived:
            fact_index.setdefault((fact[0], len(fact)), set()).add(fact)

    return frozenset(facts)


def match_all(
    literals: tuple[Literal, ...], facts: frozenset, binding: dict[str, str]
) -> list[dict[str, str]]:
    fact_index: dict[tuple[str, int], list[tuple[str, ...]]] = {}
    for fact in facts:
        fact_index.setdefault((fact[0], len(fact)), []).append(fact)

    bindings: list[dict[str, str]] = [dict(binding)]
    for lit in literals:
        if not lit.positive:
            continue
        candidates = fact_index.get((lit.atom[0], len(lit.atom)), ())
        matches = []
        for current in bindings:
            for fact in candidates:
                matched = _match_atom(lit.atom, fact, current)
                if matched is not None:
                    matches.append(matched)
        bindings = matches
        if not bindings:
            return []

    negative_atoms = [lit.atom for lit in literals if not lit.positive]
    unique: dict[tuple, dict[str, str]] = {}
    for current in bindings:
        for atom in negative_atoms:
            bound = bind(atom, current)
            if any(arg.startswith('?') for arg in bound[1:]) or bound in facts:
                break
        else:
            unique.setdefault(tuple(sorted(current.items())), current)
    return [unique[key] for key in sorted(unique)]


def parse_task(domain: Domain, text: str) -> tuple[str, ...]:
    try:
        lit = parse_literal(text)
    except PlanbotError as exc:
        raise PlanbotError('GOAL_INVALID', f'Invalid task {text!r}: {exc.message}') from None
    name, args = lit.atom[0], lit.atom[1:]
    if not lit.positive:
        raise PlanbotError('GOAL_INVALID', f'Task must not be negated: {text!r}')
    if any(arg.startswith('?') for arg in args):
        raise PlanbotError('GOAL_INVALID', f'Task arguments must be constants: {text!r}')
    if name not in domain.tasks:
        raise PlanbotError('GOAL_INVALID', f'Unknown task {name!r}: {text!r}')
    if len(args) != len(domain.tasks[name]):
        raise PlanbotError(
            'GOAL_INVALID',
            f'Task {name!r} takes {len(domain.tasks[name])} argument(s), got {len(args)}: {text!r}',
        )
    return lit.atom
