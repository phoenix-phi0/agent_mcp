# -*- coding: utf-8 -*-
"""ZBatch 客户端：从 MCP 这边提交批量 zcode 任务。

ZBatch 是跑在 Windows 上的一个小服务（`~/.zcode/batchsvc/`），把一批
提示词逐条交给 WSL 里的 zcode 跑，结果存成 json。先前只能在它的网页
仪表盘上手动提交，这个模块让 MCP 工具也能调。

## 两道限制，有意的

**不自动拉起服务。** 服务没在跑就直接报错，让人自己启动。

理由是这条链已经够长：模型 → zbatch → zcode → 文件系统。zcode 能读写
文件、能调 MCP 工具，而 zbatch 是**批量**的——一次提交跑几十分钟，后台
执行不好中断。起不起这个服务该是人的决定，不是某次工具调用的副作用。

**单次最多 MAX_TASKS 条。** 服务端允许 100，这里收紧到 10。批量失控的
代价比单次调用大得多，而十条已经够用——真要跑一百条就去仪表盘提交，
那时人是看着的。

## 心跳走 /api/ping，不走 /api/jobs

踩过两次同一个坑：提交之后立刻查状态，报「服务没在跑」——服务好好的，
只是正在跑任务、`/api/jobs` 响应慢过了超时。那个接口要把每个任务的
完整输出序列化一遍，是最重的一个，却被拿来当心跳。

现在服务端有个专门的 `/api/ping`，不碰任务内容。客户端探测打它。

端口也记住了（`_cached_port`），不每次重扫——重扫意味着最多试二十个
端口，服务忙的时候一样会超时。

## 用法

    from tools import zbatch

    zbatch.describe()                        # 服务在不在、跑着什么
    zbatch.submit(["任务一", "任务二"])       # 提交
    zbatch.status(job_id)                    # 查进度
    zbatch.wait(job_id)                      # 等跑完
    zbatch.cancel(job_id)
"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

HOME = Path.home()
BASE = HOME / ".zcode" / "batchsvc"
PORT_FILE = BASE / "port.txt"

# 服务端口的搜索范围，跟 server.py 的 serve() 一致
PORT_RANGE = range(8010, 8030)

# 普通请求的超时。查详情要读整个 job.json，任务多时有点慢。
TIMEOUT = 20
# 心跳的超时。打的是 /api/ping，那个接口很轻，两秒足够——
# 慢到这个地步说明服务真出问题了，不是「在忙」。
PROBE_TIMEOUT = 2

# 单次提交的任务数上限。服务端放到 100，这里收紧——见模块文档。
MAX_TASKS = 10

# 拼在第一条任务前面的交代。
#
# 这几条都是踩出来的：一次「读一千行、改两处、写回去」的任务跑满 600
# 秒被杀，原因是它写回失败之后一直重试、换方式、再试——zcode 不会认输，
# 而没人告诉过它什么时候该停。
#
# 只加在第一条：share 模式下后面的任务续接同一个会话，说过的话还在，
# 每条都重发是白烧 token。isolated 模式下后面的任务各自独立，本来也
# 不该假定它们要写文件。
PREAMBLE = """【环境交代，先读这一段】

1. /home/ysc/mcp-data 是**只读**挂载，你在那儿写不了文件。要写就用
   MCP 工具 mcp__agent_mcp__write_file，参数 path 相对那个目录（比如
   "tools/x.py"），key 传 8d055c36-0f9d-472a-b0cb-54ecacceb5ac。

2. **同一件事失败两次就停下来报告**，不要继续想办法。说清楚失败在哪
   一步、报的什么错、你本来想写的内容是什么——调用方能接着处理。你在
   那儿重试十分钟的话会被超时杀掉，什么都留不下。

3. 单条任务有 600 秒上限。要输出很长的内容（超过五百行）就先停下来说
   一声，别闷头写完。

4. 没让你改文件的任务就别改，只报告。

---

