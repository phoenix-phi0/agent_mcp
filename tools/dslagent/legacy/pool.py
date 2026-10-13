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
ttft_ms、wall_ms、t_start/t_end、spawn（这次是否新起进程）、wait_reset_ms，以及对冲的
hedged、winner（primary/backup/backup2）、hedge_at_ms、hedge_reason（no_token/stall）、hedges、
extra_cost（被中止那一路的估算费用，已计入 total_cost_usd），和 first_out_ms / no_output_ms / stall_ms / legs
（每一路的发出、首行、首 token、最后一行时刻）。超时、崩溃的调用也带这些字段（以前超时不带 ttft，
看着像「没出首 token」，其实可能是出了首 token 后流卡住）。

对冲见 Session 的说明（阈值 HEDGE_SEC / DSLAGENT_HEDGE_SEC，STALL_SEC / DSLAGENT_STALL_SEC）。
"""
import json
import os
import queue
import subprocess
import threading
import time
from types import SimpleNamespace

from ..common import child_env  # noqa: F401  v2 也用，挪到 common.py；旧名仍可从这里取

# 首 token 对冲阈值（秒）。依据 plan9/11/12 共 344 次带首 token 的调用：正常调用中位 2.6s、P90 4.4s、最大 5.98s，
# 之后直接断档到 8.3s；8.3s 以上的长尾 22 次（6.4%，最长 72s），另有 2 次 150 秒超时连首 token 都没出。
# 取 7s：在正常调用最大值和长尾最小值之间，按历史数据正常调用误触发 0 次。DSLAGENT_HEDGE_SEC 可改，0 = 关。
HEDGE_SEC = 7.0
# 卡流对冲阈值（秒）：出了首 token 之后这一路多久没有任何新行算卡住。正常流里行与行的间隔（含 thinking）实测 ≤2 秒，
# 首 token 之后到结果最长也就几十秒；取 20s 留足余量。DSLAGENT_STALL_SEC 可改，0 = 关。
STALL_SEC = 20.0
# 被中止那一路的费用估算（美元 / 百万 token）：CLI 被中断时报的费用是 0，只能按它 message_start 里的 usage 估。
# 中止的一路按定义还没出首 token，没有输出 token；如果连 message_start 都没收到就记 0（服务端是否计费看不到）。
PRICE = {"haiku": (1.0, 1.25, 2.0, 0.10), "opus": (5.0, 6.25, 10.0, 0.50), "": (3.0, 3.75, 6.0, 0.30)}


def hedge_sec():
    try:
        return float(os.environ.get("DSLAGENT_HEDGE_SEC", HEDGE_SEC))
    except ValueError:
        return HEDGE_SEC


def stall_sec():
    try:
        return float(os.environ.get("DSLAGENT_STALL_SEC", STALL_SEC))
    except ValueError:
        return STALL_SEC


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
    这样读结果能带超时（readline 会一直卡住），对冲时也能同时等几个进程。"""

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

    def send_async(self, text):
        """在后台线程里写问题：进程还在启动、没读 stdin 时，大问题会把管道写满、write 一直卡住（假进程实测：
        卡到进程开始读为止，进程不读就永远卡，连总超时都不生效）。写不进去（管道断了）就当进程死了：杀掉，读线程会报 EOF。"""
        def run():
            try:
                self.send(text)
            except (OSError, ValueError):
                self.kill()
        threading.Thread(target=run, daemon=True).start()

    def kill(self):
        try:
            if self.p.poll() is None:
                self.p.kill()
            self.p.wait(timeout=5)
        except Exception:
            pass


def _first_token(j):
    return j.get("type") == "stream_event" and (j.get("event") or {}).get("type") == "content_block_delta"


def _ms(x):
    return None if x is None else round(x * 1000)


