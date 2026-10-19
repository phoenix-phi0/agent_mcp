# 递归失控：loop.自转 调自己，超过深度上限报错
接口 POST /loop/run
  设 r = 调用 loop.自转 n=1
  返回 {r}
结束
