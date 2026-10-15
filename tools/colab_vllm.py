# -*- coding: utf-8 -*-
"""在 Colab T4 上启动 vLLM。

这块机器的系统内存是 13.6GB。官方 BF16 的 4B 代码模型加载时要再转一份
FP16，两份加起来大约 18GB，会用磁盘当内存，冷启动要十几分钟。默认因此用
Qwen2.5-Coder-3B-Instruct-AWQ：权重 2.7GB，按 4-bit 直接读，不用再复制一份。

启动分四步：没有会话就 colab new --gpu T4；虚拟机上没有 vllm 就安装；
没有权重就下载到 /content/models/<仓库名>；然后用一个全新的 Python 进程
跑 ``vllm serve``。不在笔记本内核里构造 LLM()。那个内核往往已经初始化过
CUDA，vLLM 只能 spawn，子进程把 torch 再导入一遍。

默认不加 --enforce-eager，启用 CUDA graph：T4 上单路约 85 token/s，
带 eager 只有约 17，代价是冷启动多约 100 秒。要关掉传 enforce_eager=True。

colab exec 即使远程代码失败，进程退出码也经常是 0，所以远程脚本用
COLAB_VLLM_* 这一行报告结果，本机只认这一行。

    from tools.colab_vllm import ColabVllm
    ColabVllm().chat("写一个判断回文的 Python 函数")
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
from dataclasses import dataclass


class ColabVllmError(RuntimeError):
    """colab 不在、会话起不来，或远程的 vLLM 没有报就绪。"""


@dataclass
class CmdResult:
    returncode: int
    stdout: str
    stderr: str


def model_dir(model_id: str) -> str:
    """Hugging Face 仓库名变成虚拟机上的目录。只取最后一段，避免多一层。"""
    name = model_id.strip().rstrip("/").split("/")[-1]
    if not name or name in (".", ".."):
        raise ColabVllmError(f"模型名不合法：{model_id!r}")
    return f"/content/models/{name}"


def serve_source(model_id: str, port: int, max_model_len: int,
                 enforce_eager: bool = False) -> str:
    """远程启动脚本。用 vllm serve，不用 LLM()。"""
    local = model_dir(model_id)
    return f"""import os, shutil, subprocess, sys, time, urllib.request
MODEL_ID = {model_id!r}
LOCAL = {local!r}
PORT = {int(port)}
MAX_LEN = {int(max_model_len)}
EAGER = {bool(enforce_eager)}
PID_FILE = "/content/vllm-serve.pid"
LOG_FILE = "/content/vllm-serve.log"

def say(line):
    print(line, flush=True)

try:
    import vllm  # noqa: F401
except ImportError:
    uv = shutil.which("uv")
    cmd = [uv, "pip", "install", "--system", "vllm"] if uv else [sys.executable, "-m", "pip", "install", "vllm"]
    subprocess.check_call(cmd)

if not os.path.isdir(LOCAL):
    from huggingface_hub import snapshot_download
    snapshot_download(MODEL_ID, local_dir=LOCAL)

url = "http://127.0.0.1:%s/v1/models" % PORT
try:
    urllib.request.urlopen(url, timeout=2).read()
    say("COLAB_VLLM_ALREADY")
    sys.exit(0)
except Exception:
    pass

log = open(LOG_FILE, "w")
proc = subprocess.Popen(
    ["vllm", "serve", LOCAL,
     "--dtype", "float16",
     "--max-model-len", str(MAX_LEN),
     *(["--enforce-eager"] if EAGER else []),
     "--gpu-memory-utilization", "0.85",
     "--host", "127.0.0.1",
     "--port", str(PORT)],
    stdout=log,
    stderr=subprocess.STDOUT,
    start_new_session=True,
)
open(PID_FILE, "w").write(str(proc.pid))
deadline = time.time() + 600
while time.time() < deadline:
    if proc.poll() is not None:
        log.flush()
        tail = open(LOG_FILE, errors="replace").read()[-2000:]
        say("COLAB_VLLM_FAIL " + tail.replace("\\n", " "))
        sys.exit(0)
    try:
        urllib.request.urlopen(url, timeout=2).read()
        say("COLAB_VLLM_READY pid=%s" % proc.pid)
        sys.exit(0)
    except Exception:
        time.sleep(3)
say("COLAB_VLLM_FAIL timeout")
"""


def stop_source() -> str:
    """只停 vLLM 进程，不停 Colab 虚拟机。按记下的 pid 杀，不用 pkill。"""
    return """import os, signal, time
PID_FILE = "/content/vllm-serve.pid"
if not os.path.isfile(PID_FILE):
    print("COLAB_VLLM_NOT_RUNNING", flush=True)
    raise SystemExit(0)
pid = int(open(PID_FILE).read().strip())
try:
    os.kill(pid, signal.SIGTERM)
