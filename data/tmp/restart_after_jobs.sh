#!/usr/bin/env bash
# 等 batch 任务都结束后重启 fs_server_v2(:8000) 和 batchmgr(:8010)。结果写 /tmp/restart_after_jobs.log
# 每 60 秒查一次；连续两次空闲才重启；最长等 4 小时。
export TZ=Asia/Tokyo
export PATH="/usr/local/bin:/usr/bin:/bin:$HOME/.grok/bin:$HOME/.local/bin:$PATH"
LOG=/tmp/restart_after_jobs.log
PY=/workspace/agent_mcp/.venv/bin/python
log() { echo "[$(date '+%F %T %Z')] $*" >> "$LOG"; }
DEADLINE=$(( $(date +%s) + 4*3600 ))
idle=0
log "开始等待（pid $$），最长 4 小时"

busy_reason() {
  # 以 API 报的状态为准（文件里写 running 但 API 报 died 的不算）
  local j
  j=$(curl -s -m 10 http://127.0.0.1:8010/api/jobs) || { echo "api 不可达"; return; }
  local act
  act=$(printf '%s' "$j" | "$PY" -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: print("api 返回解析失败"); sys.exit()
if isinstance(d,dict): d=d.get("jobs",[])
print(" ".join(f"{x.get(\"id\")}:{x.get(\"status\")}" for x in d if x.get("status") in ("running","queued")))')
  [ -n "$act" ] && { echo "任务 $act"; return; }
  local p
  p=$(pgrep -f 'goose run|codex exec' | tr '\n' ' ')
  [ -n "$p" ] && { echo "进程 $p"; return; }
  echo ""
}

while :; do
  r=$(busy_reason)
  if [ -z "$r" ]; then
    idle=$((idle+1)); log "空闲（第 $idle 次）"
    [ $idle -ge 2 ] && break
  else
    [ $idle -gt 0 ] || [ $(( $(date +%s) % 600 )) -lt 60 ] && log "忙：$r"
    idle=0
  fi
  if [ $(date +%s) -ge $DEADLINE ]; then log "超时：等了 4 小时仍有任务（$r），不重启，退出"; exit 1; fi
  sleep 60
done

log "连续两次空闲，开始重启"
# 只认真正的 python 进程（命令行以 python 开头），别误伤带这些字样的 bash 包装进程
pyproc() { pgrep -f "^(\S*/)?python3?\S* (\S*/)?$1"; }
for pat in 'fs_server_v2.py' '/workspace/batchmgr/app.py'; do
  pids=$(pyproc "$pat" | tr '\n' ' ')
  [ -n "$pids" ] && { log "停 $pat：$pids"; kill $pids; }
done
for i in $(seq 1 20); do
  ss -ltn | grep -qE '127.0.0.1:(8000|8010) ' || break; sleep 0.5
done
ss -ltn | grep -qE '127.0.0.1:(8000|8010) ' && { log "端口没释放，强杀"; kill -9 $(pyproc fs_server_v2.py) $(pyproc /workspace/batchmgr/app.py) 2>/dev/null; sleep 1; }

# bash -ic 加载 ~/.bashrc（ZHIPU_API_KEY），方式同 start_all.sh
bash -ic 'export TZ=Asia/Tokyo PATH="/usr/local/bin:/usr/bin:/bin:$HOME/.grok/bin:$HOME/.local/bin:$PATH"
cd /workspace/agent_mcp && setsid -f nohup .venv/bin/python fs_server_v2.py > /tmp/fs_server_v2.log 2>&1 < /dev/null &
/workspace/batchmgr/start.sh' >> "$LOG" 2>&1 < /dev/null

ok=1
for i in $(seq 1 30); do ss -ltn | grep -q '127.0.0.1:8000 ' && ss -ltn | grep -q '127.0.0.1:8010 ' && break; sleep 1; done
for spec in '8000 fs_server_v2.py' '8010 /workspace/batchmgr/app.py'; do
  set -- $spec
  pid=$(pyproc "$2" | head -1)
  if ss -ltn | grep -q "127.0.0.1:$1 "; then lis=监听中; else lis=没在监听; ok=0; fi
  if [ -n "$pid" ] && tr '\0' '\n' < /proc/$pid/environ 2>/dev/null | grep -q '^ZHIPU_API_KEY=.'; then k=有; else k=没有; ok=0; fi
  log ":$1 $2 pid=${pid:-无} $lis，ZHIPU_API_KEY：$k"
done
[ $ok = 1 ] && log "重启完成，全部正常" || log "重启后有异常，见上面"
exit $((1-ok))
