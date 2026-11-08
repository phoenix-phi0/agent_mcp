# -*- coding: utf-8 -*-
"""编排节点的输出格式：读格式文件、校验、给 CLI 模型挂「提交」工具。

格式文件是 JSON Schema（draft 2020-12），放在工作目录的 formats/<名字>.json，顶层必须是
type: object。流程节点写「格式 名字」时：

- claude / goose：挂上 tools/wf_submit_mcp.py，模型只能用 submit 工具交结果，交错了当场
  收到具体错误再改。SubmitChannel.run 一边等进程一边盯结果文件，文件一出现就结束进程，
  不等模型再说「好的已提交」。
- 别的后端（离线假客户端、api 通道）：照旧要 JSON 回复，拿回来用同一个 validate 校验。
- 外部 workflow.submit 交的结果也用同一个 validate。
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "tools" / "wf_submit_mcp.py"
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
CLAUDE_TOOL = "mcp__wf__submit"


class FormatError(ValueError):
    pass


def load_format(workdir, name):
    """读 <workdir>/formats/<name>.json，检查它本身是合法的 JSON Schema、顶层是对象。"""
    from jsonschema import Draft202012Validator
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise FormatError(f"格式名无效：{name}")
    path = Path(workdir) / "formats" / f"{name}.json"
    if not path.is_file():
        raise FormatError(f"没有格式文件 formats/{name}.json")
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise FormatError(f"格式文件 formats/{name}.json 不是 JSON：{e}") from e
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as e:
        raise FormatError(f"格式文件 formats/{name}.json 不是合法的 JSON Schema：{e}") from e
    if schema.get("type") != "object":
        raise FormatError(f"格式 {name} 顶层必须是 type: object（提交工具的参数是一个对象）")
    return schema


def validate(schema, obj):
    """返回错误列表（空 = 符合）。每条写明位置，模型和人都看得懂。"""
    from jsonschema import Draft202012Validator
    out = []
    for e in sorted(Draft202012Validator(schema).iter_errors(obj), key=lambda e: list(e.absolute_path)):
        where = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in e.absolute_path) or "(顶层)"
        out.append(f"{where.lstrip('.')}: {e.message}")
    return out[:20]


class SubmitError(RuntimeError):
    pass


class SubmitChannel:
    """一次调用用一个：临时目录里放格式、结果文件、错误记录。用完 close()。"""

    def __init__(self, schema, max_tries=3):
        self.dir = Path(tempfile.mkdtemp(prefix="wf_submit_"))
        self.schema_path = self.dir / "schema.json"
        self.schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
        self.out = self.dir / "result.json"
        self.log = self.dir / "errors.jsonl"
        self.max_tries = max_tries

    def env(self):
        return {"WF_SCHEMA": str(self.schema_path), "WF_OUT": str(self.out),
                "WF_LOG": str(self.log), "WF_MAX_TRIES": str(self.max_tries)}

    def claude_args(self):
        """claude -p 用：只挂这一个 MCP 服务，并放行 submit 工具。"""
        cfg = {"mcpServers": {"wf": {"command": sys.executable, "args": [str(SERVER)],
                                     "env": self.env()}}}
        return ["--strict-mcp-config", "--mcp-config", json.dumps(cfg, ensure_ascii=False)]

    def goose_extension(self):
        """goose run --with-extension 用：「名字:环境变量… 命令」（路径都是临时目录，没有空格）。"""
        envs = " ".join(f"{k}={v}" for k, v in self.env().items())
        return f"wf_submit:{envs} {sys.executable} {SERVER}"

    def run(self, cmd, cwd, env, stdin_text, timeout, label):
        """跑 cmd；结果文件一出现就结束进程组。返回 (结果 dict 或 None, 进程输出)。"""
        t0 = time.time()
        with tempfile.TemporaryFile("w+", encoding="utf-8") as so, \
                tempfile.TemporaryFile("w+", encoding="utf-8") as se:
            proc = subprocess.Popen(cmd, cwd=str(cwd), env=env,
                                    stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                                    stdout=so, stderr=se, text=True, encoding="utf-8",
                                    errors="replace", start_new_session=True)
            if stdin_text is not None:
                try:
                    proc.stdin.write(stdin_text)
                    proc.stdin.close()
                except BrokenPipeError:
                    pass
            done = False
            while True:
                if self.out.exists():
                    done = True
                    time.sleep(0.3)        # 让工具把「已提交」回完，进程退不退都收
                    break
                if proc.poll() is not None:
                    break
                if time.time() - t0 > timeout:
                    _kill(proc)
                    raise SubmitError(f"{label} 超过 {timeout} 秒没有提交")
                time.sleep(0.2)
            if proc.poll() is None:
                _kill(proc)
            so.seek(0)
            se.seek(0)
            output = so.read()[-20000:] + ("\n[stderr]\n" + se.read()[-4000:])
        if done or self.out.exists():
            return json.loads(self.out.read_text(encoding="utf-8")), output
        return None, output

    def errors(self):
        """模型交错过的记录：[{"try", "errors", "arguments"}…]"""
        if not self.log.is_file():
            return []
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines() if x.strip()]

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def _kill(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(5)
    except ProcessLookupError:
        pass
