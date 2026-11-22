"""Permission set and shortest-plan search over the expected-effect model.

Pure computation: nothing here runs commands, callbacks or touches files.
"""
from collections import deque
from itertools import product
import re
from typing import Iterable, Iterator

from .core import (
    Action, Domain, Literal, PlanbotError, bind, derive, format_atom, format_literal, holds,
)


def allowed_actions(
    domain: Domain, allow: list[str] | None, allow_irreversible: list[str] | None,
) -> frozenset[str]:
    allow_irreversible = list(allow_irreversible or [])
    for name in [*(allow or []), *allow_irreversible]:
        if name not in domain.actions:
            raise PlanbotError('USAGE', f'Unknown action {name!r}')
    for name in allow_irreversible:
        if not domain.actions[name].irreversible:
            raise PlanbotError('USAGE', f'Action {name!r} is not irreversible')

    names = set(domain.actions) if allow is None else set(allow)
    names.update(allow_irreversible)
    return frozenset(
        name for name in names
        if not domain.actions[name].irreversible or name in allow_irreversible
    )


def _universe(domain: Domain, base: frozenset, goal: tuple[Literal, ...]) -> list[str]:
    constants = {arg for fact in base for arg in fact[1:]}
    constants.update(arg for lit in goal for arg in lit.atom[1:])
    constants.update(domain.objects)
    return sorted(constants)


def _instances(
    domain: Domain, base: frozenset, goal: tuple[Literal, ...], allowed: frozenset[str],
) -> list[tuple[str, tuple[str, ...]]]:
    """All (action name, args) pairs of the allowed actions, sorted."""
    universe = _universe(domain, base, goal)
    result = []
    for name in sorted(allowed):
        action = domain.actions[name]
        for args in product(universe, repeat=len(action.params)):
            result.append((name, args))
    result.sort()
    return result


def _bound_preconditions(action: Action, args: tuple[str, ...]) -> Iterator[Literal]:
    binding = dict(zip(action.params, args))
    for lit in action.pre:
        yield Literal(lit.positive, bind(lit.atom, binding))


def _usable(domain: Domain, facts: frozenset, name: str, args: tuple[str, ...]) -> bool:
    """Whether the instance's preconditions hold on the full facts."""
    return all(holds(lit, facts) for lit in _bound_preconditions(domain.actions[name], args))


def _apply(domain: Domain, state: frozenset, name: str, args: tuple[str, ...]) -> frozenset:
    """Expected successor of a base state after the instance."""
    action = domain.actions[name]
    binding = dict(zip(action.params, args))
    removed = {bind(atom, binding) for atom in action.delete}
    added = {bind(atom, binding) for atom in action.add}
    return frozenset((state - removed) | added)


def _goal_holds(goal: tuple[Literal, ...], facts: frozenset) -> bool:
    return all(holds(lit, facts) for lit in goal)


def _search(
    domain: Domain, base: frozenset, goal: tuple[Literal, ...],
    instances: list[tuple[str, tuple[str, ...]]], max_nodes: int,
) -> tuple[str, list[tuple[str, tuple[str, ...]]], dict]:
    """Breadth-first search.

    Returns (outcome, path, seen). outcome is 'found', 'limit' or 'exhausted'.
    path is the list of (name, args) instances (only for 'found'). seen maps
    every state ever queued to (parent state, instance), in queueing order;
    the start state maps to None.
    """
    start = frozenset(base)
    seen: dict = {start: None}
    queue = deque([start])
    expanded = 0
    while queue:
        state = queue.popleft()
        facts = derive(domain, state)
        if _goal_holds(goal, facts):
            path = []
            while seen[state] is not None:
                state, instance = seen[state]
                path.append(instance)
            path.reverse()
            return 'found', path, seen
        expanded += 1
        if expanded > max_nodes:
            return 'limit', [], seen
        for name, args in instances:
            if not _usable(domain, facts, name, args):
                continue
            successor = _apply(domain, state, name, args)
            if successor not in seen:
                seen[successor] = (state, (name, args))
                queue.append(successor)
    return 'exhausted', [], seen


