#!/bin/bash
# ant beta:worker poll --on-work 调用：每领到一个会话调一次。环境变量里有 ANTHROPIC_{WORK_ID,ENVIRONMENT_ID,SESSION_ID,ENVIRONMENT_KEY}，stdin 是 work JSON。
# 会话该进哪个项目，由引擎建会话时写在 /var/lib/wfplat/sessions/<会话ID>（一行项目名）。没有登记的会话不执行。
# --max-idle 5s：poll 一次只跑一个 on-work，这个会话不退出，下一个会话就一直排队（2m 时实测下一步多等了 141 秒）。
# 引擎每个会话只发一条消息、等到 end_turn 就走，不会再续，所以 end_turn 后很快退出就行。
# 每个会话单独一层挂载：work/ 只读，只有本项目目录可写；挂好以后丢掉改挂载的权限，工具没法撤掉这层隔离。
set -euo pipefail
cat > /dev/null
WORK=/workspace/agent_mcp/workflow_demo/work
sid="${ANTHROPIC_SESSION_ID:?没有会话 ID}"
map="/var/lib/wfplat/sessions/$sid"
for _ in $(seq 1 20); do [ -f "$map" ] && break; sleep 0.5; done
[ -f "$map" ] || { echo "会话 $sid 没有登记项目，拒绝执行" >&2; exit 1; }
proj=$(tr -d ' \r\n' < "$map")
[[ "$proj" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "项目名不合法：$proj" >&2; exit 1; }
dir="$WORK/$proj"
[ -d "$dir" ] && [ ! -L "$dir" ] || { echo "项目目录不存在：$dir" >&2; exit 1; }
echo "会话 $sid → $dir" >&2
# --pid --fork --mount-proc：独立的进程空间，工具只看得见自己起的进程，读不到别的服务的环境变量
exec unshare --mount --propagation private --pid --fork --mount-proc -- /bin/bash -c '
  set -e
  stage=$(mktemp -d /tmp/wfplat-proj.XXXXXX)
  mount --bind "$1" "$stage"              # 先在别处留一份可写的项目目录
  mount --bind "$2" "$2"
  mount -o remount,bind,ro "$2"           # work/ 整个只读
  mount --bind "$stage" "$1"              # 再把可写的项目目录盖回原位
  umount "$stage"; rmdir "$stage"
  cd "$1"
  exec setpriv --bounding-set=-sys_admin,-sys_ptrace,-sys_module,-sys_rawio,-sys_boot,-net_admin,-mknod \
       --inh-caps=-sys_admin,-sys_ptrace,-sys_module,-sys_rawio,-sys_boot,-net_admin,-mknod \
       /usr/local/bin/ant beta:worker run --workdir "$1" --max-idle 5s
' _ "$dir" "$WORK"
