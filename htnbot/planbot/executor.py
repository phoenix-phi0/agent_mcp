"""Resolve plans and preview them against observed facts."""

import hashlib
import json

from . import core, htn, planner, runtime
from .core import Domain, Literal, PlanbotError
from .memory import Memory


def task_fingerprint(domain: Domain, allowed: frozenset[str], max_depth: int) -> str:
    payload = json.dumps([domain.digest, sorted(allowed), max_depth], ensure_ascii=True,
                         separators=(',', ':'))
    return hashlib.sha256(payload.encode('ascii')).hexdigest()


def resolve_plan(
    domain: Domain,
    base: frozenset,
    goal: tuple[Literal, ...],
    allowed: frozenset[str],
    memory: Memory | None = None,
    max_nodes: int = 10000,
) -> dict:
    facts = core.derive(domain, base)
    if all(core.holds(literal, facts) for literal in goal):
        return {'found': True, 'source': 'search', 'steps': [], 'failure': None}

    if memory is not None:
        for steps in memory.candidates(domain, goal, base):
            result = planner.make_plan(domain, base, goal, steps, allowed)
            if result is not None:
                return result

    return planner.plan(domain, base, goal, allowed, max_nodes)


def dry_run(
    domain: Domain,
    goal: tuple[Literal, ...],
    allowed: frozenset[str],
    memory: Memory | None = None,
    max_nodes: int = 10000,
    cwd: str = '.',
) -> dict:
    observed = runtime.observe(domain, cwd)
    facts = observed['facts']
    return {
        'goal': sorted(map(core.format_literal, goal)),
        'facts': sorted(map(core.format_atom, facts)),
        'satisfied': all(core.holds(literal, facts) for literal in goal),
        'plan': resolve_plan(domain, observed['base'], goal, allowed, memory, max_nodes),
    }


def _texts(atoms) -> list[str]:
    return sorted(map(core.format_atom, atoms))


def _expected_effects(domain: Domain, step: dict) -> tuple[frozenset, frozenset]:
    action = domain.actions[step['action']]
    binding = dict(zip(action.params, step['args']))
    add = frozenset(core.bind(atom, binding) for atom in action.add)
    delete = frozenset(core.bind(atom, binding) for atom in action.delete)
    return add, delete


def _preconditions_hold(domain: Domain, step: dict, facts: frozenset) -> bool:
    action = domain.actions[step['action']]
    binding = dict(zip(action.params, step['args']))
    return all(
        core.holds(Literal(lit.positive, core.bind(lit.atom, binding)), facts)
        for lit in action.pre
    )


def _run_step(domain: Domain, step: dict, cwd: str) -> tuple[dict, dict | None]:
    """Run one step's action; on failure run its cleanup. Returns (run_action result, cleanup)."""
    args = tuple(step['args'])
    result = runtime.run_action(domain, step['action'], args, cwd)
    cleanup = None
    if not result['ok'] and domain.actions[step['action']].on_fail is not None:
        cleanup = {'ok': runtime.run_cleanup(domain, step['action'], args, cwd)['ok']}
    return result, cleanup


def _compare_effects(domain: Domain, step: dict, base: frozenset) -> tuple[bool, list[str], list[str]]:
    add, delete = _expected_effects(domain, step)
    missing = _texts(add - base)
    unexpected = _texts(delete & base)
    return not missing and not unexpected, missing, unexpected


