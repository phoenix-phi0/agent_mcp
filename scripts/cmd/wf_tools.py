"""编排流程的机械命令（命令表里的 check_evidence、compare_failures、git_mark、git_mine、git_stage_mine、secret_scan）。

每个子命令把给人看的几行写在前面，最后一行固定是一个 JSON 对象（流程里的 data），退出码 0 = 成功，1 = 检查没过，2 = 参数或环境错误。
不读敏感文件的内容（密钥、证书、.env、配置里的 config.json），查密钥只报文件和行号、不打印命中的内容。

  evidence <目录> <记录JSON>         按记录里每条依据的「出处（文件:行）」读原文核对
  failures <基线JSON> <现在JSON或测试输出>   分成新挂、原来就挂、修好了
  mark <仓库>                          记起点：工作区和暂存区现在的样子（git stash create，不动文件），返回编号
  mine <仓库> <编号> <允许的路径…>       起点以来的改动：我的（在允许清单里）、范围外、开工前就有的
  stage <仓库> <编号> <允许的路径…>      只把起点以来、清单里的改动放进暂存区；先查密钥，打补丁冲突就一个都不放
  secrets <仓库> <路径…>               查文件里像密钥的内容
"""
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

MARKS = Path('/workspace/agent_mcp/data/tmp/wfmarks')
SENSITIVE = re.compile(r'(^|/)(\.env(\..*)?|.*\.(pem|key|p12|pfx|keystore)|id_rsa.*|id_ed25519.*|\.netrc|config\.json|'
                       r'.*credential.*|.*secret.*|\.auth_secret|auth\.json)$', re.I)
