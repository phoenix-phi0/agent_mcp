#!/usr/bin/env bash
# 按 PID 文件停正式服务（进程组 TERM，kill -0 确认；10 秒没退则 KILL）。
RUN=${KG_RUN_DIR:-/workspace/dslagent_exp/kg_v4_run}
PIDF=$RUN/server.pid
p=$(cat "$PIDF" 2>/dev/null)
[[ $p =~ ^[0-9]+$ ]] || { echo "没有有效 PID 文件"; exit 0; }
kill -0 "$p" 2>/dev/null || { echo "进程 $p 已不在"; exit 0; }
kill -TERM -- "-$p"
for i in $(seq 1 20); do kill -0 "$p" 2>/dev/null || { echo "已停止 $p"; exit 0; }; sleep 0.5; done
kill -KILL -- "-$p"; sleep 1
kill -0 "$p" 2>/dev/null && { echo "仍未退出 $p"; exit 1; } || echo "已强制停止 $p"
