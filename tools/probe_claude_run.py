#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude CLI 只读探针启动器（给 gsb_tools probe 用）。

跑 `claude -p`：permission-mode=plan，只挂 builtins + gsb_read_files MCP，
关掉 Claude.ai connectors。把 JSON 结果里的 result 写到 --out，stdout/stderr 进 --log。
退出码：0 成功；2 模型/API 临时错误（供上层重试）；其它失败。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_CAPACITY = re.compile(
    r"at capacity|overloaded|rate.?limit|too many requests|usage.?limit|"
    r"credit.?balance|429|temporarily unavailable",
    re.I,
)


def _parse_json(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def _usage_tokens(d: dict):
    mu = d.get("modelUsage") or {}
    total = 0
    n = 0
    for v in mu.values() if isinstance(mu, dict) else []:
        if not isinstance(v, dict):
            continue
        n += 1
        for k in ("inputTokens", "outputTokens", "cacheReadInputTokens",
                  "cacheCreationInputTokens"):
            try:
                total += int(v.get(k) or 0)
            except (TypeError, ValueError):
                pass
    return total if n else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Claude read-only probe runner")
    ap.add_argument("--model", required=True)
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--cwd", required=True)
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--mcp-config", required=True)
    ap.add_argument("--settings", required=True)
    ap.add_argument("--claude-bin", default="")
    ap.add_argument("--tools", default="Read,Glob,Grep,Bash")
    # verify 用：默认值就是原来的只读探针（plan、不预批工具、只加 --cwd）
    ap.add_argument("--permission-mode", default="plan")
    ap.add_argument("--allowed-tools", default="")
    ap.add_argument("--extra-dir", action="append", default=[])
    args = ap.parse_args(argv)

    exe = args.claude_bin or os.environ.get("GSB_CLAUDE_BIN") or shutil.which("claude")
    if not exe:
        Path(args.log).write_text("ERROR: 找不到 claude\n", encoding="utf-8")
        return 1
    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    wd = args.cwd
    cmd = [
        exe, "-p",
        "--model", args.model,
        "--effort", args.effort,
        "--permission-mode", args.permission_mode,
        "--tools", args.tools,
        "--strict-mcp-config",
        "--mcp-config", args.mcp_config,
        "--settings", args.settings,
        "--add-dir", wd, *[x for d in args.extra_dir for x in ("--add-dir", d)],
        "--output-format", "json",
    ]
    if args.allowed_tools:
        cmd += ["--allowed-tools", args.allowed_tools]
    cmd += ["--", prompt]
    _secret_name = re.compile(r"TOKEN|SECRET|PASSW|API_?KEY|ACCESS_KEY|PRIVATE_KEY|CREDENTIAL", re.I)
    _secret_in_value = re.compile(
        r"\bexport\s+[A-Z0-9_]*(?:TOKEN|SECRET|PASSW|API_?KEY|ACCESS_KEY|PRIVATE_KEY|CREDENTIAL)[A-Z0-9_]*\s*=",
        re.I,
    )

    def _leaky(k, v=""):
        if k == "__CURSOR_SANDBOX_ENV_RESTORE" or k.startswith("__CURSOR_SANDBOX_ENV"):
            return True
        if _secret_name.search(k):
            return True
        if v and _secret_in_value.search(v):
            return True
        return False

    env = {k: v for k, v in os.environ.items() if not _leaky(k, v)}
    env["ENABLE_CLAUDEAI_MCP_SERVERS"] = "0"

    Path(args.out).write_text("", encoding="utf-8")
    with open(args.log, "ab") as lf:
        lf.write(f"[probe_claude_run] cmd_model={args.model} effort={args.effort} cwd={wd}\n".encode())
        try:
            p = subprocess.run(cmd, cwd=wd, env=env, capture_output=True)
        except OSError as e:
            lf.write(f"ERROR: 启动 claude 失败：{e}\n".encode())
            return 1
        if p.stdout:
            lf.write(p.stdout)
            if not p.stdout.endswith(b"\n"):
                lf.write(b"\n")
        if p.stderr:
            lf.write(b"----- stderr -----\n")
            lf.write(p.stderr)
            if not p.stderr.endswith(b"\n"):
                lf.write(b"\n")

    raw = (p.stdout or b"").decode("utf-8", "replace")
    err_txt = (p.stderr or b"").decode("utf-8", "replace")
    d = _parse_json(raw)
    text = ""
    is_err = False
    if d:
        text = d.get("result") or ""
        is_err = bool(d.get("is_error"))
        tok = _usage_tokens(d)
        with open(args.log, "ab") as lf:
            if tok is not None:
                lf.write(f"tokens used\n{tok:,}\n".encode())
            actual = ",".join((d.get("modelUsage") or {}).keys()) if isinstance(d.get("modelUsage"), dict) else ""
            if actual:
                lf.write(f"actual_model={actual}\n".encode())
    Path(args.out).write_text(text or "", encoding="utf-8")

    blob = raw + "\n" + err_txt
    if p.returncode != 0 or is_err or not text.strip():
        if _CAPACITY.search(blob):
            with open(args.log, "ab") as lf:
                lf.write(b"ERROR: model overloaded / rate limit (capacity)\n")
            return 2
        return p.returncode if p.returncode else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