class Session:
    """首 token 对冲（hedge）：问题发出（开始写 stdin 就算，进程还在启动也算）hedge 秒还没出首 token，就现起一个
    同系统提示+模型的备用进程重发同一问题，两路谁先出首 token 用谁，没出的那路立刻杀掉（被杀的进程连同它里面的
    半截对话一起扔掉，不会污染下一问）。

    卡流对冲：出了首 token 之后流停住 stall 秒（这一路没有任何新行），也现起一个备用重发——plan15 B7、plan16 B4
    就是这样：首 token（thinking 的增量也算）7 秒内出了，所以没对冲，之后流卡死，干等到 150 秒总超时。
    卡住的那路不杀（它可能自己缓过来），两路谁先给出完整结果用谁。每次调用两种对冲各最多 1 次。

    赢的那路换成本会话的常驻进程（原进程杀掉，不用重建）；总超时仍从主路发出算起；计时一律用单调时钟。
    备用进程「触发时现起」而不是预热：实测 claude 常驻进程约 290MB，并发 3 个任务、每个最多 2 个会话，
    全预热备用要多占 ~1.7G（机器 3.8G、swap 已在用）；而触发率按历史约 6%，现起多等 1–2.5 秒，
    相比 8–186 秒的长尾可以接受。"""

    def __init__(self, system, model, cwd, binary, env, log=None, hedge=None, stall=None):
        self.system, self.model, self.cwd, self.binary, self.env, self.log = system, model, cwd, binary, env, log
        self.hedge = hedge_sec() if hedge is None else hedge
        self.stall = stall_sec() if stall is None else stall
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
        """从队列取下一行；until（单调时钟）到了返回 None。返回 (进程, 解析好的 JSON 对象 或 None=EOF)。"""
        while True:
            left = until - time.monotonic()
            if left <= 0:
                return None
            try:
                src, line = self.q.get(timeout=min(left, 0.5))
            except queue.Empty:
                continue
            if line is None:
                return src, None
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(j, dict):
                return src, j

    def _drain(self, proc, deadline):
        """读 proc 到 type=result（/clear 用）；别的进程留下的行扔掉。"""
        while True:
            r = self._get(deadline)
            if r is None:
                raise TimeoutError
            src, j = r
            if src is not proc:
                continue
            if j is None:
                raise EOFError("claude 常驻进程退出了")
            if j.get("type") == "result":
                return j

    def _reset_bg(self, timeout):
        pr = self.proc

        def run():
            try:
                pr.send("/clear")
                self._drain(pr, time.monotonic() + timeout)
            except Exception:
                pr.kill()       # 只杀自己清的那个进程（self.proc 这时可能已经换了）
        self.reset_thread = threading.Thread(target=run, daemon=True)
        self.reset_thread.start()

    def kill(self):
        if self.proc:
            self.proc.kill()

    def ask(self, prompt, timeout):
        """问一次。进程中途退出（EOF / 管道断了）就重起再问一次——常驻进程偶尔会死（内存紧时实测过），
        别让一个死进程把整版计划带垮；超时不重试（再等一轮太贵）。重试那次照样带对冲（已对冲过的不再对冲）。"""
        j, meta = self._ask(prompt, timeout)
        if j is None and meta.get("retry"):
            j, meta2 = self._ask(prompt, timeout, allow_hedge=not meta.get("hedged"))
            meta2["extra_cost"] = round((meta2.get("extra_cost") or 0) + (meta.get("extra_cost") or 0), 6)
            if meta.get("hedged") and not meta2.get("hedged"):
                meta2.update(hedged=True, winner="（对冲后两路都崩了，重起重问）")
            meta = dict(meta2, retried=meta["error"]) if j is not None else meta2
        return j, meta

    def _race(self, prompt, t0, deadline, hm, st, allow):
        """发问题、等结果，期间按需对冲。返回 type=result 的那行；返回时 self.proc 是赢的那路，其余路都已杀掉。
        st["legs"] 是每一路的记录（name、send/首行/首 token/最后一行的时刻、最长停顿），出错时也留着给 meta 用。"""
        legs = {}                   # 进程 -> 这一路的记录（同一个 dict 也放在 st["legs"] 里）
        tried = set()               # 已经用过的对冲种类：no_token / stall
        lead = [None]               # 第一个出首 token 的那路

        def add(pr, name):
            L = {"name": name, "pid": pr.pid, "send": time.monotonic() - t0, "out": None, "first": None,
                 "tok": None, "last": None, "gap": 0.0, "usage": None}
            legs[pr] = L
            st["legs"].append(L)
            pr.send_async(prompt)

        def drop(pr, why):
            L = legs.pop(pr)
            L["end"] = why
            if why != "died":
                pr.kill()
                if L["usage"] is not None:      # 被中止的一路：按 message_start 的 usage 估输入费用
                    hm["extra_cost"] = round(hm["extra_cost"] + _usage_cost(self.model, L["usage"]), 6)
                    hm["extra_cost_est"] = True
            if pr is self.proc and legs:
                self.proc = next(iter(legs))
            if lead[0] is pr:
                lead[0] = next((p for p, x in legs.items() if x["tok"] is not None), None)

        def hedge(reason, now):
            tried.add(reason)
            ms = round((now - t0) * 1000)
            hm["hedged"] = True
            hm["hedges"] += 1
            if hm["hedge_at_ms"] is None:
                hm["hedge_at_ms"] = ms
            hm["hedge_reason"] = "+".join(filter(None, [hm["hedge_reason"], reason]))
            try:
                add(self._new_proc(), "backup" if hm["hedges"] == 1 else f"backup{hm['hedges']}")
            except OSError as e:
                hm["backup_error"] = str(e)[:200]

        on = allow and bool(self.hedge) and self.hedge > 0
        stall_on = allow and bool(self.stall) and self.stall > 0
        add(self.proc, "primary")
        try:
            while True:
                now = time.monotonic()
                if now >= deadline:
                    raise TimeoutError
                due = [deadline]
                if on and "no_token" not in tried and lead[0] is None:
                    if now >= t0 + self.hedge:
                        hedge("no_token", now)
                        continue
                    due.append(t0 + self.hedge)
                if stall_on and "stall" not in tried and lead[0] is not None:
                    t_stall = legs[lead[0]]["last_abs"] + self.stall
                    if now >= t_stall:
                        hedge("stall", now)
                        continue
                    due.append(t_stall)
                r = self._get(min(due))
                if r is None:
                    continue
                src, j = r
                if src not in legs:
                    continue            # 之前被杀的进程留下的行
                L = legs[src]
                now = time.monotonic()
                if j is None:           # 这一路进程死了
                    if len(legs) == 1:
                        raise EOFError("claude 常驻进程退出了")
                    hm.setdefault("leg_died", []).append(L["name"])
                    drop(src, "died")
                    continue
                typ = j.get("type")
                ev = (j.get("event") or {}).get("type") if typ == "stream_event" else None
                if L["out"] is None:
                    L["out"], L["first"] = now - t0, ev or f"{typ}/{j.get('subtype') or ''}"
                if L["tok"] is not None:
                    L["gap"] = max(L["gap"], now - L["last_abs"])
                L["last"], L["last_abs"] = now - t0, now
                if ev == "message_start":
                    L["usage"] = ((j.get("event") or {}).get("message") or {}).get("usage") or {}
                if _first_token(j) and L["tok"] is None:
                    L["tok"] = now - t0
                    if lead[0] is None:
                        lead[0] = src           # 谁先出首 token 用谁：还没出首 token 的其它路杀掉
                        for pr in [p for p, x in legs.items() if p is not src and x["tok"] is None]:
                            drop(pr, "lost")
                if typ == "result":
                    if j.get("is_error") and len(legs) > 1:
                        hm.setdefault("leg_died", []).append(L["name"])     # 一路报错：扔掉，等别的路
                        drop(src, "error")
                        continue
                    for pr in [p for p in legs if p is not src]:
                        drop(pr, "lost")
                    L["end"] = "won"
                    if hm["hedged"]:
                        hm["winner"] = L["name"]
                    if src is not self.proc:
                        self.proc = src
                        self.n_turns = 0
                    return j
        except BaseException:
            for pr in [p for p in legs if p is not self.proc]:
                drop(pr, "aborted")
            raise

    @staticmethod
    def _stats(st, t0, now):
        """meta 里和计时有关的字段（成功、超时、崩溃都给）：
        ttft_ms＝用上的那路（没有就是最先出 token 的那路）的首 token；first_out_ms＝主路发出后第一行输出；
        no_output_ms＝主路发出后一行输出都没有的时长（有输出＝first_out_ms，到最后都没有＝整段时长）；
        stall_ms＝出首 token 后最长的一次停顿；last_out_ms＝最后一行输出的时刻；legs＝每一路的明细。"""
        legs = st["legs"]
        if not legs:
            return {"ttft_ms": None, "first_out_ms": None, "no_output_ms": None, "stall_ms": None, "last_out_ms": None}
        pri = legs[0]
        won = next((x for x in legs if x.get("end") == "won"), None)
        ref = won or min((x for x in legs if x["tok"] is not None), key=lambda x: x["tok"], default=None) or pri
        gap = ref["gap"]
        if ref["tok"] is not None and won is None and ref.get("last") is not None:
            gap = max(gap, (now - t0) - ref["last"])        # 超时/崩溃：最后那段停顿也算
        return {"ttft_ms": _ms(ref["tok"]), "first_out_ms": _ms(pri["out"]),
                "no_output_ms": _ms(pri["out"] if pri["out"] is not None else now - t0 - pri["send"]),
                "stall_ms": _ms(gap) if ref["tok"] is not None else None, "last_out_ms": _ms(ref["last"]),
                "legs": [{k: (_ms(v) if k in ("send", "out", "tok", "last", "gap") else v) for k, v in x.items()
                          if k not in ("usage", "last_abs")} for x in legs]}

    def _ask(self, prompt, timeout, allow_hedge=True):
        with self.lock:
            spawn = False
            w0 = time.monotonic()
            reset_stuck = False
            if self.reset_thread is not None:
                self.reset_thread.join(timeout=30)
                if self.reset_thread.is_alive():
                    # /clear 30 秒没回：杀掉重起，别让清会话的线程和这次调用抢同一个队列
                    reset_stuck = True
                    self.kill()
                    self.reset_thread.join(timeout=10)
                self.reset_thread = None
            wait_reset = time.monotonic() - w0
            if not self.alive():
                self.spawn()
                spawn = True
            t_start, t0 = time.time(), time.monotonic()
            hm = {"hedged": False, "winner": None, "hedge_at_ms": None, "hedge_reason": None, "hedges": 0,
                  "extra_cost": 0.0, "hedge_sec": self.hedge, "stall_sec": self.stall, "spawn": spawn,
                  "wait_reset_ms": round(wait_reset * 1000)}
            if reset_stuck:
                hm["reset_stuck"] = True
            st = {"legs": []}
            try:
                j = self._race(prompt, t0, t0 + timeout, hm, st, allow_hedge)
            except TimeoutError:
                self.kill()
                return None, dict(hm, **self._stats(st, t0, time.monotonic()), t_start=t_start, t_end=time.time(),
                                  error=f"claude 超过 {timeout} 秒没有返回")
            except (EOFError, BrokenPipeError, OSError) as e:
                self.kill()
                return None, dict(hm, **self._stats(st, t0, time.monotonic()), t_start=t_start, t_end=time.time(),
                                  error=f"常驻进程出错：{e}", retry=True)
            t1 = time.monotonic()
            self.n_turns += 1
            sid = j.get("session_id")
            tot = j.get("total_cost_usd") or 0
            cost = tot - self.last_total.get(sid, 0)
            self.last_total[sid] = tot
            self._reset_bg(timeout=60)
            return j, dict(hm, **self._stats(st, t0, t1), cost=cost, wall_ms=round((t1 - t0) * 1000),
                           t_start=t_start, t_end=time.time(), turn=self.n_turns)


class Pool:
    """cwd：claude 进程的工作目录（空目录，别让它读到项目的 CLAUDE.md）；env：子进程环境（已洗掉 API key 等）。"""

    def __init__(self, cwd, binary, env, log=None, hedge=None, stall=None):
        self.cwd, self.binary, self.env, self.log = str(cwd), binary, env, log
        self.hedge = hedge_sec() if hedge is None else hedge
        self.stall = stall_sec() if stall is None else stall
        self.sessions = {}
        self.lock = threading.Lock()

    def get(self, system, model):
        with self.lock:
            k = (system, model)
            if k not in self.sessions:
                self.sessions[k] = Session(system, model, self.cwd, self.binary, self.env, self.log, self.hedge, self.stall)
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