def execute(
    domain: Domain,
    goal: tuple[Literal, ...],
    allowed: frozenset[str],
    memory: Memory | None = None,
    max_nodes: int = 10000,
    max_replans: int = 3,
    cwd: str = '.',
) -> dict:
    observed = runtime.observe(domain, cwd)
    base, facts = observed['base'], observed['facts']
    initial_base = base
    initial_facts = _texts(facts)

    def satisfied(current: frozenset) -> bool:
        return all(core.holds(literal, current) for literal in goal)

    def report(status, plan, executed, replans, stuck, final_facts) -> dict:
        saved_to_memory = False
        if (status == 'done' and replans == 0 and memory is not None
                and plan['source'] == 'search' and plan['steps']):
            memory_steps = [[step['action'], list(step['args'])] for step in plan['steps']]
            memory.save(domain, goal, initial_base, memory_steps)
            saved_to_memory = True
        return {
            'status': status,
            'goal': sorted(map(core.format_literal, goal)),
            'initial_facts': initial_facts,
            'plan': plan,
            'executed': executed,
            'replans': replans,
            'stuck': stuck,
            'final_facts': _texts(final_facts),
            'saved_to_memory': saved_to_memory,
        }

    first_plan = resolve_plan(domain, base, goal, allowed, memory, max_nodes)
    if satisfied(facts):
        return report('already_satisfied', first_plan, [], 0, None, facts)
    if not first_plan['found']:
        return report('no_plan', first_plan, [], 0, None, facts)

    executed: list[dict] = []
    replans = 0
    steps = first_plan['steps']
    index = 0
    while True:
        step = steps[index]
        if step['action'] not in allowed:
            return report('no_plan', first_plan, executed, replans, None, facts)
        result, cleanup = _run_step(domain, step, cwd)
        item = {'text': step['text'], 'ok': result['ok'], 'matched': False,
                'missing': [], 'unexpected': [], 'cleanup': cleanup,
                'output': '' if result['ok'] else result['output'].strip()[-500:].strip()}
        executed.append(item)
        try:
            observed = runtime.observe(domain, cwd)
        except core.PlanbotError as exc:
            if exc.code != 'SENSOR_FAILED':
                raise
            stuck = {'step': step['text'], 'reason': 'observe_failed', 'error': exc.message,
                     'missing': [], 'unexpected': [], 'failure': None}
            return report('stuck', first_plan, executed, replans, stuck, facts)
        base, facts = observed['base'], observed['facts']

        matched, missing, unexpected = _compare_effects(domain, step, base)
        item.update(matched=matched, missing=missing, unexpected=unexpected)
        index += 1

        if matched:
            if index < len(steps):
                replan = not _preconditions_hold(domain, steps[index], facts)
            else:
                replan = not satisfied(facts)
            if not replan:
                if index >= len(steps):
                    return report('done', first_plan, executed, replans, None, facts)
                continue
        if satisfied(facts):
            return report('done', first_plan, executed, replans, None, facts)

        stuck = {'step': step['text'], 'reason': 'replan_limit',
                 'missing': missing, 'unexpected': unexpected, 'failure': None, 'error': None}
        if replans >= max_replans:
            return report('stuck', first_plan, executed, replans, stuck, facts)
        replans += 1
        new_plan = planner.plan(domain, base, goal, allowed, max_nodes)
        if not new_plan['found']:
            stuck['reason'] = 'no_plan'
            stuck['failure'] = new_plan['failure']
            return report('stuck', first_plan, executed, replans, stuck, facts)
        steps = new_plan['steps']
        index = 0


def _check_task(domain: Domain, task: tuple[str, ...]) -> None:
    if not task:
        raise PlanbotError('GOAL_INVALID', 'Task must not be empty')
    name = task[0]
    text = core.format_atom(task)
    if name not in domain.tasks:
        raise PlanbotError('GOAL_INVALID', f'Unknown task {name!r}: {text}')
    if len(task) - 1 != len(domain.tasks[name]):
        raise PlanbotError(
            'GOAL_INVALID',
            f'Task {name!r} takes {len(domain.tasks[name])} argument(s), got {len(task) - 1}: {text}',
        )


def _check_limits(max_nodes: int, max_depth: int) -> None:
    if max_nodes < 0:
        raise PlanbotError('USAGE', f'max_nodes must not be negative: {max_nodes}')
    if max_depth < 0:
        raise PlanbotError('USAGE', f'max_depth must not be negative: {max_depth}')


