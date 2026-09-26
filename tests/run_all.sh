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

run() {
  local name=$1; shift
  local out code last
  out=$("$@" 2>&1); code=$?
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
run 知识图谱    $PY tests/kg/test_kg.py
run 单词        $PY tests/kg/test_word.py
run 单词导入    $PY tests/kg/test_word_import.py
run 学习记录    $PY tests/kg/test_learn.py
run 认证        $PY tests/auth/test_auth.py
run 认证攻击    $PY tests/auth/test_auth_attack.py
run 并发隔离    $PY tests/auth/test_concurrency.py
run 增删改查E2E bash -c "cd $M/tests/e2e && node run.js"
run 登录流程E2E bash -c "cd $M/tests/e2e && node auth_run.js"
run 导航路由E2E bash -c "cd $M/tests/e2e && node route_run.js"
run 显式主键E2E bash -c "cd $M/tests/e2e && node pk_run.js"
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