def _derived_dependencies(domain: Domain) -> dict[str, set[str]]:
    """Collect basic predicate names across all rules for each derived predicate."""
    dependencies = {name: set() for name in domain.derived}
    # Core orders rules with the dependencies of each head first.
    for rule in domain.rules:
        names = dependencies[rule.head[0]]
        for lit in rule.body:
            predicate = lit.atom[0]
            if predicate in domain.predicates:
                names.add(predicate)
            else:
                names.update(dependencies[predicate])
    return dependencies


def _unifies(pattern: tuple[str, ...], atom: tuple[str, ...]) -> bool:
    if pattern[0] != atom[0] or len(pattern) != len(atom):
        return False
    variables = {}
    for arg, value in zip(pattern[1:], atom[1:]):
        if arg.startswith('?'):
            if variables.setdefault(arg, value) != value:
                return False
        elif arg != value:
            return False
    return True


def _producer_names(domain: Domain, lit: Literal, dependencies: dict[str, set[str]]) -> set[str]:
    predicate = lit.atom[0]
    if predicate in dependencies:
        return {
            action.name for action in domain.actions.values()
            if any(atom[0] in dependencies[predicate] for atom in (*action.add, *action.delete))
        }
    return {
        action.name for action in domain.actions.values()
        if any(_unifies(atom, lit.atom) for atom in (action.add if lit.positive else action.delete))
    }


def _reachable_fact_sets(
    domain: Domain, base: frozenset, initial: frozenset, seen: Iterable[frozenset],
) -> tuple[frozenset, frozenset]:
    """Return the union and intersection of the full reachable fact sets."""
    ever_present = set(initial)
    always_present = set(initial)
    for state in seen:
        if state != base:
            facts = derive(domain, state)
            ever_present.update(facts)
            always_present.intersection_update(facts)
    return frozenset(ever_present), frozenset(always_present)


def _exhausted_reason(
    domain: Domain, base: frozenset, goal: tuple[Literal, ...], allowed: frozenset[str],
    instances: list[tuple[str, tuple[str, ...]]], seen: Iterable[frozenset],
    max_nodes: int | None = None,
) -> tuple[str, list[dict]]:
    initial = derive(domain, base)
    unmet = sorted({lit for lit in goal if not holds(lit, initial)}, key=format_literal)
    dependencies = _derived_dependencies(domain)
    producers = {lit: _producer_names(domain, lit, dependencies) for lit in unmet}
    absent = [
        {'goal': format_literal(lit), 'excluded': sorted(producers[lit])}
        for lit in unmet if producers[lit].isdisjoint(allowed)
    ]
    if absent:
        return 'no_producer', absent

    # Rule 1b: would the goal be reachable if every action were allowed?
    everything = frozenset(domain.actions)
    if max_nodes is not None and not everything <= allowed:
        outcome, path, _ = _search(
            domain, base, goal, _instances(domain, base, goal, everything), max_nodes,
        )
        if outcome == 'found':
            excluded = sorted({name for name, _ in path} - allowed)
            if excluded:
                return 'no_producer', [
                    {'goal': format_literal(lit), 'excluded': excluded} for lit in unmet
                ]

    # A positive precondition can hold if its atom occurs in the union.
    # A negative one can hold if its atom is absent from the intersection.
    ever_present, always_present = _reachable_fact_sets(domain, base, initial, seen)
    blocked = []
    for lit in unmet:
        for name, args in instances:
            if name not in producers[lit]:
                continue
            action = domain.actions[name]
            if lit.atom[0] in domain.predicates:
                effects = action.add if lit.positive else action.delete
                binding = dict(zip(action.params, args))
                if not any(bind(atom, binding) == lit.atom for atom in effects):
                    continue
            missing = sorted({
                format_literal(pre) for pre in _bound_preconditions(action, args)
                if not holds(pre, ever_present if pre.positive else always_present)
            })
            if missing:
                blocked.append({'goal': format_literal(lit), 'action': format_atom((name, *args)),
                                'missing': missing})
    if blocked:
        blocked.sort(key=lambda item: (item['goal'], item['action']))
        return 'blocked', blocked
    return 'unreachable', [{'goal': format_literal(lit)} for lit in unmet]


