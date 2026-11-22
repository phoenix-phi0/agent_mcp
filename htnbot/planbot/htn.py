"""HTN total-order forward decomposition, decomposition tree and resume agenda.

Pure computation over the expected-effect model: nothing here executes
actions, observes the world, or reads or writes files.

The search is iterative.  Pending work is a linked list of frames
(``(frame, rest)`` pairs); every task item opens a choice point kept on an
explicit list, so neither the number of siblings nor chronological
backtracking deepens the Python call stack.  The produced decomposition is
recorded as a persistent linked list of events and turned into the tree only
once the whole agenda succeeded.
"""
import copy

from . import planner
from .core import (
    Domain, Literal, PlanbotError, bind, derive, format_atom, format_literal, holds,
    match_all, parse_literal,
)

_LIMIT = object()


def _goal_text(texts: list[str]) -> str:
    return 'goal ' + ', '.join(texts)


def _ref(src: dict) -> dict:
    return {
        'kind': src['kind'], 'name': src['name'], 'args': list(src['args']),
        'goal': list(src['goal']), 'text': src['text'], 'idx': src['idx'],
    }


def _plain(src: dict) -> dict:
    item = _ref(src)
    item['resume'] = None
    return item


def _bound(lit: Literal, binding: dict) -> Literal:
    return Literal(lit.positive, bind(lit.atom, binding))


def _why(method, binding: dict) -> list[str]:
    return [format_literal(_bound(lit, binding)) for lit in method.pre]


def _subitems(method, binding: dict) -> list[dict]:
    items = []
    for idx, sub in enumerate(method.subtasks):
        if sub.kind == 'goal':
            texts = [format_literal(_bound(lit, binding)) for lit in sub.goal]
            items.append({'kind': 'goal', 'name': sub.name, 'args': [], 'goal': texts,
                          'text': _goal_text(texts), 'idx': idx, 'resume': None})
        else:
            atom = bind((sub.name, *sub.args), binding)
            items.append({'kind': sub.kind, 'name': sub.name, 'args': list(atom[1:]), 'goal': [],
                          'text': format_atom(atom), 'idx': idx, 'resume': None})
    return items


def _unmet(pre: tuple[Literal, ...], binding: dict, facts: frozenset) -> list[str]:
    ground, open_ = set(), set()
    for lit in pre:
        lit = _bound(lit, binding)
        if any(arg.startswith('?') for arg in lit.atom[1:]):
            open_.add(format_literal(lit))
        elif not holds(lit, facts):
            ground.add(format_literal(lit))
    return sorted(ground) if ground else sorted(open_)


def _apply(domain: Domain, state: frozenset, name: str, args) -> frozenset:
    action = domain.actions[name]
    binding = dict(zip(action.params, args))
    removed = {bind(atom, binding) for atom in action.delete}
    added = {bind(atom, binding) for atom in action.add}
    return frozenset((state - removed) | added)


def _attempt(method: str, binding: dict, reason: str, detail: list[str], sub=None) -> dict:
    return {'method': method, 'binding': dict(binding), 'reason': reason,
            'detail': list(detail), 'sub': sub}


def _trace(text: str, detail=(), tried=()) -> dict:
    return {'item': text, 'detail': list(detail), 'tried': list(tried)}


class _Choice:
    """Choice point of one task item: its candidates and how they failed."""

    __slots__ = ('item', 'owner', 'depth', 'after', 'state', 'trail', 'options', 'tried',
                 'current', 'closed', 'ever', 'inner', 'later')

    def __init__(self, item, owner, depth, after, state, trail, options):
        self.item = item
        self.owner = owner          # choice point whose candidate holds this item
        self.depth = depth
        self.after = after          # frames to handle once this item is complete
        self.state = state          # base state at the item
        self.trail = trail          # events recorded before the item
        self.options = options      # iterator of (attempt, None) | (None, candidate)
        self.tried = []
        self.current = None         # (method name, binding) of the candidate in use
        self.closed = False         # current candidate's own subitems completed
        self.ever = False           # some candidate completed its subitems
        self.inner = None           # first failing direct subitem: (text, trace)
        self.later = None           # first failing later item after closing: (text, trace)

    def below(self, owner) -> bool:
        """Whether this item lies strictly inside the candidate of ``owner``."""
        if owner is None:
            return True
        scope = self.owner
        while scope is not None:
            if scope is owner:
                return True
            scope = scope.owner
        return False


