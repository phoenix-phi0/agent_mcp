#!/usr/bin/env bash
# 跑全部测试，每组一行结果，失败的组才展开细节。
#
#     bash tests/run_all.sh          # 仓库根自动取脚本所在仓库，M=... 可覆盖
#     PW_PYTHON=/tmp/k97_pw_venv/bin/python bash tests/run_all.sh   # 带上浏览器走查
#     npm ci --prefix tests/e2e       # 首次：装 node E2E 要的 jsdom
#
# 全用绝对路径：在 cd 之后用相对路径找解释器，这个错犯过两次，而且错误
# 被管道吞掉了，看着像测试失败或者像全部通过。
#
# 起服务的组用 setsid 放进独立进程组，结束时按组杀——serve_http.py 会派生
# 子进程持有端口，只杀父进程会留下孤儿；而 pkill -f 按命令行匹配，会连
# 跑这个脚本的 shell 一起杀掉。

set -u
M="${M:-$(cd "$(dirname "$0")/.." && pwd)}"
export M
PY=$M/.venv/bin/python
FAILED=0
KNOWN_FAILED=0
# 已知失败：「组名|该组里唯一允许失败的检查点文字」。这组仍照常运行，
# 失败的 ✗ 行全是这个检查点时记为「已知失败」，单独计数、不算失败；
# 该组还有别的 ✗、或崩溃 / 超时，照常算失败。修好后该检查点转绿，条目就该删。
#   教材导入E2E｜确认后撤下了：旧 kg 项目（kg/routes）撤下后重新载入把
#   「撤下了：…」提示盖掉，用户决定旧 kg 不修（kg_v4 已修，见 data/reports/kg_K116.md、
#   kg_K117.md）。
KNOWN=(
  "教材导入E2E|确认后撤下了"
)
# 每组的时限。一组卡住时，没有它整个脚本会一直等下去——后面十几组
# 根本没机会跑，而「卡住」和「很慢」从外面看一模一样。实际撞上过：
# 跑了十分钟没结果，查完才知道是某一组挂在那儿。
# 90 秒对现有的组都富余（最慢的 e2e 约 40 秒）。
LIMIT=${LIMIT:-90}

