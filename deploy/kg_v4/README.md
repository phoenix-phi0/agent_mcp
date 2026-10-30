# kg_v4 正式服务运维（8119）

- 服务：`gen run /workspace/dslagent_exp/kg_v4_data --登录 --real --port 8119 --不开浏览器 --host 127.0.0.1`，仓库根 /workspace/agent_mcp 执行，python 用 .venv。
- 文件：start.sh（幂等启动）/ stop.sh / watch.sh（常驻看门狗）/ server.pid（也是进程组号）/ server.log / watch.log / starts.hist。副本在 agent_mcp 的 deploy/kg_v4/（分支 k137）。

## 启停
- 启动：`bash start.sh`（PID 文件里的进程活着且命令行是 `-m gen run <kg_v4_data>` 就不动）。
- 停止：`bash stop.sh`（进程组 TERM，kill -0 确认）。**注意：看门狗会在 ≤60 秒内重新拉起**；要真停，先停看门狗：`kill $(pgrep ...)` 不可用时，用 `ps -eo pid,cmd | grep watch.sh` 找到 PID 后 kill，再 stop.sh。

## 自启机制
本机不是 systemd（PID 1 是 tini/pod-daemon），没有 cron/supervisor。开机由平台执行 `/workspace/start_all.sh`（幂等，拉起 fs_server_v2:8000、batchmgr:8010、goose 代理等），所以 kg_v4 看门狗也挂在这个脚本里：start_all.sh 以 `setsid nohup watch.sh` 启动它（flock 单实例）。watch.sh 每 60 秒跑一次 start.sh。原脚本备份 /workspace/start_all.sh.bak-k137。

## 退避
start.sh 记录每次拉起时间（starts.hist）。10 分钟内已拉起 3 次就不再拉起，watch.log 写「退避…」；窗口过去后自动恢复。排查后可清空 starts.hist 再 `bash start.sh`。

## 日志
server.log 追加写；start.sh 每次检查时发现超 20MB 就滚动为 server.log.1~.3（copytruncate，保留 3 份）。看门狗日志 watch.log。

## 手动恢复
1. `tail -50 server.log`、`tail watch.log` 看原因。
2. 修好后 `: > starts.hist; bash start.sh`；看门狗没在跑则 `setsid nohup ./watch.sh >> watch.log 2>&1 < /dev/null &`。
3. `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8119/` 应为 200。
