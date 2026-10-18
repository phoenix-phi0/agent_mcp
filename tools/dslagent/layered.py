"""newproj --layered：三级规划、一步步推进（旧 newproj.zs / newproj_split.zs 不动）。

三级规划（v2.run_newproj(layered=True) 调 run_with_cap()）：
  1 确认分层（模型 1 次，小）：{"模板","角色","规则","层"}；层从 实体/查询/接口/界面 里选（gen 增删改查由程序做，不算层）。校验不过带报错重写，共 ≤3 次。
  2 确认文件（模型 1 次，只列文件）：{"文件":[{层,路径,实体,作用,规则,依赖}]}；程序校验命名 / 路径唯一 / 每个实体都有实体文件 / 依赖方向 / 规则分配，共 ≤3 次；
    没有文件数上限。文件很多（> NEWPROJ_LAYERED_BATCH，默认 30）或这次列清单被杀 / 超长时改分批：先只列实体＋查询层，建完再列接口层（此时能看到真实的 sql），再列界面层。
  3 逐层、逐文件：实体 → 建库＋生成增删改查＋检查项目 → 查询 → 接口 → 界面，层内按清单顺序（校验保证依赖在前）。每个文件两步：
    a 单文件规划（模型，≤2 次）：输入 = 该文件项 + 分到的规则 + 项目里已真实存在的相关文件全文；输出该层的细化计划 JSON，程序校验引用必须真实存在
      （接口的 用sql 只能选已有 sql，缺的列「新sql」随本文件生成；界面的 用接口 只能选已有接口）；
    b 按计划生成（模型，≤2 次，接口有规则时另加规则核对 / 重写）：校验实体 / 名字参数与计划一致＋预编译sql / 检查项目＋校验角色＋参数核对＋核对规则 / 检查项目含 ui 解析失败。
  失败的文件撤回、记失败，依赖它的文件跳过（不调模型）；超长 / 被杀 = 该文件失败不终止；花费熔断（NEWPROJ_COST_CAP / --cost-cap）停在「部分成功：花费达上限」。
4 整体检查：检查项目 + 全部接口文件参数核对。
模型调用走 v2.Model（计数 / 墙钟 / 费用 / calls.json），不经 DSL 引擎，程序性检查直接调 verbs/newproj/defs 里的动词函数。
"""
import importlib.util
import json
import os
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
GROUPS = (("实体", "查询"), ("接口",), ("界面",))               # 分批时的批次
BATCH_ENV = "NEWPROJ_LAYERED_BATCH"
OVERFLOW = object()


class Halt(Exception):
    """整个运行停下（墙钟 / 总调用用完 / 花费熔断 / 后续批次清单不过）；文件级失败不走这条。"""

    def __init__(self, msg, kind="停"):
        super().__init__(msg)
        self.kind = kind


class FileFail(Exception):
    pass


class _Retry(Exception):
    """这次调用没有可用回复但不属于「直接判失败」：当作一次失败尝试，带原因重写。"""


def _prompt(name):
    return (PACK / "prompts" / name).read_text(encoding="utf-8").strip()


def model_system():
    return _prompt("sys_lmodel.md")


def batch_at():
    try:
        return max(1, int(os.environ.get(BATCH_ENV) or 30))
    except ValueError:
        return 30


