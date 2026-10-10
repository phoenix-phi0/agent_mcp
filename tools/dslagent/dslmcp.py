"""DSL 子任务的 MCP 服务（stdio，手写最小 JSON-RPC，不加依赖）：DSLAGENT_SUBTASK=tool 模式里挂给 claude CLI。

只暴露一个工具 `dsl`，参数 `code`（中文 DSL 文本）。白名单（dslcheck.check_call）：读片段 / 搜索代码 / 查引用 /
改文件 / 写文件 + 用包 设 如果/否则如果/否则/结束 打印；终止 / 派任务 / 并行派任务 / 执行 / 跑测试 不许。
每次调用：语法 + 白名单 → 空跑（项目拷一份真套）→ 真执行 → 返回本次输出（打印、读 / 搜 / 查的结果、改文件报错，≤ 6000 字）。
检查不过、空跑报错也作为工具结果（isError=false 的普通文本）返回，让模型改。
同一个 MCP 进程里引擎状态（变量）一直保留 = 同一个子任务里多次调用共享变量；每个子任务起自己的进程。

每次调用往 --log 文件追加一行 JSON：{ts, t, code_len, code, reply(出错时返回给模型的原文), edited(是否改了文件), files(改了哪些), sec, status(ok/check/dry/error)}，
给父进程统计、计预算。

    python dslmcp.py --workdir 项目目录 --log 日志文件 [--verbs-root 动词目录]
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.dsl_core import ScriptHalt, ScriptReturn  # noqa: E402
from tools.dslagent import dslcheck as DC  # noqa: E402

TOOL = "dsl"
OUT_CAP = 6000
PROTOCOL = "2024-11-05"
DESC = r"""【dsl 工具】参数 code：一段中文 DSL 脚本；变量在多次调用之间保留

规则
- 一行一句
- 参数按空格切分；带空格的文本先「设 名 = 文本」再用 {名} 传入
- 读片段 返回的每行带「行号| 」前缀（如「  5|     return a」）；写进改法的原文必须去掉这个前缀
- 原文一字不差：含缩进、空行；在文件里只出现一次，不唯一就多带几行上下文
- 改文件 {名} 与 #改法 名 一一对应；多个文件可写在同一个改法块里（多个 @@ 改），也可分成多个块各自命名
- #改法 块写在脚本末尾；块内只能有 @@ 改 / @@ 新建 及原文 / 新文
- 正则里的空格写 \s

语句
- 设 名 = 值 | 设 名 = 动词 参数
- 打印 文本
- 如果 条件 / 否则如果 条件 / 否则 / 结束
  条件：甲 等于|不等于|包含|不包含|大于|小于 乙；甲 为空|不为空；组合：且 / 或 / 非
- 引用 {名}，取字段 {名.字段}

动词（路径相对项目根）
- 读片段 文件:起-止 → 每行「行号| 内容」
- 搜索代码 正则 [范围] → 每行「文件:行号: 内容」；范围＝文件或目录（逗号隔开多个，不要空格），不写搜全部 .py。例：搜索代码 正则 tools/dsl.py
- 查引用 名字 py → {n, text}
- 改文件 {改法名} → {ok, msg, n}
- 写文件 {e} → {ok, msg, n}；e = {file, content}

改法块格式
#改法 名
@@ 改 路径
<<<<<<< 原文
…
=======
…
>>>>>>> 新文
@@ 新建 路径
<<<<<<< 内容
…
>>>>>>> 新文

最小示例（先读，下一次调用再改一处）
调用 1：
设 r = 读片段 pkg/calc.py:1-20
打印 {r}
调用 2（读到「  5|     return a + b」）：
设 res = 改文件 {e1}
打印 {res.msg}
#改法 e1
@@ 改 pkg/calc.py
<<<<<<< 原文
    return a + b
=======
    return a + b + 1