"""

# 上次找到的端口。服务不会换端口，除非重启过。
_cached_port = None


class ZBatchError(Exception):
    """服务没跑，或者接口返回了错误。"""


def _get(url: str, timeout: int = TIMEOUT):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(url: str, payload: dict, timeout: int = TIMEOUT):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _hosts() -> list:
    """按顺序试哪些主机。本机永远第一个；WSL 里服务在 Windows 宿主上，
    宿主 IP 从 /etc/resolv.conf 的 nameserver 读。"""
    hosts = ["127.0.0.1"]
    try:
        for line in Path("/etc/resolv.conf").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("nameserver"):
                ip = line.split()[1].strip()
                if ip not in hosts:
                    hosts.append(ip)
    except OSError:
        pass
    return hosts


def _alive(host: str, port: int) -> bool:
    """这个端口上有没有 ZBatch。

    打 /api/ping 而不是 /api/jobs：后者要序列化全部任务输出，任务跑着
    时能慢过几秒，于是「服务在忙」被判成「服务没跑」。

    老版服务端没有 ping，这时退回 /api/jobs——不然换新客户端就连不上
    旧服务了。
    """
    base = f"http://{host}:{port}"
    try:
        _get(f"{base}/api/ping", timeout=PROBE_TIMEOUT)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            try:
                _get(f"{base}/api/jobs", timeout=PROBE_TIMEOUT * 3)
                return True
            except (urllib.error.URLError, OSError, ValueError):
                return False
        return False
    except (urllib.error.URLError, OSError, ValueError):
        return False


def find_port(force: bool = False):
    """找到正在跑的服务端口，没有返回 None。

    记住上次的结果：每次调用都扫一遍最多要试二十个端口，服务忙的时候
    一样会超时。先看缓存，再看 port.txt，最后才扫——port.txt 可能是
    上次崩溃留下的陈货，所以不能只信它。
    """
    global _cached_host, _cached_port

    if _cached_port and not force and _alive(_cached_host, _cached_port):
        return _cached_host, _cached_port

    recorded = None
    try:
        recorded = int(PORT_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pass

    for host in _hosts():
        if recorded and _alive(host, recorded):
            _cached_host, _cached_port = host, recorded
            return host, recorded

        for p in PORT_RANGE:
            if p != recorded and _alive(host, p):
                _cached_host, _cached_port = host, p
                return host, p

    _cached_host = _cached_port = None
    return None


def _base_url() -> str:
    host, port = find_port()
    if port is None:
        raise ZBatchError(
            "ZBatch 服务没在跑。启动它：\n"
            f"  cd {BASE} && python app.pyw\n"
            "（用 python 而不是 pythonw，控制台留着能看到报错）\n"
            "这个模块不自动拉起服务——批量任务跑起来几十分钟不好中断，"
            "起不起该由人决定。")
    return f"http://{host}:{port}"


# ----------------------------------------------------------------------


def submit(tasks, name: str = "", mode: str = "share",
           cwd: str = "/home/ysc", preamble: bool = True) -> dict:
    """提交一批任务。tasks 是提示词列表，或 {prompt, outfile} 字典列表。

    mode="share"：后续任务用 -c 续接同一个 zcode 会话，前一条的上下文
    还在，适合「先读文件，再基于它改」这种。代价是前一条跑偏会带歪
    后面的。
    mode="isolated"：每条独立，互不影响。

    返回 {"job_id": ..., "status": ..., "tasks": N}。
    """
    items = []
    for t in tasks:
        if isinstance(t, str):
            items.append({"prompt": t, "outfile": ""})
        elif isinstance(t, dict) and t.get("prompt"):
            items.append({"prompt": t["prompt"],
                          "outfile": t.get("outfile", "")})
        else:
            raise ZBatchError(f"任务要是字符串或含 prompt 的字典，收到：{t!r}")

    if not items:
        raise ZBatchError("一条任务都没有")
    if len(items) > MAX_TASKS:
        raise ZBatchError(
            f"一次最多 {MAX_TASKS} 条，这次给了 {len(items)} 条。"
            f"真要跑更多就去仪表盘提交——那时人是看着的。")
    if mode not in ("share", "isolated"):
        raise ZBatchError(f"mode 只能是 share 或 isolated，收到：{mode}")

    # 环境交代只加在第一条：share 模式下后面的任务续接同一个会话，说过
    # 的话还在。preamble=False 给「就是要原样跑这段提示词」的场合留口子。
    if preamble:
        items[0]["prompt"] = PREAMBLE + items[0]["prompt"]

    return _post(f"{_base_url()}/api/jobs",
                 {"name": name, "tasks": items, "mode": mode, "cwd": cwd})


def status(job_id: str, full: bool = False) -> dict:
    """查一个任务的进度和输出。

    full=False 时每条输出截断到 500 字——批量任务的输出加起来很容易几万
    字，全塞进对话里没人看得完，还挤掉上下文。要完整的传 full=True，
    或者去仪表盘看。
    """
    try:
        d = _get(f"{_base_url()}/api/jobs/{job_id}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ZBatchError(f"没有这个任务：{job_id}") from e
        raise

    if not full:
        for t in d.get("tasks", []):
            out = t.get("output") or ""
            if len(out) > 500:
                t["output"] = out[:500] + f"…（还有 {len(out) - 500} 字）"
    return d


def wait(job_id: str, timeout: int = 300, every: int = 10) -> dict:
    """等一个任务跑完，返回最终状态。超时就返回当前状态，不报错。

    轮询而不是长连接：服务端没有推送，而这个客户端也不该为了等结果一直
    占着连接——一条任务四十秒起步，十条就是七八分钟。

    超时不报错是因为「还在跑」本身就是有用的信息，抛异常的话调用方还得
    再查一次才知道进展到哪了。
    """
    deadline = time.time() + timeout
    while True:
        d = status(job_id)
        if d.get("status") != "running":
            return d
        if time.time() >= deadline:
            d["_note"] = f"等了 {timeout} 秒还在跑，这是中途状态"
            return d
        time.sleep(every)


def jobs(limit: int = 10) -> list:
    """最近的任务列表，默认十条。"""
    return _get(f"{_base_url()}/api/jobs")[:limit]


def cancel(job_id: str) -> dict:
    """取消一个正在跑的任务。会杀掉当前那条的子进程。"""
    return _post(f"{_base_url()}/api/jobs/{job_id}/cancel", {})


def describe() -> str:
    """服务状态，人话版。排查时先跑这个。

    强制重扫端口：这个函数就是用来确认服务到底在不在的，缓存在这儿
    是反作用。
    """
    found = find_port(force=True)
    if found is None:
        return ("ZBatch 没在跑。\n"
                f"  启动：cd {BASE} && python app.pyw")
    host, port = found
    try:
        js = _get(f"http://{host}:{port}/api/jobs")
    except Exception as e:
        return f"ZBatch 在 {host}:{port}，但取任务列表失败：{e}"

    lines = [f"ZBatch 在 {host}:{port}，{len(js)} 个任务"]
    for j in js[:5]:
        lines.append(f"  {j['id']}  {j['status']:10} {j['progress']:8} "
                     f"{j['name'][:30]}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())
