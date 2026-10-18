"""newproj --layered：先定分层 → 每层列文件 → 按层、逐实体、逐文件生成（旧 newproj.zs / newproj_split.zs 不动）。

流程（v2.run_newproj(layered=True) 调 run()）：
  1 分层清单（模型一次，校验分层清单 不过带报错重写 1 次）
  2 实体层：按关联拓扑序一个实体一个文件 entities/<实体>.entity（输入：清单、该实体项、已写好的被关联实体全文），逐个 校验实体；
    全部写完后 生成增删改查（建库）＋ 检查项目
  3 查询层：逐实体一次调用写该实体全部 queries/<实体>_*.sql（名字/参数与清单不符算不过）＋ 预编译sql
  4 接口层：逐个接口文件。输入含分配的规则、接口项、「用sql」涉及的 sql 全文、项目摘要。写盘 → 检查项目 → 校验角色 → 参数核对（程序）→ 核对规则（模型）
  5 界面层：逐个 .ui。输入含「用接口」对应的接口/动作/入参。写盘 → 检查项目（含 ui 解析失败）
  6 整体检查：检查项目 ＋ 全部接口文件再做一遍参数核对
每个文件单独重写 1 次（规则核对引起的另算 1 次）；两次不过 → 撤回该文件、记失败、依赖它的上层文件跳过并记原因、继续。
模型输出超长 / 被杀（rc=-9、空闲超时…）= 该文件失败（不重试），不终止整个运行。花费熔断：每次调用前看 Claude 侧累计花费，≥ NEWPROJ_COST_CAP 就不再调模型，
以「部分成功：花费达上限」结束并保留已写文件（codex 的花费记不出来，只记调用数）。
模型调用走 v2.Model（计数 / 墙钟 / 费用 / calls.json 逐次记录），不经 DSL 引擎，程序性检查直接调 verbs/newproj/defs 里的动词函数。
"""
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

from . import guard as G

PKG = Path(__file__).resolve().parent
PACK = PKG / "packs" / "newproj"
DEFS = PKG / "verbs" / "newproj" / "defs"
FAST_FAIL = (G.R_LONG, G.R_IDLE, G.R_FIRST, G.R_TOTAL)       # 这类失败重试大概率重蹈覆辙还多花钱：直接判该文件失败
LAYERS = ("实体", "查询", "接口", "界面")


class CostCap(Exception):
    pass


class Halt(Exception):
    """整个运行停下（墙钟 / 总调用用完 / 花费熔断）；文件级失败不走这条。"""

    def __init__(self, msg, kind="停"):
        super().__init__(msg)
        self.kind = kind


class FileFail(Exception):
    pass


def _prompt(name):
    return (PACK / "prompts" / name).read_text(encoding="utf-8").strip()


def model_system():
    return _prompt("sys_lmodel.md")