class _Search:
    def __init__(self, domain, allowed, max_depth, max_nodes):
        self.domain = domain
        self.allowed = allowed
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.count = 0
        self.choices: list[_Choice] = []
        self.first_top = None
        self.by_task: dict[str, list] = {}
        for method in domain.methods:
            self.by_task.setdefault(method.task, []).append(method)

    # ----- candidates -------------------------------------------------
    def _fresh(self, item, state):
        facts = None
        for method in self.by_task.get(item['name'], []):
            b0 = dict(zip(method.params, item['args']))
            banned = sorted({sub.name for sub in method.subtasks
                             if sub.kind == 'action' and sub.name not in self.allowed})
            if banned:
                yield _attempt(method.name, b0, 'not_allowed', banned), None
                continue
            if facts is None:
                facts = derive(self.domain, state)
            bindings = match_all(method.pre, facts, b0)
            if not bindings:
                yield _attempt(method.name, b0, 'precondition', _unmet(method.pre, b0, facts)), None
                continue
            for binding in bindings:
                yield None, (method.name, binding, _why(method, binding),
                             _subitems(method, binding), [])

    def _resumed(self, item, state, method):
        resume = item['resume']
        binding = dict(resume['binding'])
        done = resume['done']
        yield None, (method.name, binding, _why(method, binding), resume['rest'], done)
        if not resume['switch']:
            return
        head = [(ref['kind'], ref['text']) for ref in done]
        for attempt, candidate in self._fresh(item, state):
            if candidate is None:
                yield attempt, None
                continue
            name, other, why, subs, _ = candidate
            if name == method.name and other == binding:
                continue
            if len(subs) < len(head) or [(s['kind'], s['text']) for s in subs[:len(head)]] != head:
                yield _attempt(name, other, 'prefix_mismatch', [ref['text'] for ref in done]), None
                continue
            yield None, (name, other, why, subs[len(head):], done)

    def _open(self, item, owner, depth, after, state, trail):
        """Return a failure trace, or a new choice point for a task item."""
        text = item['text']
        if depth > self.max_depth:
            return _trace(text, ['depth limit ' + str(self.max_depth)])
        methods = self.by_task.get(item['name'], [])
        resume = item.get('resume')
        if resume is None:
            if not methods:
                return _trace(text, ['no methods'])
            options = self._fresh(item, state)
        else:
            chosen = [m for m in methods if m.name == resume['method']]
            if not chosen:
                return _trace(text, ['unknown method ' + str(resume['method'])])
            options = self._resumed(item, state, chosen[0])
        return _Choice(item, owner, depth, after, state, trail, options)

    # ----- primitive items --------------------------------------------
    def _action(self, item, state):
        name = item['name']
        action = self.domain.actions.get(name)
        if action is None:
            return _trace(item['text'], ['unknown action ' + name]), state
        if name not in self.allowed:
            return _trace(item['text'], ['not allowed: ' + name]), state
        binding = dict(zip(action.params, item['args']))
        facts = derive(self.domain, state)
        missing = sorted({format_literal(_bound(lit, binding)) for lit in action.pre
                          if not holds(_bound(lit, binding), facts)})
        if missing:
            return _trace(item['text'], ['missing: ' + ', '.join(missing)]), state
        return None, _apply(self.domain, state, name, item['args'])

    def _goal(self, item, state):
        goal = tuple(parse_literal(text) for text in item['goal'])
        found = planner.plan(self.domain, state, goal, self.allowed, self.max_nodes)
        if not found['found']:
            kind = found['failure']['kind']
            detail = ['no plan: ' + kind]
            if kind == 'no_producer':
                excluded = sorted({name for entry in found['failure']['details']
                                   for name in entry.get('excluded', [])})
                if excluded:
                    detail.append('excluded: ' + ', '.join(excluded))
            return _trace(item['text'], detail), state, None
        for entry in found['steps']:
            state = _apply(self.domain, state, entry['action'], entry['args'])
        return None, state, found['steps']

    # ----- failure bookkeeping ----------------------------------------
    def _report(self, text, owner, trace):
        """A item failed on its own: tell its owner and every closed candidate before it."""
        if owner is None:
            if self.first_top is None:
                self.first_top = trace
        elif owner.inner is None:
            owner.inner = (text, trace)
        for choice in self.choices:
            if choice.closed and choice.later is None and choice.below(owner):
                choice.later = (text, trace)

    def _abandon(self, choice):
        name, binding = choice.current
        if choice.closed:
            reason, found = 'later_failed', choice.later
        else:
            reason, found = 'subtask_failed', choice.inner
        text, sub = found if found is not None else (None, None)
        return _attempt(name, binding, reason, [] if text is None else [text], sub)

    # ----- main loop --------------------------------------------------
    def run(self, base, agenda):
        frames = None
        for item in reversed(agenda):
            frames = (('item', item, None, 1), frames)
        state = frozenset(base)
        trail = None
        mode = 'forward'
        while True:
            if mode == 'forward':
                if frames is None:
                    return 'found', trail
                frame, frames = frames
                if frame[0] == 'close':
                    frame[1].closed = frame[1].ever = True
                    trail = (('close',), trail)
                    continue
                _, item, owner, depth = frame
                if item['kind'] == 'action':
                    trace, state = self._action(item, state)
                    event = ('action', item)
                elif item['kind'] == 'goal':
                    trace, state, steps = self._goal(item, state)
                    event = ('goal', item, steps)
                else:
                    opened = self._open(item, owner, depth, frames, state, trail)
                    if isinstance(opened, _Choice):
                        self.choices.append(opened)
                        mode = 'next'
                        continue
                    trace = opened
                if trace is None:
                    trail = (event, trail)
                else:
                    self._report(item['text'], owner, trace)
                    mode = 'back'
            elif mode == 'back':
                if not self.choices:
                    return 'failed', self.first_top
                choice = self.choices[-1]
                choice.tried.append(self._abandon(choice))
                mode = 'next'
            else:
                choice = self.choices[-1]
                candidate = self._next(choice)
                if candidate is _LIMIT:
                    return 'limit', None
                if candidate is None:
                    self.choices.pop()
                    if not choice.ever:
                        text = choice.item['text']
                        self._report(text, choice.owner, _trace(text, (), choice.tried))
                    mode = 'back'
                    continue
                name, binding, why, children, done = candidate
                choice.current = (name, binding)
                choice.closed = False
                choice.inner = choice.later = None
                state = choice.state
                frames = (('close', choice), choice.after)
                for child in reversed(children):
                    frames = (('item', child, choice, choice.depth + 1), frames)
                trail = (('open', choice.item, name, binding, why, choice.tried, done), choice.trail)
                mode = 'forward'

    def _next(self, choice):
        for attempt, candidate in choice.options:
            self.count += 1
            if self.count > self.max_nodes:
                return _LIMIT
            if candidate is not None:
                return candidate
            choice.tried.append(attempt)
        return None

    # ----- result -----------------------------------------------------
    def build(self, trail):
        events = []
        while trail is not None:
            event, trail = trail
            events.append(event)
        events.reverse()
        roots: list[dict] = []
        levels = [(roots, [])]
        steps: list[dict] = []
        for event in events:
            if event[0] == 'close':
                levels.pop()
                continue
            siblings, path = levels[-1]
            item = event[1]
            node = _node(item, path)
            siblings.append(node)
            here = path + [{'text': item['text'], 'idx': item['idx']}]
            if event[0] == 'open':
                _, _, name, binding, why, tried, done = event
                node.update(method=name, binding=dict(binding), why=list(why),
                            tried=list(tried), done=[_ref(ref) for ref in done])
                levels.append((node['children'], here))
            elif event[0] == 'action':
                self._leaf(node, path, steps)
            else:
                for idx, entry in enumerate(event[2]):
                    leaf = _node({'kind': 'action', 'name': entry['action'], 'args': entry['args'],
                                  'goal': [], 'text': entry['text'], 'idx': idx}, here)
                    self._leaf(leaf, here, steps)
                    node['children'].append(leaf)
        return roots, steps

    def _leaf(self, node, path, steps):
        node['step'] = len(steps) + 1
        steps.append({
            'action': node['name'], 'args': list(node['args']), 'text': node['text'],
            'irreversible': self.domain.actions[node['name']].irreversible,
            'path': [dict(el) for el in path],
        })


