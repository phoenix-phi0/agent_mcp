# gsbatch 续接判定 · Drools 规则引擎

把 `tools/gsbatch.py` 里 2026-11-01 的自动续接判定（什么错重试、什么错
不重试、几轮上限、退避多久、剩时间不够怎么办）从 Python 内联代码抽成了
Drools 产生式规则。

## 组成

    decide.drl           规则（R10–R99，salience 复刻 Python 的判断顺序）
    Attempt.java         事实：一次 goose 进程结束后的现场
    Decision.java        决策：resume / gave_up 理由 / 退避秒数
    GsbatchDecide.java   运行器：stdin 事实 JSON → stdout 决策 JSON
    build.sh             编译（JDK 用 ~/opt 的 Temurin 17，依赖直接用
                         ~/.m2 里现成的 Drools 8.44.0.Final，不联网）
    out/                 编译产物（decide.drl 会拷进来）

## Python 侧

    tools/gsbatch_rules.py
      decide_local   原逻辑原样搬运（默认，行为与老版本完全一致）
      decide_drools  同一判定的 Drools 版；引擎不可用自动回退本地，
                     engine 字段标 "drools-fallback"，不静默
      decide         gsbatch._decide_resume 的入口，
                     GSBATCH_DECIDER=drools 时走 Drools

## 用

    tools/gsbatch_drools/build.sh          # 先编译一次
    GSBATCH_DECIDER=drools gsbatch submit … # 整批走 Drools 判定

## 验证

    python3 tests/test_gsbatch_rules.py    # 16 案，两边必须逐案同判
    python3 tests/tools/test_gsbatch.py    # 95 项，本地与 drools 模式都过

改任何一边（drl / Java / _decide_local / gsbatch 的两条正则）都要重跑这两样。

## 踩过的坑

- POJO 留在默认包，DRL（tools.gsbatch 包）import 不到 → 编译期整包报错；
  拆成具名包的独立文件
- 停止类规则不 `update($a)` 标记 decided 的话，R99 照样命中，一次吐出
  两个决策（运行器按「恰好一个」校验，显式报错）
- 事实模型用 int[] 存退避表，亚秒退避（0.2）被截成 0 → 改 double；
  这个是 gsbatch 全套测试在 drools 模式下跑出来的，单看对照案例测不到
- `_run_one` 里 `d` 是 job 字典，决策变量不能也叫 `d`——撞名是
  KeyError: 'options'，看着跟变量名毫无关系
- KieHelper 的 drl 编译不报错但规则不触发（"No files found for
  KieBase"）；用 KieServices + KieFileSystem + KieBuilder 那条路才可靠