def _load_verbs(project):
    """verbs/newproj/defs 里的动词函数（WORKSPACE 指向项目）+ 两个共用模块。"""
    sys.path.insert(0, str(DEFS))
    ns = {}
    for name in ("校验实体", "拆分隔块", "预编译sql", "生成增删改查", "检查项目", "项目摘要", "校验角色", "核对规则"):
        spec = importlib.util.spec_from_file_location("_layered_" + name, DEFS / f"{name}.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.WORKSPACE = Path(project)
        ns[name] = getattr(m, name)
    import _layer
    import _params
    ns["_layer"], ns["_params"] = _layer, _params
    return ns


class Run:
    def __init__(self, M, task, project, stop_cls, cap=None, now=time.time):
        self.M, self.task, self.root, self.Stop, self.cap = M, task, Path(project), stop_cls, cap
        self.v = _load_verbs(project)
        self.k = 0
        self.recs = []
        self.state = {}          # 文件 → rec
        self.plan = None
        self.p = {n: _prompt(f"sys_l{n}.md") for n in ("plan", "ent", "sql", "zs", "ui")}
        self.p["rule"] = _prompt("sys_frule.md")
        self.fatal = ""
        self.capped = False
        self.user_max = None

    # ------------------------------------------------------------ 模型调用
    def ask(self, prompt, rec=None):
        """一次模型调用 → 回复文本。花费熔断 / 总调用或墙钟用完 → Halt；这次调用没回应（超长 / 被杀 / 空回复）→ FileFail 或带 retryable 的异常文本。"""
        if self.cap and self.M.cost >= self.cap:
            self.capped = True
            raise Halt(f"花费达上限（${self.M.cost:.2f} ≥ ${self.cap:.2f}）", "花费")
        self.k += 1
        try:
            r = self.M._call(model_system(), prompt, f"dsl{self.k:02d}")
        except self.Stop as e:
            raise Halt(str(e), "预算") from None
        if rec is not None:
            rec["调用"] = rec.get("调用", 0) + 1
        try:
            self.M.log[-1]["file"] = (rec or {}).get("文件", "")
        except IndexError:
            pass
        try:
            return self.M._text(r)
        except RuntimeError as e:
            why = getattr(e, "reason", "") or ""
            if why in FAST_FAIL or str(why).startswith("rc=-9"):
                raise FileFail(f"模型没有完成输出（{why}）") from None
            raise _Retry(str(e)) from None

    # ------------------------------------------------------------ 记录 / 文件
    def new(self, layer, file, ent="", deps=()):
        rec = {"层": layer, "文件": file, "实体": ent, "结果": "未做", "尝试": 0, "重写": 0, "调用": 0, "失败原因": "", "未实现规则": [], "依赖": list(deps)}
        self.recs.append(rec)
        self.state[file] = rec
        return rec

    def bad_deps(self, rec):
        out = []
        for d in rec["依赖"]:
            r = self.state.get(d)
            if r is not None and r["结果"] != "通过":
                out.append(f"{d}（{r['结果']}）")
        return out

    def skip(self, rec, why):
        rec.update(结果="跳过", 失败原因=why)

    def write(self, rel, content):
        p = self.root / rel
        before = p.read_text(encoding="utf-8") if p.is_file() else None
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="")
        return (rel, before)

    def undo(self, saved):
        for rel, before in saved:
            p = self.root / rel
            if before is None:
                p.unlink(missing_ok=True)
            else:
                p.write_text(before, encoding="utf-8", newline="")

    def ent_text(self, names=None):
        d = self.root / "entities"
        fs = sorted(d.glob("*.entity")) if d.is_dir() else []
        return "\n\n".join(f.read_text(encoding="utf-8").strip() for f in fs if names is None or f.stem in names)

    def plan_view(self):
        p = self.plan
        return json.dumps({"模板": p["模板"], "角色": p["角色"], "规则": p["规则表"], "实体": p["实体"], "查询": p["查询"],
                           "接口": p["接口"], "界面": p["界面"]}, ensure_ascii=False)

    def rule_texts(self, nums):
        return [f"{h}：{self.plan['规则表'][h]}" for h in nums if h in self.plan["规则表"]]

    # ------------------------------------------------------------ 1 清单
    def make_plan(self):
        err, last = "无", ""
        for i in range(2):
            try:
                text = self.ask(f"{self.p['plan']}\n需求：{self.task}\n上次的报错：{err}")
            except _Retry as e:
                err = str(e)
                continue
            except FileFail as e:
                err = str(e)
                continue
            r = self.v["_layer"].validate(text, self.task)
            if r["ok"]:
                self.plan = r
                self.M.max_calls = min(self.user_max, r["调用上限"]) if self.user_max else r["调用上限"]
                return
            err = "；".join(r["errors"])
        self.fatal = f"分层清单两次都没过：{err}"

    # ------------------------------------------------------------ 2 实体
    def entities(self):
        p = self.plan
        from tools.entity import parse
        for e in p["实体"]:
            name = e["名"]
            rel = f"entities/{name}.entity"
            rec = self.new("实体", rel, name, [f"entities/{d}.entity" for d in e["关联"]])
            bad = self.bad_deps(rec)
            if bad:
                self.skip(rec, "依赖的实体没写成：" + "、".join(bad))
                continue
            rel_text = self.ent_text(set(e["关联"])) or "（无）"
            err = "无"
            for k in (1, 2):
                rec["尝试"] = k
                rec["重写"] = k - 1
                try:
                    text = self.ask(f"{self.p['ent']}\n需求：{self.task}\n分层清单：{self.plan_view()}\n本实体：{json.dumps(e, ensure_ascii=False)}\n"
                                    f"已写好的被关联实体全文：{rel_text}\n上次的报错：{err}", rec)
                except _Retry as ex:
                    err = str(ex)
                    continue
                except FileFail as ex:
                    err = str(ex)
                    break
                blk = self.v["拆分隔块"](text, rel, "是")
                if blk["ok"] != "是" or blk["n"] != 1:
                    err = blk.get("msg") or "要恰好一个实体文件块"
                    continue
                body = blk["files"][0]["content"]
                try:
                    names = [x.name for x in parse(body)]
                except Exception as ex:  # noqa: BLE001
                    err = f"实体解析失败：{ex}"
                    continue
                if names != [name]:
                    err = f"这个文件只能定义实体 {name}，现在定义了 {names or '（没有）'}"
                    continue
                full = (self.ent_text() + "\n\n" + body).strip()
                v = self.v["校验实体"](full, p["模板"], self.task, p["角色模板"])
                if v["ok"] != "是":
                    err = v["errors"]
                    continue
                self.write(rel, body)
                rec["结果"] = "通过"
                break
            if rec["结果"] != "通过":
                rec.update(结果="失败", 失败原因=err[:600])

    def gen(self):
        ok_ents = [r for r in self.recs if r["层"] == "实体" and r["结果"] == "通过"]
        if not ok_ents:
            self.fatal = "没有一个实体写成：" + "；".join(f"{r['文件']}：{r['失败原因']}" for r in self.recs if r["层"] == "实体")[:500]
            return
        g = self.v["生成增删改查"]({"项目目录": ".", "模板": self.plan["模板"], "角色": self.plan["角色"]})
        if g["ok"] != "是":
            self.fatal = f"生成增删改查不过：{g['msg']}"
            return
        b = self.v["检查项目"]({})
        if b["ok"] != "是":
            self.fatal = f"gen 生成的项目检查不过：{b['msg']}"

    # ------------------------------------------------------------ 3 查询
    def queries(self):
        P = self.v["_params"]
        for q in self.plan["查询"]:
            if not q["sql"]:
                continue
            en = q["实体"]
            rel = f"queries/{en}_*.sql"
            rec = self.new("查询", rel, en, [f"entities/{en}.entity"])
            bad = self.bad_deps(rec)
            if bad:
                self.skip(rec, "依赖的实体没写成：" + "、".join(bad))
                continue
            ent = next(e for e in self.plan["实体"] if e["名"] == en)
            want = {s["名"]: set(s["参数"]) for s in q["sql"]}
            ents = self.ent_text({en, *ent["关联"]})
            err = "无"
            for k in (1, 2):
                rec["尝试"] = k
                rec["重写"] = k - 1
                try:
                    text = self.ask(f"{self.p['sql']}\n需求：{self.task}\n本实体：{en}\n实体全文（本实体及关联实体）：{ents}\n本实体要写的 sql 清单：{json.dumps(q['sql'], ensure_ascii=False)}\n"
                                    f"分配的规则：{json.dumps(self.rule_texts(q['规则']), ensure_ascii=False)}\n上次的报错：{err}", rec)
                except _Retry as ex:
                    err = str(ex)
                    continue
                except FileFail as ex:
                    err = str(ex)
                    break
                blk = self.v["拆分隔块"](text, f"queries/{en}_*.sql|queries/{en}.sql", "是")
                if blk["ok"] != "是":
                    err = blk.get("msg") or "没有 sql 块"
                    continue
                got = {Path(f["file"]).stem: set(P.sql_params(f["content"])) for f in blk["files"]}
                errs = []
                for n in want:
                    if n not in got:
                        errs.append(f"清单里的 sql「{n}」没写")
                    elif got[n] != want[n]:
                        errs.append(f"sql「{n}」的参数与清单不符：清单 {sorted(want[n])}，实际 {sorted(got[n])}")
                errs += [f"多写了清单里没有的 sql「{n}」" for n in got if n not in want]
                if errs:
                    err = "；".join(errs)
                    continue
                c = self.v["预编译sql"](blk, self.ent_text())
                if c["ok"] != "是":
                    err = c["msg"]
                    continue
                for f in blk["files"]:
                    self.write(f["file"], f["content"])
                rec["结果"] = "通过"
                break
            if rec["结果"] != "通过":
                rec.update(结果="失败", 失败原因=err[:600])

    # ------------------------------------------------------------ 4 接口
    def sql_owner_file(self, sql):
        en = self.plan["sql归属"].get(sql)
        if en:
            return f"queries/{en}_*.sql"
        return f"entities/{sql.rsplit('_', 1)[0]}.entity"

    def interfaces(self):
        P, L = self.v["_params"], self.v["_layer"]
        for it in self.plan["接口"]:
            rel, en = it["文件"], it["实体"]
            used = sorted({s for a in it["接口"] for s in a["用sql"]})
            rec = self.new("接口", rel, en, [f"entities/{en}.entity"] + sorted({self.sql_owner_file(s) for s in used}))
            bad = self.bad_deps(rec)
            if bad:
                self.skip(rec, "依赖的文件没写成：" + "、".join(bad))
                continue
            self.interface_file(rec, it, used, P)

    def interface_file(self, rec, it, used, P):
        rel, en = it["文件"], it["实体"]
        rules = self.rule_texts(it["规则"])
        decl = {a["路径"]: a["入参"] for a in it["接口"]}
        sqltxt = "\n".join(f"-- queries/{s}.sql\n{(self.root / 'queries' / (s + '.sql')).read_text(encoding='utf-8').strip()}" for s in used
                           if (self.root / "queries" / f"{s}.sql").is_file()) or "（无）"
        ent_names = {en, *[self.plan["sql归属"].get(s) or s.rsplit("_", 1)[0] for s in used]}
        ents = self.ent_text(ent_names)
        saved, first = None, None
        syn, rr, err, unimpl, rerr = 0, 0, "无", [], None
        done, fail = False, ""
        while not done and rr < 2:
            rr += 1
            err = rerr or "无"
            ok = False
            for _ in range(2):
                syn += 1
                rec["尝试"] = syn
                rec["重写"] = max(0, syn - 1)
                try:
                    summary = self.v["项目摘要"]({"含参数": "是"})["text"]
                    text = self.ask(f"{self.p['zs']}\n需求：{self.task}\n涉及的实体全文：{ents}\n本文件：{rel}\n接口项：{json.dumps(it['接口'], ensure_ascii=False)}\n"
                                    f"分配的规则：{json.dumps(rules, ensure_ascii=False)}\n项目角色：{json.dumps(self.plan['角色'], ensure_ascii=False)}\n"
                                    f"用sql 涉及的 sql 全文：\n{sqltxt}\n全项目名字摘要：{summary}\n上次的报错：{err}", rec)
                except _Retry as ex:
                    err = str(ex)
                    continue
                except FileFail as ex:
                    fail = str(ex)
                    break
                blk = self.v["拆分隔块"](text, rel, "否")
                if blk["ok"] != "是" or blk["n"] != 1:
                    err = blk.get("msg") or "要恰好一个文件块"
                    continue
                body = blk["files"][0]["content"]
                path = self.root / rel
                merged = (path.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + body) if path.is_file() else body     # routes/<实体>.zs 是 gen 的 CRUD 文件：追加不覆盖
                saved = [self.write(rel, merged)]
                b = self.v["检查项目"]({})
                if b["ok"] != "是":
                    err = b["msg"]
                    self.undo(saved)
                    continue
                rc = self.v["校验角色"]({"名": en, "接口": it["接口"]})
                if rc["ok"] != "是":
                    err = rc["msg"]
                    self.undo(saved)
                    continue
                pe, n = P.check_text(body, rel, self.root / "queries", decl, P.identity_vars(self.root))
                if pe:
                    err = "参数核对不过：" + "；".join(pe)
                    self.undo(saved)
                    continue
                ok = True
                break
            if fail:
                break
            if not ok:
                if rr > 1 and first:        # 规则重写这一轮语法两次不过：放回第一版（它过了检查），记未实现
                    self.write(first[0], first[1])
                    unimpl, done = first[2], True
                else:
                    fail = err
                break
            if not rules:
                done = True
                break
            try:
                chk = self.ask(f"{self.p['rule']}\n规则：{json.dumps(rules, ensure_ascii=False)} 本功能sql：{sqltxt} zs全文：{body}", rec)
            except (_Retry, FileFail):
                done = True        # 核对不了不拿它当理由重写
                break
            except Halt:
                rec.update(结果="通过", 未核对规则=rules)      # 文件已过程序检查，只是规则没核对（熔断 / 预算用完）
                raise
            rec["核对"] = rec.get("核对", 0) + 1
            cr = self.v["核对规则"](chk, {"规则": rules})
            if cr["ok"] == "是":
                done = True
            elif rr < 2:
                first = (rel, merged, cr["未实现列表"])
                rerr = f"以下业务规则没有实现，请补全（其余规则别丢）：{cr['未实现']}"
                self.undo(saved)
            else:
                unimpl, done = cr["未实现列表"], True
        if fail or not done:
            if saved:
                self.undo(saved)
            rec.update(结果="失败", 失败原因=(fail or err)[:600])
            return
        rec.update(结果="通过", 未实现规则=unimpl)

    # ------------------------------------------------------------ 5 界面
    def uis(self):
        pl = self.plan
        for u in pl["界面"]:
            rel = u["文件"]
            deps = []
            if u["实体"]:
                deps.append(f"entities/{u['实体']}.entity")
            for path in u["用接口"]:
                f = pl["路径归属"].get(path)
                deps.append(f if f else f"entities/{path.strip('/').split('/')[0]}.entity")
            rec = self.new("界面", rel, u["实体"], sorted(set(deps)))
            bad = self.bad_deps(rec)
            if bad:
                self.skip(rec, "依赖的文件没写成：" + "、".join(bad))
                continue
            info = []
            for path in u["用接口"]:
                f = pl["路径归属"].get(path)
                if f:
                    for it in pl["接口"]:
                        for a in it["接口"]:
                            if a["路径"] == path:
                                info.append({"路径": path, "动作": a["动作"], "入参": a["入参"], "文件": f, "说明": a["说明"]})
                else:
                    info.append({"路径": path, "说明": "gen 自动生成的增删改查接口（动作名见全项目名字摘要）"})
            en_set = {u["实体"]} if u["实体"] else set()
            en_set |= {p.strip("/").split("/")[0] for p in u["用接口"] if p not in pl["路径归属"]}
            for p in u["用接口"]:
                f = pl["路径归属"].get(p)
                if f:
                    en_set.add(next(it["实体"] for it in pl["接口"] if it["文件"] == f))
            ents = self.ent_text(en_set)
            err = "无"
            for k in (1, 2):
                rec["尝试"] = k
                rec["重写"] = k - 1
                try:
                    summary = self.v["项目摘要"]({"含参数": "是"})["text"]
                    text = self.ask(f"{self.p['ui']}\n需求：{self.task}\n涉及的实体全文：{ents}\n本文件：{rel}\n界面项：{json.dumps(u, ensure_ascii=False)}\n"
                                    f"用接口对应的接口/动作/入参：{json.dumps(info, ensure_ascii=False)}\n全项目名字摘要：{summary}\n上次的报错：{err}", rec)
                except _Retry as ex:
                    err = str(ex)
                    continue
                except FileFail as ex:
                    err = str(ex)
                    break
                blk = self.v["拆分隔块"](text, rel, "是")
                if blk["ok"] != "是" or blk["n"] != 1:
                    err = blk.get("msg") or "要恰好一个文件块"
                    continue
                saved = [self.write(rel, blk["files"][0]["content"])]
                b = self.v["检查项目"]({})
                if b["ok"] != "是":
                    err = b["msg"]
                    self.undo(saved)
                    continue
                rec["结果"] = "通过"
                break
            if rec["结果"] != "通过":
                rec.update(结果="失败", 失败原因=err[:600])

    # ------------------------------------------------------------ 6 整体
    def final(self):
        problems = []
        b = self.v["检查项目"]({})
        if b["ok"] != "是":
            problems.append("整体检查不过：" + b["msg"])
        P = self.v["_params"]
        ident = P.identity_vars(self.root)
        for it in self.plan["接口"]:
            r = self.state.get(it["文件"])
            if r and r["结果"] == "通过":
                f = self.root / it["文件"]
                if f.is_file():
                    pe, _ = P.check_text(f.read_text(encoding="utf-8"), it["文件"], self.root / "queries",
                                         {a["路径"]: a["入参"] for a in it["接口"]}, ident)
                    # gen 的 CRUD 在同一个文件里：只认本清单声明过路径的接口块
                    problems += [x for x in pe if any(f"接口 {a['路径']}" in x for a in it["接口"])]
        return problems


