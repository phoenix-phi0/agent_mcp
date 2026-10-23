# -*- coding: utf-8 -*-
"""tools/gsbatch.py：提交、provider / 强度路由、本批代理注入、续接、并发、超时被杀、取消、
输出截断、cwd 校验、key 不落盘。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_gsbatch.py

执行端换成假的 goose（下面的 FAKE，路径走 GSBATCH_GOOSE），上游换成本地假 z.ai
（GSBATCH_ZAI_UPSTREAM），不联网、不花钱。走本批代理时假 goose 会真的照临时 provider
的 base_url 发一次请求，用来测代理补 reasoning_effort、记响应模型和 usage。
"""

import atexit
import json
import os
import shutil
import signal
import socket
import stat
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="gsbatch_"))
LOG = TMP / "calls.jsonl"
UP_LOG = TMP / "upstream.jsonl"
SECRET = "sk-test-SECRET-0123456789abcdef"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


# ---- 假 z.ai 上游：记下收到的请求体（不含消息）和 Authorization 是否带到
class Up(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        with open(UP_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"path": self.path, "auth": self.headers.get("Authorization"),
                                "body": {k: v for k, v in body.items() if k != "messages"}},
                               ensure_ascii=False) + "\n")
        ev = [{"model": "glm-5.3-flash-real", "choices": [{"delta": {"reasoning_content": "想想"}}]},
              {"model": "glm-5.3-flash-real", "choices": [{"delta": {"content": "好"}}],
               "usage": {"prompt_tokens": 100, "completion_tokens": 20,
                         "prompt_tokens_details": {"cached_tokens": 40},
                         "completion_tokens_details": {"reasoning_tokens": 7}}}]
        out = "".join(f"data: {json.dumps(e)}\n\n" for e in ev) + "data: [DONE]\n\n"
        b = out.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


UP_PORT = free_port()
_up = ThreadingHTTPServer(("127.0.0.1", UP_PORT), Up)
threading.Thread(target=_up.serve_forever, daemon=True).start()
PROXY_PORT = free_port()

FAKE = f"""#!{sys.executable}
import json, os, sys, time, urllib.request
a = sys.argv[1:]
prompt = sys.stdin.read()
def arg(k):
    return a[a.index(k) + 1] if k in a else None
prov = arg("--provider")
root = os.environ.get("GOOSE_PATH_ROOT")
pf = None
if root and prov:
    p = os.path.join(root, "config", "custom_providers", prov + ".json")
    if os.path.exists(p):
        pf = json.load(open(p, encoding="utf-8"))
t0 = time.time()
with open({str(LOG)!r}, "a", encoding="utf-8") as f:
    f.write(json.dumps({{"prompt": prompt, "argv": a, "cwd": os.getcwd(), "t0": t0,
        "root": root, "mode": os.environ.get("GOOSE_MODE"),
        "keyring": os.environ.get("GOOSE_DISABLE_KEYRING"),
        "has_zai_key": os.environ.get("ZAI_CODING_PLAN_API_KEY") == {SECRET!r},
        "codex_eff": os.environ.get("CHATGPT_CODEX_REASONING_EFFORT"),
        "leak": sorted(k for k in os.environ if k in ("ZHIPU_API_KEY", "GH_TOKEN", "GOOSE_PROVIDER",
                                                      "CLAUDECODE") or k.startswith("CLAUDE_CODE_")),
        "pf": pf}}, ensure_ascii=False) + "\\n")
if pf:
    rq = urllib.request.Request(pf["base_url"] + "/chat/completions",
        json.dumps({{"model": arg("--model"), "messages": [], "stream": True}}).encode(),
        {{"Authorization": "Bearer " + os.environ.get(pf["api_key_env"], ""),
         "Content-Type": "application/json"}})
    urllib.request.urlopen(rq, timeout=10).read()
if "SLEEP2" in prompt:
    time.sleep(2)
elif "SLEEP" in prompt:
    time.sleep(30)
resume = arg("--session-id")
sid = resume or ("20261023_" + str(int(t0 * 1000000) % 100000))
print("")
print("    __( O)>  ● new session · " + str(prov) + " " + str(arg("--model")))
print("   \\\\____)    " + sid + " · " + os.getcwd())
print("     L L     goose is ready", flush=True)
def emit(o):
    print(json.dumps(o, ensure_ascii=False), flush=True)
def msg(mid, content, role="assistant"):
    emit({{"type": "message", "message": {{"id": mid, "role": role, "content": content,
          "metadata": {{"inference": {{"provider": prov, "requestedModel": arg("--model")}}}}}}}})
if "ERR" in prompt:
    emit({{"type": "error", "error": "模型不可用"}})
    sys.exit(0)
if "RC3" in prompt:
    sys.stderr.write("boom")
    sys.exit(3)
msg("m1", [{{"type": "thinking", "thinking": "嗯"}}])
if "TOOL" in prompt:
    msg("m1", [{{"type": "text", "text": "先写文件"}}])
    msg("m1", [{{"type": "toolRequest", "id": "c1", "toolCall": {{"status": "success",
        "value": {{"name": "write", "arguments": {{}}}}}}}}])
    msg("u1", [{{"type": "toolResponse", "id": "c1"}}], role="user")
text = "X" * 150000 if "BIG" in prompt else "答：" + prompt
msg("m2", [{{"type": "text", "text": text[:3]}}])
msg("m2", [{{"type": "text", "text": text[3:]}}])
base = 1000 if resume else 0
emit({{"type": "complete", "total_tokens": base + 15, "input_tokens": base + 10,
      "output_tokens": 5, "cache_read_input_tokens": 4, "cache_write_input_tokens": 0,
      "cost_usd": 0.001}})
"""

