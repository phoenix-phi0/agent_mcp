import copy
import json
import re
import subprocess

from planbot.core import Domain, PlanbotError, Sensor, derive, parse_literal

_TIMEOUT = 30
_TEMPLATE_KEY = re.compile(r'\{([^{}]*)\}')
_ACTION_PARAMETER = re.compile(r'\{([A-Za-z_][A-Za-z0-9_]*)\}')


def _fail(sensor: Sensor, message: str) -> PlanbotError:
    return PlanbotError('SENSOR_FAILED', f'sensor {sensor.name}: {message}')


def _cmd_output(domain: Domain, sensor: Sensor, cmd: dict) -> str:
    runner = domain.cmd_runner
    if runner is None:
        raise _fail(sensor, 'no cmd runner')
    try:
        result = runner(cmd['name'], copy.deepcopy(cmd['args']))
    except Exception as exc:
        raise _fail(sensor, f'cmd runner raised {exc!r}') from exc
    if not isinstance(result, dict):
        raise _fail(sensor, 'cmd result is not a dict')
    if 'exit_code' not in result or 'output' not in result:
        raise _fail(sensor, 'cmd result lacks exit_code or output')
    exit_code = result['exit_code']
    if not isinstance(exit_code, int) or isinstance(exit_code, bool) or exit_code != 0:
        raise _fail(sensor, f'cmd exit_code is {exit_code!r}, expected 0')
    if not isinstance(result['output'], str):
        raise _fail(sensor, 'cmd output is not str')
    return result['output']


def _run_output(domain: Domain, sensor: Sensor, cwd: str) -> str:
    run = sensor.run
    if 'callback' in run:
        try:
            output = domain.callbacks[run['callback']]({'cwd': cwd})
        except Exception as exc:
            raise _fail(sensor, f'callback raised {exc!r}') from exc
        if not isinstance(output, str):
            raise _fail(sensor, 'callback did not return str')
        return output
    if 'cmd' in run:
        return _cmd_output(domain, sensor, run['cmd'])
    parts = []
    for argv in run['cmds']:
        try:
            done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            raise _fail(sensor, f'command {argv!r} timed out') from exc
        except OSError as exc:
            raise _fail(sensor, f'command {argv!r} could not start: {exc}') from exc
        if done.returncode != 0:
            raise _fail(sensor, f'command {argv!r} exited with {done.returncode}')
        parts.append(done.stdout)
    return ''.join(parts)


def _fill(template: str, values: dict[str, str]) -> str:
    def replace(match):
        return values.get(match.group(1), match.group(0))
    return _TEMPLATE_KEY.sub(replace, template)


def _regex_texts(rule: dict, output: str) -> list[str]:
    texts = []
    pattern = re.compile(rule['pattern'])
    for line in output.splitlines():
        match = pattern.search(line)
        if match is None:
            continue
        values = {str(i): g for i, g in enumerate(match.groups(), 1) if g is not None}
        values.update({k: v for k, v in match.groupdict().items() if v is not None})
        texts.extend(_fill(template, values) for template in rule['facts'])
    return texts


def _text(value) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def _json_node(data, path: list) -> list:
    for key in path:
        if isinstance(data, dict) and isinstance(key, str) and key in data:
            data = data[key]
        elif (isinstance(data, list) and isinstance(key, int)
              and not isinstance(key, bool) and 0 <= key < len(data)):
            data = data[key]
        else:
            return []
    return data if isinstance(data, list) else [data]


def _json_texts(sensor: Sensor, rule: dict, output: str) -> list[str]:
    try:
        data = json.loads(output)
    except ValueError as exc:
        raise _fail(sensor, 'output is not valid JSON') from exc
    where = rule.get('where') or {}
    texts = []
    for element in _json_node(data, rule.get('path', [])):
        if isinstance(element, dict):
            if any(key not in element or _text(element[key]) != want for key, want in where.items()):
                continue
            values = {key: _text(value) for key, value in element.items()}
        else:
            if where:
                continue
            values = {'value': _text(element)}
        texts.extend(_fill(template, values) for template in rule['facts'])
    return texts