def resolve_task(
    domain: Domain,
    base: frozenset,
    task: tuple[str, ...],
    allowed: frozenset[str],
    memory: Memory | None = None,
    max_nodes: int = 10000,
    max_depth: int = 20,
) -> dict:
    _check_task(domain, task)
    _check_limits(max_nodes, max_depth)

    if memory is not None:
        fingerprint = task_fingerprint(domain, allowed, max_depth)
        for tree in memory.candidates_task(domain, core.format_atom(task), base, fingerprint):
            result = htn.from_memory(domain, base, task, tree, allowed)
            if result is not None:
                return result

    return htn.decompose_task(domain, base, task, allowed, max_depth, max_nodes)


def dry_run_task(
    domain: Domain,
    task: tuple[str, ...],
    allowed: frozenset[str],
    memory: Memory | None = None,
    max_nodes: int = 10000,
    max_depth: int = 20,
    cwd: str = '.',
) -> dict:
    _check_task(domain, task)
    _check_limits(max_nodes, max_depth)
    if memory is not None:
        memory.list()

    observed = runtime.observe(domain, cwd)
    return {
        'task': core.format_atom(task),
        'facts': _texts(observed['facts']),
        'plan': resolve_task(domain, observed['base'], task, allowed, memory, max_nodes, max_depth),
    }


def _first_cmd_step(domain: Domain, result: dict) -> str | None:
    for step in result['steps']:
        if 'cmd' in domain.actions[step['action']].run:
            return step['text']
    return None


def _path_text(path: list[dict]) -> str:
    return ' > '.join(f"{el['text']}#{el['idx']}" for el in path)


def _action_leaf(nodes: list[dict], step_no: int) -> dict | None:
    stack = list(nodes)
    while stack:
        node = stack.pop()
        if node['kind'] == 'action' and node['step'] == step_no:
            return node
        stack.extend(node['children'])
    return None


def _same_instance(new: dict, last: dict) -> bool:
    first = new['steps'][0]
    if first['text'] != last['text'] or len(first['path']) != len(last['path']):
        return False
    if any(a['text'] != b['text'] or a['idx'] != b['idx']
           for a, b in zip(first['path'], last['path'])):
        return False
    leaf = _action_leaf(new['tree'], 1)
    return leaf is not None and leaf['idx'] == last['idx']


