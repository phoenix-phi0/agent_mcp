# -*- coding: utf-8 -*-
"""tools/colab_vllm.py：会话不在就新建，启动脚本走 vllm serve，停止按 pid。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_colab_vllm.py

runner 是假的，不调用本机的 colab，也不分配 GPU。
"""

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.colab_vllm import (  # noqa: E402
    ColabVllm, ColabVllmError, CmdResult, chat_source, model_dir, serve_source,
    stop_source,
)


def test_serve_source_is_a_fresh_process():
    src = serve_source("Qwen/Qwen2.5-Coder-3B-Instruct-AWQ", 8000, 2048)
    compile(src, "<serve>", "exec")
    assert '"vllm", "serve"' in src
    assert "LLM(" not in src
    assert "--dtype" in src and "float16" in src
    assert "EAGER = False" in src
    assert "EAGER = True" in serve_source("a/b", 8000, 2048, enforce_eager=True)
    assert "start_new_session=True" in src
    assert model_dir("Qwen/Qwen2.5-Coder-3B-Instruct-AWQ") in src
    assert "pkill" not in src
    stopped = stop_source()
    compile(stopped, "<stop>", "exec")
    assert "SIGTERM" in stopped
    assert "pkill" not in stopped


def test_start_creates_session_then_serves():
    calls = []

    def runner(args, input_text, timeout):
        calls.append((list(args), input_text, timeout))
        if args[0] == "status":
            return CmdResult(1, "", "[colab] Session 'vllm' not found.")
        if args[0] == "new":
            return CmdResult(0, "[colab] Session READY.\n", "")
        if args[0] == "exec":
            return CmdResult(0, "noise\nCOLAB_VLLM_READY pid=4321\n", "")
        raise AssertionError(args)

    out = ColabVllm(runner=runner).start()
    assert out["created"] is True
    assert out["already"] is False
    assert out["pid"] == 4321
    assert out["dir"] == "/content/models/Qwen2.5-Coder-3B-Instruct-AWQ"
    assert calls[0][0] == ["status", "-s", "vllm"]
    assert calls[1][0] == ["new", "-s", "vllm", "--gpu", "T4"]
    assert calls[2][0][:3] == ["exec", "-s", "vllm"]
    assert '"vllm", "serve"' in calls[2][1]


def test_start_skips_new_when_session_exists():
    calls = []

    def runner(args, input_text, timeout):
        calls.append(args[0])
        if args[0] == "status":
            return CmdResult(0, "Status: IDLE\n", "")
        if args[0] == "exec":
            return CmdResult(0, "COLAB_VLLM_ALREADY\n", "")
        raise AssertionError(args)

    out = ColabVllm(runner=runner).start()
    assert out["created"] is False
    assert out["already"] is True
    assert calls == ["status", "exec"]


def test_exec_retries_lost_connection():
    n = {"exec": 0}

    def runner(args, input_text, timeout):
        if args[0] == "status":
            return CmdResult(0, "Status: IDLE\n", "")
        n["exec"] += 1
        if n["exec"] == 1:
            return CmdResult(0, "Connection was lost\n", "")
        return CmdResult(0, "COLAB_VLLM_READY pid=9\n", "")

    out = ColabVllm(runner=runner).start()
    assert n["exec"] == 2
    assert out["pid"] == 9


def test_start_failure_and_stop():
    def fail_runner(args, input_text, timeout):
        if args[0] == "status":
            return CmdResult(0, "Status: IDLE\n", "")
        return CmdResult(0, "COLAB_VLLM_FAIL worker died\n", "")

    try:
        ColabVllm(runner=fail_runner).start()
    except ColabVllmError as e:
        assert "worker died" in str(e)
    else:
        raise AssertionError("应该失败")

    seen = {}

    def stop_runner(args, input_text, timeout):
        if args[0] == "status":
            return CmdResult(0, "Status: IDLE\n", "")
        seen["src"] = input_text
        return CmdResult(0, "COLAB_VLLM_STOPPED\n", "")

    out = ColabVllm(runner=stop_runner).stop()
    assert out["stopped"] is True
    assert "SIGTERM" in seen["src"]
    assert "pkill" not in seen["src"]


def test_new_timeout_reports_orphan():
    def runner(args, input_text, timeout):
        if args[0] == "status":
            return CmdResult(1, "Session 'vllm' not found.\n", "")
        if args[0] == "new":
            return CmdResult(1, "", "ReadTimeout: Read timed out\n")
        if args[0] == "sessions":
            return CmdResult(0, "[?] gpu-t4-s-abc | Hardware: T4\n", "")
        return CmdResult(0, "", "")

    try:
        ColabVllm(runner=runner).start()
    except ColabVllmError as e:
        assert "gpu-t4-s-abc" in str(e)
        assert "ReadTimeout" in str(e)
    else:
        raise AssertionError("应该失败")


def test_status_when_session_down():
    def runner(args, input_text, timeout):
        assert args[0] == "status"
        return CmdResult(1, "", "not found")

    out = ColabVllm(runner=runner).status()
    assert out == {"session": "vllm", "session_up": False, "serving": False, "port": 8000}


def test_bad_model_name():
    try:
        model_dir("..")
    except ColabVllmError:
        pass
    else:
        raise AssertionError("空名字应该拒绝")


def _reply(text: str) -> str:
    return "COLAB_VLLM_REPLY " + base64.b64encode(text.encode()).decode()


def test_chat_when_already_serving():
    calls = []

    def runner(args, input_text, timeout):
        calls.append(args[0])
        if args[0] == "status":
            return CmdResult(0, "Status: IDLE\n", "")
        src = input_text or ""
        if "chat/completions" in src:
            assert "写一个回文" in src
            assert "max_tokens" in src
            return CmdResult(0, _reply("def is_palindrome(s):\n    return True\n") + "\n", "")
        if "COLAB_VLLM_UP" in src:
            return CmdResult(0, "COLAB_VLLM_UP\n", "")
        raise AssertionError(args)

    out = ColabVllm(runner=runner).chat("写一个回文", max_tokens=512)
    assert out["started"] is False
    assert "is_palindrome" in out["text"]
    assert "new" not in calls
    compile(chat_source("你好", ColabVllm.MODEL, 8000, 32, 0), "<chat>", "exec")


def test_chat_starts_when_down_and_rejects_empty():
    def runner(args, input_text, timeout):
        if args[0] == "status":
            return CmdResult(0, "Status: IDLE\n", "")
        src = input_text or ""
        if "chat/completions" in src:
            return CmdResult(0, _reply("好") + "\n", "")
        if "COLAB_VLLM_UP" in src:
            return CmdResult(0, "COLAB_VLLM_DOWN\n", "")
        if '"vllm", "serve"' in src:
            return CmdResult(0, "COLAB_VLLM_READY pid=3\n", "")
        raise AssertionError(src[:120])

    out = ColabVllm(runner=runner).chat("在吗")
    assert out["started"] is True
    assert out["text"] == "好"
    try:
        ColabVllm(runner=runner).chat("  ")
    except ColabVllmError as e:
        assert "空" in str(e)
    else:
        raise AssertionError("空对话应该拒绝")


if __name__ == "__main__":
    test_serve_source_is_a_fresh_process()
    test_start_creates_session_then_serves()
    test_start_skips_new_when_session_exists()
    test_exec_retries_lost_connection()
    test_start_failure_and_stop()
    test_new_timeout_reports_orphan()
    test_status_when_session_down()
    test_bad_model_name()
    test_chat_when_already_serving()
    test_chat_starts_when_down_and_rejects_empty()
    print("通过 10")
