# -*- coding: utf-8 -*-
"""模型调用那一组：问、问JSON、流式、对话、挂载文件、带工具。

从 dsl.py 拆出来的第二块，做成 mixin 混进 DSLEngine。

## 为什么用 mixin 而不是独立的类

这些方法离不开引擎状态——`self.client`、`self.system`、`self.temperature`、
`self.history`、`self.verbs`、`self._emit`、`self.expand`。做成独立的类
就要把这七样传来传去，或者反过来持有引擎的引用，那跟 mixin 是同一件事，
只是多绕一道。

代价是隐式依赖：这个文件里的方法用到的 self.xxx，定义在 dsl.py 里。
改那边的属性名要记得搜这边。下面的 REQUIRES 列出全部依赖，改属性时
照着查。

## 依赖的引擎属性和方法

    self.client         ZhipuClient（或假客户端）
    self.system         系统提示词
    self.temperature
    self.model          「模型 X」设的模型，None 用客户端默认
    self.history        对话历史
    self.verbs          动词表
    self.vars           变量表（store 写）
    self._depth         嵌套深度，工具调脚本动词时要判
    self._last_result   逐项块的自动输出

    self.expand()       变量插值
    self.store()        写变量
    self._emit()        输出一行
    self._safe_path()   路径越界检查
    self._rel()         显示用的相对路径
    self._eval_against() 重试的条件判断
    self._sub_engine()  脚本动词起子引擎
"""

import inspect
import json
import re as _re
from pathlib import Path

from . import config
from .dsl_core import (ATTACH_RE, DEFAULT_TOOL_ROUNDS, DSLError,
                       MAX_CALL_DEPTH, MODEL_ID_RE, MODEL_RE, RETRY_RE,
                       TOOLS_RE, UNEXPANDED_RE, to_text)


# ----------------------------------------------------------------------
# 问JSON 的「格式」后缀：问JSON r = 提示词 格式 action:合格|重做 note?:文本 重问 3 次
#
# 只认语句末尾、「格式」后面每个词都是「名字:类型」的情况，否则「格式」两个字
# 当提示词正文。在展开之前的原文上认，变量的值里有「格式 a:b」不影响。
# ----------------------------------------------------------------------

FORMAT_RE = _re.compile(r"\s+格式((?:\s+\S+)+?)(?:\s+重问\s+(\d+)\s*次)?\s*$")
FIELD_RE = _re.compile(r"^([^\s:?]+)(\?)?:(\S+)$")
FORMAT_TYPES = ("文本", "数字", "是否", "列表")
DEFAULT_REASKS = 2
MAX_REASKS = 5
_BAD_JSON = object()        # 解析不了的标记，跟 JSON 里的 null 区分开
_REASK = ("你上次的回复不符合要求：{}。请改正后重新输出：只输出一个 JSON 对象，"
          "不要代码围栏，不要任何解释。")


def _split_format(rest: str, lineno: int):
    """剥「格式 …」后缀，返回 (剩下的, 字段表或 None, 重问次数)。

    字段表是 [(名字, 可选, 类型, 枚举值列表或 None)]。多个「格式」时从最右边
    那个起认；类型写错（像格式却认不出）直接报错，不静默当提示词。
    """
    starts = [i.start() for i in _re.finditer(r"\s+格式\s", rest)]
    for start in reversed(starts):
        m = FORMAT_RE.match(rest, start)
        if not m or not rest[:start].strip():
            continue
        tokens = m.group(1).split()
        fields = [FIELD_RE.match(t) for t in tokens]
        if not all(f and f.group(1).isidentifier() for f in fields):
            continue
        spec = []
        for f in fields:
            kind = f.group(3)
            options = None
            if "|" in kind:
                options = [o.strip() for o in kind.split("|")]
                if not all(options):
                    raise DSLError(f"第 {lineno + 1} 行：「格式」里 {f.group(1)} "
                                   f"的可选值有空的：{kind}")
                kind = "枚举"
            elif kind not in FORMAT_TYPES:
                raise DSLError(f"第 {lineno + 1} 行：「格式」里 {f.group(1)} 的类型"
                               f"「{kind}」不认识，只能是 文本 数字 是否 列表 "
                               f"或 A|B|C")
            spec.append((f.group(1), bool(f.group(2)), kind, options))
        reasks = DEFAULT_REASKS
        if m.group(2) is not None:
            reasks = int(m.group(2))
            if reasks > MAX_REASKS:
                raise DSLError(f"第 {lineno + 1} 行：「重问 {reasks} 次」最多 "
                               f"{MAX_REASKS} 次")
        return rest[:start], spec, reasks
    return rest, None, 0