def execute_task(
    domain: Domain,
    task: tuple[str, ...],
    allowed: frozenset[str],
    memory: Memory | None = None,
    max_nodes: int = 10000,
    max_replans: int = 3,
    max_depth: int = 20,
    cwd: str = '.',
) -> dict:
    _check_task(domain, task)
    if max_nodes < 0:
        raise PlanbotError('USAGE', f'max_nodes must not be negative: {max_nodes}')
    if max_replans < 0:
        raise PlanbotError('USAGE', f'max_replans must not be negative: {max_replans}')
    if max_depth < 0:
        raise PlanbotError('USAGE', f'max_depth must not be negative: {max_depth}')
    if memory is not None:
        memory.list()

    text = core.format_atom(task)
    observed = runtime.observe(domain, cwd)
    initial_base, base, facts = observed['base'], observed['base'], observed['facts']
    initial_facts = _texts(facts)

    first = resolve_task(domain, initial_base, task, allowed, memory, max_nodes, max_depth)
    executed: list[dict] = []
    replanned: list[dict] = []
    state = {'replans': 0, 'trigger': None, 'stuck': None, 'facts': facts}

    def report(status: str) -> dict:
        saved = False
        if (status == 'done' and state['replans'] == 0 and memory is not None
                and first['source'] == 'decompose' and first['steps']):
            memory.save_task(domain, text, initial_base, first['tree'],
                             task_fingerprint(domain, allowed, max_depth))
            saved = True
        return {
            'status': status, 'task': text, 'initial_facts': initial_facts, 'plan': first,
            'executed': executed, 'replans': state['replans'], 'replanned': replanned,
            'trigger': state['trigger'], 'stuck': state['stuck'],
            'final_facts': _texts(state['facts']), 'saved_to_memory': saved,
        }

    def check_runner(result: dict) -> None:
        if domain.cmd_runner is None:
            step_text = _first_cmd_step(domain, result)
            if step_text is not None:
                raise PlanbotError('USAGE', 'no cmd runner: ' + step_text)

    if not first['found']:
        return report('no_plan')
    if not first['steps']:
        return report('already_satisfied')

    cur = first
    check_runner(cur)
    k = 0
    last_step = None
    last = None
    while True:
        need = None
        for check in htn.goal_checks(cur, k):
            literals = [core.parse_literal(item) for item in check['goal']]
            if not all(core.holds(literal, facts) for literal in literals):
                need = ({'kind': 'goal', 'step': check['text']}, {'loc': check['loc']})
                break
        if need is None:
            if k == len(cur['steps']):
                return report('done')
            step = cur['steps'][k]
            if not _preconditions_hold(domain, step, facts):
                need = ({'kind': 'precondition', 'step': step['text']}, {'step': k + 1})
            else:
                if step['action'] not in allowed:
                    return report('no_plan')
                before = base
                result, _cleanup = _run_step(domain, step, cwd)
                last_step = step
                item = {'text': step['text'], 'ok': result['ok'], 'matched': False,
                        'missing': [], 'unexpected': [], 'path': step['path']}
                executed.append(item)
                try:
                    observed = runtime.observe(domain, cwd)
                except core.PlanbotError as exc:
                    if exc.code != 'SENSOR_FAILED':
                        raise
                    raise PlanbotError(
                        'SENSOR_FAILED',
                        f"{exc.message}; after {len(executed)} executed step(s), "
                        f"last {step['text']} @ {_path_text(step['path'])}; "
                        're-observe the current state before retrying',
                    ) from exc
                base, facts = observed['base'], observed['facts']
                state['facts'] = facts
                matched, missing, unexpected = _compare_effects(domain, step, base)
                item.update(matched=matched, missing=missing, unexpected=unexpected)
                leaf = _action_leaf(cur['tree'], k + 1)
                last = {'text': step['text'], 'path': step['path'],
                        'idx': leaf['idx'] if leaf is not None else None,
                        'unchanged': before == base}
                k += 1
                if not matched:
                    need = ({'kind': 'mismatch', 'step': step['text']}, {'step': k})
        if need is None:
            continue

        trigger, where = need
        ra = htn.remaining_agenda(cur, **where)
        state['trigger'] = trigger
        stuck = {'step': last_step['text'] if last_step else None, 'node': ra['resume'],
                 'idx': ra['idx'], 'path': ra['path'], 'reason': 'replan_limit',
                 'missing': executed[-1]['missing'] if executed else [],
                 'unexpected': executed[-1]['unexpected'] if executed else [],
                 'failure': None}
        if state['replans'] >= max_replans:
            state['stuck'] = stuck
            return report('stuck')
        state['replans'] += 1
        new = htn.decompose(domain, base, ra['agenda'], allowed, max_depth, max_nodes)
        replanned.append({
            'after': len(executed), 'resume': ra['resume'], 'idx': ra['idx'], 'path': ra['path'],
            'trigger': trigger, 'found': new['found'], 'steps': [s['text'] for s in new['steps']],
        })
        if not new['found']:
            stuck['reason'] = 'no_plan'
            stuck['failure'] = new['failure']
            state['stuck'] = stuck
            return report('stuck')
        if (last is not None and last['unchanged'] and new['steps']
                and _same_instance(new, last)):
            stuck['reason'] = 'no_progress'
            state['stuck'] = stuck
            return report('stuck')
        cur = new
        check_runner(cur)
        k = 0