def _step_dict(domain: Domain, name: str, args: tuple[str, ...]) -> dict:
    return {
        'action': name,
        'args': list(args),
        'text': format_atom((name, *args)),
        'irreversible': domain.actions[name].irreversible,
        'reasons': [],
    }


def _record_reasons(
    steps: list[dict], literals: Iterable[Literal], last_change: dict[tuple[str, ...], int],
    for_step: int | None, for_text: str,
) -> None:
    # Every demand holds at its point of use, so its latest truth change established it.
    for lit in sorted(set(literals), key=format_literal):
        producer = last_change.get(lit.atom)
        if producer is not None:
            steps[producer]['reasons'].append({
                'literal': format_literal(lit), 'for_step': for_step, 'for_text': for_text,
            })


def _annotated_steps(
    domain: Domain, path: list[tuple[str, tuple[str, ...]]],
    states: list[frozenset], goal: tuple[Literal, ...],
) -> list[dict]:
    steps = [_step_dict(domain, name, args) for name, args in path]
    last_change: dict[tuple[str, ...], int] = {}
    for index, (name, args) in enumerate(path):
        _record_reasons(
            steps, _bound_preconditions(domain.actions[name], args),
            last_change, index + 1, steps[index]['text'],
        )
        for atom in states[index] ^ states[index + 1]:
            last_change[atom] = index
    _record_reasons(steps, goal, last_change, None, 'goal')
    for step in steps:
        if not step['reasons']:
            step['reasons'].append({'literal': '', 'for_step': None, 'for_text': 'indirect'})
    return steps


def plan(
    domain: Domain, base: frozenset, goal: tuple[Literal, ...],
    allowed: frozenset[str], max_nodes: int = 10000,
) -> dict:
    instances = _instances(domain, base, goal, allowed)
    outcome, path, seen = _search(domain, base, goal, instances, max_nodes)
    if outcome == 'found':
        state = frozenset(base)
        states = [derive(domain, state)]
        for name, args in path:
            state = _apply(domain, state, name, args)
            states.append(derive(domain, state))
        return {
            'found': True,
            'source': 'search',
            'steps': _annotated_steps(domain, path, states, goal),
            'failure': None,
        }
    if outcome == 'limit':
        failure = {'kind': 'limit', 'details': [], 'max_nodes': max_nodes}
    else:
        kind, details = _exhausted_reason(domain, base, goal, allowed, instances, seen, max_nodes)
        failure = {'kind': kind, 'details': details, 'max_nodes': max_nodes}
    return {'found': False, 'source': 'search', 'steps': [], 'failure': failure}


def make_plan(
    domain: Domain, base: frozenset, goal: tuple[Literal, ...],
    steps: list, allowed: frozenset[str],
) -> dict | None:
    """Validate and annotate a supplied sequence using expected effects."""
    if not isinstance(steps, list):
        return None
    state = base
    states = [derive(domain, state)]
    path = []
    for step in steps:
        if not isinstance(step, list) or len(step) != 2:
            return None
        name, args = step
        if not isinstance(name, str) or name not in domain.actions or name not in allowed:
            return None
        if not isinstance(args, list) or len(args) != len(domain.actions[name].params):
            return None
        if any(not isinstance(arg, str) or re.fullmatch(r'[\w./-]+', arg) is None for arg in args):
            return None
        bound_args = tuple(args)
        if not _usable(domain, states[-1], name, bound_args):
            return None
        state = _apply(domain, state, name, bound_args)
        states.append(derive(domain, state))
        path.append((name, bound_args))

    if not _goal_holds(goal, states[-1]):
        return None
    return {
        'found': True,
        'source': 'memory',
        'steps': _annotated_steps(domain, path, states, goal),
        'failure': None,
    }