fake = TMP / "goose"
fake.write_text(FAKE, encoding="utf-8")
fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

# 假的 zai_low 启动脚本：只记一下被调过；日志放一条“同时间段”的请求
START_MARK = TMP / "start_called"
start = TMP / "start_proxy.sh"
start.write_text(f"#!/bin/bash\ntouch {START_MARK}\n", encoding="utf-8")
ZLOG = TMP / "zai_low_req.jsonl"


def _cleanup():
    for p in Path("/proc").iterdir():
        if p.name.isdigit() and (_cmd_has(p, str(fake)) or
                                 (_cmd_has(p, "tools.gsbatch") and _env_has(p, str(TMP)))):
            try:
                os.kill(int(p.name), signal.SIGKILL)
            except OSError:
                pass
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)

os.environ.update(
    GSBATCH_HOME=str(TMP / "jobs"), GSBATCH_GOOSE=str(fake),
    GSBATCH_GOOSE_ROOT=str(TMP / "groot"), GSBATCH_PROXY_PORT=str(PROXY_PORT),
    GSBATCH_ZAI_UPSTREAM=f"http://127.0.0.1:{UP_PORT}",
    GSBATCH_ZAI_LOW_START=str(start), GSBATCH_ZAI_LOW_PORT=str(UP_PORT),
    GSBATCH_ZAI_LOW_LOG=str(ZLOG),
    ZHIPU_API_KEY=SECRET, GH_TOKEN="ghp_fakefakefakefake", GOOSE_PROVIDER="openai",
    CLAUDECODE="1", CLAUDE_CODE_SESSION_ID="parent")
os.environ.pop("ZAI_CODING_PLAN_API_KEY", None)

from tools import gsbatch    # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"：{extra}" if extra else ""))


def calls():
    return [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines()] \
        if LOG.exists() else []


def ups():
    return [json.loads(l) for l in UP_LOG.read_text(encoding="utf-8").splitlines()] \
        if UP_LOG.exists() else []


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except gsbatch.GSBatchError as e:
        return str(e)
    return None


def arg(c, k):
    return c["argv"][c["argv"].index(k) + 1] if k in c["argv"] else None


