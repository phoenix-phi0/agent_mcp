"""Command-line entry point and output rendering."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Iterable

from . import core, executor, htn, planner, runtime
from .memory import Memory


def _emit_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True))


def _facts_lines(facts_texts: Iterable[str]) -> list[str]:
    lines = [f'  {fact}' for fact in sorted(facts_texts)]
    return ['facts:', *(lines or ['  (none)'])]


def _memory_from_args(args: argparse.Namespace) -> Memory | None:
    if getattr(args, 'no_memory', False):
        return None
    return Memory(args.memory_file)


def _observe(args: argparse.Namespace) -> int:
    domain = core.load_domain(args.domain, cmd_runner=getattr(args, 'cmd_runner', None))
    observed = runtime.observe(domain, args.cwd)
    facts = map(core.format_atom, observed['facts'])
    if args.json:
        _emit_json({'facts': sorted(facts), 'base': sorted(map(core.format_atom, observed['base']))})
    else:
        print('\n'.join(_facts_lines(facts)))
    return 0


def _memory_list(args: argparse.Namespace) -> int:
    entries = Memory(args.memory_file).list()
    if args.json:
        _emit_json({'entries': entries})
    elif not entries:
        print('(empty)')
    else:
        for entry in entries:
            goal = f"task {entry['task']}" if 'task' in entry else ', '.join(entry['goal'])
            start = ', '.join(entry['start']) or '-'
            steps = ' ; '.join(core.format_atom((name, *params)) for name, params in entry['steps'])
            print(f"{entry['domain']}: {goal} <- {start} => {steps}")
    return 0


def _memory_clear(args: argparse.Namespace) -> int:
    count = Memory(args.memory_file).clear()
    if args.json:
        _emit_json({'cleared': count})
    else:
        print(f'cleared {count}')
    return 0


def _failure_lines(failure: dict) -> list[str]:
    kind = failure['kind']
    if kind == 'limit':
        return [f"  search limit {failure['max_nodes']} reached"]
    lines = []
    for detail in failure['details']:
        goal = detail['goal']
        if kind == 'no_producer':
            line = f'  {goal}: no usable action produces it'
            if detail['excluded']:
                line += f" (excluded: {', '.join(detail['excluded'])})"
        elif kind == 'blocked':
            line = f"  {goal}: {detail['action']} blocked by {', '.join(detail['missing'])}"
        else:
            line = f'  {goal}: unreachable'
        lines.append(line)
    return lines


def _reason_text(reason: dict) -> str:
    literal = reason['literal'] or 'indirect'
    if reason['for_step'] is None:
        return f'{literal} -> goal'
    return f"{literal} -> step {reason['for_step']} {reason['for_text']}"


def _plan_lines(plan: dict) -> list[str]:
    if not plan['found']:
        return [f"no plan: {plan['failure']['kind']}", *_failure_lines(plan['failure'])]
    steps = plan['steps']
    if not steps:
        return ['plan: goal already satisfied']
    lines = [f"plan: {len(steps)} steps (source: {plan['source']})"]
    for index, step in enumerate(steps, 1):
        mark = ' [irreversible]' if step['irreversible'] else ''
        reasons = '; '.join(_reason_text(reason) for reason in step['reasons'])
        lines.append(f"  {index}. {step['text']}{mark} -- {reasons}")
    return lines


def _plan_exit_code(plan: dict) -> int:
    return 0 if plan['found'] else 1


def _fmt_path(path: list[dict]) -> str:
    return ' > '.join(f"{el['text']}#{el['idx']}" for el in path)


def _render_attempts(tried: list, indent: int) -> list[str]:
    lines = []
    pad = ' ' * indent
    for attempt in tried:
        line = f"{pad}skipped {attempt['method']}: {attempt['reason']}"
        if attempt['detail']:
            line += ': ' + ', '.join(attempt['detail'])
        lines.append(line)
        sub = attempt['sub']
        if sub:
            sub_line = f"{pad}  {sub['item']}"
            if sub['detail']:
                sub_line += ': ' + '; '.join(sub['detail'])
            lines.append(sub_line)
            lines.extend(_render_attempts(sub['tried'], indent + 4))
    return lines


def _render_node(node: dict, depth: int, steps: list[dict]) -> list[str]:
    pad = ' ' * (2 + 2 * depth)
    inner = pad + '  '
    kind = node['kind']
    if kind == 'task':
        line = f"{pad}{node['text']} [method: {node['method']}]"
        if node['binding']:
            line += ' {' + ', '.join(f'{k}={v}' for k, v in sorted(node['binding'].items())) + '}'
        lines = [line]
        if node['done']:
            lines.append(f"{inner}done: {', '.join(item['text'] for item in node['done'])}")
        lines.append(f"{inner}why: {', '.join(node['why']) or '-'}")
        lines.extend(_render_attempts(node['tried'], len(inner)))
    elif kind == 'action':
        line = f"{pad}{node['step']}. {node['text']}"
        if steps[node['step'] - 1]['irreversible']:
            line += ' [irreversible]'
        return [line]
    else:
        lines = [f"{pad}{node['text']}"]
    for child in node['children']:
        lines.extend(_render_node(child, depth + 1, steps))
    return lines


def _render_tree(result: dict) -> list[str]:
    if result['found']:
        lines = ['tree:']
        for node in result['tree']:
            lines.extend(_render_node(node, 0, result['steps']))
        return lines
    failure = result['failure']
    lines = [f"no decomposition: {failure['kind']}"]
    if failure['kind'] == 'limit':
        lines.append(f"  search limit {failure['max_nodes']} reached")
    else:
        line = f"  {failure['item']}"
        if failure['detail']:
            line += ': ' + '; '.join(failure['detail'])
        lines.append(line)
        lines.extend(_render_attempts(failure['tried'], 4))
    return lines


def _render_htn_plan(result: dict) -> list[str]:
    if not result['found']:
        return []
    steps = result['steps']
    if not steps:
        return ['plan: nothing to do']
    lines = [f"plan: {len(steps)} steps (source: {result['source']})"]
    for index, step in enumerate(steps, 1):
        mark = ' [irreversible]' if step['irreversible'] else ''
        lines.append(f"  {index}. {step['text']}{mark}")
    return lines


def _prepare(args: argparse.Namespace):
    domain = core.load_domain(args.domain, cmd_runner=getattr(args, 'cmd_runner', None))
    goal = core.parse_goal(domain, args.goal)
    allowed = planner.allowed_actions(domain, args.allow, args.allow_irreversible)
    return domain, goal, allowed


def _run(args: argparse.Namespace) -> int:
    domain, goal, allowed = _prepare(args)
    if args.execute:
        return _run_execute(args, domain, goal, allowed)
    result = executor.dry_run(domain, goal, allowed, memory=_memory_from_args(args),
                              max_nodes=args.max_nodes, cwd=args.cwd)
    if args.json:
        _emit_json({**result, 'mode': 'dry-run'})
    else:
        lines = [*_facts_lines(result['facts']), 'goal: ' + ', '.join(result['goal']),
                 *_plan_lines(result['plan']), 'mode: dry-run']
        print('\n'.join(lines))
    return _plan_exit_code(result['plan'])


def _list_text(items: list[str]) -> str:
    return ', '.join(sorted(items)) or '-'


def _executed_line(index: int, item: dict) -> str:
    text = item['text']
    if item['matched']:
        line = f"  {index}. {text} {'ok' if item['ok'] else 'failed'}"
    else:
        line = (f"  {index}. {text} MISMATCH missing: {_list_text(item['missing'])}; "
                f"unexpected: {_list_text(item['unexpected'])}")
        if not item['ok']:
            line += ' (failed)'
    if not item['ok'] and item.get('cleanup') is not None:
        line += f" [cleanup {'ok' if item['cleanup']['ok'] else 'failed'}]"
    return line


def _report_lines(report: dict) -> list[str]:
    executed = [_executed_line(index, item) for index, item in enumerate(report['executed'], 1)]
    lines = [*_facts_lines(report['initial_facts']), 'goal: ' + ', '.join(report['goal']),
             *_plan_lines(report['plan']), 'executed:', *(executed or ['  (none)']),
             f"replans: {report['replans']}", f"status: {report['status']}"]
    stuck = report['stuck']
    if stuck:
        lines.append(f"stuck at: {stuck['step']} ({stuck['reason']})")
        if stuck['reason'] == 'no_plan':
            lines.extend(_failure_lines(stuck['failure']))
        if stuck['reason'] == 'observe_failed':
            lines.append(f"  observe failed: {stuck['error']}")
        if report['executed'] and report['executed'][-1].get('output'):
            output = report['executed'][-1]['output']
            last = next(line for line in reversed(output.splitlines()) if line.strip())
            lines.append(f'  last output: {last[-200:]}')
    return [*lines, 'mode: execute']


def _run_execute(args: argparse.Namespace, domain, goal, allowed) -> int:
    report = executor.execute(domain, goal, allowed, memory=_memory_from_args(args),
                              max_nodes=args.max_nodes, max_replans=args.max_replans, cwd=args.cwd)
    if args.json:
        _emit_json({**report, 'mode': 'execute'})
    else:
        print('\n'.join(_report_lines(report)))
    return 0 if report['status'] in ('done', 'already_satisfied') else 1


def _prepare_task(args: argparse.Namespace):
    """Validate in the agreed order: domain, task, names/numbers (all before any observation)."""
    domain = core.load_domain(args.domain, cmd_runner=getattr(args, 'cmd_runner', None))
    task = core.parse_task(domain, args.task)
    allowed = planner.allowed_actions(domain, args.allow, args.allow_irreversible)
    for option in ('max_nodes', 'max_depth', 'max_replans'):
        value = getattr(args, option, None)
        if value is not None and value < 0:
            raise core.PlanbotError('USAGE', f"--{option.replace('_', '-')} must not be negative: {value}")
    return domain, task, allowed


def _print_task_result(args: argparse.Namespace, out: dict) -> int:
    plan = out['plan']
    if args.json:
        _emit_json(out)
    else:
        lines = [f"task: {out['task']}", *_render_tree(plan), *_render_htn_plan(plan)]
        if 'mode' in out:
            lines.append(f"mode: {out['mode']}")
        print('\n'.join(lines))
    return _plan_exit_code(plan)


def _task_replan_line(item: dict) -> str:
    trigger = item['trigger']
    line = (f"  redo {item['resume']}#{item['idx']} after step {item['after']} "
            f"({trigger['kind']}: {trigger['step']}): ")
    if not item['found']:
        return line + 'no decomposition'
    return line + (' ; '.join(item['steps']) or 'nothing to do')


def _task_report_lines(report: dict) -> list[str]:
    executed = [f"{_executed_line(index, item)} @ {_fmt_path(item['path'])}"
                for index, item in enumerate(report['executed'], 1)]
    plan = report['plan']
    lines = [*_facts_lines(report['initial_facts']), f"task: {report['task']}",
             *_render_tree(plan), *_render_htn_plan(plan),
             'executed:', *(executed or ['  (none)']),
             f"replans: {report['replans']}",
             *(_task_replan_line(item) for item in report['replanned']),
             f"status: {report['status']}"]
    stuck = report['stuck']
    if stuck:
        where = _fmt_path([*stuck['path'], {'text': stuck['node'], 'idx': stuck['idx']}])
        trigger = report['trigger']
        lines.append(f"stuck at: {stuck['step'] or '-'} ({stuck['reason']}) in {where}")
        lines.append(f"trigger: {trigger['kind']} {trigger['step']}")
        if stuck['reason'] == 'no_plan':
            lines.extend(_render_tree({'found': False, 'failure': stuck['failure']}))
    return [*lines, 'mode: execute']


def _task_execute(args: argparse.Namespace, domain, task, allowed) -> int:
    report = executor.execute_task(domain, task, allowed, memory=_memory_from_args(args),
                                   max_nodes=args.max_nodes, max_replans=args.max_replans,
                                   max_depth=args.max_depth, cwd=args.cwd)
    if args.json:
        _emit_json({**report, 'mode': 'execute'})
    else:
        print('\n'.join(_task_report_lines(report)))
    return 0 if report['status'] in ('done', 'already_satisfied') else 1


def _task(args: argparse.Namespace) -> int:
    domain, task, allowed = _prepare_task(args)
    if args.execute:
        return _task_execute(args, domain, task, allowed)
    result = executor.dry_run_task(domain, task, allowed, memory=_memory_from_args(args),
                                   max_nodes=args.max_nodes, max_depth=args.max_depth, cwd=args.cwd)
    return _print_task_result(args, {'task': result['task'], 'plan': result['plan'], 'mode': 'dry-run'})


def _explain_task(args: argparse.Namespace) -> int:
    domain, task, allowed = _prepare_task(args)
    base = runtime.observe(domain, args.cwd)['base']
    plan = htn.decompose_task(domain, base, task, allowed, max_depth=args.max_depth,
                              max_nodes=args.max_nodes)
    return _print_task_result(args, {'task': core.format_atom(task), 'plan': plan})


def _explain(args: argparse.Namespace) -> int:
    if args.task is not None:
        return _explain_task(args)
    domain, goal, allowed = _prepare(args)
    base = runtime.observe(domain, args.cwd)['base']
    plan = planner.plan(domain, base, goal, allowed, args.max_nodes)
    goal_texts = sorted(map(core.format_literal, goal))
    if args.json:
        _emit_json({'goal': goal_texts, 'plan': plan})
    else:
        print('\n'.join(['goal: ' + ', '.join(goal_texts), *_plan_lines(plan)]))
    return _plan_exit_code(plan)


def _split_names(value: str) -> list[str]:
    return value.split(',')


class _OnceAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f'{option_string} may be given only once')
        setattr(namespace, self.dest, values)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='planbot')
    commands = parser.add_subparsers(dest='command', required=True)
    memory_path = os.environ.get('PLANBOT_MEMORY', os.path.expanduser('~/.planbot/memory.json'))

    for name in ('observe', 'run', 'explain', 'task'):
        command = commands.add_parser(name)
        command.add_argument('--domain', required=True, metavar='PATH')
        command.add_argument('--cwd', default='.', metavar='DIR')
        command.add_argument('--json', action='store_true')
        if name == 'observe':
            command.set_defaults(handler=_observe)
            continue

        if name in ('run', 'explain'):
            command.add_argument('--goal', required=(name == 'run'), action='append', metavar='LITERAL')
        if name in ('explain', 'task'):
            command.add_argument('--task', required=(name == 'task'), action=_OnceAction,
                                 default=None, metavar='CALL')
            command.add_argument('--max-depth', type=int, default=20, metavar='N')
        command.add_argument('--allow', type=_split_names, metavar='a,b')
        command.add_argument('--allow-irreversible', type=_split_names, metavar='a,b')
        command.add_argument('--max-nodes', type=int, default=10000, metavar='N')
        command.add_argument('--memory-file', default=memory_path, metavar='PATH')
        command.add_argument('--no-memory', action='store_true')
        if name in ('run', 'task'):
            command.add_argument('--max-replans', type=int, default=3, metavar='N')
        if name in ('run', 'task'):
            command.add_argument('--execute', action='store_true')
        command.set_defaults(handler={'run': _run, 'explain': _explain, 'task': _task}[name])

    memory = commands.add_parser('memory').add_subparsers(required=True)
    for name, handler in (('list', _memory_list), ('clear', _memory_clear)):
        command = memory.add_parser(name)
        command.add_argument('--memory-file', default=memory_path, metavar='PATH')
        command.add_argument('--json', action='store_true')
        command.set_defaults(handler=handler)
    return parser


def main(argv: list[str] | None = None, cmd_runner: Callable | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == 'explain' and bool(args.goal) == (args.task is not None):
            parser.error('explain needs exactly one of --goal and --task')
    except SystemExit as exc:
        return exc.code

    args.cmd_runner = cmd_runner
    try:
        return args.handler(args)
    except core.PlanbotError as exc:
        if args.json:
            _emit_json({'error': {'code': exc.code, 'message': exc.message}})
        else:
            print(f'error: {exc.code}: {exc.message}', file=sys.stderr)
        return 2