class _Retry(Exception):
    """这次调用没有可用回复但不属于「直接判文件失败」：当作本文件的一次失败尝试，带原因重写。"""


def env_cap():
    """NEWPROJ_COST_CAP（美元，Claude 侧累计）；没设 / 0 / 不是数字 = 不限。"""
    import os
    try:
        return float(os.environ.get("NEWPROJ_COST_CAP") or 0) or None
    except ValueError:
        return None


def run_with_cap(M, task, project, stop_cls, cap=None, max_calls=None):
    """跑完整个分层流程，返回 {状态, 结论, 原因, 文件, 清单, 整体问题, 花费, codex调用}。不抛业务错误（Stop 在这里接住）。"""
    r = Run(M, task, project, stop_cls, cap)
    r.user_max = max_calls
    halt = None
    try:
        r.make_plan()
        if not r.fatal:
            r.entities()
            r.gen()
        if not r.fatal:
            r.queries()
            r.interfaces()
            r.uis()
    except Halt as h:
        halt = h
    problems = []
    if not r.fatal and r.plan:
        try:
            problems = r.final()
        except Exception as e:  # noqa: BLE001
            problems = [f"整体检查出错：{type(e).__name__}: {e}"]
    for rec in r.recs:
        if rec["结果"] == "未做" and halt:
            rec["失败原因"] = f"未做：{halt}"
    if r.plan and halt:       # 被熔断 / 预算停下时，后面几层还没建记录
        have = {x["文件"] for x in r.recs}
        for it in r.plan["查询"]:
            if it["sql"] and f"queries/{it['实体']}_*.sql" not in have:
                r.new("查询", f"queries/{it['实体']}_*.sql", it["实体"]).update(失败原因=f"未做：{halt}")
        for it in r.plan["接口"]:
            if it["文件"] not in have:
                r.new("接口", it["文件"], it["实体"]).update(失败原因=f"未做：{halt}")
        for u in r.plan["界面"]:
            if u["文件"] not in have:
                r.new("界面", u["文件"], u["实体"]).update(失败原因=f"未做：{halt}")
    failed = [x["文件"] for x in r.recs if x["结果"] == "失败"]
    skipped = [x["文件"] for x in r.recs if x["结果"] == "跳过"]
    undone = [x["文件"] for x in r.recs if x["结果"] == "未做"]
    unimpl = {x["文件"]: x["未实现规则"] for x in r.recs if x["未实现规则"]}
    out = {"文件": r.recs, "清单": ({"模板": r.plan["模板"], "角色": r.plan["角色"], "文件数": r.plan["数量"], "调用上限": r.plan["调用上限"]} if r.plan else None),
           "整体问题": problems, "花费": round(M.cost, 4), "codex调用": sum(1 for c in M.log if c.get("engine") == "codex")}
    if r.fatal:
        out.update(状态="失败", 结论="失败", 原因=r.fatal)
    elif halt and halt.kind == "花费":
        out.update(状态="失败", 结论="部分成功", 原因=f"部分成功：花费达上限（${M.cost:.2f}，NEWPROJ_COST_CAP={cap}）；已写文件保留；没做：{'、'.join(undone) or '无'}；失败：{'、'.join(failed) or '无'}")
    elif halt:
        some = any(x["结果"] == "通过" for x in r.recs)
        out.update(状态="失败", 结论="部分成功" if some else "失败",
                   原因=f"{'部分成功' if some else '失败'}：{halt}；没做：{'、'.join(undone) or '无'}；失败：{'、'.join(failed) or '无'}")
    elif failed or skipped or unimpl or problems:
        parts = []
        if failed:
            parts.append("失败的文件：" + "、".join(failed))
        if skipped:
            parts.append("因依赖失败跳过：" + "、".join(skipped))
        if unimpl:
            parts.append("规则没全部实现：" + "；".join(f"{k} {v}" for k, v in unimpl.items()))
        if problems:
            parts.append("；".join(problems)[:400])
        out.update(状态="失败", 结论="部分成功", 原因="部分成功：" + "；".join(parts))
    else:
        out.update(状态="成功", 结论="成功", 原因="")
    return out
