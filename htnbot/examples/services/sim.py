"""In-memory service simulator used by the services example domain."""

import json

_deps = {}
_running = set()
_locked = set()
_faults = {}
_calls = []


def reset(services, running=(), locked=()):
    _deps.clear()
    _deps.update({name: list(deps) for name, deps in services.items()})
    _running.clear()
    _running.update(running)
    _locked.clear()
    _locked.update(locked)
    _faults.clear()
    _calls.clear()


def set_fault(action, service, times):
    _faults[(action, service)] = times


def calls():
    return list(_calls)


def _apply(action, service, effect):
    _calls.append((action, service))
    left = _faults.get((action, service), 0)
    if left > 0:
        _faults[(action, service)] = left - 1
        return
    effect(service)


def _snapshot(ctx):
    return json.dumps({
        'services': [{'name': name, 'running': name in _running, 'locked': name in _locked}
                     for name in sorted(_deps)],
        'depends': [{'service': name, 'dep': dep} for name in sorted(_deps) for dep in sorted(_deps[name])],
    })


def _start(binding, ctx):
    _apply('start', binding['s'], _running.add)


def _stop(binding, ctx):
    _apply('stop', binding['s'], _running.discard)


CALLBACKS = {'snapshot': _snapshot, 'start': _start, 'stop': _stop}
