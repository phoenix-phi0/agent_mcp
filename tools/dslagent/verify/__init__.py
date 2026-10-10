"""验收（verify）：v2 规划核心按任务类型插拔的「验收 / 补改」那一半。选择：环境变量 DSLAGENT_VERIFY，缺省跟随 DSLAGENT_PACK
（再缺省 code）。目前只有 code（全量测试、清单核对、残留检查、边界复核、补改入参组装）。

接口（模块级名字）：
  NAME                  str，取值名。
  detect_cmd(project, given) -> str|None   验收要用的命令（code：测试命令；given 优先，探测不到给 None）。
  MISSING_MSG           str，detect_cmd 给 None 时判失败的原因。
  setup(out, cmd)       计划执行前设好验收要的环境（code：测试命令 / 超时的环境变量）。
  check(project, plan_result, checklist) -> dict
      验收一次。plan_result：{"task": 任务原文, "base": 开局快照, "cur": 当前快照, "main": 计划主脚本, "tests": 计划内
      测试记录（可复用，引擎和验收共用同一个 list）, "accept": 验收记录（check 往里写字段）, "test_cmd", "stage":
      "验收" | "补改后"（补改后的复核不再组补改入参）}；checklist：计划 #清单 解出的 {"items": [(操作, 路径, 位置)]}。
      出参：{"通过": bool, "缺口列表": [{"说明": ...}], "补改入参": 给补改调用的 user 文本（通过 / 补改后复核时为 None）,
             "补改系统": 补改调用的 system 提示, "原因": 没通过时的失败原因, "测试摘要": str}
  fix(M, project, chk, tag="fix") -> dict   用 check 的出参派 1 次补改（回复不合格重答 1 次、能套就套），返回补改记录。
  boundary(M, project, plan_result) -> {"状态", "原因"}   可选：验收通过后的边界复核（M 模型调用；plan_result 另含 "out" 任务目录、
      "bound" 边界记录 dict，函数往里写）。没有这个名字就跳过、按成功处理。

以后加「文档」「数据」类验收要实现的：detect_cmd / MISSING_MSG / setup / check / fix（boundary 可不实现）。check 里按任务类型核对
（文档：清单里的章节都在、引用都解析得开；数据：行数 / 校验和 / 约束），把缺口写成「说明」，补改入参自己组装。
"""
import importlib
import os

REGISTRY = {"code": "tools.dslagent.verify.code"}
DEFAULT = "code"


def available():
    return sorted(REGISTRY)


def pick(name):
    """按取值拿验收模块；不认识的名字报 ValueError（列出可用的）。"""
    n = (name or "").strip().lower()
    if not n:
        n = DEFAULT
    if n not in REGISTRY:
        raise ValueError(f"DSLAGENT_VERIFY 取值不对：{name!r}，可用：{'、'.join(available())}")
    return importlib.import_module(REGISTRY[n])


def current():
    """DSLAGENT_VERIFY 选的验收；没设就跟随 DSLAGENT_PACK（packs.pick 校验）。"""
    v = (os.environ.get("DSLAGENT_VERIFY") or "").strip()
    if v:
        return pick(v)
    from .. import packs
    packs.pick(os.environ.get("DSLAGENT_PACK"))          # 跟随时先校验 PACK
    return pick((os.environ.get("DSLAGENT_PACK") or "").strip().lower() or None)
