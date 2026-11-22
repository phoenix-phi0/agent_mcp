"""Store and retrieve plans by their relevant starting facts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .core import Domain, Literal, PlanbotError, format_atom, format_literal


def _related_predicates(domain: Domain, goal: tuple[Literal, ...], steps: list) -> set[str]:
    names = {literal.atom[0] for literal in goal}
    names.update(_step_predicates(domain, steps))
    return _expand(domain, names)


def _step_predicates(domain: Domain, steps: list) -> set[str]:
    names = set()
    for action_name, _ in steps:
        action = domain.actions[action_name]
        names.update(literal.atom[0] for literal in action.pre)
        names.update(atom[0] for atom in action.add)
        names.update(atom[0] for atom in action.delete)
    return names


def _expand(domain: Domain, names: set[str]) -> set[str]:
    # Core places each dependency before its users, so walk from heads to bodies.
    for rule in reversed(domain.rules):
        if rule.head[0] in names:
            names.update(literal.atom[0] for literal in rule.body)
    return names.intersection(domain.predicates)


def _method_predicates(domain: Domain) -> set[str]:
    names = set()
    for method in domain.methods:
        names.update(literal.atom[0] for literal in method.pre)
        for subtask in method.subtasks:
            if subtask.kind == 'goal':
                names.update(literal.atom[0] for literal in subtask.goal)
    return names


def _tree_steps(tree: list) -> list:
    """Action leaves of a decomposition tree, left to right."""
    steps = []
    stack = list(reversed(tree))
    while stack:
        node = stack.pop()
        if node['kind'] == 'action':
            steps.append([node['name'], node['args']])
        stack.extend(reversed(node['children']))
    return steps


def _start_text(base: frozenset, predicates: set[str]) -> list[str]:
    return sorted(format_atom(atom) for atom in base if atom[0] in predicates)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f'{value} is not a JSON constant')


def _is_text_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_entry(entry) -> bool:
    if not isinstance(entry, dict) or not isinstance(entry.get('domain'), str):
        return False
    if 'task' in entry and not (isinstance(entry['task'], str) and isinstance(entry.get('tree'), list)):
        return False
    if not all(_is_text_list(entry.get(key)) for key in ('goal', 'predicates', 'start')):
        return False
    steps = entry.get('steps')
    return isinstance(steps, list) and all(
        isinstance(step, list) and len(step) == 2
        and isinstance(step[0], str) and _is_text_list(step[1])
        for step in steps
    )


class Memory:
    def __init__(self, path: str):
        self._path = Path(path)

    def _read(self) -> list[dict] | None:
        try:
            text = self._path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return None

        try:
            data = json.loads(text, parse_constant=_reject_json_constant)
        except ValueError as exc:
            raise PlanbotError('USAGE', f'Invalid JSON in memory file {str(self._path)!r}') from exc

        entries = data.get('entries') if isinstance(data, dict) else None
        if not isinstance(entries, list) or not all(_is_entry(entry) for entry in entries):
            raise PlanbotError('USAGE', f'Invalid entries in memory file {str(self._path)!r}')
        return entries

    def _write(self, entries: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        target = NamedTemporaryFile(mode='w', encoding='utf-8', dir=self._path.parent, delete=False)
        temporary_path = Path(target.name)
        try:
            with target:
                target.write(json.dumps({'entries': entries}, sort_keys=True))
            os.replace(temporary_path, self._path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def candidates(self, domain: Domain, goal: tuple[Literal, ...], base: frozenset) -> list[list]:
        goal_text = sorted(map(format_literal, goal))
        return [
            entry['steps'] for entry in self.list()
            if 'task' not in entry
            and entry['domain'] == domain.name and entry['goal'] == goal_text
            and entry['start'] == _start_text(base, set(entry['predicates']))
        ]

    def save(self, domain: Domain, goal: tuple[Literal, ...], base: frozenset, steps: list) -> None:
        entries = self.list()
        predicates = _related_predicates(domain, goal, steps)
        goal_text = sorted(map(format_literal, goal))
        start = _start_text(base, predicates)
        entry = {
            'domain': domain.name, 'goal': goal_text, 'predicates': sorted(predicates),
            'start': start, 'steps': steps,
        }
        remaining = [
            old for old in entries
            if 'task' in old or (old['domain'], old['goal'], old['start']) != (domain.name, goal_text, start)
        ]
        self._write([entry, *remaining])

    def candidates_task(self, domain: Domain, task: str, base: frozenset, fingerprint: str) -> list[list]:
        return [
            entry['tree'] for entry in self.list()
            if 'task' in entry and entry['domain'] == domain.name and entry['task'] == task
            and entry.get('fingerprint') == fingerprint
            and entry['start'] == _start_text(base, set(entry['predicates']))
        ]

    def save_task(
        self, domain: Domain, task: str, base: frozenset, tree: list, fingerprint: str,
    ) -> None:
        entries = self.list()
        steps = _tree_steps(tree)
        predicates = _expand(domain, _step_predicates(domain, steps) | _method_predicates(domain))
        start = _start_text(base, predicates)
        entry = {
            'domain': domain.name, 'task': task, 'goal': [], 'predicates': sorted(predicates),
            'start': start, 'steps': steps, 'tree': tree, 'fingerprint': fingerprint,
        }
        remaining = [
            old for old in entries
            if 'task' not in old or (old['domain'], old['task'], old['start']) != (domain.name, task, start)
        ]
        self._write([entry, *remaining])

    def list(self) -> list[dict]:
        return self._read() or []

    def clear(self) -> int:
        entries = self._read()
        if entries is None:
            return 0
        self._write([])
        return len(entries)
