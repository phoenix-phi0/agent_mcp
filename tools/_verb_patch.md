# 引擎需要的三处改动（贴进 tools/dsl.py）

## 一、顶部加 import

from .verbs import VerbRegistry, VerbError


## 二、__init__ 增加 verbs 参数

    def __init__(self, client=None, workdir=None, verbose=True,
                 verbs: "VerbRegistry | None" = None, _depth: int = 0):
        ...
        self.verbs = verbs
        ...

（子引擎创建处也要传下去，见第三节的 _do_call 修改）


## 三、_exec_block 里，在 "未知语句" 之前拦截动词

把 _exec_stmt 的调用改成先查动词表。在 _exec_block 中
`try: self._exec_stmt(head, rest, i)` 这一段之前插入：

            # 动词：不是内置语句时，查动词表
            if (self.verbs is not None
                    and head not in KEYWORDS.values()
                    and self.verbs.has(head)):
                try:
                    self._do_verb(head, rest, i)
                except VerbError as e:
                    raise DSLError(f"第 {i + 1} 行：{e}") from e
                i += 1
                continue

注意 _split_head 对未知词返回的 head 是原词本身，所以这里 head 就是动词名。


## 四、新增 _do_verb 方法（放在 _do_verdict 后面）

    def _do_verb(self, name: str, rest: str, lineno: int,
                 assign_to: str | None = None) -> None:
        """执行一个动词。脚本动词起子引擎，Python 动词直接调函数。"""
        args = [self.expand(a) for a in rest.split()] if rest.strip() else []
        params = self.verbs.bind(name, args)
        kind, impl = self.verbs.resolve(name)

        if kind == "python":
            result = impl(**params)
            result = "" if result is None else str(result)
        else:
            if self._depth >= MAX_CALL_DEPTH:
                raise DSLError(f"动词调用层数超过 {MAX_CALL_DEPTH}，可能存在循环调用")
            sub = DSLEngine(
                client=self.client,
                workdir=self.workdir,
                verbose=False,
                verbs=self.verbs,
                _depth=self._depth + 1,
            )
            sub.system = self.system
            sub.temperature = self.temperature
            sub.vars.update(params)
            result = sub.run(Path(impl).read_text(encoding="utf-8"))

        self._last_result = result
        if assign_to:
            self.vars[assign_to] = result
        elif result:
            for line in result.splitlines():
                self._emit(line)


## 五、set 分支里支持「设 X = 动词 ...」

在 _exec_stmt 的 set 分支，把原来的判断扩展成：

        elif head == "set":
            name, value = self._split_assign(rest, "设")
            sub_head, sub_rest = self._split_head(value)
            if sub_head == "call":
                self._do_call(sub_rest, lineno, assign_to=name)
            elif (self.verbs is not None
                    and sub_head not in KEYWORDS.values()
                    and self.verbs.has(sub_head)):
                self._do_verb(sub_head, sub_rest, lineno, assign_to=name)
            else:
                self.vars[name] = self.expand(value)


## 六、_do_call 里创建子引擎时把 verbs 传下去

            sub = DSLEngine(
                client=self.client,
                workdir=self.workdir,
                verbose=False,
                verbs=self.verbs,          # ← 加这行
                _depth=self._depth + 1,
            )


## 七、run_script 便捷入口（可选）

def run_script(path, verbs=None, **kwargs):
    p = Path(path)
    engine = DSLEngine(workdir=p.parent, verbs=verbs, **kwargs)
    return engine.run_file(p)