SECRET_PATTERNS = [
    ('私钥', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('AWS 访问密钥', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('API 密钥（sk-）', re.compile(r'\bsk-[A-Za-z0-9_-]{20,}')),
    ('GitHub 令牌', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}')),
    ('Slack 令牌', re.compile(r'\bxox[abprs]-[A-Za-z0-9-]{10,}')),
    ('赋值给 key/secret/token/password 的长字符串',
     re.compile(r'(?i)(api[_-]?key|secret|token|passw(or)?d|access[_-]?key)["\']?\s*[:=]\s*["\'][^"\'\s]{12,}["\']')),
    ('赋值给 key 的 UUID', re.compile(r'(?i)key["\']?\s*[:=]\s*["\']?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')),
]


def out(data, lines=(), code=0):
    for line in lines:
        print(line)
    print(json.dumps(data, ensure_ascii=False))
    sys.exit(code)


def fail(msg):
    out({'状态': '错误', 'error': msg}, [msg], 2)


def load_json(text, what):
    try:
        return json.loads(text)
    except ValueError as e:
        fail(f'{what}不是合法的 JSON：{e}')


# ---- 抽查依据 ----

def _norm(s):
    return re.sub(r'\s+', '', s)


def _evidence_items(x, path='$'):
    if isinstance(x, dict):
        if isinstance(x.get('出处'), str) and isinstance(x.get('原文'), str):
            yield path, x
        for k, v in x.items():
            yield from _evidence_items(v, f'{path}.{k}')
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _evidence_items(v, f'{path}[{i}]')


def evidence(root, record_text):
    root = Path(root).resolve()
    if not root.is_dir():
        fail(f'目录不存在：{root}')
    record = load_json(record_text, '记录')
    bad, ok, skipped = [], 0, 0
    for where, ev in _evidence_items(record):
        src = ev['出处'].strip()
        m = re.fullmatch(r'([^\s:]+):(\d+)(?:-(\d+))?', src)
        if not m:
            skipped += 1          # 不是文件:行（比如记录员写的「第 3 步」），不抽查
            continue
        rel, a, b = m[1], int(m[2]), int(m[3] or m[2])
        f = (root / rel).resolve()
        problem = None
        if root not in f.parents:
            problem = '出处越出项目目录'
        elif SENSITIVE.search(rel):
            problem = '出处是敏感文件，不读'
        elif not f.is_file():
            problem = '文件不存在'
        elif b < a:
            problem = '行号范围倒了'
        else:
            lines = f.read_text(encoding='utf-8', errors='replace').splitlines()
            if a > len(lines):
                problem = f'行号超出文件（共 {len(lines)} 行）'
            else:
                window = ''.join(lines[max(0, a - 4):min(len(lines), b + 3)])     # 前后各放 3 行余量
                want = _norm(ev['原文'].replace('…', ''))
                if not want:
                    problem = '原文是空的'
                elif want not in _norm(window):
                    problem = '原文和文件里这几行对不上'
        if problem:
            bad.append({'位置': where, '出处': src, '问题': problem})
        else:
            ok += 1
    total = ok + len(bad)
    lines = [f'依据 {total} 条：对得上 {ok}，对不上 {len(bad)}，不是文件:行没抽查 {skipped}']
    lines += [f'  ✗ {x["出处"]}：{x["问题"]}（{x["位置"]}）' for x in bad]
    state = '成功' if not bad and total else ('没有依据' if not total else '失败')
    out({'状态': state, 'checked': total, 'ok': ok, 'skipped': skipped, 'bad': bad}, lines, 0 if state == '成功' else 1)


# ---- 对照失败 ----

def parse_failures(text):
    """从测试输出里认出失败项：pytest、unittest、run_all。认不出就返回空列表。"""
    names = []
    for line in text.splitlines():
        s = line.strip()
        if re.match(r'^FAILED \(', s):          # unittest 的汇总行「FAILED (failures=1)」，不是用例
            continue
        m = (re.match(r'^(?:FAILED|ERROR)\s+(\S+?)(?:\s+-\s.*)?$', s)                 # pytest -q 末尾的短摘要
             or re.match(r'^(?:FAIL|ERROR):\s+(.+?)\s*$', s)                          # unittest
             or re.match(r'^✗\s+(.+?)\s*$', s))                                       # run_all 的组
        if m and m[1] not in names:
            names.append(m[1])
    return names


def _as_list(text, what):
    t = text.strip()
    if t.startswith('['):
        v = load_json(t, what)
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            fail(f'{what}要是用例名的列表')
        # 列表里照抄了输出行（「FAIL: x」「FAILED x - …」）的，按输出的规则取出用例名
        return list(dict.fromkeys((parse_failures(x) or [x.strip()])[0] for x in v))
    if t.startswith('{'):
        v = load_json(t, what)
        lst = v.get('failing_tests') if isinstance(v, dict) else None
        if not isinstance(lst, list):
            fail(f'{what}是对象时要有 failing_tests 列表（基线核对的格式）')
        return list(dict.fromkeys(str(x) for x in lst))
    return parse_failures(text)


def _with_exit(text, names, name):
    """认不出用例名、但输出说明测试没过（EXIT 不是 0、有 Traceback）时，把整个测试当一个失败项。
    agent_mcp 自己的测试大多是脚本：失败只打一个 Traceback，没有 FAILED 那种行。"""
    if names or text.strip().startswith(('[', '{')):
        return names
    m = re.findall(r'^EXIT=(\d+)\s*$', text, re.M)
    if (m and m[-1] != '0') or 'Traceback (most recent call last)' in text:
        return [name or '（整个测试）']
    return names


def failures(base_text, now_text, name=''):
    base = _with_exit(base_text, _as_list(base_text, '基线'), name)
    now = _with_exit(now_text, _as_list(now_text, '现在的结果'), name)
    new = [x for x in now if x not in base]
    still = [x for x in now if x in base]
    fixed = [x for x in base if x not in now]
    lines = [f'新挂 {len(new)}，原来就挂 {len(still)}，修好了 {len(fixed)}']
    lines += [f'  新挂：{x}' for x in new[:50]]
    out({'状态': '成功' if not new else '失败', 'new': new, 'still': still, 'fixed': fixed}, lines, 0 if not new else 1)


# ---- git：记起点、我的改动、暂存、查密钥 ----

def git(repo, *args, check=True, input=None):
    p = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, input=input,
                       env=dict(os.environ, GIT_TERMINAL_PROMPT='0', LC_ALL='C'))
    if check and p.returncode != 0:
        fail(f'git {args[0]} 失败：{p.stderr.decode("utf-8", "replace").strip()[:300]}')
    return p


def _repo(repo):
    r = Path(repo).resolve()
    top = git(r, 'rev-parse', '--show-toplevel', check=False)
    if top.returncode != 0:
        fail(f'不是 git 仓库：{r}')
    return Path(top.stdout.decode().strip())


def _untracked(repo):
    names = git(repo, 'ls-files', '--others', '--exclude-standard', '-z').stdout.decode('utf-8', 'surrogateescape')
    res = {}
    for n in filter(None, names.split('\0')):
        f = repo / n
        if f.is_file() and not f.is_symlink():
            res[n] = hashlib.sha1(f.read_bytes()).hexdigest()
    return res


def mark(repo):
    repo = _repo(repo)
    head = git(repo, 'rev-parse', '--verify', '-q', 'HEAD', check=False).stdout.decode().strip() or None
    if not head:
        fail('仓库还没有提交，记不了起点')
    snap = git(repo, 'stash', 'create').stdout.decode().strip() or head     # 干净的工作区：起点就是 HEAD
    mid = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    git(repo, 'update-ref', f'refs/wfsnap/{mid}', snap)                    # 挂个引用，免得被当垃圾回收
    MARKS.mkdir(parents=True, exist_ok=True)
    info = {'id': mid, 'repo': str(repo), 'base': snap, 'head': head, 'untracked': _untracked(repo),
            'at': time.strftime('%Y-%m-%d %H:%M:%S')}
    (MARKS / f'{mid}.json').write_text(json.dumps(info, ensure_ascii=False), encoding='utf-8')
    dirty = len(git(repo, 'diff', '--name-only', 'HEAD').stdout.decode().split())
    out({'状态': '成功', 'id': mid, 'base': snap, 'head': head, 'dirty_at_mark': dirty, 'untracked_at_mark': len(info['untracked'])},
        [f'起点 {mid}：HEAD {head[:10]}，开工前已有改动的文件 {dirty} 个，未跟踪文件 {len(info["untracked"])} 个'])


def _load_mark(repo, mid):
    if not re.fullmatch(r'\d{8}-\d{6}-[0-9a-f]{6}', mid or ''):
        fail(f'起点编号不对：{mid}')
    f = MARKS / f'{mid}.json'
    if not f.is_file():
        fail(f'没有这个起点：{mid}')
    info = json.loads(f.read_text(encoding='utf-8'))
    if Path(info['repo']) != repo:
        fail(f'起点 {mid} 记的是别的仓库：{info["repo"]}')
    return info


def _allowed(path, allow):
    for a in allow:
        a = a.strip().rstrip('/')
        if not a:
            continue
        if path == a or path.startswith(a + '/') or fnmatch.fnmatchcase(path, a):
            return True
    return False


def _changes(repo, info):
    """起点以来变了的文件：已跟踪的（起点 → 工作区有差异）和未跟踪的（新出现或内容变了）。"""
    tracked = git(repo, 'diff', '--name-only', '--no-renames', '-z', info['base']).stdout.decode('utf-8', 'surrogateescape')
    changed = {n: 'tracked' for n in filter(None, tracked.split('\0'))}
    now = _untracked(repo)
    for n, h in now.items():
        if n in changed:
            continue
        old = info['untracked'].get(n)
        if old is None:
            changed[n] = 'new'
        elif old != h:
            changed[n] = 'untracked_changed'         # 开工前就有、开工后又改了的未跟踪文件：分不清哪部分是我的
    return changed


def mine(repo, mid, allow):
    repo = _repo(repo)
    info = _load_mark(repo, mid)
    changed = _changes(repo, info)
    mine_, outside, unclear = [], [], []
    for n, kind in sorted(changed.items()):
        if not _allowed(n, allow):
            outside.append(n)
        elif kind == 'untracked_changed':
            unclear.append(n)
        else:
            mine_.append(n)
    before = len(git(repo, 'diff', '--name-only', info['head'], info['base']).stdout.decode().split())
    lines = [f'起点 {mid} 以来：我的 {len(mine_)}，范围外 {len(outside)}，归属不明 {len(unclear)}（开工前就有改动的文件 {before} 个，不动）']
    lines += [f'  我的：{n}' for n in mine_] + [f'  范围外：{n}' for n in outside] + [f'  归属不明：{n}' for n in unclear]
    ok = not outside and not unclear
    out({'状态': '成功' if ok else '失败', 'mine': mine_, 'outside': outside, 'unclear': unclear, 'before': before}, lines, 0 if ok else 1)


def _scan_text(text):
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        for label, pat in SECRET_PATTERNS:
            if pat.search(line):
                hits.append((i, label))
                break
    return hits


def secrets(repo, paths):
    repo = _repo(repo)
    hits = []
    for rel in paths:
        f = (repo / rel).resolve()
        if repo not in f.parents or not f.is_file():
            continue
        if SENSITIVE.search(rel):
            hits.append({'文件': rel, '行': 0, '类别': '敏感文件名（不该提交）'})
            continue
        for line, label in _scan_text(f.read_text(encoding='utf-8', errors='replace')):
            hits.append({'文件': rel, '行': line, '类别': label})
    lines = [f'查了 {len(paths)} 个文件，可疑 {len(hits)} 处'] + [f'  ✗ {h["文件"]}:{h["行"]} {h["类别"]}' for h in hits]
    out({'状态': '成功' if not hits else '失败', 'hits': hits}, lines, 0 if not hits else 1)


def stage(repo, mid, allow):
    repo = _repo(repo)
    info = _load_mark(repo, mid)
    changed = _changes(repo, info)
    picked = {n: k for n, k in changed.items() if _allowed(n, allow)}
    unclear = [n for n, k in picked.items() if k == 'untracked_changed']
    if unclear:
        out({'状态': '失败', 'reason': '归属不明', 'unclear': unclear},
            [f'归属不明的文件（开工前就有、开工后又改了的未跟踪文件），一个都没放：{unclear}'], 1)
    if not picked:
        out({'状态': '失败', 'reason': '没有改动', 'staged': []}, ['起点以来清单里没有改动，没有可暂存的'], 1)
    tracked = [n for n, k in picked.items() if k == 'tracked']
    new = [n for n, k in picked.items() if k == 'new']
    patch = git(repo, 'diff', '--binary', '--no-renames', info['base'], '--', *tracked).stdout if tracked else b''
    # 查密钥：补丁里新加的行和新文件的内容
    hits = []
    added = '\n'.join(l[1:] for l in patch.decode('utf-8', 'replace').splitlines() if l.startswith('+') and not l.startswith('+++'))
    for line, label in _scan_text(added):
        hits.append({'文件': '（补丁新增行）', '行': line, '类别': label})
    for n in new:
        if SENSITIVE.search(n):
            hits.append({'文件': n, '行': 0, '类别': '敏感文件名（不该提交）'})
            continue
        for line, label in _scan_text((repo / n).read_text(encoding='utf-8', errors='replace')):
            hits.append({'文件': n, '行': line, '类别': label})
    for n in tracked:
        if SENSITIVE.search(n):
            hits.append({'文件': n, '行': 0, '类别': '敏感文件名（不该提交）'})
    if hits:
        out({'状态': '失败', 'reason': '查到像密钥的内容', 'hits': hits},
            ['查到像密钥的内容，一个都没放：'] + [f'  ✗ {h["文件"]}:{h["行"]} {h["类别"]}' for h in hits], 1)
    if patch:
        chk = git(repo, 'apply', '--cached', '--check', '--binary', '-', check=False, input=patch)
        if chk.returncode != 0:
            msg = chk.stderr.decode('utf-8', 'replace').strip()[:500]
            out({'状态': '失败', 'reason': '补丁和暂存区对不上', 'detail': msg},
                ['起点以来的改动放不进暂存区（和开工前别人的改动挨在一起，或者暂存区已经有东西）：', msg, '一个都没放，交给人处理'], 1)
        git(repo, 'apply', '--cached', '--binary', '-', input=patch)
    if new:
        git(repo, 'add', '--', *new)
    staged = sorted(tracked + new)
    out({'状态': '成功', 'staged': staged}, [f'放进暂存区 {len(staged)} 个文件：'] + [f'  {n}' for n in staged])


# ---- 小检查：输出对正则、文件大小 ----

def expect(text, pattern):
    try:
        rx = re.compile(pattern, re.M)
    except re.error as e:
        fail(f'正则写错了：{e}')
    m = rx.search(text)
    if m:
        out({'状态': '成功', 'match': m.group(0)[:300]}, [f'匹配到：{m.group(0)[:200]}'])
    out({'状态': '失败', 'match': None}, [f'没有匹配 {pattern}（输出共 {len(text.splitlines())} 行）'], 1)


def size(path, limit):
    p = Path(path)
    if not p.exists():
        fail(f'不存在：{path}')
    total = p.stat().st_size if p.is_file() else sum(f.stat().st_size for f in p.rglob('*') if f.is_file() and not f.is_symlink())
    limit = int(limit)
    ok = total <= limit
    out({'状态': '成功' if ok else '失败', 'bytes': total, 'limit': limit},
        [f'{path}：{total} 字节，上限 {limit}，{"没超" if ok else "超了"}'], 0 if ok else 1)


# ---- 工作树和在别处跑测试 ----

WORK_ROOTS = (Path('/workspace/agent_mcp/workflow_demo/work'), Path('/workspace/agent_mcp/data/tmp'))
PY = '/workspace/agent_mcp/.venv/bin/python'


def _under_roots(p):
    p = Path(p).resolve()
    if not any(r == p.parent or r in p.parents for r in WORK_ROOTS):
        fail(f'只能放在 {"、".join(map(str, WORK_ROOTS))} 下面：{p}')
    return p


def wt_add(repo, path):
    """在 path 开一个 repo 的 git 工作树（分支 wf/<目录名>，从 HEAD 开）。已经是这个仓库的工作树就接着用。"""
    repo = _repo(repo)
    path = _under_roots(path)
    branch = f'wf/{path.name}'
    if path.exists():
        common = git(path, 'rev-parse', '--git-common-dir', check=False)
        top = git(path, 'rev-parse', '--show-toplevel', check=False)
        mine_ = (common.returncode == 0 and Path(path, common.stdout.decode().strip()).resolve() == (repo / '.git').resolve()
                 and Path(top.stdout.decode().strip()).resolve() == path)
        if not mine_:
            fail(f'{path} 已经存在，但不是 {repo} 的工作树')
        head = git(path, 'rev-parse', 'HEAD').stdout.decode().strip()
        out({'状态': '成功', 'path': str(path), 'branch': branch, 'head': head, 'reused': True},
            [f'工作树已经在：{path}（{branch}），接着用'])
    exists = git(repo, 'rev-parse', '--verify', '-q', f'refs/heads/{branch}', check=False).returncode == 0
    args = ['worktree', 'add', str(path), branch] if exists else ['worktree', 'add', '-b', branch, str(path), 'HEAD']
    git(repo, *args)
    head = git(path, 'rev-parse', 'HEAD').stdout.decode().strip()
    out({'状态': '成功', 'path': str(path), 'branch': branch, 'head': head, 'reused': False},
        [f'开了工作树 {path}（分支 {branch}，从 {head[:10]}）'])


def _run_test_in(cwd, test, limit):
    if not re.fullmatch(r'tests/[\w./-]+\.py', test) or '..' in test:
        fail(f'测试路径不对：{test}')
    if not (Path(cwd) / test).is_file():
        print(f'没有这个测试：{test}')
        print('EXIT=2')
        sys.exit(2)
    timeout = max(10, int(os.environ.get('CMD_TIMEOUT', '160')) - 5)
    try:
        p = subprocess.run([PY, test], cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        lines, rc = (p.stdout + p.stderr).splitlines(), p.returncode
    except subprocess.TimeoutExpired:
        lines, rc = [f'超时（{timeout} 秒）'], 124
    print('\n'.join(lines[-int(limit):]))
    print(f'EXIT={rc}')
    sys.exit(rc)


def dir_test(cwd, test, limit):
    """在指定目录（工作树）里跑一个测试，用主仓库的虚拟环境。输出和 run_test 一样，最后一行 EXIT=退出码。"""
    _run_test_in(_under_roots(cwd), test, limit)


def staged_test(repo, test, source, limit):
    """把暂存区（source=staged）或 HEAD（source=head）检出到临时目录，在那里跑测试，跑完删掉。"""
    import shutil
    import tempfile
    repo = _repo(repo)
    tmp = Path(tempfile.mkdtemp(prefix='staged_test_', dir='/workspace/agent_mcp/data/tmp'))
    try:
        if source == 'staged':
            git(repo, 'checkout-index', '-a', '-f', f'--prefix={tmp}/')
        elif source == 'head':
            arc = git(repo, 'archive', 'HEAD').stdout
            subprocess.run(['tar', '-x', '-C', str(tmp)], input=arc, check=True)
        else:
            fail(f'source 只能是 staged 或 head：{source}')
        print(f'检出 {source} 到临时目录，跑 {test}')
        try:
            _run_test_in(tmp, test, limit)
        except SystemExit as e:
            code = e.code
        else:
            code = 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(code)


def main(argv):
    if not argv:
        fail('要写子命令：evidence / failures / mark / mine / stage / secrets')
    cmd, rest = argv[0], argv[1:]
    if cmd == 'evidence' and len(rest) == 2:
        evidence(*rest)
    elif cmd == 'failures' and len(rest) in (2, 3):
        failures(*rest)
    elif cmd == 'expect' and len(rest) == 2:
        expect(*rest)
    elif cmd == 'size' and len(rest) == 2:
        size(*rest)
    elif cmd == 'wt_add' and len(rest) == 2:
        wt_add(*rest)
    elif cmd == 'dir_test' and len(rest) == 3:
        dir_test(*rest)
    elif cmd == 'staged_test' and len(rest) == 4:
        staged_test(*rest)
    elif cmd == 'mark' and len(rest) == 1:
        mark(rest[0])
    elif cmd == 'mine' and len(rest) >= 3:
        mine(rest[0], rest[1], rest[2:])
    elif cmd == 'stage' and len(rest) >= 3:
        stage(rest[0], rest[1], rest[2:])
    elif cmd == 'secrets' and len(rest) >= 2:
        secrets(rest[0], rest[1:])
    else:
        fail(f'参数不对：{cmd} {len(rest)} 个参数')


if __name__ == '__main__':
    main(sys.argv[1:])
