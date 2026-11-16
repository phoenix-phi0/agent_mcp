import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""VS Code 插件交代码的整条链路（不开 VS Code）：起真的查看服务（带口令、--write），
插件那一侧的 lib/workdir.js 用 Node 的 fetch 和本机 git 跑：

  拉取 api/workfiles → 写进本地空文件夹记基线 → 改文件 → 找出改动 → POST api/submit_files
  → 服务器写入、跑测试、生成实现记录 → 本地基线前移；测试没过时服务器撤回、本地改动还在。
"""
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_wf_submit_files import CMD, PASS, FAIL, USER, check, setup  # noqa: E402
from tools import workflow_ctl as wc  # noqa: E402

TOKEN = "e2eTokenForSubmitFiles_0123"

NODE = r"""
const W = require(process.env.WORKDIR_JS);
const root = process.env.ROOT_URL, name = process.env.RUN, dir = process.env.DIR;
const fs = require("fs"), path = require("path");
(async () => {
  const out = {};
  let r = await fetch(root + "api/workfiles?name=" + encodeURIComponent(name));
  const wf = await r.json();
  out.pull_status = r.status;
  await W.pullInto(dir, wf, { run: name, server: root });
  fs.writeFileSync(path.join(dir, "user.py"), process.env.USER_PY);
  fs.writeFileSync(path.join(dir, "check.py"), process.env.CHECK_PY);
  const files = await W.collectChanges(dir);
  out.changes = files.map((f) => [f.path, f.action]);
  const send = async () => {
    const body = JSON.stringify({ name, step: wf.step, attempt: wf.attempt, summary: "插件交的", status: "完成",
      open_issues: [], files: files.map((f) => ({ path: f.path, content: f.content })) });
    const r = await fetch(root + "api/submit_files", { method: "POST", headers: { "Content-Type": "application/json" }, body });
    return [r.status, await r.json()];
  };
  const [code, res] = await send();
  out.code = code;
  out.res = res;
  if (code === 200) await W.markSubmitted(dir, "已交");
  out.after = (await W.collectChanges(dir)).map((f) => f.path);
  console.log(JSON.stringify(out));
})().catch((e) => { console.log(JSON.stringify({ crash: String(e && e.stack || e) })); process.exit(1); });
"""


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def node(env):
    p = subprocess.run(["node", "-e", NODE], env={**os.environ, **env}, capture_output=True, text=True, timeout=300)
    line = (p.stdout.strip().splitlines() or ["{}"])[-1]
    out = json.loads(line)
    if "crash" in out:
        raise AssertionError(out["crash"] + p.stderr)
    return out


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='vscsub-', dir=ROOT / 'data/tmp'))
    srv = None
    try:
        demo, run_id = setup(tmp, 'e')
        name = Path(run_id).name
        port = free_port()
        log = open(tmp / 'srv.log', 'w')
        srv = subprocess.Popen([_sys.executable, str(ROOT / 'tools/trace_server.py'), str(demo), '--port', str(port),
                                '--token', TOKEN, '--write'], stdout=log, stderr=subprocess.STDOUT,
                               start_new_session=True)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        base = {"WORKDIR_JS": str(ROOT / 'tools/vscode/lib/workdir.js'), "ROOT_URL": f"http://127.0.0.1:{port}/{TOKEN}/",
                "RUN": name}

        # 测试没过：服务器拒、撤回；本地改动还在
        d1 = tmp / 'local1'
        out = node({**base, "DIR": str(d1), "USER_PY": USER, "CHECK_PY": FAIL})
        check(out['pull_status'] == 200 and sorted(out['changes']) == [['check.py', '新增'], ['user.py', '新增']],
              '拉下来（空目录）→ 本地新增两个文件，插件找出两条改动')
        check(out['code'] == 400 and '测试没过' in out['res']['error'] and '1 failed' in out['res']['error'],
              '测试没过：服务器 400，带测试输出')
        check(not (demo / 'work/demo/user.py').exists(), '服务器上的文件撤回了')
        check(sorted(out['after']) == ['check.py', 'user.py'], '本地改动还在，改完可以再交')
        check(wc.status(run_id)['pending']['step'] == 6, '还停在第 6 步')

        # 测试通过：服务器收，往下走；本地基线前移
        d2 = tmp / 'local2'
        out = node({**base, "DIR": str(d2), "USER_PY": USER, "CHECK_PY": PASS})
        rec = out['res']['status']['submitted_files']['record'] if out['code'] == 200 else {}
        check(out['code'] == 200 and rec['verification']['method'] == CMD
              and rec['verification']['result'] == '通过（退出码 0）：1 passed', '测试通过：服务器收下，验证是真跑的')
        check((demo / 'work/demo/user.py').read_text() == USER, '文件写进了这一步的工作目录')
        check(out['after'] == [], '本地基线前移，没有没交的改动')
        for _ in range(100):           # 交了以后后台进程往下推进到第 7 步
            st = wc.status(run_id)
            if st['status'] == 'waiting' and st['pending']['step'] == 7:
                break
            time.sleep(0.1)
        check(st['steps'][5]['status'] == 'ok' and st['steps'][5]['source'] == 'external'
              and st['pending']['step'] == 7, '第 6 步记成外部结果，停在第 7 步')
    finally:
        if srv is not None:
            try:
                os.killpg(srv.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            srv.wait(timeout=10)
        time.sleep(0.3)
        shutil.rmtree(tmp, ignore_errors=True)
    print('插件交代码整条链路：全部通过')


if __name__ == '__main__':
    run()