def run(tasks, **k):
    LOG.unlink(missing_ok=True)
    UP_LOG.unlink(missing_ok=True)
    j = gsbatch.submit(tasks, cwd=str(TMP), **k)
    d = gsbatch.wait(j["job_id"], timeout=40, every=0.2)
    return d, calls()


def main():
    print("参数检查")
    check(raises(gsbatch.submit, []), "空列表报错")
    check(raises(gsbatch.submit, ["x"] * 11), "超过 MAX_TASKS 报错")
    check(raises(gsbatch.submit, ["x"], mode="both"), "mode 不对报错")
    check(raises(gsbatch.submit, [{"no": 1}]), "字典缺 prompt 报错")
    check(raises(gsbatch.submit, ["x"], concurrency=9), "并发超上限报错")
    check(raises(gsbatch.submit, ["x"], provider="openai"), "provider 不对报错")
    check(raises(gsbatch.submit, ["x"], permission_mode="approve"), "不收 approve")
    check(raises(gsbatch.submit, ["x"], permission_mode="bypassPermissions"), "不收 bypassPermissions")
    check(raises(gsbatch.submit, ["x"], effort="turbo"), "effort 不对报错")
    check(gsbatch._norm_effort("max", "chatgpt_codex") == "xhigh"
          and gsbatch._norm_effort("极高", "zai_low") == "max", "两家最高档名字互认")
    check(raises(gsbatch.submit, ["x"], extensions=["bad name"]), "扩展名不对报错")
    check(raises(gsbatch.submit, ["x"], model="a b", cwd=str(TMP)), "模型名有空格报错")
    check(raises(gsbatch.status, "nope"), "查不存在的任务报错")
    check(raises(gsbatch.status, "../etc"), "任务 id 带路径报错")

    print("cwd 校验")
    check(raises(gsbatch.submit, ["x"], cwd=str(Path.home())), "不收家目录")
    check(raises(gsbatch.submit, ["x"], cwd="/"), "不收 /")
    check(raises(gsbatch.submit, ["x"], cwd="~/x"), "不收 ~")
    check(raises(gsbatch.submit, ["x"], cwd=str(TMP / "不存在")), "不收不存在的目录")

    print("默认：zai_low + low，直连全局 provider")
    ZLOG.write_text(json.dumps({"t": time.time() + 1, "forwarded": {"model": "glm-5.3-flash",
                                "reasoning_effort": "low"}, "resp_models": ["glm-5.3-flash"]}) + "\n")
    d, cs = run(["一 TOOL", "二"], name="基本", concurrency=2)
    check(d["status"] == "done", "整批 done", d["status"])
    check([t["output"] for t in d["tasks"]] == ["先写文件\n\n答：一 TOOL", "答：二"],
          "输出按顺序、逐字流拼好、工具前后分段", [t["output"] for t in d["tasks"]])
    t = d["tasks"][0]
    check(t["tokens"]["input"] == 10 and t["tokens"]["output"] == 5 and t["tool_calls"] == 1
          and t["cost_usd"] is None and t["cost_est_usd"] == 0.001 and t["rc"] == 0
          and t["session_id"].startswith("20261023_"), "tokens / 工具次数 / 不算费用 / 会话 id", t)
    check(t["route"] == "zai_low" and t["model_used"] == "glm-5.3-flash" and t["effort_sent"] == "low",
          "zai_low 按时间窗从共用日志对出响应模型", t)
    c = next(x for x in cs if x["prompt"] == "一 TOOL")
    check(c["argv"][:5] == ["run", "--no-profile", "--output-format", "stream-json", "--provider"]
          and arg(c, "--provider") == "zai_low" and arg(c, "--model") == "glm-5.3-flash"
          and c["argv"][-2:] == ["-i", "-"], "goose run --no-profile stream-json，提示词走 stdin", c["argv"])
    check(arg(c, "--with-builtin") == "developer" and c["mode"] == "auto" and c["keyring"] == "1",
          "默认挂 developer、GOOSE_MODE=auto、关 keyring")
    check(c["root"] is None and START_MARK.exists(), "zai_low 不设 GOOSE_PATH_ROOT，跑前调了 start_proxy.sh")
    check(c["has_zai_key"] and not c["leak"], "ZAI key 只进子进程环境，别的凭证/GOOSE_* 没漏", c["leak"])
    check(arg(c, "--system") == gsbatch.PREAMBLE + "\n" + gsbatch.PREAMBLE_TOOLS + "\n" + gsbatch.PREAMBLE_PROBE + "\n" + gsbatch.PREAMBLE_REVIEW
          and c["prompt"] == "一 TOOL", "preamble 走 --system（带附加工具两句 + probe 一句），stdin 是提示词本身")
    check("probe" in gsbatch.PREAMBLE_PROBE and "只读" in gsbatch.PREAMBLE_PROBE
          and "probe" not in gsbatch.PREAMBLE_TOOLS, "probe 那句单独放在 PREAMBLE_PROBE")
    pr = gsbatch.PREAMBLE_REVIEW
    check(pr.startswith("9. ") and "\n" not in pr and "10. " not in pr
          and "review" in pr and "task_file" in pr and "report_file" in pr and "commit/push" in pr
          and "初步审查" in pr and "不是定论" in pr and "误报" in pr and "漏报" in pr
          and "review" not in gsbatch.PREAMBLE_TOOLS + gsbatch.PREAMBLE_PROBE,
          "只有第 9 句：初步审查、只是线索；没有第 10 条及以后", pr)
    check("\n10. " not in arg(c, "--system") and "存疑" not in arg(c, "--system")
          and "通过也不免检" not in arg(c, "--system"), "整个 PREAMBLE 里没有第 10 条", arg(c, "--system")[-300:])
    ext = arg(c, "--with-extension")
    check(ext == gsbatch._extra_tools_arg(d["options"]) and ext.startswith("gsb_tools:GSB_MAX_BLOCK=")
          and ext.split()[1] == "GSB_PROBE=1" and ext.split()[2] == "GSB_REVIEW=1"
          and ext.split()[-1] == str(gsbatch.EXTRA_TOOLS_SCRIPT) and gsbatch.EXTRA_TOOLS_SCRIPT.is_file()
          and " " not in str(gsbatch.EXTRA_TOOLS_SCRIPT), "默认挂 gsb_tools 扩展（--with-extension）", ext)
    check(d["options"]["extra_tools"] is True and d["options"]["probe"] is True
          and d["options"]["review"] is True, "job.json 记了 extra_tools、probe、review", d["options"])
    check(c["cwd"] == str(TMP), "在指定 cwd 里跑")

    print("别的强度：本批代理补 reasoning_effort")
    d, cs = run(["甲"], effort="high")
    t, c, u = d["tasks"][0], cs[0], ups()
    check(t["status"] == "done" and t["route"] == "proxy", "走本批代理", t)
    check(c["root"] == str(TMP / "groot") and c["pf"]
          and c["pf"]["api_key_env"] == "ZAI_CODING_PLAN_API_KEY"
          and f":{PROXY_PORT}/gsb/high/{d['id']}/1/" in c["pf"]["base_url"],
          "临时 provider 在本批配置根里，base_url 带强度和任务号", c["pf"])
    check(u and u[0]["body"].get("reasoning_effort") == "high"
          and u[0]["body"].get("thinking") == {"type": "enabled"}
          and u[0]["path"] == "/api/coding/paas/v4/chat/completions"
          and u[0]["auth"] == "Bearer " + SECRET, "上游收到 reasoning_effort=high、thinking、原样的 key", u)
    check(t["model_used"] == "glm-5.3-flash-real" and t["effort_sent"] == "high"
          and t["tokens"] == {"input": 100, "cached_input": 40, "output": 20, "reasoning": 7, "total": 120},
          "从代理日志记实际响应模型和推理 token", t)
    check(not list((TMP / "groot" / "config" / "custom_providers").glob("gsbt_*")),
          "跑完删掉临时 provider")
    jd = TMP / "jobs" / d["id"]
    leaked = [f.name for f in jd.rglob("*") if f.is_file() and SECRET in f.read_text(errors="replace")]
    leaked += [f.name for f in (TMP / "groot").rglob("*") if f.is_file()
               and SECRET in f.read_text(errors="replace")]
    check(not leaked, "key 没写进任务目录和配置根", leaked)

    print("zai_coding_plan + None：经代理但不注入")
    d, cs = run(["乙"], provider="zai_coding_plan", effort=None)
    u = ups()
    check(d["status"] == "done" and "reasoning_effort" not in u[0]["body"]
          and "/gsb/-/" in cs[0]["pf"]["base_url"], "不补 reasoning_effort", u)

    print("chatgpt_codex：不经代理，强度走环境变量")
    d, cs = run(["丙"], provider="chatgpt_codex", effort="极高")
    c, t = cs[0], d["tasks"][0]
    check(arg(c, "--provider") == "chatgpt_codex" and arg(c, "--model") == "gpt-6-sol"
          and c["codex_eff"] == "xhigh" and c["root"] is None and not c["has_zai_key"],
          "默认 gpt-6-sol、xhigh、默认配置根、不给 zai key", c)
    check(t["model_used"] is None and t["model_requested"] == "gpt-6-sol", "只记请求的模型", t)

    print("probe=False：照挂 gsb_tools，但不开 probe、不加第 8 句")
    d, cs = run(["戊 probe"], probe=False)
    c = cs[0]
    ext = arg(c, "--with-extension")
    check(ext and "GSB_PROBE" not in ext and "GSB_REVIEW=1" in ext and ext.startswith("gsb_tools:GSB_MAX_BLOCK=")
          and arg(c, "--system") == gsbatch.PREAMBLE + "\n" + gsbatch.PREAMBLE_TOOLS + "\n" + gsbatch.PREAMBLE_REVIEW
          and gsbatch.PREAMBLE_PROBE not in arg(c, "--system")
          and d["options"]["extra_tools"] is True and d["options"]["probe"] is False
          and d["options"]["review"] is True,
          "probe=False：扩展不带 GSB_PROBE=1，preamble 是 6、7 + 9~12", c["argv"])

    print("review=False：不开 review、不加第 9~12 句")
    d, cs = run(["戊 review"], review=False)
    c = cs[0]
    ext = arg(c, "--with-extension")
    check(ext and "GSB_REVIEW" not in ext and "GSB_PROBE=1" in ext
          and arg(c, "--system") == gsbatch.PREAMBLE + "\n" + gsbatch.PREAMBLE_TOOLS + "\n" + gsbatch.PREAMBLE_PROBE
          and d["options"]["review"] is False and d["options"]["probe"] is True,
          "review=False：扩展不带 GSB_REVIEW=1，preamble 没有第 9~12 句", c["argv"])
    d, cs = run(["戊 都关"], probe=False, review=False)
    c = cs[0]
    ext = arg(c, "--with-extension")
    check(ext and "GSB_" not in ext.split()[0][len("gsb_tools:GSB_MAX_BLOCK="):] and len(ext.split()) == 3
          and arg(c, "--system") == gsbatch.PREAMBLE + "\n" + gsbatch.PREAMBLE_TOOLS,
          "probe、review 都关：只剩 read_files / run_wait / wait_pid 和 6、7 两句", ext)

    print("extra_tools=False / 不挂 developer：不挂附加工具")
    d, cs = run(["戊"], extra_tools=False)
    c = cs[0]
    check("--with-extension" not in c["argv"] and arg(c, "--system") == gsbatch.PREAMBLE
          and arg(c, "--with-builtin") == "developer" and d["options"]["extra_tools"] is False
          and d["options"]["probe"] is False and d["options"]["review"] is False,
          "extra_tools=False 不挂扩展，preamble 不加那几句，probe 也跟着关", c["argv"])
    d, cs = run(["己"], extensions=["memory"])
    c = cs[0]
    check("--with-extension" not in c["argv"] and arg(c, "--system") == gsbatch.PREAMBLE,
          "没挂 developer 就不挂附加工具", c["argv"])

    print("chat / 关 preamble / max_turns")
    d, cs = run(["丁 创建文件"], permission_mode="readonly", preamble=False, max_turns=3)
    c = cs[0]
    check(c["mode"] == "chat" and "--with-builtin" not in c["argv"] and "--system" not in c["argv"]
          and arg(c, "--max-turns") == "3" and "--with-extension" not in c["argv"]
          and d["options"]["extra_tools"] is False and d["options"]["probe"] is False
          and d["options"]["review"] is False,
          "readonly=chat 不挂扩展（含附加工具），preamble 关，max-turns 传了", c["argv"])
    check(any("developer" in w for w in d["warnings"]), "chat 下要写文件给警告", d["warnings"])

    print("默认 cwd：任务目录下的空目录")
    LOG.unlink(missing_ok=True)
    j = gsbatch.submit(["x"])
    gsbatch.wait(j["job_id"], timeout=30, every=0.2)
    c = calls()[0]
    check(c["cwd"] == str(TMP / "jobs" / j["job_id"] / "work"), "不传 cwd 用空目录", c["cwd"])

    print("share：后一条 --resume --session-id 接前一条，失败后断开，token 按差值")
    d, cs = run(["甲", "乙", "丙 ERR", "丁"], mode="share")
    t = d["tasks"]
    check("--resume" not in cs[0]["argv"] and arg(cs[1], "--session-id") == t[0]["session_id"]
          and "-n" not in cs[1]["argv"], "第二条续接第一条的会话", cs[1]["argv"])
    check(arg(cs[0], "--with-extension") and "--with-extension" not in cs[1]["argv"]
          and "GSB_PROBE=1 GSB_REVIEW=1" in arg(cs[0], "--with-extension")
          and arg(cs[1], "--system") == gsbatch.PREAMBLE + "\n" + gsbatch.PREAMBLE_TOOLS + "\n" + gsbatch.PREAMBLE_PROBE + "\n" + gsbatch.PREAMBLE_REVIEW,
          "续接时不再传 --with-extension（会话里已有，重传会报重名）", cs[1]["argv"])
    check(t[1]["tokens"]["input"] == 1000 and t[1]["session_tokens"]["input"] == 1010,
          "续接那条的 token = 会话累计 − 上一条累计", t[1]["tokens"])
    check(t[2]["status"] == "error" and "模型不可用" in t[2]["error"], "error 事件记 error", t[2])
    check("--resume" not in cs[3]["argv"], "前一条失败，下一条开新会话")
    check(d["status"] == "partial", "有成有败 partial", d["status"])
    d, cs = run(["甲", {"prompt": "乙", "effort": "high"}], mode="share")
    check("--resume" not in cs[1]["argv"], "换了配置根（low→high）就不续接")

    print("退出码非 0")
    d, cs = run(["RC3"])
    t = d["tasks"][0]
    check(t["status"] == "error" and t["rc"] == 3 and "boom" in t["stderr"] and d["status"] == "failed",
          "记 rc 和 stderr 摘要", t)

    print("输出截断")
    d, cs = run(["BIG"])
    out = d["tasks"][0]["output"]
    check("还有" in out and len(out) < 700, "status 默认预览截断", len(out))
    full = gsbatch.status(d["id"], full=True)["tasks"][0]["output"]
    check(len(full) < 150000 and "已截断" in full, "full 返回存盘截断后的全文", len(full))

    print("并发")
    t0 = time.time()
    d, cs = run(["SLEEP2 a", "SLEEP2 b", "SLEEP2 c"], concurrency=3)
    starts = sorted(c["t0"] for c in cs)
    check(d["status"] == "done" and starts[-1] - starts[0] < 1.5, "3 条几乎同时开始", starts[-1] - starts[0])
    check(time.time() - t0 < 6, "总耗时远小于串行 6 秒", time.time() - t0)
    d, cs = run(["SLEEP2 a", "SLEEP2 b"], concurrency=1)
    starts = sorted(c["t0"] for c in cs)
    check(starts[1] - starts[0] >= 1.9, "concurrency=1 顺序跑", starts[1] - starts[0])

    print("超时被杀")
    d, cs = run(["SLEEP", "后面照跑"], timeout=1)
    t = d["tasks"]
    check(t[0]["status"] == "timeout" and t[0]["seconds"] < 10, "超时那条记 timeout", t[0])
    check(t[1]["status"] == "done", "之后接着跑", t[1]["status"])
    time.sleep(0.3)
    check(not [p for p in Path("/proc").iterdir()
               if p.name.isdigit() and _cmd_has(p, str(fake)) and _cmd_has(p, "SLEEP")],
          "假 goose 进程已被杀掉")

    print("取消")
    LOG.unlink(missing_ok=True)
    j = gsbatch.submit(["SLEEP 一", "SLEEP 二"], cwd=str(TMP), concurrency=2)
    for _ in range(80):
        if gsbatch.status(j["job_id"])["tasks"][0]["status"] == "running" and len(calls()) >= 2:
            break
        time.sleep(0.1)
    pid = gsbatch.status(j["job_id"])["pid"]
    r = gsbatch.cancel(j["job_id"])
    d = gsbatch.status(j["job_id"])
    check(r["status"] == "cancelled" and {t["status"] for t in d["tasks"]} == {"cancelled"},
          "状态是 cancelled", [t["status"] for t in d["tasks"]])
    check(not _alive(pid), "执行器进程已经没了")
    time.sleep(0.5)
    check(not [p for p in Path("/proc").iterdir()
               if p.name.isdigit() and _cmd_has(p, str(fake)) and _cmd_has(p, "SLEEP")],
          "正在跑的 goose 子进程也被杀")
    check(gsbatch.cancel(j["job_id"]).get("note") == "已经结束了", "重复取消不报错")

    print("执行器死掉")
    j = gsbatch.submit(["SLEEP"], cwd=str(TMP))
    for _ in range(50):
        if gsbatch.status(j["job_id"]).get("pid"):
            break
        time.sleep(0.1)
    os.killpg(gsbatch.status(j["job_id"])["pid"], signal.SIGKILL)
    time.sleep(0.3)
    check(gsbatch.status(j["job_id"])["status"] == "died", "进程没了就是 died")
    check(any(x["id"] == j["job_id"] for x in gsbatch.jobs(50)), "jobs 列得到")
    text = gsbatch.describe()
    check("zai_low" in text and "chatgpt_codex" in text and "low" in text, "describe 有 provider 和 effort")

    print("没有 key")
    k = os.environ.pop("ZHIPU_API_KEY")
    check(raises(gsbatch.submit, ["x"], cwd=str(TMP)), "环境里没 key 就报错")
    check(raises(gsbatch.submit, ["x"], cwd=str(TMP), provider="chatgpt_codex") is None,
          "chatgpt_codex 不需要 zai key")
    os.environ["ZHIPU_API_KEY"] = k
    time.sleep(0.5)

    _cleanup()
    check(not TMP.exists(), "临时目录已删")
    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _cmd_has(p, s):
    try:
        return s in (p / "cmdline").read_bytes().decode("utf-8", "replace")
    except OSError:
        return False


def _env_has(p, s):
    try:
        return s in (p / "environ").read_bytes().decode("utf-8", "replace")
    except OSError:
        return False


if __name__ == "__main__":
    main()