_KIND_DESC = {"文本": "文本（非空字符串）", "数字": "数字",
              "是否": "是否（true 或 false）", "列表": "列表（JSON 数组）"}
_KIND_SAMPLE = {"文本": "……", "数字": 0, "是否": True, "列表": ["……"]}


def _format_note(spec: list) -> str:
    """附在提示词末尾的格式说明：字段、类型、可选值，加一个示例。"""
    lines = ["", "", "输出格式：只输出一个 JSON 对象，不要代码围栏，不要任何解释。字段："]
    sample = {}
    for name, optional, kind, options in spec:
        desc = ("只能是 " + "、".join(f"\"{o}\"" for o in options) + " 之一"
                if options else _KIND_DESC[kind])
        if optional:
            desc += "；可选，没有就不写这个字段"
        lines.append(f"- {name}：{desc}")
        sample[name] = options[0] if options else _KIND_SAMPLE[kind]
    lines.append("示例：" + json.dumps(sample, ensure_ascii=False))
    return "\n".join(lines)


def _show(value) -> str:
    text = to_text(value) if value is not None else "null"
    return text if len(text) <= 50 else text[:50] + "…"


def _check_format(data, spec: list):
    """按字段表查一遍，返回 (规范化后的对象, 问题列表)。只查顶层，多余字段留着。"""
    if data is _BAD_JSON:
        return None, ["回复不是合法 JSON"]
    if not isinstance(data, dict):
        what = "列表" if isinstance(data, list) else "字符串或其他值"
        return None, [f"回复应该是一个 JSON 对象，你回的是{what}"]
    out, problems = dict(data), []
    for name, optional, kind, options in spec:
        v = data.get(name)
        if optional and (v is None or isinstance(v, str) and not v.strip()):
            # 可选字段 null / 缺失 / 空串 / 纯空白都算「没给」：不算错，去掉这个键
            out.pop(name, None)
            continue
        if v is None:
            problems.append(f"缺少字段 {name}")
            continue
        if kind == "文本":
            if isinstance(v, str) and v.strip():
                continue
            problems.append(f"{name} 应该是非空的文本，你回了 {_show(v)}")
        elif kind == "数字":
            n = _as_number(v)
            if n is None:
                problems.append(f"{name} 应该是数字，你回了 {_show(v)}")
            else:
                out[name] = n
        elif kind == "是否":
            b = _as_bool(v)
            if b is None:
                problems.append(f"{name} 应该是 true 或 false，你回了 {_show(v)}")
            else:
                out[name] = b
        elif kind == "列表":
            if not isinstance(v, list):
                problems.append(f"{name} 应该是列表（JSON 数组），你回了 {_show(v)}")
        else:
            s = to_text(v).strip() if not isinstance(v, (dict, list)) else None
            if s in options:
                out[name] = s
            else:
                problems.append(f"{name} 只能是 {_or(options)}，你回了 {_show(v)}")
    return out, problems


def _or(options: list) -> str:
    return options[0] if len(options) == 1 else \
        "、".join(options[:-1]) + " 或 " + options[-1]


def _as_number(v):
    """int / float 原样；能转成数字的字符串转过来（整数出 int）；别的 None。"""
    import math
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v if math.isfinite(v) else None
    if isinstance(v, str):
        s = v.strip()
        try:
            return int(s)
        except ValueError:
            pass
        try:
            f = float(s)
        except ValueError:
            return None
        return f if math.isfinite(f) else None
    return None


def _as_bool(v):
    """布尔原样；是/否/true/false 字符串转成布尔（插值时 to_text 出 是/否）。"""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("是", "true"):
            return True
        if s in ("否", "false"):
            return False
    return None