except ProcessLookupError:
    print("COLAB_VLLM_NOT_RUNNING", flush=True)
    raise SystemExit(0)
for _ in range(20):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        print("COLAB_VLLM_STOPPED", flush=True)
        raise SystemExit(0)
    time.sleep(0.25)
os.kill(pid, signal.SIGKILL)
print("COLAB_VLLM_STOPPED", flush=True)
"""


def chat_source(message: str, model_id: str, port: int,
                max_tokens: int, temperature: float) -> str:
    """在虚拟机上请求本机的 vLLM。回复用一行 base64 传回，避免换行被截断。"""
    local = model_dir(model_id)
    return f"""import base64, json, urllib.request
body = json.dumps({{
    "model": {local!r},
    "messages": [{{"role": "user", "content": {message!r}}}],
    "max_tokens": {int(max_tokens)},
    "temperature": {float(temperature)},
}}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:{int(port)}/v1/chat/completions",
    data=body,
    headers={{"Content-Type": "application/json"}},
)
try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode())
    text = data["choices"][0]["message"]["content"]
    print("COLAB_VLLM_REPLY " + base64.b64encode(text.encode()).decode(), flush=True)
except Exception as e:
    err = base64.b64encode(str(e).encode()).decode()
    print("COLAB_VLLM_FAIL " + err, flush=True)
"""


def probe_source(port: int) -> str:
    return f"""import urllib.request
try:
    urllib.request.urlopen("http://127.0.0.1:{int(port)}/v1/models", timeout=2).read()
    print("COLAB_VLLM_UP", flush=True)
except Exception:
    print("COLAB_VLLM_DOWN", flush=True)