def _node(item: dict, path: list[dict]) -> dict:
    node = _ref(item)
    node.update(path=[dict(el) for el in path], method=None, binding=None, why=[], tried=[],
                done=[], children=[], step=None)
    return node


def decompose(
    domain: Domain, base: frozenset, agenda: list[dict], allowed: frozenset[str],
    max_depth: int = 20, max_nodes: int = 10000,
) -> dict:
    search = _Search(domain, allowed, max_depth, max_nodes)
    outcome, payload = search.run(base, agenda)
    result = {'found': False, 'source': 'decompose', 'agenda': copy.deepcopy(agenda),
              'steps': [], 'tree': [], 'failure': None}
    if outcome == 'found':
        result['tree'], result['steps'] = search.build(payload)
        result['found'] = True
    elif outcome == 'limit':
        result['failure'] = {'kind': 'limit', 'item': None, 'detail': [], 'tried': [],
                             'max_depth': max_depth, 'max_nodes': max_nodes}
    else:
        trace = payload or _trace(None)
        result['failure'] = {'kind': 'no_method', 'item': trace['item'], 'detail': trace['detail'],
                             'tried': trace['tried'], 'max_depth': max_depth, 'max_nodes': max_nodes}
    return result


def decompose_task(
    domain: Domain, base: frozenset, task: tuple[str, ...], allowed: frozenset[str],
    max_depth: int = 20, max_nodes: int = 10000,
) -> dict:
    root = {'kind': 'task', 'name': task[0], 'args': list(task[1:]), 'goal': [],
            'text': format_atom(tuple(task)), 'idx': 0, 'resume': None}
    return decompose(domain, base, [root], allowed, max_depth, max_nodes)