def _load_verbs(project):
    """verbs/newproj/defs 里的动词函数（WORKSPACE 指向项目）+ 共用模块。"""
    sys.path.insert(0, str(DEFS))
    ns = {}
    for name in ("校验实体", "拆分隔块", "预编译sql", "生成增删改查", "检查项目", "项目摘要", "校验角色", "核对规则"):
        spec = importlib.util.spec_from_file_location("_layered_" + name, DEFS / f"{name}.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.WORKSPACE = Path(project)
        ns[name] = getattr(m, name)
    import _lstep
    import _params
    ns["_lstep"], ns["_params"] = _lstep, _params
    return ns


class Run:
    def __init__(self, M, task, project, stop_cls, cap=None):
        self.M, self.task, self.root, self.Stop, self.cap = M, task, Path(project), stop_cls, cap
        self.v = _load_verbs(project)
        self.S = self.v["_lstep"]
        self.k = 0
        self.recs, self.state = [], {}          # 文件 → rec
        self.steps = []                           # 分层确认 / 文件清单 各步的尝试记录
        self.layers = None                        # 第一步的结果
        self.files = []                           # 已接受的文件项（按列出顺序）
        self.mode, self.mode_why = "全量", ""
        self.paths, self.acts = {}, set()         # 已建好的定制接口：路径 → {动作, 入参, 文件, 实体}
        self.ifaces = {}                          # 接口文件 → 计划里的接口项
        self.sql_owner = {}                       # 定制 sql 名 → 所在文件
        self.p = {n: _prompt(f"sys_l{n}.md") for n in ("layer", "files", "fplan", "ent", "sql", "zs", "ui")}
        self.p["rule"] = _prompt("sys_frule.md")
        self.fatal = ""
        self.capped = False
        self.user_max = None
        self.base = 0
        self.bumped = 0

    # ------------------------------------------------------------ 调用预算
    def bump(self, n):
        """总调用上限随进度放宽：每确认一批文件按「规划 + 生成」最坏次数加；显式给的 max_calls 取较小值。"""
        self.base += n
        self.M.max_calls = min(self.user_max, self.base) if self.user_max else self.base

    @staticmethod
    def file_calls(item):
        return 2 + (2 + (4 if item["规则"] else 0) if item["层"] == "接口" else 2)

    # ------------------------------------------------------------ 模型调用
    def ask(self, prompt, rec=None):
        """一次模型调用 → 回复文本。花费熔断 / 总调用或墙钟用完 → Halt；没回应：超长 / 被杀 → FileFail，其它 → _Retry。"""
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
    def step(self, name, **kw):
        st = {"步骤": name, "文件": name, "尝试": 0, "调用": 0, **kw}
        self.steps.append(st)
        return st

    def new(self, layer, file, ent="", deps=()):
        rec = {"层": layer, "文件": file, "实体": ent, "结果": "未做", "规划尝试": 0, "生成尝试": 0, "重写": 0, "调用": 0,
               "失败原因": "", "未实现规则": [], "依赖": list(deps)}
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

    def write(self, rel, content):
        p = self.root / rel
        before = p.read_text(encoding="utf-8") if p.is_file() else None
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="")
        return (rel, before)

    def undo(self, saved):
        for rel, before in reversed(saved):
            p = self.root / rel
            if before is None:
                p.unlink(missing_ok=True)
            else:
                p.write_text(before, encoding="utf-8", newline="")

    def ent_text(self, names=None):
        d = self.root / "entities"
        fs = sorted(d.glob("*.entity")) if d.is_dir() else []
        return "\n\n".join(f.read_text(encoding="utf-8").strip() for f in fs if names is None or f.stem in names)

    def ok_ents(self):
        return {r["实体"] for r in self.recs if r["层"] == "实体" and r["结果"] == "通过"}

    def disk_sqls(self):
        """磁盘上真实存在的 sql：名 → [:参数…]。"""
        P = self.v["_params"]
        d = self.root / "queries"
        return {f.stem: P.sql_params(f.read_text(encoding="utf-8")) for f in sorted(d.glob("*.sql"))} if d.is_dir() else {}

    def sql_full(self, names):
        out = []
        for s in names:
            f = self.root / "queries" / f"{s}.sql"
            if f.is_file():
                out.append(f"-- queries/{s}.sql\n{f.read_text(encoding='utf-8').strip()}")
        return "\n".join(out) or "（无）"

    def sql_owner_file(self, sql):
        return self.sql_owner.get(sql) or f"entities/{sql.rsplit('_', 1)[0]}.entity"

    def rule_texts(self, nums):
        t = self.layers["规则表"]
        return [f"{h}：{t[h]}" for h in nums if h in t]

    def layers_view(self):
        L = self.layers
        return json.dumps({"模板": L["模板"], "角色": L["角色"], "层": L["层"], "规则": L["规则表"]}, ensure_ascii=False)

    def fplan_prompt(self, layer):
        t = self.p["fplan"]
        head, *secs = re.split(r"^## 层：", t, flags=re.M)
        for s in secs:
            if s.startswith(layer):
                return head.strip() + "\n## 层：" + s.strip()
        return head.strip()

    # ------------------------------------------------------------ 1 确认分层
    def make_layers(self):
        st = self.step("分层确认")
        self.bump(3)
        err = "无"
        for k in (1, 2, 3):
            st["尝试"] = k
            try:
                text = self.ask(f"{self.p['layer']}\n需求：{self.task}\n上次的报错：{err}", st)
            except (_Retry, FileFail) as e:
                err = str(e)
                continue
            r = self.S.validate_layers(text, self.task)
            if r["ok"]:
                self.layers = r
                return
            err = "；".join(r["errors"])
        self.fatal = f"分层确认三次都没过：{err}"

    # ------------------------------------------------------------ 2 确认文件
    def list_files(self, allow, final, name, detect_overflow=False):
        """列一批文件。返回本批文件项列表；失败返回 None（原因在 st["失败原因"]）；detect_overflow 时这次被杀 / 超长返回 OVERFLOW。"""
        st = self.step(name, 层=list(allow))
        self.bump(3)
        known = [{"层": f["层"], "路径": f["路径"], "实体": f["实体"], "作用": f["作用"], "结果": self.state[f["路径"]]["结果"] if f["路径"] in self.state else "未做"}
                 for f in self.files]
        extra = ""
        if self.recs:
            extra = "\n项目现状（真实存在的 sql 名(参数) / 接口 / 界面）：" + self.v["项目摘要"]({"含参数": "是"})["text"]
        err = "无"
        for k in (1, 2, 3):
            st["尝试"] = k
            try:
                text = self.ask(f"{self.p['files']}\n需求：{self.task}\n已确认分层：{self.layers_view()}\n本批只列这几层：{'、'.join(allow)}\n"
                                f"项目里已经有的文件（不要重复列）：{json.dumps(known, ensure_ascii=False) if known else '（无）'}{extra}\n上次的报错：{err}", st)
            except _Retry as e:
                err = str(e)
                continue
            except FileFail as e:
                if detect_overflow:
                    st["失败原因"] = str(e)
                    return OVERFLOW
                st["失败原因"] = str(e)
                return None
            r = self.S.validate_files(text, self.layers["层"], self.layers["规则表"], self.files, allow, final, self.layers["模板"])
            if r["ok"]:
                st["文件数"] = len(r["files"])
                return r["files"]
            err = "\n".join(r["errors"])
        st["失败原因"] = f"文件清单三次都没过：{err}"[:800]
        return None

    def accept(self, items):
        self.files += items
        self.bump(sum(self.file_calls(i) for i in items))

    # ------------------------------------------------------------ 3 逐层逐文件
    def build(self, layers):
        for layer in LAYERS:
            if layer not in layers or self.fatal:
                continue
            items = [f for f in self.files if f["层"] == layer and f["路径"] not in self.state]
            fn = {"实体": self.entities, "查询": self.queries, "接口": self.interfaces, "界面": self.uis}[layer]
            for it in items:
                rec = self.new(layer, it["路径"], it["实体"], it["依赖"])
                bad = self.bad_deps(rec)
                if bad:
                    rec.update(结果="跳过", 失败原因="依赖的文件没写成：" + "、".join(bad))
                    continue
                try:
                    fn(rec, it)
                except FileFail as e:
                    rec.update(结果="失败", 失败原因=str(e)[:600])
            if layer == "实体":
                self.gen()

    def file_plan(self, rec, layer, it, body, validate):
        """单文件规划：≤2 次，校验不过带报错重写。返回计划对象；两次不过抛 FileFail。"""
        err = "无"
        for k in (1, 2):
            rec["规划尝试"] = k
            try:
                text = self.ask(f"{self.fplan_prompt(layer)}\n需求：{self.task}\n本层：{layer}\n本文件项：{json.dumps(it, ensure_ascii=False)}\n"
                                f"分配的规则：{json.dumps(self.rule_texts(it['规则']), ensure_ascii=False)}\n{body}\n上次的报错：{err}", rec)
            except _Retry as e:
                err = str(e)
                continue
            plan, errs = validate(text)
            if not errs:
                return plan
            err = "；".join(errs)
        raise FileFail(f"单文件规划两次没过：{err}"[:600])

    def gen_loop(self, rec, attempt):
        """生成最多 2 次；attempt(err) 返回 None 表示通过，返回文本表示这次不过的原因。"""
        err = "无"
        for k in (1, 2):
            rec["生成尝试"] = k
            rec["重写"] = k - 1
            try:
                why = attempt(err)
            except _Retry as e:
                err = str(e)
                continue
            if why is None:
                rec["结果"] = "通过"
                return
            err = why
        raise FileFail(err[:600])

    # -- 实体
    def entities(self, rec, it):
        name, rel = it["实体"], it["路径"]
        from tools.entity import parse
        dep_ents = [Path(d).stem for d in it["依赖"] if d.endswith(".entity")]
        rel_text = self.ent_text(set(dep_ents)) or "（无）"
        ctx = f"已写好的被关联实体全文：{rel_text}"
        fp = self.file_plan(rec, "实体", it, ctx, lambda t: self.S.plan_entity(t, set(dep_ents)))

        def attempt(err):
            text = self.ask(f"{self.p['ent']}\n需求：{self.task}\n本文件：{rel}\n本文件项：{json.dumps(it, ensure_ascii=False)}\n单文件计划：{json.dumps(fp, ensure_ascii=False)}\n"
                            f"分配的规则：{json.dumps(self.rule_texts(it['规则']), ensure_ascii=False)}\n{ctx}\n上次的报错：{err}", rec)
            blk = self.v["拆分隔块"](text, rel, "是")
            if blk["ok"] != "是" or blk["n"] != 1:
                return blk.get("msg") or "要恰好一个实体文件块"
            body = blk["files"][0]["content"]
            try:
                names = [x.name for x in parse(body)]
            except Exception as ex:  # noqa: BLE001
                return f"实体解析失败：{ex}"
            if names != [name]:
                return f"这个文件只能定义实体 {name}，现在定义了 {names or '（没有）'}"
            v = self.v["校验实体"]((self.ent_text() + "\n\n" + body).strip(), self.layers["模板"], self.task, self.layers["角色模板"])
            if v["ok"] != "是":
                return v["errors"]
            self.write(rel, body)
            return None
        self.gen_loop(rec, attempt)

    def gen(self):
        if not self.ok_ents():
            self.fatal = "没有一个实体写成：" + "；".join(f"{r['文件']}：{r['失败原因']}" for r in self.recs if r["层"] == "实体")[:500]
            return
        g = self.v["生成增删改查"]({"项目目录": ".", "模板": self.layers["模板"], "角色": self.layers["角色"]})
        if g["ok"] != "是":
            self.fatal = f"生成增删改查不过：{g['msg']}"
            return
        b = self.v["检查项目"]({})
        if b["ok"] != "是":
            self.fatal = f"gen 生成的项目检查不过：{b['msg']}"

    # -- 查询
    def queries(self, rec, it):
        P = self.v["_params"]
        en, rel = it["实体"], it["路径"]
        rel_ents = {en} | {Path(d).stem for d in it["依赖"] if d.endswith(".entity")}
        ents = self.ent_text(rel_ents)
        taken = self.disk_sqls()
        ctx = f"实体全文：{ents}\n项目里已有的 sql 名：{sorted(taken)}"
        fp = self.file_plan(rec, "查询", it, ctx, lambda t: self.S.plan_query(t, en, it["规则"], set(taken)))
        want = {s["名"]: set(s["参数"]) for s in fp["sql"]}

        def attempt(err):
            text = self.ask(f"{self.p['sql']}\n需求：{self.task}\n本文件：{rel}\n本实体：{en}\n实体全文（本实体及关联实体）：{ents}\n单文件计划：{json.dumps(fp, ensure_ascii=False)}\n"
                            f"分配的规则：{json.dumps(self.rule_texts(it['规则']), ensure_ascii=False)}\n上次的报错：{err}", rec)
            blk = self.v["拆分隔块"](text, f"queries/{en}_*.sql|queries/{en}.sql", "是")
            if blk["ok"] != "是":
                return blk.get("msg") or "没有 sql 块"
            got = {Path(f["file"]).stem: set(P.sql_params(f["content"])) for f in blk["files"]}
            errs = []
            for n in want:
                if n not in got:
                    errs.append(f"计划里的 sql「{n}」没写")
                elif got[n] != want[n]:
                    errs.append(f"sql「{n}」的参数与计划不符：计划 {sorted(want[n])}，实际 {sorted(got[n])}")
            errs += [f"多写了计划里没有的 sql「{n}」" for n in got if n not in want]
            if errs:
                return "；".join(errs)
            c = self.v["预编译sql"](blk, self.ent_text())
            if c["ok"] != "是":
                return c["msg"]
            for f in blk["files"]:
                self.write(f["file"], f["content"])
            return None
        self.gen_loop(rec, attempt)
        for n in want:
            self.sql_owner[n] = rel

    # -- 接口
    def interfaces(self, rec, it):
        P = self.v["_params"]
        rel, en = it["路径"], it["实体"]
        taken = self.disk_sqls()
        dep_ents = {Path(d).stem for d in it["依赖"] if d.endswith(".entity")} | {en}
        gen = self.v["_lstep"].gen_sqls(dep_ents)
        focus = {s for s in taken if self.sql_owner_file(s) in it["依赖"] or s in gen}
        others = "；".join(f"{s}({','.join(p)})" for s, p in taken.items() if s not in focus) or "（无）"
        routes = self.v["项目摘要"]({"含参数": "是"})["routes"]
        taken_paths = set(self.paths) | {x["path"] for x in routes}
        taken_acts = set(self.acts) | {x["action"] for x in routes if x.get("action")}
        ctx = (f"相关实体全文：{self.ent_text(dep_ents)}\n已有 sql 全文（依赖文件和主实体的）：\n{self.sql_full(sorted(focus))}\n其它已有 sql 名(参数)：{others}\n"
               f"项目角色：{json.dumps(self.layers['角色'], ensure_ascii=False)}\n已被占用的接口路径：{sorted(taken_paths)}")
        fp = self.file_plan(rec, "接口", it, ctx, lambda t: self.S.plan_iface(t, en, it["规则"], self.layers["角色"], taken_paths, taken_acts, set(taken)))
        used = sorted({s for a in fp["接口"] for s in a["用sql"]})
        new_want = {s["名"]: set(s["参数"]) for s in fp["新sql"]}
        decl = {a["路径"]: a["入参"] for a in fp["接口"]}
        rules = self.rule_texts(it["规则"])
        ents = self.ent_text(dep_ents | {self.state[o]["实体"] for o in map(self.sql_owner_file, used) if o in self.state})
        sqltxt = self.sql_full([s for s in used if s in taken])
        state = {"saved": [], "first": None, "body": "", "merged": "", "unimpl": [], "rr": 0}
        pat = f"{rel}|queries/{en}_*.sql"

        def write_ok(err):
            """生成一次并写盘检查；通过返回 None。"""
            summary = self.v["项目摘要"]({"含参数": "是"})["text"]
            text = self.ask(f"{self.p['zs']}\n需求：{self.task}\n涉及的实体全文：{ents}\n本文件：{rel}\n单文件计划：{json.dumps(fp, ensure_ascii=False)}\n"
                            f"分配的规则：{json.dumps(rules, ensure_ascii=False)}\n项目角色：{json.dumps(self.layers['角色'], ensure_ascii=False)}\n"
                            f"用sql 里已有 sql 的全文：\n{sqltxt}\n全项目名字摘要：{summary}\n上次的报错：{err}", rec)
            blk = self.v["拆分隔块"](text, pat, "否")
            if blk["ok"] != "是":
                return blk.get("msg") or "没有分隔块"
            zs = [f for f in blk["files"] if f["file"] == rel]
            sq = [f for f in blk["files"] if f["file"] != rel]
            if len(zs) != 1:
                return f"要恰好一个 {rel} 块（现在 {len(zs)} 个）"
            got = {Path(f["file"]).stem: set(P.sql_params(f["content"])) for f in sq}
            errs = []
            for n in new_want:
                if n not in got:
                    errs.append(f"计划的新sql「{n}」没写（要 === queries/{n}.sql === 块）")
                elif got[n] != new_want[n]:
                    errs.append(f"新sql「{n}」的参数与计划不符：计划 {sorted(new_want[n])}，实际 {sorted(got[n])}")
            errs += [f"多写了计划里没有的 sql「{n}」" for n in got if n not in new_want]
            errs += [f"sql 文件名「{f['file']}」要是 queries/<名>.sql" for f in sq if f["file"] != f"queries/{Path(f['file']).stem}.sql"]
            if errs:
                return "；".join(errs)
            if sq:
                c = self.v["预编译sql"]({"files": sq}, self.ent_text())
                if c["ok"] != "是":
                    return c["msg"]
            body = zs[0]["content"]
            path = self.root / rel
            merged = (path.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + body) if path.is_file() else body      # routes/<实体>.zs 是 gen 的 CRUD 文件：追加不覆盖
            saved = [self.write(f["file"], f["content"]) for f in sq]
            saved.append(self.write(rel, merged))
            state["saved"] = saved
            b = self.v["检查项目"]({})
            if b["ok"] != "是":
                self.undo(saved)
                return b["msg"]
            rc = self.v["校验角色"]({"名": en, "接口": fp["接口"]})
            if rc["ok"] != "是":
                self.undo(saved)
                return rc["msg"]
            pe, _ = P.check_text(body, rel, self.root / "queries", decl, P.identity_vars(self.root))
            if pe:
                self.undo(saved)
                return "参数核对不过：" + "；".join(pe)
            state["body"], state["merged"] = body, merged
            return None

        # 语法 / 参数最多 2 次；有规则时核对不过再重写一轮（另算，最多 2 次）
        rr, rerr, done = 0, None, False
        try:
            while not done and rr < 2:
                rr += 1
                ok, err = False, rerr or "无"
                for _ in range(2):
                    rec["生成尝试"] += 1
                    rec["重写"] = max(0, rec["生成尝试"] - 1)
                    try:
                        why = write_ok(err)
                    except _Retry as e:
                        err = str(e)
                        continue
                    if why is None:
                        ok = True
                        break
                    err = why
                if not ok:
                    if rr > 1 and state["first"]:       # 规则重写这一轮语法两次不过：放回第一版（它过了检查），记未实现
                        saved = [self.write(f, c) for f, c in state["first"][0]]
                        state["unimpl"], done = state["first"][1], True
                        state["saved"] = saved
                        break
                    raise FileFail(err[:600])
                if not rules:
                    done = True
                    break
                try:
                    chk = self.ask(f"{self.p['rule']}\n规则：{json.dumps(rules, ensure_ascii=False)} 本功能sql：{self.sql_full(used)} zs全文：{state['body']}", rec)
                except (_Retry, FileFail):
                    done = True          # 核对不了不拿它当理由重写
                    break
                except Halt:
                    rec.update(结果="通过", 未核对规则=rules)       # 文件已过程序检查，只是规则没核对（熔断 / 预算用完）
                    self.register_iface(rec, it, fp)
                    raise
                rec["核对"] = rec.get("核对", 0) + 1
                cr = self.v["核对规则"](chk, {"规则": rules})
                if cr["ok"] == "是":
                    done = True
                elif rr < 2:
                    state["first"] = ([(f, (self.root / f).read_text(encoding="utf-8")) for f, _b in state["saved"]], cr["未实现列表"])
                    rerr = f"以下业务规则没有实现，请补全（其余规则别丢）：{cr['未实现']}"
                    self.undo(state["saved"])
                else:
                    state["unimpl"], done = cr["未实现列表"], True
        except FileFail:
            if state["saved"]:
                self.undo(state["saved"])
            raise
        rec.update(结果="通过", 未实现规则=state["unimpl"])
        self.register_iface(rec, it, fp)

    def register_iface(self, rec, it, fp):
        self.ifaces[it["路径"]] = fp["接口"]
        for a in fp["接口"]:
            self.paths[a["路径"]] = {"动作": a["动作"], "入参": a["入参"], "文件": it["路径"], "实体": it["实体"], "说明": a["说明"]}
            self.acts.add(a["动作"])
        for s in fp["新sql"]:
            self.sql_owner[s["名"]] = it["路径"]

    # -- 界面
    def uis(self, rec, it):
        rel = it["路径"]
        avail = set(self.paths) | {x["path"] for x in self.v["项目摘要"]({"含参数": "是"})["routes"]}
        ent_names = ({it["实体"]} if it["实体"] else set()) | {Path(d).stem for d in it["依赖"] if d.endswith(".entity")}
        for d in it["依赖"]:
            ent_names |= {x["实体"] for x in self.paths.values() if x["文件"] == d}
        ents = self.ent_text(ent_names)
        listing = [{"路径": p, **{k: v[k] for k in ("动作", "入参", "说明")}} for p, v in self.paths.items() if v["文件"] in it["依赖"]]
        ctx = (f"涉及的实体全文：{ents}\n已有接口（依赖文件里的）：{json.dumps(listing, ensure_ascii=False)}\n"
               f"全部可用接口路径（含 gen 自带的增删改查）：{sorted(avail)}")
        fp = self.file_plan(rec, "界面", it, ctx, lambda t: self.S.plan_ui(t, avail))
        used_paths = sorted({u for pg in fp["页面"] for u in pg["用接口"]})
        ents = self.ent_text(ent_names | ({p.strip("/").split("/")[0] for p in used_paths if p not in self.paths} & self.ok_ents()))
        info = []
        for p in used_paths:
            v = self.paths.get(p)
            info.append({"路径": p, "动作": v["动作"], "入参": v["入参"], "文件": v["文件"], "说明": v["说明"]} if v
                        else {"路径": p, "说明": "gen 自动生成的增删改查接口（动作名见全项目名字摘要）"})

        def attempt(err):
            summary = self.v["项目摘要"]({"含参数": "是"})["text"]
            text = self.ask(f"{self.p['ui']}\n需求：{self.task}\n涉及的实体全文：{ents}\n本文件：{rel}\n单文件计划：{json.dumps(fp, ensure_ascii=False)}\n"
                            f"用接口对应的接口/动作/入参：{json.dumps(info, ensure_ascii=False)}\n全项目名字摘要：{summary}\n上次的报错：{err}", rec)
            blk = self.v["拆分隔块"](text, rel, "是")
            if blk["ok"] != "是" or blk["n"] != 1:
                return blk.get("msg") or "要恰好一个文件块"
            saved = [self.write(rel, blk["files"][0]["content"])]
            b = self.v["检查项目"]({})
            if b["ok"] != "是":
                self.undo(saved)
                return b["msg"]
            return None
        self.gen_loop(rec, attempt)

    # ------------------------------------------------------------ 4 整体
    def final(self):
        problems = []
        b = self.v["检查项目"]({})
        if b["ok"] != "是":
            problems.append("整体检查不过：" + b["msg"])
        P = self.v["_params"]
        ident = P.identity_vars(self.root)
        for file, items in self.ifaces.items():
            r = self.state.get(file)
            f = self.root / file
            if r and r["结果"] == "通过" and f.is_file():
                pe, _ = P.check_text(f.read_text(encoding="utf-8"), file, self.root / "queries", {a["路径"]: a["入参"] for a in items}, ident)
                # gen 的 CRUD 在同一个文件里：只认本计划声明过路径的接口块
                problems += [x for x in pe if any(f"接口 {a['路径']}" in x for a in items)]
        return problems

    # ------------------------------------------------------------ 主流程
    def drive(self):
        L = self.layers["层"]
        groups = [[n for n in g if n in L] for g in GROUPS]
        groups = [g for g in groups if g]
        first = self.list_files(L, True, "文件清单（全量）", detect_overflow=len(groups) > 1)
        if first is None:
            self.fatal = next((s["失败原因"] for s in reversed(self.steps) if s.get("失败原因")), "文件清单没列成")
            return
        if first is OVERFLOW or (len(first) > batch_at() and len(groups) > 1):
            self.mode = "分批"
            self.mode_why = (f"全量清单 {len(first)} 个文件 > {batch_at()}" if first is not OVERFLOW else f"全量清单没列完（{self.steps[-1]['失败原因']}）") + "：改分批（先实体＋查询，建完再列接口，再列界面）"
            if first is OVERFLOW:
                first = self.list_files(groups[0], False, "文件清单（批1：实体＋查询）")
                if first is None:
                    self.fatal = self.steps[-1]["失败原因"]
                    return
            else:
                first = [f for f in first if f["层"] in groups[0]]
        else:
            groups = [L]
        self.accept(first)
        self.build(groups[0])
        for n, g in enumerate(groups[1:], 2):
            if self.fatal:
                return
            fs = self.list_files(g, g is groups[-1], f"文件清单（批{n}：{'＋'.join(g)}）")
            if fs is None:
                raise Halt(f"{'＋'.join(g)}层的文件清单没列成：{self.steps[-1]['失败原因']}", "清单")
            self.accept(fs)
            self.build(g)


