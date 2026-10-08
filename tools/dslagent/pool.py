"""常驻 claude 进程池：替换 llm_router.ClaudeCLIClient._run_local，模型调用不再每次起 claude -p。

每个 (系统提示, 模型) 一个常驻进程：
  claude -p --input-format stream-json --output-format stream-json --verbose --include-partial-messages
         --tools "" --strict-mcp-config --system-prompt S --model M
每次调用写一条 user 消息、读到 type=result 为止；拿到结果后**立刻**再发一条 "/clear"（CLI 内置的会话重置，
不调 API、不花钱），在后台线程里把它的 result 读掉——下一次调用前会话已清空，每次调用都是独立问题。
选「清空」不选「累积上下文」：DSL 里每问本来独立，累积会让输入越滚越长、cache 读也要钱，还可能被前几轮带偏。

缓存：Claude Code 自己在系统提示和最后一条消息上打 cache_control；真正能命中的是跨调用不变的前缀，
所以规划提示里不变的大段放在规划的系统提示里（见 prompts.SYSTEM），定位.zs / 读改测.zs 的固定说明放在
prompts.LIB_SYSTEM 里（两种用途共用一个进程）；用户消息只放变化内容。

实测（plan6）：单次调用墙钟 5.0s → 2.1s，首 token 3.0s → 1.1s，API 时间不变。

返回一个像 subprocess.CompletedProcess 的对象：stdout 是 --output-format json 那样的单个 JSON
（result、total_cost_usd、is_error、duration_ms、duration_api_ms、usage），外加 _pool 字段：
ttft_ms、wall_ms、t_start/t_end、spawn（这次是否新起进程）、wait_reset_ms。
"""
import json
import os
import subprocess
import threading
import time
from types import SimpleNamespace


def _opt(cmd, name, default=None):
    return cmd[cmd.index(name) + 1] if name in cmd and cmd.index(name) + 1 < len(cmd) else default


class Session:
    def __init__(self, system, model, cwd, binary, env, log=None):
        self.system, self.model, self.cwd, self.binary, self.env, self.log = system, model, cwd, binary, env, log
        self.p = None
        self.reset_thread = None
        self.last_total = {}   # session_id -> 已累计 total_cost_usd（stream-json 里是会话累计值）
        self.lock = threading.Lock()
        self.n_turns = 0

    def spawn(self):
        cmd = [self.binary, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
               "--include-partial-messages", "--tools", "", "--strict-mcp-config",
               "--system-prompt", self.system]
        if self.model:
            cmd += ["--model", self.model]
        err = open(self.log, "ab") if self.log else subprocess.DEVNULL
        try:
            self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err,
                                      text=True, encoding="utf-8", errors="replace", cwd=self.cwd, env=self.env,
                                      bufsize=1)
        finally:
            if self.log:
                err.close()
        self.n_turns = 0

    def alive(self):
        return self.p is not None and self.p.poll() is None

    def _send(self, text):
        self.p.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": text}},
                                      ensure_ascii=False) + "\n")
        self.p.stdin.flush()

    def _read_result(self, deadline, t0=None, mark=None):
        """读到 type=result；mark 是 dict，记第一个文字增量的时刻。"""
        while True:
            if time.time() > deadline:
                raise TimeoutError
            line = self.p.stdout.readline()
            if not line:
                raise EOFError("claude 常驻进程退出了")
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                continue
            if mark is not None and "ttft" not in mark and j.get("type") == "stream_event" and \
                    (j.get("event") or {}).get("type") == "content_block_delta":
                mark["ttft"] = time.time() - t0
            if j.get("type") == "result":
                return j

    def _reset_bg(self, timeout):
        def run():
            try:
                self._send("/clear")
                self._read_result(time.time() + timeout)
            except Exception:
                self.kill()
        self.reset_thread = threading.Thread(target=run, daemon=True)
        self.reset_thread.start()

    def kill(self):
        try:
            if self.p and self.p.poll() is None:
                self.p.kill()
                self.p.wait(timeout=5)
        except Exception:
            pass

    def ask(self, prompt, timeout):
        """问一次。进程中途退出（EOF / 管道断了）就重起再问一次——常驻进程偶尔会死（内存紧时实测过），
        别让一个死进程把整版计划带垮；超时不重试（再等一轮太贵）。"""
        j, meta = self._ask(prompt, timeout)
        if j is None and meta.get("retry"):
            j, meta2 = self._ask(prompt, timeout)
            meta = dict(meta2, retried=meta["error"]) if j is not None else meta2
        return j, meta

    def _ask(self, prompt, timeout):
        with self.lock:
            spawn = False
            w0 = time.time()
            if self.reset_thread is not None:
                self.reset_thread.join(timeout=30)
                self.reset_thread = None
            wait_reset = time.time() - w0
            if not self.alive():
                self.spawn()
                spawn = True
            t0 = time.time()
            mark = {}
            try:
                self._send(prompt)
                j = self._read_result(t0 + timeout, t0, mark)
            except TimeoutError:
                self.kill()
                return None, {"error": f"claude 超过 {timeout} 秒没有返回"}
            except (EOFError, BrokenPipeError, OSError) as e:
                self.kill()
                return None, {"error": f"常驻进程出错：{e}", "retry": True}
            t1 = time.time()
            self.n_turns += 1
            sid = j.get("session_id")
            tot = j.get("total_cost_usd") or 0
            cost = tot - self.last_total.get(sid, 0)
            self.last_total[sid] = tot
            self._reset_bg(timeout=60)
            return j, {"cost": cost, "ttft_ms": round(mark["ttft"] * 1000) if "ttft" in mark else None,
                       "wall_ms": round((t1 - t0) * 1000), "t_start": t0, "t_end": t1, "spawn": spawn,
                       "wait_reset_ms": round(wait_reset * 1000), "turn": self.n_turns}