def _usage(message: str) -> PlanbotError:
    return PlanbotError('USAGE', message)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _chain_to_step(nodes: list[dict], step: int):
    """[(node, position), ...] from a top-level node down to the leaf with ``step``."""
    for position, node in enumerate(nodes):
        if node['step'] == step:
            return [(node, position)]
        below = _chain_to_step(node['children'], step)
        if below is not None:
            return [(node, position)] + below
    return None


def remaining_agenda(result: dict, step: int | None = None, loc: list[int] | None = None) -> dict:
    if (step is None) == (loc is None):
        raise _usage('give exactly one of step and loc')
    tree = result['tree']
    if step is not None:
        if not _is_int(step) or not 1 <= step <= len(result['steps']):
            raise _usage(f'step {step!r} is not in 1..{len(result["steps"])}')
        chain = _chain_to_step(tree, step)
        if chain is None or len(chain) < 2:
            raise _usage(f'step {step} is a top-level item without a parent node')
        leaf_position = chain[-1][1]
        chain = chain[:-1]
    else:
        if not isinstance(loc, list) or not loc:
            raise _usage('loc must be a nonempty list of positions')
        chain = []
        nodes = tree
        for position in loc:
            if not _is_int(position) or not 0 <= position < len(nodes):
                raise _usage(f'loc {loc!r} is out of range')
            chain.append((nodes[position], position))
            nodes = nodes[position]['children']
        if chain[-1][0]['kind'] != 'goal':
            raise _usage(f'loc {loc!r} does not point to a goal node')
        leaf_position = None

    target = chain[-1][0]
    entry = _plain(target)
    if target['kind'] == 'task':
        done = [_ref(ref) for ref in target['done']]
        done += [_ref(child) for child in target['children'][:leaf_position]]
        if done:
            entry['resume'] = {
                'method': target['method'], 'binding': dict(target['binding']), 'done': done,
                'rest': [_plain(child) for child in target['children'][leaf_position:]],
                'switch': True,
            }
    for level in range(len(chain) - 2, -1, -1):
        node = chain[level][0]
        position = chain[level + 1][1]
        outer = _plain(node)
        outer['resume'] = {
            'method': node['method'], 'binding': dict(node['binding']),
            'done': [_ref(ref) for ref in node['done']] + [_ref(c) for c in node['children'][:position]],
            'rest': [entry] + [_plain(c) for c in node['children'][position + 1:]],
            'switch': False,
        }
        entry = outer
    top = chain[0][1]
    return {
        'resume': target['text'], 'idx': target['idx'],
        'path': [dict(el) for el in target['path']],
        'agenda': [entry] + copy.deepcopy(result['agenda'][top + 1:]),
    }


