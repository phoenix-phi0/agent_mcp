# 怎么跑全量测试

    bash tests/run_all.sh

在哪个仓库 / worktree 里跑就测哪个（仓库根取脚本所在目录，`M=/别处 bash tests/run_all.sh` 可覆盖）。
解释器用仓库根的 `.venv/bin/python`（worktree 里先 `ln -s <主仓库>/.venv .venv`）。

首次要准备的东西（缺了脚本会提示或自己补，不会静默跳过）：

- **node E2E（15 组）**：要 jsdom，`npm ci --prefix tests/e2e`（版本锁在 tests/e2e/package-lock.json；node_modules 不进 git）。缺了脚本开头会打一行提示。
- **kg_v4走查（浏览器）**：要装了 playwright 的 python，不往 `.venv` 装，用环境变量指过去：
  `PW_PYTHON=/tmp/k97_pw_venv/bin/python bash tests/run_all.sh`。不设就打印「跳过」。
  浏览器用系统 Chrome（`/usr/bin/google-chrome`）。
- **规则对照**：读真库 `kg/app.db`（`*.db` 不进 git）。没有时脚本先跑 `py -m kg setup` 建一份。

每组一行结果，失败的组下面展开细节；每组默认 90 秒时限（`LIMIT=…` 可调，个别慢组在脚本里单独放宽）。
全量约 12–15 分钟，别放到有更短时限的地方跑。
