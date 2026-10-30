#!/usr/bin/env bash
# 常驻看门狗：每 60 秒跑一次 start.sh。单实例（flock）。由 /workspace/start_all.sh 在开机时拉起。
RUN=${KG_RUN_DIR:-/workspace/dslagent_exp/kg_v4_run}
mkdir -p "$RUN"
exec 8>"$RUN/watch.lock"; flock -n 8 || exit 0
D=$(dirname "$(readlink -f "$0")")
while :; do bash "$D/start.sh" >> "$RUN/watch.log" 2>&1 < /dev/null; sleep "${KG_INTERVAL:-60}"; done
