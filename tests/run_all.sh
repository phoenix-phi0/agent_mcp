#!/usr/bin/env bash
# 跑全部测试，每组一行结果，失败的组才展开细节。
#
#     bash /home/ysc/mcp/tests/run_all.sh
#
# 全用绝对路径：在 cd 之后用相对路径找解释器，这个错犯过两次，而且错误
# 被管道吞掉了，看着像测试失败或者像全部通过。
#
# 起服务的组用 setsid 放进独立进程组，结束时按组杀——serve_http.py 会派生
# 子进程持有端口，只杀父进程会留下孤儿；而 pkill -f 按命令行匹配，会连
# 跑这个脚本的 shell 一起杀掉。

set -u
M=/home/ysc/mcp
PY=$M/.venv/bin/python
FAILED=0
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
  last=$(printf '%s\n' "$out" | grep -E '通过 *[0-9]+|passed|OK|完成' | tail -1)
  [ -z "$last" ] && last=$(printf '%s\n' "$out" | grep -v '^\s*$' | tail -1)
  printf '%-12s 退出码 %s  %s\n' "$name" "$code" "$last"
  if [ "$code" -ne 0 ]; then
    FAILED=$((FAILED + 1))
    printf '%s\n' "$out" | grep -E '✗|Error|Traceback|失败' | head -12 | sed 's/^/    /'
  fi
}

cd $M
run 引擎        $PY -m tools.test_dsl
run 序号和默认值 $PY tests/dsl/test_loop_default.py
run 界面编译    $PY -m tools.test_ui
run 会话        $PY tests/http/test_session.py
run 库出错      $PY tests/http/test_db_errors.py
run 模板命名    $PY tests/gen/test_templates.py
run 只加迁移    $PY tests/gen/test_migrate.py
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
run 规则对照    $PY tests/kg/test_rules_equiv.py
run 老师讲语法  $PY tests/kg/test_teacher_bunpou.py
run 问老师      $PY tests/kg/test_teacher_chat.py
run 请老师讲课  $PY tests/kg/test_teacher_lesson.py
run 教材和进度  $PY tests/kg/test_pages.py
run 多人模式    $PY tests/kg/test_multiuser.py
run 并发用包    $PY tests/dsl/test_use_concurrent.py
run 假模型脚本  $PY tests/dsl/test_mock_script.py
run 模型可选    $PY tests/dsl/test_model_select.py
run 模型后端    $PY tests/dsl/test_model_backends.py
run 模型档位    $PY tests/dsl/test_model_tiers.py
run 模型通道    $PY tests/dsl/test_model_channels.py
run 运行时兜底  $PY tests/dsl/test_model_fallback_runtime.py
run 经WSL调CLI  $PY tests/dsl/test_cli_via_wsl.py
run 运行模式    $PY tests/dsl/test_run_mode.py
run 命名约定    $PY tests/dsl/test_naming.py
run 字符串动词  $PY tests/dsl/test_text_verbs.py
run 批量claude  $PY tests/tools/test_cbatch.py
run 认证        $PY tests/auth/test_auth.py
run 认证攻击    $PY tests/auth/test_auth_attack.py
run 并发隔离    $PY tests/auth/test_concurrency.py
run 增删改查E2E bash -c "cd $M/tests/e2e && node run.js"
run 登录流程E2E bash -c "cd $M/tests/e2e && node auth_run.js"
run 导航路由E2E bash -c "cd $M/tests/e2e && node route_run.js"
run 显式主键E2E bash -c "cd $M/tests/e2e && node pk_run.js"
run 做题页E2E   bash -c "cd $M/tests/e2e && node quiz_run.js"
run 问老师E2E   bash -c "cd $M/tests/e2e && node teacher_run.js"
run 复习E2E     bash -c "cd $M/tests/e2e && node review_run.js"
run 默写E2E     bash -c "cd $M/tests/e2e && node dictation_run.js"
run 教材进度E2E bash -c "cd $M/tests/e2e && node pages_run.js"
run 教材系列E2E bash -c "cd $M/tests/e2e && node series_run.js"
run 教材导入E2E bash -c "cd $M/tests/e2e && node textbook_import_run.js"
run 多人E2E     bash -c "cd $M/tests/e2e && node multiuser_run.js"
run app2编译    bash -c "cd $M/app2 && $PY build.py"

# 上传要先起 dsl/ 的服务
( cd $M/dsl && setsid $PY serve_http.py > /tmp/run_all_upload.log 2>&1 & echo $! > /tmp/run_all_upload.pid )
sleep 5
run 文件上传    bash -c "cd $M/dsl && $PY test_upload.py"
kill -TERM -"$(cat /tmp/run_all_upload.pid)" 2>/dev/null
sleep 1

echo "----"
if [ "$FAILED" -eq 0 ]; then echo "全部通过"; else echo "$FAILED 组失败"; fi
exit "$FAILED"
