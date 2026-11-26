## 提交说明的样子
```
订单：数量为 0 时报 BAD_QTY

- app/orders.py：create_order 先校验数量，0 和负数报 BAD_QTY（原来会写进库）
- tests/test_orders.py：补两条用例（数量 0、数量 -1）
- 验证：.venv/bin/python -m pytest -q → 48 passed in 3.2s

已知问题：批量下单接口还没加同样的校验（验收记录 checked[3]）
```

## 依据的写法
每段对应参考文本里的一项：`{"出处": "task_results[0].changes[1]", "原文": "app/orders.py 修改：create_order 先校验数量"}`。

## 把握
参考文本前后对不上（比如实现记录说全过、验收说有失败）时把握写低，正文里把两边都写出来，不替它们下结论。
