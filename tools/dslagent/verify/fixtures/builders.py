"""边界复核表执行器的夹具构造：通用工作区（文本文件、项目树、符号链接）和按模块登记的专用夹具（modules.json 里的「构造」名 → BUILDERS）。"""
import json
import os
from pathlib import Path

SHORT = ["a1", "a2", "a3"]
NORMAL = [f"line{i}" for i in range(1, 21)]
PROJECT_FILES = ["a.py", ".hidden.py", "sub/mod.py", "sub/.x/y.py", "venv/x.py", "venv2/y.py", "build/b.py", "builds/c.py",
                 "dist/d.py", "env/e.py", "node_modules/n.py", "site-packages/s.py", "__pycache__/p.py", ".git/g.py",
                 "pkg/__init__.py", "pkg/m.py", "sub/venv/z.py", "sub/build/w.py"]


def build_workspace(tmp: Path) -> Path:
    """tmp/ws 是工作区；tmp/outside.txt 在工作区外。返回 ws。"""
    ws = Path(tmp) / "ws"
    ws.mkdir(parents=True)
    (Path(tmp) / "outside.txt").write_text("out1\nout2\n", encoding="utf-8")
    (ws / "empty.txt").write_text("", encoding="utf-8")
    (ws / "short.txt").write_text("\n".join(SHORT) + "\n", encoding="utf-8")
    (ws / "normal.txt").write_text("\n".join(NORMAL) + "\n", encoding="utf-8")
    (ws / "sub").mkdir()
    (ws / "sub" / "inner.txt").write_text("in1\nin2\n", encoding="utf-8")
    for rel in PROJECT_FILES:
        p = ws / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"X = '{rel}'\n", encoding="utf-8")
    os.symlink(ws / "normal.txt", ws / "link_in.txt")
    os.symlink(Path(tmp) / "outside.txt", ws / "link_out.txt")
    return ws


def _job(name, status, tasks, pid=None):
    d = {"id": name, "name": f"n-{name}", "status": status, "created": "2026-01-01T00:00:00", "tasks": tasks}
    if pid is not None:
        d["pid"] = pid
    return d


def build_jobs(jobs_dir: Path):
    """cbatch/gbatch 专用夹具（为 T3 的 jobs 接口专门写的）：8 个任务目录，含死掉的、坏 JSON、非对象、缺 tasks、无 job.json。"""
    jobs_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "j8_done": _job("j8_done", "done", [{"status": "done"}]),
        "j7_nojson": None,
        "j6_failed": _job("j6_failed", "failed", [{"status": "failed"}, {"status": "done"}]),
        "j5_notasks": {"id": "j5_notasks", "name": "x", "status": "done", "created": "2026-01-01T00:00:00"},
        "j4_died": _job("j4_died", "running", [{"status": "running"}, {"status": "pending"}], pid=999999),
        "j3_list": [],
        "j2_bad": "{not json",
        "j1_done": _job("j1_done", "done", [{"status": "done"}, {"status": "done"}]),
    }
    for i in range(1, 13):                       # 第二轮扩充：12 个正常任务，条数多于缺省 limit(10)
        st = "done" if i % 2 else "failed"
        nm = f"k{i:02d}_{st}"
        spec[nm] = _job(nm, st, [{"status": st}])
    for name, d in spec.items():
        (jobs_dir / name).mkdir(exist_ok=True)
        if d is None:
            continue
        txt = d if isinstance(d, str) else json.dumps(d, ensure_ascii=False)
        (jobs_dir / name / "job.json").write_text(txt, encoding="utf-8")


def build_jobs_both(tmp: Path):
    """jobs 夹具：CBATCH_HOME / GBATCH_HOME 各指一份。"""
    build_jobs(Path(tmp) / "cb_jobs")
    build_jobs(Path(tmp) / "gb_jobs")


BUILDERS = {"jobs": build_jobs_both}
