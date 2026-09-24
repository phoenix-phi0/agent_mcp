# _call_tx_verb 的修法

`tools/dsl.py` 里把这个方法整个换掉：

```python
    def _call_tx_verb(self, name: str, target: str) -> None:
        """调事务的三个动词之一。

        只有「事务开始」要知道库名，「事务提交」和「事务回滚」用的是
        已经挂在连接上的那个——所以按动词自己声明的参数个数决定传不传，
        而不是一律传一个。

        先前一律传库名，结果零参数的「事务提交」直接报「最多接受 0 个
        参数」。按签名来也让别的存储后端有余地：某个后端的提交需要参数
        的话，它自己把参数声明出来就行。
        """
        args = [target] if (target and self.verbs.params_of(name)) else []
        params = self.verbs.bind(name, args)
        kind, impl = self.verbs.resolve(name)
        if kind != "python":
            raise DSLError(f"「{name}」必须是 Python 动词")
        result = to_text(impl(**params))
        if result.startswith("["):
            # 动词用 [出错] 这种前缀报问题。事务的三个时刻出错都要让脚本
            # 停下——继续跑下去写入会落在没有事务的连接上。
            raise DSLError(f"{name} 失败：{result}")
```

改动只有第一行：`args` 从无条件 `[target]` 改成「动词声明了参数才传」。