"""


def _sentinel(text: str) -> str:
    """远程输出里最后一行 COLAB_VLLM_*。colab 会在前面夹进度和警告。"""
    found = ""
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("COLAB_VLLM_"):
            found = line
    return found


class ColabVllm:
    """启动、查看、停止，以及直接对话。runner 换成假的就能测，不碰网络。"""

    MODEL = "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"
    SESSION = "vllm"
    GPU = "T4"
    PORT = 8000
    MAX_MODEL_LEN = 2048

    def __init__(self, runner=None, colab: str = "colab"):
        self.colab = colab
        self._runner = runner or self._default_runner

    def _default_runner(self, args: list[str], input_text: str | None, timeout: int) -> CmdResult:
        bin_path = shutil.which(self.colab) or self.colab
        if os.path.sep not in bin_path and shutil.which(bin_path) is None:
            raise ColabVllmError(
                "找不到 colab。安装：uv tool install google-colab-cli")
        try:
            proc = subprocess.run(
                [bin_path, *args],
                input=input_text,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise ColabVllmError(f"colab {' '.join(args)} 超过 {timeout} 秒") from e
        return CmdResult(proc.returncode, proc.stdout or "", proc.stderr or "")

    def _exec(self, session: str, source: str, timeout: int) -> str:
        # 新内核的 WebSocket 有时还没连上，第一次 exec 会 Connection was lost。
        # 再跑一次即可，不用再建会话。
        last = ""
        for attempt in range(2):
            result = self._runner(
                ["exec", "-s", session, "--timeout", str(timeout)],
                source,
                timeout + 30,
            )
            text = (result.stdout or "") + "\n" + (result.stderr or "")
            line = _sentinel(text)
            if line:
                return line
            last = text
            if attempt == 0 and "Connection was lost" not in text:
                break
        raise ColabVllmError("远程没有返回 COLAB_VLLM_*：\n" + last.strip()[-2000:])

    def _session_up(self, session: str) -> bool:
        result = self._runner(["status", "-s", session], None, 60)
        text = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            return False
        if "not found" in text.lower():
            return False
        return "Status:" in text or "READY" in text

    def orphans(self) -> list[str]:
        """服务器上有、本机状态里没有的虚拟机。colab sessions 里以 [?] 开头。"""
        try:
            result = self._runner(["sessions"], None, 60)
        except ColabVllmError:
            return []
        text = (result.stdout or "") + (result.stderr or "")
        return [ln.strip() for ln in text.splitlines() if ln.strip().startswith("[?]")]

    def start(self, model: str | None = None, session: str | None = None,
              gpu: str | None = None, port: int | None = None,
              max_model_len: int | None = None, timeout: int = 900,
              enforce_eager: bool = False) -> dict:
        """保证会话、vLLM、权重和服务都在。已经在听端口就不再启动。"""
        model = model or self.MODEL
        session = session or self.SESSION
        gpu = gpu or self.GPU
        port = self.PORT if port is None else port
        max_model_len = self.MAX_MODEL_LEN if max_model_len is None else max_model_len
        created = False
        if not self._session_up(session):
            created = True
            result = self._runner(
                ["new", "-s", session, "--gpu", gpu], None, timeout)
            text = (result.stdout or "") + (result.stderr or "")
            if result.returncode != 0 or "READY" not in text:
                hint = ""
                lost = self.orphans()
                if lost:
                    hint = ("\n服务器上有本机不认识的虚拟机（分配请求超时但实际成功了），"
                            "会占免费 T4 额度，colab stop 关不掉。"
                            "到 colab.research.google.com 的“管理会话”里结束它，再重试：\n"
                            + "\n".join(lost))
                raise ColabVllmError("创建会话失败：\n" + text.strip()[-1500:] + hint)
        line = self._exec(
            session, serve_source(model, port, max_model_len, enforce_eager), timeout)
        if line.startswith("COLAB_VLLM_FAIL"):
            raise ColabVllmError(line)
        ready = line.startswith("COLAB_VLLM_READY") or line.startswith("COLAB_VLLM_ALREADY")
        if not ready:
            raise ColabVllmError(line)
        pid = None
        if "pid=" in line:
            pid = int(line.split("pid=", 1)[1].split()[0])
        return {
            "session": session,
            "model": model,
            "dir": model_dir(model),
            "port": port,
            "created": created,
            "already": line.startswith("COLAB_VLLM_ALREADY"),
            "pid": pid,
        }

    def status(self, session: str | None = None, port: int | None = None) -> dict:
        session = session or self.SESSION
        port = self.PORT if port is None else port
        up = self._session_up(session)
        serving = False
        if up:
            line = self._exec(session, probe_source(port), 60)
            serving = line.startswith("COLAB_VLLM_UP")
        return {"session": session, "session_up": up, "serving": serving, "port": port}

    def stop(self, session: str | None = None) -> dict:
        """停 vLLM。Colab 虚拟机还在，下次 start 不用重新分配 GPU。"""
        session = session or self.SESSION
        if not self._session_up(session):
            return {"session": session, "stopped": False, "reason": "会话不在"}
        line = self._exec(session, stop_source(), 60)
        return {
            "session": session,
            "stopped": line.startswith("COLAB_VLLM_STOPPED"),
            "was_running": not line.startswith("COLAB_VLLM_NOT_RUNNING"),
        }

    def chat(self, message: str, model: str | None = None, session: str | None = None,
             port: int | None = None, max_tokens: int = 1024, temperature: float = 0,
             timeout: int = 900) -> dict:
        """发一句话，返回模型回复。服务没开就先 start()。"""
        if not (message or "").strip():
            raise ColabVllmError("对话内容是空的")
        model = model or self.MODEL
        session = session or self.SESSION
        port = self.PORT if port is None else port
        started = False
        if not self.status(session, port)["serving"]:
            self.start(model=model, session=session, port=port, timeout=timeout)
            started = True
        line = self._exec(
            session,
            chat_source(message, model, port, max_tokens, temperature),
            timeout,
        )
        if line.startswith("COLAB_VLLM_FAIL"):
            payload = line.split(" ", 1)[1] if " " in line else ""
            try:
                detail = base64.b64decode(payload).decode()
            except Exception:
                detail = payload
            raise ColabVllmError(detail or line)
        if not line.startswith("COLAB_VLLM_REPLY "):
            raise ColabVllmError(line)
        text = base64.b64decode(line.split(" ", 1)[1]).decode()
        return {"text": text, "session": session, "model": model, "started": started}


def describe() -> str:
    return (
        "ColabVllm：在 Colab T4 上启动 vLLM。\n"
        f"默认模型 {ColabVllm.MODEL}，会话 {ColabVllm.SESSION}，"
        f"端口 {ColabVllm.PORT}。\n"
        "start() 开会话、装 vLLM、下载权重，并用新进程跑 vllm serve。\n"
        "chat(message) 直接对话；服务没开就先启动。默认最多生成 1024 个 token。\n"
        "stop() 只停 vLLM，不停虚拟机。status() 看会话和服务在不在。"
    )


def start(model: str = ColabVllm.MODEL, session: str = ColabVllm.SESSION,
          gpu: str = ColabVllm.GPU, port: int = ColabVllm.PORT,
          max_model_len: int = ColabVllm.MAX_MODEL_LEN, timeout: int = 900,
          enforce_eager: bool = False) -> dict:
    return ColabVllm().start(model, session, gpu, port, max_model_len, timeout,
                             enforce_eager)


def status(session: str = ColabVllm.SESSION, port: int = ColabVllm.PORT) -> dict:
    return ColabVllm().status(session, port)


def stop(session: str = ColabVllm.SESSION) -> dict:
    return ColabVllm().stop(session)


def chat(message: str, model: str = ColabVllm.MODEL, session: str = ColabVllm.SESSION,
         port: int = ColabVllm.PORT, max_tokens: int = 1024, temperature: float = 0,
         timeout: int = 900) -> dict:
    return ColabVllm().chat(message, model, session, port, max_tokens, temperature, timeout)
