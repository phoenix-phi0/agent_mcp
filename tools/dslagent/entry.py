"""统一入口：按资料包跑一次「规划 .zs → 执行 → 验收 → 补改」（v2 核心，场景差异全在 packs/<名>）。

    from tools.dslagent.entry import run_task
    r = run_task(project, task, "dslproj", scope=None, model=None, out=None)
    r["状态"], r["原因"], r["花费"]          # 状态：成功 | 失败 | 超出预期 | 部分成功

命令行（__main__.py）：python -m tools.dslagent run --pack <名> --project DIR --task-file F --out DIR [--scope a/,b/*.zs]
（不写 --pack = 旧命令，行为不变；写了 --pack 就走 v2，与 DSLAGENT_PLANNER 无关。）
run_pack 返回 v2.run 的完整结果字典；run_task 只挑关键字段，给以后的 DSL 动词（如「做模块」）调用。
"""
import tempfile
from pathlib import Path

from . import common as C
from . import packs


def run_pack(project, task, pack, out_dir, scope=None, model=None, test_cmd=None, wall=None, **kw):
    """v2.run 的薄封装：pack 是包名或包对象；其它参数同 v2.run。"""
    from . import v2
    pk = packs.pick(pack)
    extra = {"wall": wall} if wall else {}
    return v2.run(project, task, out_dir, test_cmd=test_cmd, model=model, scope=scope, pack=pk, **extra, **kw)


def run_task(project, task, pack="code", scope=None, model=None, out=None, **kw):
    """做一件事 → {状态, 原因, 花费, 记录目录, 改动文件}。out 缺省在 DSLAGENT_TMP 下建一个临时记录目录；
    model 是假模型 backend(system, user, tag, timeout)（测试用，缺省走真模型）；scope 缺省取包的 scope_for。"""
    out_dir = Path(out) if out else Path(tempfile.mkdtemp(prefix="dslagent_task_", dir=C.tmp_dir()))
    res = run_pack(project, task, pack, out_dir, scope=scope, model=model, **kw)
    r = res.get("reply") or {}
    return {"状态": r.get("状态") or ("成功" if res.get("fixed") else "失败"), "原因": r.get("原因") or res.get("stop") or "",
            "花费": res.get("cost", 0.0), "记录目录": str(out_dir), "改动文件": res.get("changed_files", [])}
