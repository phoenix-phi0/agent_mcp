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
ttft_ms、wall_ms、t_start/t_end、spawn（这次是否新起进程）、wait_reset_ms，以及首 token 对冲的
hedged、winner（primary/backup）、hedge_at_ms、extra_cost（被中止那一路的估算费用，已计入 total_cost_usd）。

首 token 对冲见 Session 的说明（阈值 HEDGE_SEC / DSLAGENT_HEDGE_SEC）。
"""
import json
import os
import queue
import subprocess
import threading
import time
from types import SimpleNamespace

# 首 token 对冲阈值（秒）。依据 plan9/11/12 共 344 次带首 token 的调用：正常调用中位 2.6s、P90 4.4s、最大 5.98s，
# 之后直接断档到 8.3s；8.3s 以上的长尾 22 次（6.4%，最长 72s），另有 2 次 150 秒超时连首 token 都没出。
# 取 7s：在正常调用最大值和长尾最小值之间，按历史数据正常调用误触发 0 次。DSLAGENT_HEDGE_SEC 可改，0 = 关。
HEDGE_SEC = 7.0
# 被中止那一路的费用估算（美元 / 百万 token）：CLI 被中断时报的费用是 0，只能按它 message_start 里的 usage 估。
# 中止的一路按定义还没出首 token，没有输出 token；如果连 message_start 都没收到就记 0（服务端是否计费看不到）。
PRICE = {"haiku": (1.0, 1.25, 2.0, 0.10), "opus": (5.0, 6.25, 10.0, 0.50), "": (3.0, 3.75, 6.0, 0.30)}


def hedge_sec():
    try:
        return float(os.environ.get("DSLAGENT_HEDGE_SEC", HEDGE_SEC))
    except ValueError:
        return HEDGE_SEC


def _opt(cmd, name, default=None):
    return cmd[cmd.index(name) + 1] if name in cmd and cmd.index(name) + 1 < len(cmd) else default


def _usage_cost(model, u):
    """按 message_start 的 usage 估输入费用（输入 / 5 分钟缓存写 / 1 小时缓存写 / 缓存读）。"""
    inp, w5, w1, rd = next((v for k, v in PRICE.items() if k and k in (model or "")), PRICE[""])
    cc = u.get("cache_creation") or {}
    c1 = cc.get("ephemeral_1h_input_tokens") or 0
    c5 = cc.get("ephemeral_5m_input_tokens")
    if c5 is None:
        c5 = max(0, (u.get("cache_creation_input_tokens") or 0) - c1)
    return ((u.get("input_tokens") or 0) * inp + c5 * w5 + c1 * w1 + (u.get("cache_read_input_tokens") or 0) * rd) / 1e6


class Proc:
    """一个 claude 子进程 + 读 stdout 的后台线程：每行连同自己一起塞进会话的队列（进程退出时塞 None），
    这样读结果能带超时（readline 会一直卡住），对冲时也能同时等两个进程。"""

    def __init__(self, cmd, cwd, env, log, q):
        err = open(log, "ab") if log else subprocess.DEVNULL
        try:
            self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err,
                                      text=True, encoding="utf-8", errors="replace", cwd=cwd, env=env, bufsize=1)
        finally:
            if log:
                err.close()
        self.pid = self.p.pid
        threading.Thread(target=self._pump, args=(q,), daemon=True).start()

    def _pump(self, q):
        try:
            for line in self.p.stdout:
                q.put((self, line))
        except (OSError, ValueError):
            pass
        q.put((self, None))

    def alive(self):
        return self.p.poll() is None

    def send(self, text):
        self.p.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": text}},
                                      ensure_ascii=False) + "\n")
        self.p.stdin.flush()

    def kill(self):
        try:
            if self.p.poll() is None:
                self.p.kill()
            self.p.wait(timeout=5)
        except Exception:
            pass


def _first_token(j):
    return j.get("type") == "stream_event" and (j.get("event") or {}).get("type") == "content_block_delta"


class Session:
    """首 token 对冲（hedge）：问题发出 hedge 秒还没出首 token，就现起一个同系统提示+模型的备用进程重发同一问题，
    两路谁先出首 token 用谁，另一路立刻杀掉（被杀的进程连同它里面的半截对话一起扔掉，不会污染下一问）；
    备用赢了就把它换成本会话的常驻进程（原进程杀掉，不用重建）。每次调用最多对冲 1 次；总超时仍从主路发出算起。
    备用进程「触发时现起」而不是预热：实测 claude 常驻进程约 290MB，并发 3 个任务、每个最多 2 个会话，
    全预热备用要多占 ~1.7G（机器 3.8G、swap 已在用）；而触发率按历史约 6%，现起多等 1–2.5 秒，
    相比 8–186 秒的长尾可以接受。"""

    def __init__(self, system, model, cwd, binary, env, log=None, hedge=None):
        self.system, self.model, self.cwd, self.binary, self.env, self.log = system, model, cwd, binary, env, log
        self.hedge = hedge_sec() if hedge is None else hedge
        self.proc = None
        self.q = queue.Queue()
        self.reset_thread = None
        self.last_total = {}   # session_id -> 已累计 total_cost_usd（stream-json 里是会话累计值）
        self.lock = threading.Lock()
        self.n_turns = 0

    @property
    def p(self):
        return self.proc.p if self.proc else None

    def _new_proc(self):
        cmd = [self.binary, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
               "--include-partial-messages", "--tools", "", "--strict-mcp-config",
               "--system-prompt", self.system]
        if self.model:
            cmd += ["--model", self.model]
        return Proc(cmd, self.cwd, self.env, self.log, self.q)

    def spawn(self):
        self.proc = self._new_proc()
        self.n_turns = 0

    def alive(self):
        return self.proc is not None and self.proc.alive()

    def _get(self, until):
        """从队列取下一行（只认活着的当前进程的）；until 到了抛 TimeoutError。返回 (进程, 解析好的 JSON 或 None=EOF)。"""
        while True:
            left = until - time.time()
            if left <= 0:
                raise TimeoutError
            try:
                src, line = self.q.get(timeout=min(left, 0.5))
            except queue.Empty:
                continue
            if line is None:
                return src, None
            try:
                return src, json.loads(line)
            except json.JSONDecodeError:
                continue

    def _read_result(self, deadline, t0=None, mark=None):
        """读当前进程到 type=result；mark 是 dict，记第一个文字增量的时刻。"""
        while True:
            src, j = self._get(deadline)
            if src is not self.proc:
                continue            # 之前被杀的进程留下的行
            if j is None:
                raise EOFError("claude 常驻进程退出了")
            if mark is not None and "ttft" not in mark and _first_token(j):
                mark["ttft"] = time.time() - t0
            if j.get("type") == "result":
                return j

    def _reset_bg(self, timeout):
        def run():
            try:
                self.proc.send("/clear")
                self._read_result(time.time() + timeout)
            except Exception:
                self.kill()
        self.reset_thread = threading.Thread(target=run, daemon=True)
        self.reset_thread.start()

    def kill(self):
        if self.proc:
            self.proc.kill()

    def ask(self, prompt, timeout):
        """问一次。进程中途退出（EOF / 管道断了）就重起再问一次——常驻进程偶尔会死（内存紧时实测过），
        别让一个死进程把整版计划带垮；超时不重试（再等一轮太贵）。重试那次不再对冲（每次调用最多对冲 1 次）。"""
        j, meta = self._ask(prompt, timeout)
        if j is None and meta.get("retry"):
            j, meta2 = self._ask(prompt, timeout, allow_hedge=not meta.get("hedged"))
            meta2["extra_cost"] = round((meta2.get("extra_cost") or 0) + (meta.get("extra_cost") or 0), 6)
            if meta.get("hedged") and not meta2.get("hedged"):
                meta2.update(hedged=True, winner="（对冲后两路都崩了，重起重问）")
            meta = dict(meta2, retried=meta["error"]) if j is not None else meta2
        return j, meta

    def _race(self, prompt, t0, deadline, mark, hm):
        """主路发出后等首 token；hedge 秒没等到就起备用重发，谁先出首 token 用谁，败者杀掉。
        返回时 self.proc 是赢的那路（已出首 token 或没对冲），hm 里记 hedged/winner/extra_cost 等。"""
        legs = {self.proc: "primary"}
        starts = {}                 # 进程 -> message_start 的 usage（败者估费用用）
        t_hedge = t0 + self.hedge if self.hedge and self.hedge > 0 and hm.pop("allow") else None
        while True:
            until = min(deadline, t_hedge) if t_hedge and len(legs) == 1 else deadline
            try:
                src, j = self._get(until)
            except TimeoutError:
                if time.time() >= deadline:
                    for pr in legs:
                        if pr is not self.proc:
                            pr.kill()
                    raise
                # 到阈值了：起备用重发（只一次，起不来也不再试）
                t_hedge = None
                hm.update(hedged=True, hedge_at_ms=round((time.time() - t0) * 1000))
                try:
                    b = self._new_proc()
                    b.send(prompt)
                    legs[b] = "backup"
                    hm["backup_pid"] = b.pid
                except OSError as e:
                    hm["backup_error"] = str(e)[:200]
                continue
            if src not in legs:
                continue
            if j is None:           # 某一路进程死了
                if len(legs) == 1:
                    raise EOFError("claude 常驻进程退出了")
                hm.setdefault("leg_died", []).append(legs.pop(src))
                if src is self.proc:
                    self.proc = next(iter(legs))
                continue
            if j.get("type") == "stream_event" and (j.get("event") or {}).get("type") == "message_start":
                starts[src] = ((j.get("event") or {}).get("message") or {}).get("usage") or {}
            if j.get("type") == "result" and j.get("is_error") and len(legs) > 1:
                hm.setdefault("leg_died", []).append(legs.pop(src))     # 一路没出首 token 就报错：扔掉，等另一路
                src.kill()
                if src is self.proc:
                    self.proc = next(iter(legs))
                continue
            if _first_token(j) or j.get("type") == "result":
                if _first_token(j):
                    mark["ttft"] = time.time() - t0
                win = src
                if hm.get("hedged"):
                    hm["winner"] = legs[win]
                    for pr, name in legs.items():
                        if pr is not win:
                            pr.kill()
                            if pr in starts:
                                hm["extra_cost"] = round(hm.get("extra_cost", 0) + _usage_cost(self.model, starts[pr]), 6)
                                hm["extra_cost_est"] = True
                    if win is not self.proc:
                        self.proc = win
                        self.n_turns = 0
                return j

    def _ask(self, prompt, timeout, allow_hedge=True):
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
            hm = {"allow": allow_hedge, "hedged": False, "winner": None, "extra_cost": 0.0}
            try:
                self.proc.send(prompt)
                j = self._race(prompt, t0, t0 + timeout, mark, hm)
                if j.get("type") != "result":
                    j = self._read_result(t0 + timeout, t0, mark)
            except TimeoutError:
                self.kill()
                return None, dict(hm, error=f"claude 超过 {timeout} 秒没有返回")
            except (EOFError, BrokenPipeError, OSError) as e:
                self.kill()
                return None, dict(hm, error=f"常驻进程出错：{e}", retry=True)
            t1 = time.time()
            self.n_turns += 1
            sid = j.get("session_id")
            tot = j.get("total_cost_usd") or 0
            cost = tot - self.last_total.get(sid, 0)
            self.last_total[sid] = tot
            self._reset_bg(timeout=60)
            hm.pop("allow", None)
            return j, dict(hm, cost=cost, ttft_ms=round(mark["ttft"] * 1000) if "ttft" in mark else None,
                           wall_ms=round((t1 - t0) * 1000), t_start=t0, t_end=t1, spawn=spawn,
                           wait_reset_ms=round(wait_reset * 1000), turn=self.n_turns, hedge_sec=self.hedge)


class Pool:
    """cwd：claude 进程的工作目录（空目录，别让它读到项目的 CLAUDE.md）；env：子进程环境（已洗掉 API key 等）。"""

    def __init__(self, cwd, binary, env, log=None, hedge=None):
        self.cwd, self.binary, self.env, self.log = str(cwd), binary, env, log
        self.hedge = hedge_sec() if hedge is None else hedge
        self.sessions = {}
        self.lock = threading.Lock()

    def get(self, system, model):
        with self.lock:
            k = (system, model)
            if k not in self.sessions:
                self.sessions[k] = Session(system, model, self.cwd, self.binary, self.env, self.log, self.hedge)
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
            out = {"type": "result", "is_error": True, "result": meta["error"], "total_cost_usd": meta.get("extra_cost") or 0,
                   "_pool": meta}
            return SimpleNamespace(stdout=json.dumps(out, ensure_ascii=False), stderr=meta["error"], returncode=1)
        out = {"type": "result", "subtype": j.get("subtype"), "is_error": j.get("is_error"), "result": j.get("result"),
               "total_cost_usd": meta["cost"] + (meta.get("extra_cost") or 0), "duration_ms": j.get("duration_ms"),
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
