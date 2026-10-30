#!/usr/bin/env bash
# 正式服务（kg_v4_data，8119）幂等启动：已在跑就什么都不做；掉线则拉起，带退避和日志轮转。
# 可用环境变量覆盖（演练用）：KG_RUN_DIR KG_DATA KG_PORT
RUN=${KG_RUN_DIR:-/workspace/dslagent_exp/kg_v4_run}
DATA=${KG_DATA:-/workspace/dslagent_exp/kg_v4_data}
PORT=${KG_PORT:-8119}
REPO=/workspace/agent_mcp
PIDF=$RUN/server.pid; LOG=$RUN/server.log; WLOG=$RUN/watch.log; HIST=$RUN/starts.hist
MAXSTART=3; WINDOW=600; MAXLOG=$((20*1024*1024)); KEEP=3
export TZ=Asia/Tokyo
export PATH="/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin:$PATH"
say(){ echo "$(date '+%F %T') [start.sh] $*" >> "$WLOG"; }
mkdir -p "$RUN"

exec 9>"$RUN/start.lock"; flock -n 9 || exit 0

alive(){ # PID 文件里的进程还活，且命令行是 gen run <DATA>
  local p; p=$(cat "$PIDF" 2>/dev/null) || return 1
  [[ $p =~ ^[0-9]+$ ]] && kill -0 "$p" 2>/dev/null || return 1
  local c; c=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null) || return 1
  [[ $c == *" -m gen run $DATA "* ]]
}

rotate(){ # server.log 超过 20MB：.1 .2 .3 滚动，保留 3 份
  local sz; sz=$(stat -c %s "$LOG" 2>/dev/null || echo 0)
  [ "$sz" -gt "$MAXLOG" ] || return 0
  rm -f "$LOG.$KEEP"
  for ((i=KEEP-1;i>=1;i--)); do [ -e "$LOG.$i" ] && mv "$LOG.$i" "$LOG.$((i+1))"; done
  cp "$LOG" "$LOG.1" && : > "$LOG"   # copytruncate：运行中的服务仍持有同一个文件描述符
  say "日志轮转（$sz 字节）"
}

if alive; then rotate; exit 0; fi

now=$(date +%s)
recent=$(awk -v n="$now" -v w="$WINDOW" 'n-$1<w' "$HIST" 2>/dev/null | wc -l)
if [ "$recent" -ge "$MAXSTART" ]; then
  say "退避：最近 $((WINDOW/60)) 分钟已拉起 $recent 次（上限 $MAXSTART），暂停拉起；窗口过去后自动恢复，或排查后手动 start.sh"
  exit 0
fi
awk -v n="$now" -v w="$WINDOW" 'n-$1<w' "$HIST" 2>/dev/null > "$HIST.tmp"; echo "$now" >> "$HIST.tmp"; mv "$HIST.tmp" "$HIST"

rotate
cd "$REPO" || exit 1
# 与 K119 同一条命令；--real 需要 ZHIPU_API_KEY，环境里没有就经 bash -ic 载入 ~/.bashrc（同 start_all.sh 的做法）
CMD='.venv/bin/python -m gen run "$KG_DATA_" --登录 --real --port "$KG_PORT_" --不开浏览器 --host 127.0.0.1'
export KG_DATA_=$DATA KG_PORT_=$PORT
if [ -n "$ZHIPU_API_KEY" ]; then
  setsid bash -c "exec $CMD" >> "$LOG" 2>&1 < /dev/null 8>&- 9>&- &
else
  setsid bash -ic "exec $CMD" >> "$LOG" 2>&1 < /dev/null 8>&- 9>&- &
fi
echo $! > "$PIDF"
say "已拉起 PID $(cat "$PIDF")（最近窗口内第 $((recent+1)) 次）"