>>>>>>> 新文"""
SCHEMA = {"type": "object", "properties": {"code": {"type": "string", "description": "DSL 脚本文本（#改法 段写在最后）"}},
          "required": ["code"]}


class Server:
    def __init__(self, workdir, log, verbs_root=None):
        from tools.dslagent.engine import AgentEngine
        from tools.mock import MockClient
        self.workdir = Path(workdir)
        self.log = Path(log) if log else None
        self.engine = AgentEngine(client=MockClient(default="（本工具不调模型）", offline=True), workdir=self.workdir, verbose=False,
                                  verbs_root=verbs_root)
        self.sub = self.engine._sub_engine()
        self.rec = []
        DC.record_reads(self.sub, self.rec)
        self.sub.run("用包 common text code")
        self.calls = 0

    def _log(self, **kw):
        if not self.log:
            return
        try:
            with open(self.log, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": round(time.time(), 3), "t": time.strftime("%Y-%m-%d %H:%M:%S"), **kw},
                                   ensure_ascii=False) + "\n")
        except OSError:
            pass

    def run_code(self, code):
        """返回 (输出文本, 日志字段)。"""
        from tools.dslagent import v2 as V2
        t0 = time.time()
        self.calls += 1
        info = {"n": self.calls, "code_len": len(code or ""), "code": code or "", "edited": False, "files": []}
        script, probs = DC.check_call(code or "", first=False)
        if probs:
            info.update(status="check", sec=round(time.time() - t0, 2))
            return ("【检查不过】\n" + "\n".join(f"- {p}" for p in probs[:12]) + "\n文件没有改动，请改正后重新调用。"), info
        err = DC.dry_run(self.engine, script, dict(self.sub.vars))
        if err:
            info.update(status="dry", sec=round(time.time() - t0, 2))
            return f"【空跑没过】{err}\n文件没有改动，请改正后重新调用。", info
        del self.rec[:]
        mark = len(self.sub.output)
        before = V2.snapshot(self.workdir)
        err_text = ""
        try:
            self.sub.run(script)
        except (ScriptReturn, ScriptHalt):
            err_text = "脚本里不能用 返回 / 终止"
        except Exception as e:  # noqa: BLE001
            err_text = f"脚本运行出错：{type(e).__name__}: {str(e)[:400]}"
        files = V2.changed(before, V2.snapshot(self.workdir))
        printed = "\n".join(self.sub.output[mark:])
        recs = [r for r in self.rec if r.split("\n", 1)[-1] not in printed]      # 打印里已经有的读 / 搜结果不重复贴
        parts = [x for x in (printed and f"[打印]\n{printed}", "\n".join(recs), err_text) if x]
        if files:
            parts.append("[改了文件] " + "、".join(files))
        info.update(status="error" if err_text else "ok", edited=bool(files), files=files, sec=round(time.time() - t0, 2))
        return DC.clip("\n".join(parts) or "（本段没有任何输出）", OUT_CAP), info

    def handle(self, msg):
        """一条 JSON-RPC 消息 → 响应 dict 或 None（通知不回）。"""
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:
            return None
        if method == "initialize":
            ver = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL
            res = {"protocolVersion": ver, "capabilities": {"tools": {}}, "serverInfo": {"name": "dslagent-dsl", "version": "1"}}
        elif method == "ping":
            res = {}
        elif method == "tools/list":
            res = {"tools": [{"name": TOOL, "description": DESC, "inputSchema": SCHEMA}]}
        elif method == "tools/call":
            p = msg.get("params") or {}
            if p.get("name") != TOOL:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"没有工具 {p.get('name')}"}}
            code = (p.get("arguments") or {}).get("code")
            if not isinstance(code, str):
                text, info = "参数 code 必须是字符串（DSL 文本）", {"status": "check", "code_len": 0, "edited": False, "files": [], "sec": 0}
            else:
                try:
                    text, info = self.run_code(code)
                except Exception as e:  # noqa: BLE001
                    text, info = f"工具内部出错：{type(e).__name__}: {str(e)[:300]}", {
                        "status": "internal", "code_len": len(code), "code": code, "edited": False, "files": [], "sec": 0}
            if info.get("status") != "ok":
                info["reply"] = text                      # 返回给模型的报错原文（检查不过 / 空跑没过 / 运行出错）
            self._log(**info)
            res = {"content": [{"type": "text", "text": text}], "isError": False}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"不支持 {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": res}

    def serve(self, fin=None, fout=None):
        fin, fout = fin or sys.stdin, fout or sys.stdout
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            out = self.handle(msg)
            if out is not None:
                fout.write(json.dumps(out, ensure_ascii=False) + "\n")
                fout.flush()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--log", default="")
    ap.add_argument("--verbs-root", default="")
    ap.add_argument("--state", default="")       # 本进程自己的状态目录（笔记 / 日志），并行子任务各用各的
    a = ap.parse_args(argv)
    if a.state:
        os.environ["DSLAGENT_STATE"] = a.state
    Server(a.workdir, a.log, a.verbs_root or str(ROOT / "tools" / "dslagent" / "verbs")).serve()


if __name__ == "__main__":
    main()