def goal_checks(result: dict, done_steps: int) -> list[dict]:
    """Goal nodes whose boundary falls exactly after ``done_steps`` executed steps."""
    found: list[dict] = []
    _collect_goals(result['tree'], [], done_steps, found, [0])
    return found


def _collect_goals(nodes: list[dict], prefix: list[int], done_steps: int, found: list,
                   seen: list) -> None:
    """Walk siblings left to right; ``seen`` is a one-slot counter of action leaves passed."""
    for position, node in enumerate(nodes):
        loc = prefix + [position]
        if node['kind'] == 'action':
            seen[0] += 1
        elif node['kind'] == 'goal':
            after = node['children'][-1]['step'] if node['children'] else seen[0]
            if after == done_steps:
                found.append({'loc': list(loc), 'text': node['text'], 'goal': list(node['goal']),
                              'idx': node['idx'], 'path': [dict(el) for el in node['path']]})
        _collect_goals(node['children'], loc, done_steps, found, seen)


def from_memory(domain: Domain, base: frozenset, task: tuple[str, ...], tree: list,
                allowed: frozenset[str]) -> dict | None:
    """Replay a remembered tree from ``base``; None unless every recorded check still holds."""
    try:
        return _replay_tree(domain, base, task, tree, allowed)
    except (PlanbotError, KeyError, TypeError, AttributeError, ValueError, IndexError):
        return None


def _replay_tree(domain: Domain, base: frozenset, task: tuple[str, ...], tree: list,
                 allowed: frozenset[str]) -> dict | None:
    if not isinstance(tree, list) or len(tree) != 1 or not task:
        return None
    root = tree[0]
    if root['kind'] != 'task' or root['name'] != task[0] or root['args'] != list(task[1:]):
        return None
    steps: list[dict] = []
    state = _replay(domain, allowed, tree, frozenset(base), steps)
    if state is None:
        return None
    agenda_root = {'kind': 'task', 'name': task[0], 'args': list(task[1:]), 'goal': [],
                   'text': format_atom(tuple(task)), 'idx': 0, 'resume': None}
    return {'found': True, 'source': 'memory', 'agenda': [agenda_root], 'steps': steps,
            'tree': tree, 'failure': None}


def _replay(domain: Domain, allowed: frozenset[str], nodes: list[dict], state: frozenset,
            steps: list[dict]) -> frozenset | None:
    """Replay sibling nodes left to right; the state after them, or None if a check fails."""
    for node in nodes:
        if node['done'] != []:
            return None
        if node['kind'] == 'action':
            state = _replay_leaf(domain, allowed, node, state, steps)
        elif node['kind'] == 'goal':
            if any(child['kind'] != 'action' for child in node['children']):
                return None
            state = _replay(domain, allowed, node['children'], state, steps)
            if state is not None and not _goals_hold(domain, state, node['goal']):
                return None
        elif node['kind'] == 'task':
            state = _replay(domain, allowed, node['children'], state, steps)
        else:
            return None
        if state is None:
            return None
    return state


def _replay_leaf(domain: Domain, allowed: frozenset[str], node: dict, state: frozenset,
                 steps: list[dict]) -> frozenset | None:
    name = node['name']
    args = list(node['args'])
    action = domain.actions.get(name)
    if action is None or name not in allowed or len(args) != len(action.params):
        return None
    if node['step'] != len(steps) + 1:
        return None
    binding = dict(zip(action.params, args))
    facts = derive(domain, state)
    if not all(holds(_bound(lit, binding), facts) for lit in action.pre):
        return None
    steps.append({'action': name, 'args': args, 'text': node['text'],
                  'irreversible': action.irreversible,
                  'path': [dict(el) for el in node['path']]})
    return _apply(domain, state, name, args)


def _goals_hold(domain: Domain, state: frozenset, texts: list[str]) -> bool:
    facts = derive(domain, state)
    return all(holds(parse_literal(text), facts) for text in texts)
