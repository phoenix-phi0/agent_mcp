"""小 Datalog 求值器（半朴素自底向上）：reason.py 的逻辑规则（安全.dl 等）和旧路径的推理候选（legacy/infer.py）共用。
规则文本格式见 parse_rules；求值 Datalog(rules).add(谓词, 值…) → run()。"""
import re
import time
from collections import defaultdict


class Timeout(Exception):
    pass


def _check(deadline):
    if deadline is not None and time.time() > deadline:
        raise Timeout("超时")


# ============================================================ 规则解析与求值

def _parse_atom(s):
    m = re.match(r"\s*(\w+)\((.*)\)\s*$", s)
    return m.group(1), tuple(a.strip() for a in m.group(2).split(","))


def parse_rules(text):
    rules = []
    for line in text.splitlines():
        line = line.split("%", 1)[0].strip()
        if not line:
            continue
        head, body = line.rstrip(".").split(":-")
        atoms = re.findall(r"\w+\([^)]*\)", body)
        rules.append((_parse_atom(head), [_parse_atom(a) for a in atoms]))
    return rules


def _is_var(a):
    return a[:1].isupper() or a == "_"


class Datalog:
    """元组集合 + 规则；半朴素求值（每轮只用上一轮新增的 delta 去驱动连接）。builtins：全绑定时的过滤谓词。"""

    def __init__(self, rules, builtins=None, deadline=None):
        self.rules = rules
        self.db = defaultdict(set)
        self.builtins = builtins or {}
        self.deadline = deadline

    def add(self, pred, *args):
        self.db[pred].add(tuple(args))

    def _match(self, atom, tup, env):
        pred, args = atom
        env = dict(env)
        for a, v in zip(args, tup):
            if a == "_":
                continue
            if _is_var(a):
                if a in env and env[a] != v:
                    return None
                env[a] = v
            elif a.strip('"') != v:
                return None
        return env

    def _eval_body(self, body, sources, env=None, i=0):
        env = env or {}
        if i == len(body):
            yield env
            return
        pred, args = body[i]
        if pred in self.builtins:
            if self.builtins[pred](*[env[a] for a in args]):
                yield from self._eval_body(body, sources, env, i + 1)
            return
        src = sources[i]
        for j, a in enumerate(args):
            key = env.get(a) if _is_var(a) and a != "_" else (None if _is_var(a) else a.strip('"'))
            if key is not None:
                ix = self._ix.get((id(src), j))
                if ix is None:
                    ix = defaultdict(list)
                    for t in src:
                        ix[t[j]].append(t)
                    self._ix[(id(src), j)] = ix
                src = ix.get(key, ())
                break
        for tup in src:
            e = self._match(body[i], tup, env)
            if e is not None:
                yield from self._eval_body(body, sources, e, i + 1)

    def run(self):
        idb = {r[0][0] for r in self.rules}
        delta = {p: set(self.db[p]) for p in list(self.db)}
        first = True
        while True:
            _check(self.deadline)
            new = defaultdict(set)
            self._ix = {}
            for head, body in self.rules:
                pos = [j for j, (p, _) in enumerate(body) if p not in self.builtins]
                drivers = pos if not first else [None]
                for d in drivers:
                    if d is not None and not delta.get(body[d][0]):
                        continue
                    srcs = []
                    for j, (p, _) in enumerate(body):
                        srcs.append(delta.get(p, set()) if j == d else self.db.get(p, set()))
                    for env in self._eval_body(body, srcs):
                        t = tuple(env.get(a, a.strip('"')) for a in head[1])
                        if t not in self.db[head[0]]:
                            new[head[0]].add(t)
            first = False
            if not any(new.values()):
                break
            for p, ts in new.items():
                self.db[p] |= ts
            delta = new
        return {p: self.db[p] for p in idb}
