用包 common text code
预算 调用 3 秒 180
设 res = 改文件 {e1}
如果 {res.ok} 不等于 是
  设 inp.src = tools/cbatch.py:480-495,tools/gbatch.py:467-482
  设 inp.error = {res.msg}
  设 desc = 修复两个批量执行器 jobs 接口，按任务要求增加 status 筛选和坏 job.json 容错
  设 logic = edits 每项字段名固定为 file、old、new；old 必须从入参原文一字不差抄写；保留现有排序和概要字段；status 缺省 None，逗号分隔状态筛选；上限在筛选后计算；坏 JSON、非对象、缺必需字段或结构损坏的任务列为 broken，progress 为 ?，name 和 created 为空串，含 error 原因；无 job.json 继续跳过；只改这两个非测试文件
  设 r = 派任务 {desc} {inp} {logic} edits:列表,note:文本
  如果 {r.状态} 不等于 成功
    终止 失败 预设改法未能应用：{res.msg}；子任务失败：{r.原因}
  结束
  设 res = 改文件 {r.结果}
  如果 {res.ok} 不等于 是
    终止 失败 修复改法未能应用：{res.msg}
  结束
结束
终止 成功 两个批量执行器的 jobs 接口已增加状态筛选、筛后限额和坏任务目录容错：{res.msg}

#改法 e1
@@ 改 tools/cbatch.py
<<<<<<< 原文
def jobs(limit: int = 10) -> list:
    """最近的任务（新的在前），每个只给概要。"""
    if not JOBS.is_dir():
        return []
    out = []
    for jd in sorted(JOBS.iterdir(), reverse=True):
        if not (jd / "job.json").is_file():
            continue
        d = _settle(_load(jd.name))
        done = sum(t["status"] not in ("pending", "running") for t in d["tasks"])
        out.append({"id": d["id"], "name": d["name"], "status": d["status"],
                    "progress": f"{done}/{len(d['tasks'])}",
                    "created": d["created"]})
        if len(out) >= limit:
            break
    return out
=======
def jobs(limit: int = 10, status: str = None) -> list:
    """最近的任务（新的在前），每个只给概要；可按状态筛选。"""
    if not JOBS.is_dir():
        return []
    wanted = {s.strip() for s in status.split(",") if s.strip()} if status else None
    out = []
    for jd in sorted(JOBS.iterdir(), reverse=True):
        if not (jd / "job.json").is_file():
            continue
        try:
            d = _load(jd.name)
            if not isinstance(d, dict):
                raise ValueError("job.json 不是对象")
            missing = [k for k in ("id", "name", "status", "tasks", "created") if k not in d]
            if missing:
                raise ValueError(f"job.json 缺必需字段：{', '.join(missing)}")
            if not isinstance(d["tasks"], list) or any(
                    not isinstance(t, dict) or "status" not in t for t in d["tasks"]):
                raise ValueError("job.json 的 tasks 结构无效")
            d = _settle(d)
            done = sum(t["status"] not in ("pending", "running") for t in d["tasks"])
            item = {"id": d["id"], "name": d["name"], "status": d["status"],
                    "progress": f"{done}/{len(d['tasks'])}",
                    "created": d["created"]}
        except Exception as exc:
            item = {"id": jd.name, "name": "", "status": "broken",
                    "progress": "?", "created": "", "error": str(exc)}
        if wanted is not None and item["status"] not in wanted:
            continue
        out.append(item)
        if len(out) >= limit:
            break
    return out
>>>>>>> 新文
@@ 改 tools/gbatch.py
<<<<<<< 原文
def jobs(limit: int = 10) -> list:
    """最近的任务（新的在前），每个只给概要。"""
    if not JOBS.is_dir():
        return []
    out = []
    for jd in sorted(JOBS.iterdir(), reverse=True):
        if not (jd / "job.json").is_file():
            continue
        d = _settle(_load(jd.name))
        done = sum(t["status"] not in ("pending", "running") for t in d["tasks"])
        out.append({"id": d["id"], "name": d["name"], "status": d["status"],
                    "progress": f"{done}/{len(d['tasks'])}",
                    "created": d["created"]})
        if len(out) >= limit:
            break
    return out
=======
def jobs(limit: int = 10, status: str = None) -> list:
    """最近的任务（新的在前），每个只给概要；可按状态筛选。"""
    if not JOBS.is_dir():
        return []
    wanted = {s.strip() for s in status.split(",") if s.strip()} if status else None
    out = []
    for jd in sorted(JOBS.iterdir(), reverse=True):
        if not (jd / "job.json").is_file():
            continue
        try:
            d = _load(jd.name)
            if not isinstance(d, dict):
                raise ValueError("job.json 不是对象")
            missing = [k for k in ("id", "name", "status", "tasks", "created") if k not in d]
            if missing:
                raise ValueError(f"job.json 缺必需字段：{', '.join(missing)}")
            if not isinstance(d["tasks"], list) or any(
                    not isinstance(t, dict) or "status" not in t for t in d["tasks"]):
                raise ValueError("job.json 的 tasks 结构无效")
            d = _settle(d)
            done = sum(t["status"] not in ("pending", "running") for t in d["tasks"])
            item = {"id": d["id"], "name": d["name"], "status": d["status"],
                    "progress": f"{done}/{len(d['tasks'])}",
                    "created": d["created"]}
        except Exception as exc:
            item = {"id": jd.name, "name": "", "status": "broken",
                    "progress": "?", "created": "", "error": str(exc)}
        if wanted is not None and item["status"] not in wanted:
            continue
        out.append(item)
        if len(out) >= limit:
            break
    return out
>>>>>>> 新文

#清单
改 tools/cbatch.py:jobs
改 tools/gbatch.py:jobs