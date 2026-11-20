# 怎么跑全量测试

    bash tests/run_all.sh

在哪个仓库 / worktree 里跑就测哪个（仓库根取脚本所在目录，`M=/别处 bash tests/run_all.sh` 可覆盖）。
解释器用仓库根的 `.venv/bin/python`（worktree 里先 `ln -s <主仓库>/.venv .venv`）。

首次要准备的东西（缺了脚本会提示或自己补，不会静默跳过）：

- **node E2E（15 组）**：要 jsdom，`npm ci --prefix tests/e2e`（版本锁在 tests/e2e/package-lock.json；node_modules 不进 git）。缺了脚本开头会打一行提示。
- **kg_v4走查 / 日语残留检查（浏览器）**：要装了 playwright 的 python，不往 `.venv` 装。本机持久环境 `/opt/kg_pw_venv`
  （python3.13 + playwright，chromium 由 `playwright install chromium` 装在 `~/.cache/ms-playwright`，系统库由
  `playwright install-deps chromium` 经 apt 装，K196），`run_all.sh` 没设 `PW_PYTHON` 时默认用它；别的解释器用
  `PW_PYTHON=/别处/bin/python bash tests/run_all.sh`。两者都没有就打印「跳过」。
  浏览器按顺序找：环境变量 `KG_CHROME` / `PW_CHROMIUM_PATH` → playwright 自带 chromium → `/usr/bin/google-chrome`；
  都找不到时两组退出码 2、打「跳过：找不到浏览器（逐项原因）」，不计失败。
- **规则对照**：自己照 kg 搭临时库，经导入接口导入 kg 的题和词（tests/kg/helpers），不读也不写 `kg/app.db`（K173）。

每组一行结果，失败的组下面展开细节；每组默认 90 秒时限（`LIMIT=…` 可调，个别慢组在脚本里单独放宽）。
**已知失败**：`run_all.sh` 顶部的 `KNOWN` 列出「组名|唯一允许失败的检查点」（现有一条：旧 kg 的「教材导入E2E：确认后撤下了」，旧项目按决定不修，见 data/reports/kg_K116.md）。这类组照常运行，失败的 ✗ 全是该检查点时单独计入末尾的「已知失败 n」、不算失败；有别的 ✗、崩溃、超时仍算失败。修好后删掉条目。
全量约 12–15 分钟，别放到有更短时限的地方跑。