def env_cap():
    """NEWPROJ_COST_CAP（美元，Claude 侧累计）；没设 / 0 / 不是数字 = 不限。"""
    try:
        return float(os.environ.get("NEWPROJ_COST_CAP") or 0) or None
    except ValueError:
        return None


def run_with_cap(M, task, project, stop_cls, cap=None, max_calls=None):
    """跑完整个三级流程，返回 {状态, 结论, 原因, 文件, 清单, 整体问题, 花费, codex调用}。不抛业务错误（Stop 在这里接住）。"""
    r = Run(M, task, project, stop_cls, cap)
    r.user_max = max_calls
    halt = None
    try:
        r.make_layers()
        if not r.fatal:
            r.drive()
    except Halt as h:
        halt = h
    problems = []
    if not r.fatal and r.layers and r.recs:
        try:
            problems = r.final()
        except Exception as e:  # noqa: BLE001
            problems = [f"整体检查出错：{type(e).__name__}: {e}"]
    if r.layers and halt:       # 被熔断 / 预算停下时，清单里还没建记录的文件记「未做」
        for f in r.files:
            if f["路径"] not in r.state:
                r.new(f["层"], f["路径"], f["实体"], f["依赖"])
    for rec in r.recs:
        if rec["结果"] == "未做" and halt:
            rec["失败原因"] = f"未做：{halt}"
    failed = [x["文件"] for x in r.recs if x["结果"] == "失败"]
    skipped = [x["文件"] for x in r.recs if x["结果"] == "跳过"]
    undone = [x["文件"] for x in r.recs if x["结果"] == "未做"]
    unimpl = {x["文件"]: x["未实现规则"] for x in r.recs if x["未实现规则"]}
    for x in r.recs:        # 规则核对时被熔断：未核对规则也要报出来
        if x.get("未核对规则"):
            unimpl.setdefault(x["文件"], []).extend(f"（未核对）{t}" for t in x["未核对规则"])
    lay = None
    if r.layers:
        lay = {"模板": r.layers["模板"], "角色": r.layers["角色"], "层": r.layers["层"], "规则数": len(r.layers["规则表"]), "文件数": len(r.files),
               "模式": r.mode, "分批原因": r.mode_why, "批次": [s for s in r.steps if s["步骤"].startswith("文件清单")], "调用上限": M.max_calls}
    out = {"文件": r.recs, "清单": lay, "步骤": r.steps, "整体问题": problems, "花费": round(M.cost, 4), "codex调用": sum(1 for c in M.log if c.get("engine") == "codex")}
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