run() {
  local name=$1; shift
  local out code last
  # --foreground 让 timeout 杀整个进程组，不只是它直接起的那个进程。
  #
  # 不加的话对 `bash -c "... node run.js"` 这种没用：timeout 杀掉 bash，
  # 而 node 起的服务是孙子进程，活着并且握着管道的写端，$(...) 就一直
  # 等管道关闭——脚本照样无限挂着，加了超时等于没加。实际撞上过：
  # 以为限住了，结果又跑了十几分钟。
  out=$(setsid timeout --foreground --signal=TERM --kill-after=5 "$LIMIT" "$@" 2>&1); code=$?
  if [ "$code" -eq 124 ] || [ "$code" -eq 137 ]; then
    printf '%-12s 超时（%s 秒没跑完，已终止）\n' "$name" "$LIMIT"
    FAILED=$((FAILED + 1))
    printf '%s\n' "$out" | tail -6 | sed 's/^/    /'
    return
  fi
  # 浏览器走查在 PW_PYTHON 指的解释器没装 playwright 时退出码 2 = 跳过，不计失败
  if [ "$code" -eq 2 ] && [ "$name" = "kg_v4走查" ]; then
    printf '%-12s 跳过（没装 playwright，不计失败）\n' "$name"
    return
  fi
  last=$(printf '%s\n' "$out" | grep -E '通过 *[0-9]+|passed|OK|完成' | tail -1)
  [ -z "$last" ] && last=$(printf '%s\n' "$out" | grep -v '^\s*$' | tail -1)
  printf '%-12s 退出码 %s  %s\n' "$name" "$code" "$last"
  if [ "$code" -ne 0 ]; then
    local k known="" marks others
    for k in "${KNOWN[@]}"; do
      [ "${k%%|*}" = "$name" ] && known=${k#*|}
    done
    if [ -n "$known" ] && [ "$code" -eq 1 ]; then
      marks=$(printf '%s\n' "$out" | grep -c '✗')
      others=$(printf '%s\n' "$out" | grep '✗' | grep -vc -- "$known")
      if [ "$marks" -ge 1 ] && [ "$others" -eq 0 ] && ! printf '%s\n' "$out" | grep -qE 'Traceback|Error'; then
        KNOWN_FAILED=$((KNOWN_FAILED + 1))
        printf '    已知失败：%s（旧 kg 项目，按决定不修，见 data/reports/kg_K116.md）\n' "$known"
        return
      fi
    fi
    FAILED=$((FAILED + 1))
    printf '%s\n' "$out" | grep -E '✗|Error|Traceback|失败' | head -12 | sed 's/^/    /'
  fi
}

cd $M
# node E2E 要 jsdom（tests/e2e/package.json，node_modules 不进版本库）。缺了不静默跳过：
# 提示一行，后面的 E2E 组会照常报错。
[ -d "$M/tests/e2e/node_modules/jsdom" ] || echo "!! 缺 jsdom，node E2E 会失败；先跑：npm ci --prefix $M/tests/e2e"
run 引擎        $PY -m tools.test_dsl
run 序号和默认值 $PY tests/dsl/test_loop_default.py
run 遍历JSON列表 $PY tests/dsl/test_each_json_list.py
run JSON字面量转义 $PY tests/dsl/test_json_literal.py
run 动词参数    $PY tests/dsl/test_verb_params.py
run 界面编译    $PY -m tools.test_ui
run 会话        $PY tests/http/test_session.py
run 库出错      $PY tests/http/test_db_errors.py
run 服务并发    $PY tests/http/test_concurrent.py
run 块识别当重复 $PY tests/http/test_block_openers.py
LIMIT=300 run kg_v4项目  $PY tests/kg_v4/test_project.py
run 设定行科目列  $PY tests/kg_v4/test_tr_rows.py
run 学生页设定表  $PY tests/kg_v4/test_report_notes.py
run 整库引用保护 $PY tests/kg_v4/test_kg_refs.py
run 导入规则     $PY tests/kg_v4/test_kg_import_rules.py
run 助手草稿     $PY tests/kg_v4/test_assist_drafts.py
run 助手材料     $PY tests/kg_v4/test_assist_material.py
run 助手学情     $PY tests/kg_v4/test_assist_insight.py
run 科目等级     $PY tests/kg_v4/test_subject_levels.py
run 问老师人设   $PY tests/kg_v4/test_tutor_persona.py
run 教师助手人设 $PY tests/kg_v4/test_assist_persona.py
run 空白传参与设定预览 $PY tests/kg_v4/test_k166_whitespace_preview.py
# 浏览器走查（K97）：起服务 + playwright + 系统 Chrome，比别的组慢，时限给 300 秒。
# 没 playwright 的机器上打「跳过」退出码 2——run() 里单独按「跳过」处理，详见脚本头部。
# 解释器由 PW_PYTHON 指定（如 /tmp/k97_pw_venv/bin/python），不往 .venv 装 playwright。
if [ -n "${PW_PYTHON:-}" ] && [ -x "$PW_PYTHON" ]; then
  LIMIT=300 run kg_v4走查  "$PW_PYTHON" tests/kg_v4/e2e_walk.py
else
  echo "kg_v4走查    跳过（未设 PW_PYTHON 或不可执行；设成装了 playwright 的 python 即可跑）"
fi
run 模板命名    $PY tests/gen/test_templates.py
run 按端拆页面  $PY tests/gen/test_ends.py
run 界面序      $PY tests/gen/test_order.py
run 只加迁移    $PY tests/gen/test_migrate.py
run 显式重建表  $PY tests/gen/test_migrate_rebuild.py
run 科目切换器  $PY tests/gen/test_subject_switch.py
run private权限  $PY tests/gen/test_perms.py
run 知识图谱    $PY tests/kg/test_kg.py
run 单词        $PY tests/kg/test_word.py
run 单词导入    $PY tests/kg/test_word_import.py
run 学习记录    $PY tests/kg/test_learn.py
run 掌握得分    $PY tests/kg/test_score.py
run 对账清理    $PY tests/kg/test_prune.py
run 课文        $PY tests/kg/test_lesson.py
run 教材系列    $PY tests/kg/test_series.py
run 教材导入    $PY tests/kg/test_textbook_import.py
run 语法题库    $PY tests/quiz/test_bunpou.py
run 做题        $PY tests/kg/test_quiz.py
run 做题总结    $PY tests/kg/test_quiz_summary.py
run 复习薄弱点  $PY tests/kg/test_quiz_review.py
run 单词默写    $PY tests/kg/test_dictation.py
# 规则对照读真库 kg/app.db（*.db 不进 git，新 clone / 新 worktree 里没有）：缺了先 setup 建一份
[ -f "$M/kg/app.db" ] || { echo "建 kg/app.db（py -m kg setup）…"; $PY -m kg setup >/dev/null 2>&1; }
run 规则对照    $PY tests/kg/test_rules_equiv.py
run 老师讲语法  $PY tests/kg/test_teacher_bunpou.py
run 问老师      $PY tests/kg/test_teacher_chat.py
run 请老师讲课  $PY tests/kg/test_teacher_lesson.py
run AI老师设定  $PY tests/kg/test_teacher_note.py
run AI老师传达  $PY tests/kg/test_teacher_relay.py
run 教材和进度  $PY tests/kg/test_pages.py
run 多人模式    $PY tests/kg/test_multiuser.py
run 命令行别名  $PY tests/kg/test_cli_alias.py
run 教师学生分端 $PY tests/kg/test_roles.py
run 教师端入口 $PY tests/kg/test_teacher_entry.py
run 并发用包    $PY tests/dsl/test_use_concurrent.py
run 假模型脚本  $PY tests/dsl/test_mock_script.py
run 问JSON格式  $PY tests/dsl/test_ask_json_format.py
run 模型可选    $PY tests/dsl/test_model_select.py
run 模型后端    $PY tests/dsl/test_model_backends.py
run 模型档位    $PY tests/dsl/test_model_tiers.py
run 模型通道    $PY tests/dsl/test_model_channels.py
run 运行时兜底  $PY tests/dsl/test_model_fallback_runtime.py
run 经WSL调CLI  $PY tests/dsl/test_cli_via_wsl.py
run 运行模式    $PY tests/dsl/test_run_mode.py
run 命名约定    $PY tests/dsl/test_naming.py
run 字符串动词  $PY tests/dsl/test_text_verbs.py
run 读csv       $PY tests/dsl/test_doc_csv.py
run 参数或默认  $PY tests/dsl/test_alt_args.py
run 条件计算正则 $PY tests/dsl/test_cond_calc_regex.py
run 循环        $PY tests/dsl/test_loop_while.py
run 业务层        $PY tests/dsl/test_service_layer.py
run 终止与派任务 $PY tests/dsl/test_halt_task.py
run 改法段与预算 $PY tests/dsl/test_edit_budget.py
run 批量claude  $PY tests/tools/test_cbatch.py
run DSL修bug   $PY tests/tools/test_dslagent.py
run DSL推理    $PY tests/tools/test_dslagent_infer.py
run DSL规则    $PY tests/tools/test_dslagent_rules.py
run DSL任务    $PY tests/tools/test_dslagent_task.py
run DSL分支规划 $PY tests/tools/test_dslagent_branch.py
run DSL改法段   $PY tests/tools/test_dslagent_edits.py
run DSL工具子任务 $PY tests/tools/test_dslagent_tool.py
run DSL规划读码 $PY tests/tools/test_dslagent_planread.py
run DSL测试环境 $PY tests/tools/test_dslagent_testenv.py
run DSL按步骤模型 $PY tests/tools/test_dslagent_models.py
run DSL资料包   $PY tests/tools/test_dslagent_packs.py
run DSL做模块   $PY tests/tools/test_dslagent_dslproj.py
run DSLv2流程 $PY tests/tools/test_dslagent_v2.py
run DSLv2拆分 $PY tests/tools/test_dslagent_split.py
run DSL范围 $PY tests/tools/test_dslagent_scope.py
run DSL试调 $PY tests/tools/test_dslagent_trial.py
run DSL接口约定 $PY tests/tools/test_dslagent_contract.py
run DSL规划骨架 $PY tests/tools/test_dslagent_dslplan.py
run DSLv3流程 $PY tests/tools/test_dslagent_v3.py
run DSLaudit2范围 $PY tests/tools/test_dslagent_k77.py
run DSL整份重写 $PY tests/tools/test_dslagent_k84.py
run 批量opencode $PY tests/tools/test_obatch.py
run 批量codex   $PY tests/tools/test_cxbatch.py
run 批量goose   $PY tests/tools/test_gsbatch.py
run Colab启动   $PY tests/tools/test_colab_vllm.py
run 批量grok    $PY tests/tools/test_gbatch.py
run grok权限    $PY tests/tools/test_gbatch_perm.py
run grok并发    $PY tests/tools/test_gbatch_concurrency.py
run 代理工作目录 $PY tests/tools/test_zcode_workdir.py
run 认证        $PY tests/auth/test_auth.py
run 认证攻击    $PY tests/auth/test_auth_attack.py
run 并发隔离    $PY tests/auth/test_concurrency.py
run 增删改查E2E bash -c "cd $M/tests/e2e && node run.js"
run 登录流程E2E bash -c "cd $M/tests/e2e && node auth_run.js"
run 导航路由E2E bash -c "cd $M/tests/e2e && node route_run.js"
run 显式主键E2E bash -c "cd $M/tests/e2e && node pk_run.js"
run 做题页E2E   bash -c "cd $M/tests/e2e && node quiz_run.js"
run 问老师E2E   bash -c "cd $M/tests/e2e && node teacher_run.js"
run 消息按钮E2E bash -c "cd $M/tests/e2e && node msg_actions_run.js"
run 复习E2E     bash -c "cd $M/tests/e2e && node review_run.js"
run 默写E2E     bash -c "cd $M/tests/e2e && node dictation_run.js"
run 教材进度E2E bash -c "cd $M/tests/e2e && node pages_run.js"
run 教材系列E2E bash -c "cd $M/tests/e2e && node series_run.js"
run 教材导入E2E bash -c "cd $M/tests/e2e && node textbook_import_run.js"
run 多人E2E     bash -c "cd $M/tests/e2e && node multiuser_run.js"
run 两端页面E2E bash -c "cd $M/tests/e2e && node ends_run.js"
run 老师设定E2E bash -c "cd $M/tests/e2e && node teacher_note_run.js"
run 老师传达E2E bash -c "cd $M/tests/e2e && node teacher_relay_run.js"
run app2编译    bash -c "cd $M/app2 && $PY build.py"

# 上传要先起 dsl/ 的服务。
#
# 每次运行用自己的空闲端口，服务的进程号记在本脚本的变量里，不落到共用的
# 文件。早先是固定的 /tmp/run_all_upload.pid 和默认端口 8091：几个会话同时
# 跑全量时，后起的覆盖了 pid 文件，先跑完的那个按文件杀掉的是别人的服务，
# 自己那个没人收；测试也可能连到别人的服务上。实际攒下过十几个残留。
#
# trap 兜底：脚本被 Ctrl+C、超时杀掉、终端断开时也把服务收掉。按进程组杀
# （setsid 起的，组号就是它的进程号），服务派生的子进程一起走。
UPORT=$($PY -c "import socket; s=socket.socket(); s.bind(('127.0.0.1', 0)); print(s.getsockname()[1]); s.close()")
ULOG=$(mktemp /tmp/run_all_upload.XXXXXX.log)
( cd $M/dsl && exec setsid $PY serve_http.py --port "$UPORT" > "$ULOG" 2>&1 ) &
UPID=$!
trap 'kill -TERM -"$UPID" 2>/dev/null' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
# 等它真的在听，而不是固定睡几秒：机器忙时 5 秒不够，闲时又白等
for _ in $(seq 1 30); do
  $PY -c "import socket,sys; socket.create_connection(('127.0.0.1', $UPORT), 0.5)" 2>/dev/null && break
  sleep 0.5
done
run 文件上传    bash -c "cd $M/dsl && $PY test_upload.py --port $UPORT"
kill -TERM -"$UPID" 2>/dev/null
rm -f "$ULOG"

echo "----"
echo "已知失败 $KNOWN_FAILED"
if [ "$FAILED" -eq 0 ]; then echo "全部通过"; else echo "$FAILED 组失败"; fi
exit "$FAILED"