def _rule_texts(sensor: Sensor, rule: dict, output: str) -> list[str]:
    kind = rule.get('type')
    if kind == 'regex':
        return _regex_texts(rule, output)
    if kind == 'json':
        return _json_texts(sensor, rule, output)
    raise _fail(sensor, f'unknown extract rule type {kind!r}')


def _to_fact(domain: Domain, sensor: Sensor, text: str) -> tuple[str, ...]:
    try:
        atom = parse_literal(text).atom
    except PlanbotError as exc:
        raise _fail(sensor, f'invalid fact {text!r}: {exc.message}') from exc
    arity = domain.predicates.get(atom[0])
    if arity is None:
        raise _fail(sensor, f'fact {text!r} is not a declared base predicate')
    if len(atom) - 1 != arity:
        raise _fail(sensor, f'fact {text!r} has wrong arity, expected {arity}')
    return atom


def observe(domain: Domain, cwd: str = '.') -> dict:
    base = set()
    for sensor in domain.sensors:
        output = _run_output(domain, sensor, cwd)
        for rule in sensor.extract:
            for text in _rule_texts(sensor, rule, output):
                base.add(_to_fact(domain, sensor, text))
    base = frozenset(base)
    return {'base': base, 'facts': derive(domain, base)}


def run_action(domain: Domain, name: str, args: tuple[str, ...], cwd: str = '.') -> dict:
    action = domain.actions.get(name)
    if action is None:
        raise PlanbotError('USAGE', f'Unknown action {name!r}')
    if len(args) != len(action.params):
        raise PlanbotError(
            'USAGE', f'Action {name!r} expects {len(action.params)} arguments, got {len(args)}',
        )

    binding = dict(zip(action.params, args))
    if 'cmd' in action.run:
        return _run_cmd_action(domain, action.run['cmd'], binding)
    return _run_action_spec(domain, action.run, binding, cwd)


def _substitute(value, binding: dict[str, str]):
    if isinstance(value, str):
        return _ACTION_PARAMETER.sub(lambda m: binding.get(m.group(1), m.group(0)), value)
    if isinstance(value, list):
        return [_substitute(item, binding) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, binding) for key, item in value.items()}
    return value


def _run_cmd_action(domain: Domain, cmd: dict, binding: dict[str, str]) -> dict:
    runner = domain.cmd_runner
    if runner is None:
        return {'ok': False, 'output': 'no cmd runner'}
    try:
        cmd_args = _substitute(copy.deepcopy(cmd['args']), binding)
        result = runner(cmd['name'], cmd_args)
        if not isinstance(result, dict):
            return {'ok': False, 'output': 'invalid cmd result'}
        exit_code = result.get('exit_code')
        ok = isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code == 0
        return {'ok': ok, 'output': str(result['output']) if 'output' in result else ''}
    except Exception as exc:
        return {'ok': False, 'output': str(exc)}


def run_cleanup(domain: Domain, name: str, args: tuple[str, ...], cwd: str = '.') -> dict:
    action = domain.actions[name]
    return _run_action_spec(domain, action.on_fail, dict(zip(action.params, args)), cwd, continue_on_error=True)


def _run_action_spec(domain, run, binding, cwd, continue_on_error=False):
    if 'callback' in run:
        try:
            value = domain.callbacks[run['callback']](binding, {'cwd': cwd})
            output = '' if value is None else str(value)
        except Exception as exc:
            return {'ok': False, 'output': str(exc)}
        return {'ok': True, 'output': output}

    def replace_parameter(match):
        return binding[match.group(1)]

    parts = []
    ok = True
    for command in run['cmds']:
        argv = [_ACTION_PARAMETER.sub(replace_parameter, item) for item in command]
        try:
            if not argv:
                raise OSError('empty command')
            done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
            parts.extend((done.stdout, done.stderr))
            failed = done.returncode != 0
        except OSError:
            failed = True
        if failed:
            ok = False
            if not continue_on_error:
                break
    return {'ok': ok, 'output': ''.join(parts)}