class Pool:
    """cwd：claude 进程的工作目录（空目录，别让它读到项目的 CLAUDE.md）；env：子进程环境（已洗掉 API key 等）。"""

    def __init__(self, cwd, binary, env, log=None):
        self.cwd, self.binary, self.env, self.log = str(cwd), binary, env, log
        self.sessions = {}
        self.lock = threading.Lock()

    def get(self, system, model):
        with self.lock:
            k = (system, model)
            if k not in self.sessions:
                self.sessions[k] = Session(system, model, self.cwd, self.binary, self.env, self.log)
            return self.sessions[k]

    def prewarm(self, system, model):
        s = self.get(system, model)
        with s.lock:
            if not s.alive():
                s.spawn()

    def run_local(self, cmd, timeout):
        """llm_router.ClaudeCLIClient._run_local 的替身：cmd = [claude, -p, prompt, --output-format json, …]。"""
        prompt = cmd[2] if len(cmd) > 2 else ""
        s = self.get(_opt(cmd, "--system-prompt", ""), _opt(cmd, "--model", ""))
        j, meta = s.ask(prompt, timeout)
        if j is None:
            out = {"type": "result", "is_error": True, "result": meta["error"], "_pool": meta}
            return SimpleNamespace(stdout=json.dumps(out, ensure_ascii=False), stderr=meta["error"], returncode=1)
        out = {"type": "result", "subtype": j.get("subtype"), "is_error": j.get("is_error"), "result": j.get("result"),
               "total_cost_usd": meta["cost"], "duration_ms": j.get("duration_ms"),
               "duration_api_ms": j.get("duration_api_ms"), "usage": j.get("usage"), "num_turns": j.get("num_turns"),
               "_pool": meta}
        return SimpleNamespace(stdout=json.dumps(out, ensure_ascii=False), stderr="",
                               returncode=1 if j.get("is_error") else 0)

    def close(self):
        for s in self.sessions.values():
            if s.reset_thread is not None:
                s.reset_thread.join(timeout=10)
            try:
                if s.alive():
                    s.p.stdin.close()
                    s.p.wait(timeout=5)
            except Exception:
                s.kill()

    def kill(self):
        for s in self.sessions.values():
            s.kill()


def child_env(tmp):
    """claude 子进程的环境：洗掉 CLAUDECODE / CLAUDE_CODE_*（cbatch 同款）和 ANTHROPIC_API_KEY（要走订阅登录），
    TMPDIR / CLAUDE_CODE_TMPDIR 指到可写的临时目录（/tmp 满了 claude 会 ENOSPC 秒退，plan7 撞上过）。"""
    from tools.cbatch import _child_env
    env = _child_env()
    env.pop("ANTHROPIC_API_KEY", None)
    env["TMPDIR"] = env["CLAUDE_CODE_TMPDIR"] = str(tmp)
    return env