class ModelMixin:
    """调模型的那一组语句。混进 DSLEngine。"""

    # ------------------------------------------------------------------
    # 后缀：挂载文件、带工具
    # ------------------------------------------------------------------

    def _split_attach(self, rest: str):
        """把「… 附 a.md,b.md」的后缀剥下来。"""
        import re
        m = ATTACH_RE.search(rest)
        if not m:
            return rest, []
        files = [x.strip() for x in re.split(r"[,，]", m.group(1)) if x.strip()]
        return rest[:m.start()], files

    def _split_tools(self, rest: str):
        """把「… 带工具 挑题,题目数 最多 3 轮」剥下来。"""
        import re
        m = TOOLS_RE.search(rest)
        if not m:
            return rest, [], 0
        names = [x.strip() for x in re.split(r"[,，]", m.group(1)) if x.strip()]
        return rest[:m.start()], names, int(m.group(2) or DEFAULT_TOOL_ROUNDS)

    def _split_model(self, rest: str):
        """把「… 用 快」剥下来，返回 (剩下的, 解析后的模型名或 None)。

        「用」在提示词里很常见（「请 用 中文 回答」），所以名字只认三种：
        models.json 的档位/别名（含 config.json 旧的 models 别名）、
        像模型名的 ASCII 串（glm-4-flash、api:zhipu/glm-5.3）或带通道前缀的名字
        （cli:… / api:… / 旧的 claude:… / zcode:…）、一个 {变量}。都不是就当
        提示词的一部分，原样留着。名字写得不对（未知通道等）在调用时由路由报错。
        """
        m = MODEL_RE.search(rest)
        if not m:
            return rest, None
        name = m.group(1)
        if UNEXPANDED_RE.match(name):
            # {变量} 取到空值就是没指定（用默认）；没定义则报错——
            # 把「{模型名}」这串字当模型名发出去，接口回的错看不出原因
            name = to_text(self.expand(name)).strip()
            if UNEXPANDED_RE.match(name):
                raise DSLError(f"「用 {m.group(1)}」：变量没有定义")
        elif not (name in config.model_names()
                  or MODEL_ID_RE.match(name)
                  # 带通道前缀的后半不限 ASCII（zcode 的后半本来就忽略）
                  or name.startswith(("api:", "cli:", "claude:", "zcode:"))):
            return rest, None
        return rest[:m.start()], config.resolve_model(name)

    def _attach(self, prompt: str, files: list) -> str:
        """文件内容拼到提示词前面。

        文件在前、指令在后：长上下文里指令放最后模型更容易照做，反过来
        的话几千字的正文会把那句要求冲淡。

        读不到直接报错，不静默跳过——挂载失败而照样发请求的话，模型会
        基于空上下文编个答案，看着像正常回复，比报错难查。
        """
        if not files:
            return prompt
        blocks = []
        for name in files:
            path = self._safe_path(self.expand(name))
            if not path.is_file():
                raise DSLError(f"挂载的文件不存在：{self._rel(path)}")
            blocks.append(
                f"── {self._rel(path)} ──\n{path.read_text(encoding='utf-8')}")
        return "\n\n".join(blocks) + "\n\n" + prompt

    def _prompt_of(self, rest: str, kw: str):
        """生成类语句的共同前半段：剥挂载后缀、拆赋值、展开、拼文件。"""
        rest, files = self._split_attach(rest)
        name, prompt = self._split_assign(rest, kw)
        return name, self._attach(self.expand(prompt), files)

    # ------------------------------------------------------------------
    # 工具调用
    # ------------------------------------------------------------------

    def _tools_schema(self, names: list) -> list:
        """动词转 OpenAI 兼容的 tools 定义。

        参数一律 string——动词签名本来就全是 str。必填与否从函数签名的
        默认值读：有默认值的不进 required，模型就知道那个可以不给。

        实测智谱认中文函数名，所以不用做名字映射。
        """
        tools = []
        for name in names:
            if not self.verbs or not self.verbs.has(name):
                raise DSLError(f"没有名为「{name}」的动词，无法当工具用")
            params = self.verbs.params_of(name)
            kind, impl = self.verbs.resolve(name)
            desc = (getattr(impl, "__verb_description__", "")
                    if kind == "python" else f"执行脚本 {name}")

            required = list(params)
            if kind == "python":
                try:
                    required = [
                        p.name
                        for p in inspect.signature(impl).parameters.values()
                        if p.default is inspect.Parameter.empty]
                except (TypeError, ValueError):
                    pass

            tools.append({"type": "function", "function": {
                "name": name, "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": {p: {"type": "string", "description": p}
                                   for p in params},
                    "required": required,
                }}})
        return tools

    def _call_verb_by_name(self, name: str, args: dict) -> str:
        """按参数名调用动词。

        模型给的是参数对象，顺序跟函数签名不一定一致——所以按名字绑定。
        多给的键丢掉（通常是模型自己编的字段，塞进去会 TypeError），
        少给的让动词用默认值。
        """
        if not self.verbs or not self.verbs.has(name):
            return f"[没有这个动词] {name}"
        params = self.verbs.params_of(name)
        kwargs = {k: to_text(v) for k, v in args.items() if k in params}
        kind, impl = self.verbs.resolve(name)
        if kind != "python":
            sub = self._sub_engine()
            sub.vars.update(kwargs)
            return sub.run(Path(impl).read_text(encoding="utf-8"))
        try:
            return to_text(impl(**kwargs))
        except Exception as e:
            # 不抛出去：工具执行失败是模型该知道的信息，让它换参数重试，
            # 比整个脚本崩掉强
            return f"[执行失败] {type(e).__name__}: {e}"

    def _chat_tools(self, messages: list, names: list,
                    max_rounds: int, model: str | None = None) -> str:
        """带工具的对话循环。messages 会被就地追加。"""
        tools = self._tools_schema(names)

        for _ in range(max(1, max_rounds)):
            data = self.client.chat_raw(messages, tools=tools,
                                        tool_choice="auto",
                                        temperature=self.temperature,
                                        model=model or self.model)
            msg = data["choices"][0]["message"]
            # reasoning_content 不能回传：推理模型返回的思考过程原样发
            # 回去白烧 token，有的接口还会报错
            messages.append({k: v for k, v in msg.items()
                             if k in ("role", "content", "tool_calls")})

            calls = msg.get("tool_calls") or []
            if not calls:
                return msg.get("content") or ""

            for c in calls:
                fn = c.get("function", {})
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}
                result = self._call_verb_by_name(fn.get("name", ""), args)
                # 打印出来，不静默执行——这是 agent 最难调试的地方
                self._emit(f"[工具] {fn.get('name')}({raw_args[:60]}) "
                           f"→ {result[:80]}")
                messages.append({"role": "tool",
                                 "tool_call_id": c.get("id", ""),
                                 "content": result})

        self._emit(f"[工具调用满 {max_rounds} 轮仍未收敛]")
        return messages[-1].get("content") or ""

    # ------------------------------------------------------------------
    # 语句
    # ------------------------------------------------------------------

    def _generate(self, prompt: str, model: str | None = None) -> str:
        # 模型那头出错（超时、进程退出、网络）：异常原样抛，只打个标记。
        # HTTP 接口据此回 502 和一句人话（见 dsl_http 的 dispatch），
        # 不当成脚本写错了回 500 加一段原文
        try:
            return self.client.chat(prompt, system=self.system,
                                    temperature=self.temperature,
                                    model=model or self.model)
        except Exception as e:
            e.model_call = True
            raise

    def _do_ask(self, rest: str, lineno: int) -> None:
        """问 X = 提示词 [附 文件] [带工具 …] [重试 N 次 直到 条件] [用 模型]

        后缀从外往里剥：「用」最外（只管这一次的模型），然后重试、
        带工具，最后挂载。所以「附 a.md 带工具 X 重试 2 次 直到 … 用 快」
        这个顺序是对的。
        """
        rest, model = self._split_model(rest)
        retry, cond = 0, None
        m = RETRY_RE.search(rest)
        if m:
            retry, cond = int(m.group(1)), m.group(2).strip()
            rest = rest[:m.start()]

        rest, tool_names, max_rounds = self._split_tools(rest)
        name, prompt = self._prompt_of(rest, "问")

        def once() -> str:
            if not tool_names:
                return self._generate(prompt, model)
            msgs = []
            if self.system:
                msgs.append({"role": "system", "content": self.system})
            msgs.append({"role": "user", "content": prompt})
            return self._chat_tools(msgs, tool_names, max_rounds, model)

        result = once()
        attempts = 1
        while cond and not self._eval_against(result, cond, lineno):
            if attempts >= max(1, retry):
                self._emit(f"[重试 {attempts} 次后仍不满足「{cond}」，"
                           f"采用最后一次结果]")
                break
            attempts += 1
            result = once()

        self.store(name, result)
        self._last_result = result

    def _do_ask_json(self, rest: str, lineno: int) -> None:
        """问JSON X = 提示词 [附 文件] [格式 字段:类型 … [重问 N 次]] [用 模型]

        解析失败抛错而不是给空对象：后面 {决策.意图} 取不到会原样保留成
        字符串，扔进条件判断只会一路走到「否则」，错得很隐蔽。

        带「格式」时走 _ask_json_format：附格式说明、检查、不对就重问，
        重问用完抛错。不带的旧写法一行不变。
        """
        rest, model = self._split_model(rest)
        rest, spec, reasks = _split_format(rest, lineno)
        if spec is None:
            # 「附」写在「格式」后面也认；都没有就原样不动
            head, files = self._split_attach(rest)
            if files:
                head, spec, reasks = _split_format(head, lineno)
                if spec is not None:
                    rest = f"{head} 附 {','.join(files)}"
        if spec is not None:
            name, prompt = self._prompt_of(rest, "问JSON")
            result = self._ask_json_format(prompt + _format_note(spec), spec,
                                           reasks, model, lineno)
            self.store(name, result)
            self._last_result = to_text(result)
            return
        name, prompt = self._prompt_of(rest, "问JSON")
        try:
            result = self.client.chat_json(
                prompt, system=self.system, temperature=self.temperature,
                model=model or self.model)
        except ValueError as e:
            raise DSLError(f"第 {lineno + 1} 行：{e}") from e
        self.store(name, result)
        self._last_result = to_text(result)

    def _ask_json_format(self, prompt: str, spec: list, reasks: int,
                         model, lineno: int):
        """带格式的问JSON：问一次，查一次，不对就把问题和它上次的回复
        一起发回去重问，最多 reasks 次。非法 JSON 也算格式错。

        自己调 chat_messages 拿原文、自己解析，不走 chat_json：重问要带上
        上次的原文，而且 api / cli / 假客户端这样走的是同一条路。
        """
        from .zhipu import strip_json
        msgs = []
        if self.system:
            msgs.append({"role": "system", "content": self.system})
        msgs.append({"role": "user", "content": prompt})
        for attempt in range(reasks + 1):
            reply = self.client.chat_messages(
                msgs, temperature=self.temperature, model=model or self.model)
            if isinstance(reply, (dict, list)):     # 假客户端的 handler 可直接回结构
                data, last = reply, to_text(reply)
            else:
                last = str(reply)
                try:
                    data = json.loads(strip_json(last))
                except json.JSONDecodeError:
                    data = _BAD_JSON
            value, problems = _check_format(data, spec)
            if not problems:
                return value
            if attempt < reasks:
                msgs = msgs + [
                    {"role": "assistant", "content": last},
                    {"role": "user", "content": _REASK.format(
                        "；".join(problems))}]
        raise DSLError(f"第 {lineno + 1} 行：问JSON 格式不对："
                       f"{'；'.join(problems)}；最后一次回复：{last[:200]}")

    def _do_stream(self, rest: str) -> None:
        """流式 X = 提示词 —— 边生成边打印，最后把整段存进变量。"""
        rest, model = self._split_model(rest)
        name, prompt = self._prompt_of(rest, "流式")
        parts = []
        for chunk in self.client.stream(prompt, system=self.system,
                                        temperature=self.temperature,
                                        model=model or self.model):
            parts.append(chunk)
            if self.verbose:
                print(chunk, end="", flush=True)
        if self.verbose:
            print()
        text = "".join(parts)
        self.store(name, text)
        self._last_result = text

    def _do_chat(self, rest: str) -> None:
        """对话 X = 提示词 [带工具 …] —— 多轮，保留历史。"""
        rest, model = self._split_model(rest)
        rest, tool_names, max_rounds = self._split_tools(rest)
        name, prompt = self._prompt_of(rest, "对话")
        self._ensure_system()
        self.history.append({"role": "user", "content": prompt})
        if tool_names:
            # _chat_tools 自己会追加 assistant 消息，这里不要再 append
            reply = self._chat_tools(self.history, tool_names, max_rounds,
                                     model)
        else:
            reply = self.client.chat_messages(
                self.history, temperature=self.temperature,
                model=model or self.model)
            self.history.append({"role": "assistant", "content": reply})
        self.store(name, reply)
        self._last_result = reply

    def _do_verdict(self, rest: str, lineno: int) -> None:
        """判定 X = 提示词 甲→输出 乙→输出 否则→输出

        注意分支列表**不会发给模型**，它们只在本地匹配模型的回复开头。
        所以期望的选项要自己写进提示词里，否则模型回一段话，
        startswith 不命中，直接落到「否则」。
        """
        from .dsl_core import BRANCH_RE, check_name
        import re

        name, _, tail = rest.partition("=")
        if not name.strip():
            raise DSLError(f"第 {lineno + 1} 行：「判定」的语法应为："
                           f"判定 名 = 提示词 值→输出")

        branches = [(m.group(1), m.group(2)) for m in BRANCH_RE.finditer(tail)]
        if not branches:
            raise DSLError(f"第 {lineno + 1} 行：「判定」至少要有一个分支，"
                           f"形如 正确→○")
        first = re.search(r"\S+?\s*(?:→|->)", tail)
        prompt = tail[:first.start()].strip() if first else tail.strip()

        result = self._generate(self.expand(prompt))
        self.store(check_name(name.strip(), lineno), result)
        self._last_result = result

        fallback = None
        for key, out in branches:
            if key in ("否则", "else", "其他"):
                fallback = out
                continue
            if result.strip().startswith(key):
                self._emit(out)
                break
        else:
            if fallback:
                self._emit(fallback)
