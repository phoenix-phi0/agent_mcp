#!/usr/bin/env bash
# build_bundle.sh —— 把 kg_v4 项目 + 引擎最小运行集打包成可单独上线的文件夹
# （K178；最小运行集的分析与验证见 agent_mcp data/reports/kg_K178_glm.md，前作 K123。）
#
# 用法：
#   bash scripts/build_bundle.sh [输出目录]
# 输出默认 /workspace/dslagent_exp/kg_v4_bundle，旁边生成 kg_v4_bundle.tar.gz。
#
# 原则：
# - 基线一律 git archive HEAD：工作区未提交改动不进包，包内容与提交号一一对应。
# - 密钥不进包：不带 config.json / .auth_secret / 任何 key；只给 config.example.json。
# - 最小运行集：gen/（去 out/、*.pyw）、tools/ 运行时模块（含 cbatch/zcode_tool，理由见下）、
#   templates/ 全部、verbs/ 全量（懒加载裁不动）、app2/assets/vue.global.prod.js（本地 Vue）、models.json。
#   不带：dslagent、开发用批处理驱动（gsbatch/zbatch/obatch/gbatch）、tests、kg/、gen/out、data/。
#   带 cbatch/zcode_tool 的理由：它们虽叫批处理，但 llm_router 的 cli:claude / cli:zcode 后端
#   （models.json 默认档位 快/平衡/强 都是 cli:claude，--real 时用）会懒加载 cbatch.CLAUDE_BIN、
#   cbatch._child_env、zcode_tool（llm_router.py:496/539/577）；缺了会抛 ModuleNotFoundError 而不是
#   BackendError，请求直接断。cbatch 模块级只依赖 stdlib+zcode_tool，dslagent 都是函数内懒加载，
#   引擎的 llm 路径碰不到。
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT=${1:-/workspace/dslagent_exp/kg_v4_bundle}
TAG=$(git -C "$REPO" rev-parse HEAD)
SHORT=${TAG:0:7}
PACK_TIME=$(date '+%Y-%m-%d %H:%M:%S %z')
say(){ echo "[build_bundle] $*"; }

# ---- 1 导出 HEAD ----
TMP=$(mktemp -d /tmp/build_bundle.XXXXXX)
trap 'rm -rf "$TMP"' EXIT
say "导出 HEAD=$SHORT（git archive，不含工作区未提交改动）"
git -C "$REPO" archive "$TAG" gen tools templates verbs app2 models.json kg_v4 | tar -x -C "$TMP"

# ---- 2 组装 ----
say "组装 $OUT"
rm -rf "$OUT" "${OUT}.tar.gz"
mkdir -p "$OUT/engine" "$OUT/project" "$OUT/scripts" "$OUT/wheels"

TOOLS="tools/__init__.py tools/auth.py tools/cbatch.py tools/config.py tools/db_errors.py tools/db_tx.py tools/dsl.py \
tools/dsl_budget.py tools/dsl_calc.py tools/dsl_core.py tools/dsl_history.py tools/dsl_http.py \
tools/dsl_model.py tools/dsl_sections.py tools/dsl_service.py tools/dsl_task.py tools/entity.py \
tools/http_ctx.py tools/json_repair.py tools/kg_dag.py tools/llm_router.py tools/migrate.py \
tools/mock.py tools/packs.py tools/render.py tools/ui.py tools/ui_entity.py tools/ui_site.py \
tools/verbs.py tools/zcode_tool.py tools/zhipu.py"
for f in $TOOLS; do
  [ -f "$TMP/$f" ] || { echo "!! 引擎里缺 $f：运行时模块清单变了，核对 scripts/build_bundle.sh"; exit 1; }
done
( cd "$TMP" && tar cf - \
    --exclude='gen/out' --exclude='__pycache__' \
    --exclude='gen/app.pyw' --exclude='gen/edit.pyw' \
    gen templates verbs \
    $TOOLS \
    app2/assets/vue.global.prod.js \
    models.json ) | tar xf - -C "$OUT/engine"
# project：kg_v4 的提交内容（本来就不含 app.db、uploads、web 生成物）；
# plan/ 只留 top.zs（deploy 只同步它；*.md 设计/历史文档含开发机路径字样，不随包）
cp -a "$TMP/kg_v4/." "$OUT/project/"
find "$OUT/project/plan" -name '*.md' -delete 2>/dev/null || true

# ---- 3 requirements.txt（版本钉开发机 .venv）----
VENV_PY="$REPO/.venv/bin/python"; VENV_PIP="$REPO/.venv/bin/pip"
[ -x "$VENV_PIP" ] || { echo "!! 没找到 $VENV_PIP，无法钉版本/下 wheels"; exit 1; }
FREEZE=$("$VENV_PIP" freeze)
pin(){ echo "$FREEZE" | grep -i -m1 "^$1=="; }
PYVER=$("$VENV_PY" -c 'import platform; print(platform.python_implementation(), platform.python_version())')
{
  echo "# kg_v4 运行时直接依赖（传递依赖由 pip 按 wheels/ 解出）。版本钉开发机 .venv（$PYVER）。"
  echo "# 追踪分析（audit hook + AST 闭包）：requests / PyYAML / pypdf 是懒加载（真模型 / 读YAML / 读PDF），但都要装。"
  pin Flask   | sed 's/$/   # HTTP 服务（tools\/dsl_http.py、gen\/project.py）/'
  pin Jinja2  | sed 's/$/   # 界面与代码生成模板/'
  pin PyYAML  | sed 's/$/   # verbs\/data「读YAML」（懒加载）/'
  pin requests | sed 's/$/   # tools\/zhipu.py 真模型（懒加载）/'
  pin pypdf   | sed 's/$/   # verbs\/doc「读文档」读PDF（懒加载）/'
} > "$OUT/requirements.txt"

# ---- 4 wheels（离线安装用）----
say "pip download wheels/（cp$( "$VENV_PY" -c 'import sys;print("%d%d"%sys.version_info[:2])' ) / $(uname -m)）"
if "$VENV_PIP" download -q -r "$OUT/requirements.txt" -d "$OUT/wheels"; then
  N=$( { ls "$OUT/wheels"/*.whl 2>/dev/null || true; } | wc -l )
  say "wheels：$N 个"
else
  say "!! pip download 失败（网络？）：wheels/ 留空，install.sh 会退回联网安装（写进 README 已知限制）"
fi
{
  echo "Python: $PYVER"
  echo "平台: $(uname -s) $(uname -m)，wheel 标签见文件名（cp3xx manylinux 为二进制，py3-none-any 为纯 Python）"
  echo "pip: $("$VENV_PIP" -V 2>/dev/null | awk '{print $1, $2}')"
  echo "换平台/Python 版本：联网机上 pip download -r requirements.txt -d wheels/ 换掉本目录"
  ls "$OUT/wheels"
} > "$OUT/wheels/WHEELS.txt"

# ---- 5 scripts/ ----
say "写 scripts/（install / init_data / start / stop / watch / deploy / add_teacher）"

cat > "$OUT/scripts/install.sh" <<'XEOF_INSTALL'
#!/usr/bin/env bash
# 安装：建 .venv、装依赖（离线优先 wheels/，没有再联网 PyPI）、导入自检。
# 用法：在本目录（解压出的 kg_v4_bundle/ 顶层）跑：bash scripts/install.sh
# PYTHON=python3.13 可指定解释器（wheels 是按 CPython 3.13 / linux x86_64 打的，见 wheels/WHEELS.txt）。
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$HERE"
PY=${PYTHON:-python3}
"$PY" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,10) else 1)' \
  || { echo "!! 需要 Python >= 3.10（wheels 按 CPython 3.13 / linux x86_64 打的，见 wheels/WHEELS.txt）"; exit 1; }
if [ ! -x .venv/bin/python ]; then
  echo "== 建 .venv（$PY）"
  "$PY" -m venv .venv
fi
if [ -n "$(ls wheels/*.whl 2>/dev/null)" ]; then
  echo "== 离线安装依赖（wheels/）"
  .venv/bin/python -m pip install --no-index --find-links wheels -r requirements.txt
else
  echo "== wheels/ 为空，改联网安装（PyPI）"
  .venv/bin/python -m pip install -r requirements.txt
fi
echo "== 导入自检"
.venv/bin/python - <<'XPY'
import flask, jinja2, yaml, requests, pypdf
from importlib.metadata import version
print("依赖自检 OK，Flask", version("flask"))
XPY
echo "装好了。下一步："
echo "  新机器：KG_PASSWORD='口令' bash scripts/init_data.sh   # 建库 + 建管理员"
echo "  迁移旧库：把现有 app.db（及 uploads/）放进 data/，见 README.md「迁移现有数据」"
# deploy.sh 的 wait_ready/deploy/watch 依赖这些命令；缺了提前报，免得上线中途走回滚
for c in curl flock setsid sha256sum ss ps stat; do
  command -v "$c" >/dev/null 2>&1 || { echo "!! 缺命令 $c（装 iproute2/coreutils/curl 后重跑）"; exit 1; }
done
echo "依赖命令检查 OK（curl/flock/setsid/sha256sum/ss/ps/stat）"
XEOF_INSTALL

cat > "$OUT/scripts/add_teacher.py" <<'XEOF_ADDTEACHER'
#!/usr/bin/env python
"""建教师/学生账号（不灌内容）。等同 app/setup/init_data.py 的 make_teacher。
口令从环境变量读，不进命令行历史：
    KG_PASSWORD='口令' .venv/bin/python scripts/add_teacher.py 用户名 [显示名] [--role student]
数据目录默认 <bundle>/data，可 --data 路径 指定。账号已存在则不动；库不存在先按 project/entities 建库。"""
import os, sqlite3, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent      # bundle 顶层
sys.path.insert(0, str(HERE / "engine"))
from gen.project import ensure_db          # noqa: E402
from tools.auth import hash_password       # noqa: E402

argv = sys.argv[1:]
data = HERE / "data"
if "--data" in argv:
    i = argv.index("--data")
    data = Path(argv[i + 1])
    del argv[i:i + 2]
role = "teacher"
if "--role" in argv:
    i = argv.index("--role")
    if i + 1 < len(argv):
        role = argv[i + 1]
        del argv[i:i + 2]
args = [a for a in argv if not a.startswith("--")]
if not args:
    sys.exit(__doc__)
user = args[0]
display = args[1] if len(args) > 1 else args[0]
pw = os.environ.get("KG_PASSWORD", "")
if not pw:
    sys.exit("!! 请用环境变量 KG_PASSWORD 给口令（不写进命令行）")
ensure_db(data.resolve())
con = sqlite3.connect(data / "app.db")
try:
    if con.execute("select 1 from account_user where username=?", (user,)).fetchone():
        print(f"账号 {user} 已存在，没动")
        sys.exit(0)
    con.execute("INSERT INTO account_user(username,password_hash,display_name,role,disabled,created_at) "
                "VALUES(?,?,?,?,0,?)",
                (user, hash_password(pw), display, role, time.strftime("%Y-%m-%d %H:%M:%S")))
    con.commit()
    print(f"建了{role}账号 {user}（{data/'app.db'}）")
finally:
    con.close()
XEOF_ADDTEACHER

cat > "$OUT/scripts/init_data.sh" <<'XEOF_INIT'
#!/usr/bin/env bash
# 新机器初始化数据目录（默认 <bundle>/data）：
#   - 没有 app.db 时按 project/entities 建空库；
#   - 建首个教师账号（口令走环境变量 KG_PASSWORD，不进命令行）。
# 用法：KG_PASSWORD='口令' bash scripts/init_data.sh [数据目录]
#       KG_ADMIN=名字 指定管理员用户名（默认 admin）。
# 注意：带旧库上线不要用本脚本建库——直接把现有 app.db（及 uploads/）拷进数据目录，
#       gen run 启动时会做增量迁移（见 README「迁移现有数据」）。
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DATA=${1:-$HERE/data}
mkdir -p "$DATA"
if [ ! -x "$HERE/.venv/bin/python" ]; then echo "!! 先跑 bash scripts/install.sh"; exit 1; fi
# 引擎目录模型：数据目录 = 项目源 + 库（gen run 在同一目录读 entities/、写 app.db 和 web/）。
# 全新机器的数据目录是空的：先把 project/ 铺进去，再建库。
if [ -z "$(ls "$DATA/entities"/*.entity 2>/dev/null)" ]; then
  echo "== 数据目录是空的：先把 project/ 铺进 $DATA（数据目录=项目源+库）"
  cp -a "$HERE/project/." "$DATA/"
fi
if [ ! -f "$DATA/app.db" ]; then
  echo "== 建空库 $DATA/app.db（按 project/entities）"
  ( cd "$HERE/engine" && "$HERE/.venv/bin/python" -c \
    'import sys; from pathlib import Path; sys.path.insert(0, "."); from gen.project import ensure_db; print(ensure_db(Path(sys.argv[1]).resolve()))' "$DATA" )
else
  echo "== $DATA/app.db 已存在，不重建"
fi
if [ -z "${KG_PASSWORD:-}" ]; then
  echo "!! 没给 KG_PASSWORD：跳过建账号。之后：KG_PASSWORD='口令' .venv/bin/python scripts/add_teacher.py 管理员名"
else
  U=${KG_ADMIN:-admin}
  KG_PASSWORD="$KG_PASSWORD" "$HERE/.venv/bin/python" "$HERE/scripts/add_teacher.py" "$U" 管理员 --data "$DATA"
fi
echo "初始化完成。启动：bash scripts/start.sh（默认 127.0.0.1:8119）"
XEOF_INIT

# 可选配置文件样板：拷成顶层 bundle.conf 生效。:= 只在变量还没有时赋值，环境变量优先。
cat > "$OUT/scripts/bundle.conf.example" <<'XEOF_CONF'
# 拷成 bundle 顶层 bundle.conf 后生效（被 start/stop/watch/deploy 自动加载）。
# 写法用 :=：只在变量还没有时赋值——同名环境变量优先于本文件。
# 数据目录（默认 <bundle>/data）
# : ${DATA_DIR:=$HERE/data}
# 服务端口 / 监听地址（对外服务务必保持 127.0.0.1 + 反向代理，见 README）
# : ${PORT:=8119}
# : ${HOST:=127.0.0.1}
# 运行时目录（pid/日志/锁，默认 <bundle>/run）
# : ${RUN_DIR:=$HERE/run}
# 备份目录（deploy.sh 用，默认 <bundle>/backups）
# : ${BACKUPS:=$HERE/backups}
# 看门狗间隔秒数
# : ${KG_INTERVAL:=60}
# 真模型：置 1 并配好 engine/config.json（或环境变量 ZHIPU_API_KEY）才生效；默认假模型
# : ${REAL:=}
# 附加给 gen run 的参数，例如 HTTPS 反代时：
# : ${EXTRA_ARGS:=--安全cookie}
XEOF_CONF

# 真模型配置样板：只有键名和占位值，不含密钥。不打包任何 config.json。
cat > "$OUT/scripts/config.example.json" <<'XEOF_CFG'
{
  "_说明": "要真模型时：拷成 engine/config.json 再填值，然后 REAL=1 bash scripts/start.sh；没有它就是假模型（回复带 [模拟回复]），页面全部可演示。也可以不建文件，改用环境变量 ZHIPU_API_KEY / ZHIPU_MODEL / ZHIPU_BASE_URL。config.json 含密钥：不要提交、不要打进压缩包、不要发给别人。",
  "api_key": "<填你的 API Key>",
  "model": "<模型名，不写则按 engine/models.json 的档位>",
  "base_url": "https://open.bigmodel.cn/api/paas/v4",
  "timeout": 60,
  "temperature": 0.7
}
XEOF_CFG

cat > "$OUT/scripts/start.sh" <<'XEOF_START'
#!/usr/bin/env bash
# 幂等启动 kg_v4 服务：已在跑就什么都不做；掉线则拉起（带退避、日志轮转）。
# 前台调试：FOREGROUND=1 bash scripts/start.sh（Ctrl+C 停，不写看门狗日志）。
# 可配置：环境变量 > bundle.conf（拷 scripts/bundle.conf.example 到顶层改名）> 默认值。
#   DATA_DIR（默认 <bundle>/data）  PORT（8119）  HOST（127.0.0.1）  RUN_DIR（<bundle>/run）
#   REAL=1 真模型（需 engine/config.json 或环境变量 ZHIPU_API_KEY；两者都没有就按假模型起并记日志）
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[ -f "$HERE/bundle.conf" ] && . "$HERE/bundle.conf"
DATA=${DATA_DIR:-$HERE/data}
PORT=${PORT:-8119}
HOST=${HOST:-127.0.0.1}
RUN=${RUN_DIR:-$HERE/run}
ENGINE=$HERE/engine
PY=$HERE/.venv/bin/python
PIDF=$RUN/server.pid; LOG=$RUN/server.log; WLOG=$RUN/watch.log; HIST=$RUN/starts.hist
MAXSTART=3; WINDOW=600; MAXLOG=$((20*1024*1024)); KEEP=3
export TZ=${TZ:-Asia/Tokyo}
# 供 cli:claude / cli:zcode 后端找本机 claude/zcode 可执行文件（同正式 start.sh 的做法）
export PATH="/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin:$PATH"
say(){ echo "$(date '+%F %T') [start.sh] $*" >> "$WLOG"; }
mkdir -p "$RUN"
exec 9>"$RUN/start.lock"; flock -n 9 || exit 0
[ -x "$PY" ] || { echo "!! 没找到 $PY：先 bash scripts/install.sh"; exit 1; }
[ -f "$DATA/app.db" ] || { echo "!! 没找到 $DATA/app.db：先 bash scripts/init_data.sh，或把现有库放进数据目录（README「迁移现有数据」）"; exit 1; }

alive(){ # PID 文件里的进程还活，且命令行是 gen run <DATA>
  local p; p=$(cat "$PIDF" 2>/dev/null) || return 1
  [[ $p =~ ^[0-9]+$ ]] && kill -0 "$p" 2>/dev/null || return 1
  local c; c=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null) || return 1
  [[ $c == *" -m gen run $DATA "* ]]
}

rotate(){ # server.log 超 20MB：.1 .2 .3 滚动，保留 3 份（copytruncate，运行中的服务仍持有同一 fd）
  local sz; sz=$(stat -c %s "$LOG" 2>/dev/null || echo 0)
  [ "$sz" -gt "$MAXLOG" ] || return 0
  rm -f "$LOG.$KEEP"
  for ((i=KEEP-1;i>=1;i--)); do [ -e "$LOG.$i" ] && mv "$LOG.$i" "$LOG.$((i+1))"; done
  cp "$LOG" "$LOG.1" && : > "$LOG"
  say "日志轮转（$sz 字节）"
}

if alive; then rotate; exit 0; fi

now=$(date +%s)
recent=$( { awk -v n="$now" -v w="$WINDOW" 'n-$1<w' "$HIST" 2>/dev/null || true; } | wc -l )
if [ "$recent" -ge "$MAXSTART" ]; then
  say "退避：最近 $((WINDOW/60)) 分钟已拉起 $recent 次（上限 $MAXSTART），暂停拉起；窗口过去后自动恢复，或排查后清空 $HIST 再手动 start.sh"
  exit 0
fi
awk -v n="$now" -v w="$WINDOW" 'n-$1<w' "$HIST" 2>/dev/null > "$HIST.tmp" || true; echo "$now" >> "$HIST.tmp"; mv "$HIST.tmp" "$HIST"
rotate

ARGS=(-m gen run "$DATA" --登录 --port "$PORT" --host "$HOST" --不开浏览器)
# 附加参数（bundle.conf 的 EXTRA_ARGS，如 --安全cookie；有意不加引号让多参数分词）
[ -n "${EXTRA_ARGS:-}" ] && ARGS+=(${EXTRA_ARGS})
if [ -n "${REAL:-}" ]; then
  if [ -f "$ENGINE/config.json" ] || [ -n "${ZHIPU_API_KEY:-}" ]; then
    ARGS+=(--real)
  else
    say "REAL=1 但既没有 $ENGINE/config.json 也没有 ZHIPU_API_KEY：按假模型起（要真模型：拷 scripts/config.example.json 为 engine/config.json 填好再重启）"
  fi
fi

cd "$ENGINE"
if [ -n "${FOREGROUND:-}" ]; then
  exec "$PY" "${ARGS[@]}"
fi
# 后台：关掉 3–255 号描述符再 setsid 起新会话（不经调用方的管道/锁；PID 文件记 setsid exec 后的同一 PID）
setsid bash -c 'for fd in $(seq 3 255); do eval "exec $fd>&-" 2>/dev/null; done; exec "$0" "$@"' \
  "$PY" "${ARGS[@]}" >> "$LOG" 2>&1 < /dev/null 8>&- 9>&- &
echo $! > "$PIDF"
say "已拉起 PID $(cat "$PIDF")（最近窗口内第 $((recent+1)) 次）http://$HOST:$PORT/"
XEOF_START

cat > "$OUT/scripts/stop.sh" <<'XEOF_STOP'
#!/usr/bin/env bash
# 按 PID 文件停服务（进程组 TERM，kill -0 确认；10 秒没退则 KILL）。
# 注意：看门狗（watch.sh）在跑的话 ≤KG_INTERVAL 秒会拉回来；要真停先停看门狗（见 README）。
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[ -f "$HERE/bundle.conf" ] && . "$HERE/bundle.conf"
RUN=${RUN_DIR:-$HERE/run}
PIDF=$RUN/server.pid
p=$(cat "$PIDF" 2>/dev/null)
[[ $p =~ ^[0-9]+$ ]] || { echo "没有有效 PID 文件"; exit 0; }
kill -0 "$p" 2>/dev/null || { echo "进程 $p 已不在"; rm -f "$PIDF"; exit 0; }
kill -TERM -- "-$p" 2>/dev/null || kill -TERM "$p" 2>/dev/null || true
for i in $(seq 1 20); do kill -0 "$p" 2>/dev/null || { echo "已停止 $p"; rm -f "$PIDF"; exit 0; }; sleep 0.5; done
kill -KILL -- "-$p" 2>/dev/null || kill -KILL "$p" 2>/dev/null || true
sleep 1
kill -0 "$p" 2>/dev/null && { echo "!! 仍未退出 $p"; exit 1; } || { echo "已强制停止 $p"; rm -f "$PIDF"; }
XEOF_STOP

cat > "$OUT/scripts/watch.sh" <<'XEOF_WATCH'
#!/usr/bin/env bash
# 常驻看门狗：每 KG_INTERVAL（默认 60）秒跑一次 start.sh；flock 单实例。
# 起法（setsid -f 自己 fork、父进程立即返回；不要再加 &）：
#   cd <bundle>/run 2>/dev/null || mkdir -p <bundle>/run && cd <bundle>/run
#   for fd in $(seq 3 255); do eval "exec $fd>&-" 2>/dev/null; done
#   exec setsid -f nohup ../scripts/watch.sh >> watch.log 2>&1 < /dev/null
# （deploy.sh 会自动起/停看门狗，一般不用手动。）
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[ -f "$HERE/bundle.conf" ] && . "$HERE/bundle.conf"
RUN=${RUN_DIR:-$HERE/run}
mkdir -p "$RUN"
exec 8>"$RUN/watch.lock"; flock -n 8 || exit 0
D=$(dirname "$(readlink -f "$0")")
while :; do bash "$D/start.sh" >> "$RUN/watch.log" 2>&1 < /dev/null; sleep "${KG_INTERVAL:-60}"; done
XEOF_WATCH

cat > "$OUT/scripts/deploy.sh" <<'XEOF_DEPLOY'
#!/usr/bin/env bash
# kg_v4 标准上线脚本（bundle 版，改自正式服务的 deploy.sh）：用新版 project/ 目录同步数据目录。
#
#   bash scripts/deploy.sh [--dry-run] <新版project目录> [标签]
#
# 流程：停看门狗（按 watch.lock 找进程组，不用 pgrep -f）→ stop.sh → 数据目录整份备份到
#       backups/kg_v4_<时间>_before_<标签>（.auth_secret 只拷不读，按大小/权限/修改时间核对）
#       + diff/cmp 校验 → 同步约定目录（contracts entities queries routes scripts services ui
#       setup + plan/top.zs；只覆盖/新增，不删数据目录里多出的文件）→ start.sh → GET / 200
#       → 起看门狗（setsid -f：自己 fork 父进程立即返回；标准输入输出全部重定向到文件，
#         关掉 3 号以上描述符，不经 tee/管道，脚本立即返回）→ 打印停服秒数、备份路径。
# --dry-run：只核对源目录、列出要同步的差异、找到的看门狗/服务进程；不停服、不备份、不同步。
# 停服之后任何一步失败：先从本次备份还原约定目录，再拉起服务（确认 GET / 200 且 server.pid
#       就是监听端口的进程）之后才起看门狗，退出码 1。
#
# 可配置：环境变量 > bundle.conf > 默认。DATA_DIR RUN_DIR PORT BACKUPS
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[ -f "$HERE/bundle.conf" ] && . "$HERE/bundle.conf"
RUN=${RUN_DIR:-$HERE/run}
D=${DATA_DIR:-$HERE/data}
PORT=${PORT:-8119}
BK=${BACKUPS:-$HERE/backups}
DIRS="contracts entities queries routes scripts services ui setup"
FILES="plan/top.zs"
mkdir -p "$RUN"

DRY=0
[ "${1:-}" = "--dry-run" ] && { DRY=1; shift; }
SRC=${1:-}; [ -n "$SRC" ] || { echo "用法：bash scripts/deploy.sh [--dry-run] <新版project目录> [标签]"; exit 2; }
SRC=$(cd "$SRC" && pwd) || { echo "!! 源目录不存在：$SRC"; exit 2; }
for d in $DIRS; do [ -d "$SRC/$d" ] || { echo "!! 源目录里没有 $d：传的应是新版包的 project/ 目录"; exit 2; }; done
for f in $FILES; do [ -f "$SRC/$f" ] || { echo "!! 源目录里没有 $f"; exit 2; }; done
[ -x "$HERE/.venv/bin/python" ] || { echo "!! 先 bash scripts/install.sh"; exit 1; }
[ -f "$D/app.db" ] || { echo "!! 数据目录 $D 没有 app.db（先 bash scripts/init_data.sh 或迁移现有库）"; exit 1; }
TAG=${2:-$(date +%Y%m%d-%H%M%S)}
[[ $TAG =~ ^[A-Za-z0-9._-]+$ ]] || { echo "!! 标签只能是字母数字和 . _ -：$TAG"; exit 2; }
TS=$(date +%Y%m%d-%H%M%S); B=$BK/kg_v4_${TS}_before_${TAG}
say(){ echo "[$(date '+%T')] $*"; }
STAGE=pre      # pre：还没停服；stopped：已停服、正式目录没动；syncing：开始改正式目录；up：已起服
die(){
  echo "!! $*"
  case $STAGE in
    stopped|syncing)
      if [ $STAGE = syncing ]; then
        echo "!! 从备份 $B 还原约定目录"
        for d in $DIRS; do rm -rf "${D:?}/$d" && cp -a "$B/$d" "$D/$d" || echo "!! 还原 $d 失败"; done
        for f in $FILES; do cp -a "$B/$f" "$D/$f" || echo "!! 还原 $f 失败"; done
      fi
      echo "!! 拉起原服务（确认就绪之后才起看门狗，避免两者同一秒各拉一个）"
      start_server
      if wait_ready 120; then say "恢复：server.pid $(cat "$RUN/server.pid") 就是监听 $PORT 的进程，GET / 200"
      else
        echo "!! 恢复：服务 120 秒内没就绪（server.pid=$(cat "$RUN/server.pid" 2>/dev/null)，监听 $PORT 的是 $(port_pid || echo 没有进程)）；看 $RUN/server.log、watch.log"
        tail -3 "$RUN/watch.log" 2>/dev/null | grep -q '退避' && echo "!! watch.log 里是「退避」：start.sh 的 10 分钟 3 次拉起上限被触发（部署+恢复连续拉起会撞上），不是服务坏；窗口过去后看门狗自动恢复，不要手动清 starts.hist"
      fi
      start_watch || echo "!! 恢复：看门狗没起来" ;;
  esac
  exit 1
}
# 关掉 3–255 号描述符再跑：否则服务会继承 deploy.lock（7 号）和调用方的管道
start_server(){ ( for fd in $(seq 3 255); do eval "exec $fd>&-" 2>/dev/null; done; exec bash "$HERE/scripts/start.sh" ); }
# 子 shell 里关描述符、全部重定向到文件，再 exec setsid -f：fork 出新会话后父进程立即退出，
# 不留任何握着调用方管道的进程
start_watch(){
  ( cd "$RUN" || exit 1
    for fd in $(seq 3 255); do eval "exec $fd>&-" 2>/dev/null; done
    exec setsid -f nohup "$HERE/scripts/watch.sh" >> "$RUN/watch.log" 2>&1 < /dev/null )
  for i in $(seq 1 10); do lock_free || return 0; sleep 0.3; done
  return 1
}
# 看门狗 = 握着 watch.lock 的进程（watch.sh 本身和它正在 sleep/跑 start.sh 的子进程）。
# 不用 pgrep -f（会匹配到自己）；按 /proc/*/fd 找，返回它们的进程组号（去重，排除服务和本脚本的组）。
watch_pgids(){
  local lock p fd pg sp me
  lock=$(readlink -f "$RUN/watch.lock"); sp=$(cat "$RUN/server.pid" 2>/dev/null); me=$(ps -o pgid= $$ | tr -d ' ')
  for p in /proc/[0-9]*; do
    for fd in "$p"/fd/*; do
      [ "$(readlink "$fd" 2>/dev/null)" = "$lock" ] || continue
      pg=$(ps -o pgid= "${p#/proc/}" 2>/dev/null | tr -d ' ')
      [ -n "$pg" ] && [ "$pg" != "$sp" ] && [ "$pg" != "$me" ] && echo "$pg"
      break
    done
  done | sort -u
}
lock_free(){ flock -n "$RUN/watch.lock" -c true; }
# 监听 $PORT 的进程号（ss 拿不到就是空串）
port_pid(){ ss -ltnp "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]\+' | head -1 | cut -d= -f2; }
# 服务就绪 = server.pid 里的进程活着、就是监听 $PORT 的进程、GET / 200。
# 只看 GET 200 不行：孤儿服务占着端口时新服务起不来，200 是孤儿答的（正式部署踩过）。参数=轮询次数（0.5 秒一次）。
wait_ready(){
  local i p c
  for i in $(seq 1 "${1:-120}"); do
    p=$(cat "$RUN/server.pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null && [ "$(port_pid)" = "$p" ]; then
      c=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" 2>/dev/null)
      [ "$c" = 200 ] && return 0
    fi
    sleep 0.5
  done
  return 1
}

# 单实例：两个人同时上线会互相停对方起的服务
exec 7>"$RUN/deploy.lock"; flock -n 7 || die "另一个 deploy.sh 正在跑（$RUN/deploy.lock）"

echo "== 要同步的差异（源 $SRC vs 数据目录 $D）"
n=0
for d in $DIRS; do
  while IFS= read -r l; do echo "  $l"; n=$((n+1)); done < <(diff -rq "$SRC/$d" "$D/$d" 2>&1 | grep -v "^Only in $D/")
done
for f in $FILES; do cmp -s "$SRC/$f" "$D/$f" || { echo "  $f 不同"; n=$((n+1)); }; done
echo "  共 $n 处"
extra=$(for d in $DIRS; do diff -rq "$SRC/$d" "$D/$d" 2>&1 | grep "^Only in $D/"; done)
[ -n "$extra" ] && { echo "  （数据目录里有、源里没有的文件，不删，只列出）"; echo "$extra" | sed 's/^/    /'; }

WP=$(watch_pgids | tr '\n' ' '); SP=$(cat "$RUN/server.pid" 2>/dev/null)
say "看门狗进程组：${WP:-（没找到）}；服务 PID：${SP:-（没有）}；监听 $PORT：$(port_pid || echo 无)"
if [ $DRY = 1 ]; then
  echo "== --dry-run：不停服、不备份、不同步。真跑时备份到 $B"
  exit 0
fi

# 1 停看门狗（进程组）
for g in $WP; do kill -TERM -- "-$g" 2>/dev/null; done
for i in $(seq 1 20); do lock_free && break; sleep 0.5; done
lock_free && say "看门狗已停（watch.lock 可拿到）" || die "watch.lock 仍被占，看门狗没停，未停服"

# 2 停服
T0=$(date +%s.%N); say "停服开始"
bash "$HERE/scripts/stop.sh"
if [ -n "$SP" ] && kill -0 "$SP" 2>/dev/null; then
  start_watch; die "服务 $SP 没停（服务仍在原样运行，已重新起看门狗）"
fi
STAGE=stopped
Q=$(port_pid); [ -z "$Q" ] || die "停服后端口 $PORT 仍被 PID $Q 占着（不是本服务，先处理它；服务和看门狗即将拉回）"

# 3 完整备份（cp -a；.auth_secret 只拷不读，不进 diff，按 大小/权限/修改时间 核对）
mkdir -p "$BK"; cp -a "$D" "$B" || die "备份失败（数据目录没动）"
(cd "$D" && sha256sum app.db) > "$B.app.db.sha256"
diff -rq --exclude=.auth_secret "$D" "$B" > /dev/null && say "备份与原目录一致（diff -rq，除 .auth_secret）" || die "备份不一致 $B（数据目录没动）"
cmp -s "$D/app.db" "$B/app.db" && say "app.db 字节一致" || die "app.db 备份不一致（数据目录没动）"
if [ -e "$D/.auth_secret" ]; then
  [ "$(stat -c '%s %a %Y' "$D/.auth_secret")" = "$(stat -c '%s %a %Y' "$B/.auth_secret")" ] \
    && say ".auth_secret 已拷（大小/权限/修改时间一致，未读内容）" || die ".auth_secret 备份不一致（数据目录没动）"
fi

# 4 同步约定目录（只覆盖/新增，不删数据目录里多出的文件）
STAGE=syncing
for d in $DIRS; do cp -a "$SRC/$d/." "$D/$d/" || die "同步 $d 失败"; done
for f in $FILES; do cp -a "$SRC/$f" "$D/$f" || die "同步 $f 失败"; done
bad=0
for d in $DIRS; do diff -rq "$SRC/$d" "$D/$d" | grep -v "^Only in $D/" && bad=1; done
for f in $FILES; do cmp -s "$SRC/$f" "$D/$f" || { echo "  $f 不一致"; bad=1; }; done
[ $bad = 0 ] && say "同步后逐目录与源一致" || die "同步不一致"

# 5 起服
STAGE=up
LOG0=$(stat -c %s "$RUN/server.log" 2>/dev/null || echo 0)
start_server
P=$(cat "$RUN/server.pid" 2>/dev/null); say "新 PID $P"
if wait_ready 120; then c=200
else c=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" 2>/dev/null); fi
T1=$(date +%s.%N)
DOWN=$(awk -v a="$T0" -v b="$T1" 'BEGIN{printf "%.1f", b-a}')
RC=0
if [ "$c" = 200 ]; then say "GET / 200（$P 就是监听 $PORT 的进程）"
else
  Q=$(port_pid)
  if [ -n "$Q" ] && [ "$Q" != "$P" ]; then echo "!! 端口 $PORT 被 PID $Q 占着（不是新服务 $P）：GET $c 不可信，新服务可能没起来"
  elif ! kill -0 "$P" 2>/dev/null; then echo "!! 新服务 $P 已退出（看 server.log；回滚：从 $B 拷回约定目录后 bash scripts/start.sh）"
  else echo "!! 新版本 120 秒内 GET / 不是 200（看 server.log；回滚：从 $B 拷回约定目录后 bash scripts/start.sh）"; fi
  RC=1
fi

# 6 起看门狗（新版本没起来也照样起：它每 60 秒重试 start.sh，有退避）
if start_watch; then say "看门狗已在跑（watch.lock 被占用），进程组 $(watch_pgids | tr '\n' ' ')"
else echo "!! watch.lock 空闲，看门狗没起来（手动起法见 scripts/watch.sh 头注）"; RC=1; fi

# 7 启动日志里的警告
NEW=$(tail -c +$((LOG0+1)) "$RUN/server.log" 2>/dev/null)
echo "== 本次启动日志：[迁移警告] $(grep -c '迁移警告' <<<"$NEW") 行，Traceback $(grep -c 'Traceback' <<<"$NEW") 处"
grep -E '迁移|Traceback' <<<"$NEW" | head -5 | sed 's/^/  /'

echo "== 结果：源 $SRC，GET / $c，停服秒数 $DOWN，备份 $B"
exit $RC
XEOF_DEPLOY

# ---- 6 README.md（中文，新机器上线完整步骤）----
cat > "$OUT/README.md" <<'XEOF_README'
# kg_v4 独立上线包

自包含文件夹：拿到一台新机器，解压 → 装依赖 → 初始化（或迁移旧库）→ 启动，不依赖开发机上的任何东西。
默认假模型（回复带 [模拟回复]），页面全部可演示；配好密钥可切真模型。
引擎基线、打包时间、Python 版本见 `VERSION`；打包脚本在引擎仓库 `scripts/build_bundle.sh`，可重复打包。

## 目录
| 路径 | 内容 |
|---|---|
| `engine/` | 引擎最小运行集（`python -m gen run` 实际 import/读取的，经追踪分析验证）：`gen/`（不含 out/ 与编辑器 .pyw）、`tools/` 31 个运行时模块（含 cbatch/zcode_tool：--real 的 cli:claude/cli:zcode 后端懒加载，缺了请求直接断）、`templates/`（db+frontend 的 .j2）、`gen/templates/`、`verbs/` 全量（动词包懒加载，裁不动）、`app2/assets/vue.global.prod.js`（本地 Vue）、`models.json`（模型档位说明，无密钥） |
| `project/` | kg_v4 项目源：contracts entities queries routes scripts services setup ui plan/top.zs req.md README.md。**不含** app.db、uploads、web 生成物；plan/ 只带 top.zs（设计 .md 不随包） |
| `scripts/` | `install.sh`（装依赖）· `init_data.sh`（建库+建管理员）· `add_teacher.py`（建账号）· `start.sh`（幂等启动）· `stop.sh` · `watch.sh`（看门狗）· `deploy.sh`（上线）· `config.example.json`（真模型样板）· `bundle.conf.example`（配置样板） |
| `wheels/` | 离线依赖 wheel，平台见 `WHEELS.txt` |
| `requirements.txt` | 直接依赖，精确版本（传递依赖由 pip 按 wheels/ 解出） |
| `data/` | 数据目录（初始化或迁移后出现）：`app.db`、`uploads/`、`web/`（每次启动重新编译的生成物）、`.auth_secret`（首次启动自动生成，登录签名密钥） |
| `run/` | 运行时产生：server.pid、server.log（超 20MB 自动滚动留 3 份）、watch.log、starts.hist、各锁文件 |
| `backups/` | deploy.sh 每次上线的完整备份 |

**不会打进包的东西**：config.json、.auth_secret、任何密钥、*.db、uploads、web 生成物、日志。

## 要求
- Linux x86_64，Python >= 3.10。wheels/ 按 CPython 3.13 / manylinux 打的（markupsafe、pyyaml、charset_normalizer 是二进制 wheel，其余纯 Python）。换平台或 Python 版本：在联网机上 `pip download -r requirements.txt -d wheels/` 重打 wheels/。
- wheels/ 齐全时安装全程不用联网；`wheels/` 为空则 install.sh 退回从 PyPI 装。

## 新机器上线（完整步骤）
### 1. 安装
    tar xzf kg_v4_bundle.tar.gz && cd kg_v4_bundle
    bash scripts/install.sh          # 建 .venv，离线优先装依赖，导入自检

### 2. 数据（二选一）
**全新机器**（空库）：
    KG_PASSWORD='管理员口令' bash scripts/init_data.sh     # 建空库 + 建管理员（用户名默认 admin，KG_ADMIN=名字 可改）
    KG_PASSWORD='口令' .venv/bin/python scripts/add_teacher.py 学生名 --role student   # 需要时再建学生/教师

**迁移现有数据**：停掉旧服务 → 把旧数据目录里的 `app.db`（及 `app.db-wal`/`-shm` 若有）拷进 `data/` → 要上传文件就拷 `uploads/` → 想沿用登录会话再拷 `.auth_secret`（不拷则所有人重新登录）→ 启动时自动做增量迁移（加列），迁移不了的结构变化看启动日志的「迁移警告」。

### 3. 配置（可选）
默认假模型。要真模型：`cp scripts/config.example.json engine/config.json` 填 `api_key`（字段说明在样板文件里），然后 `REAL=1 bash scripts/start.sh`；或用环境变量 `ZHIPU_API_KEY / ZHIPU_MODEL / ZHIPU_BASE_URL`（不用建文件）。
注意档位：引擎 models.json 里 快/平衡/强 默认走本机 claude CLI（cli:claude，需 PATH 上有 claude，start.sh 已把 ~/.local/bin 加进 PATH），没有 claude 时自动落到 api:zhipu（需要上面配好的 key）；纯 zhipu 用法在 config.json 写 `model` 即可。
端口、数据目录等：拷 `scripts/bundle.conf.example` 到顶层改名 `bundle.conf` 改注释掉的行，或用同名环境变量（环境变量优先）。

### 4. 启动 / 停止
    bash scripts/start.sh                 # 幂等后台启动，默认 127.0.0.1:8119，日志 run/server.log
    FOREGROUND=1 bash scripts/start.sh    # 前台跑（调试用，Ctrl+C 停）
    bash scripts/stop.sh                  # 停（进程组 TERM，kill -0 确认，10 秒不退 KILL）

### 5. 看门狗（掉线自动拉起，可选但建议）
    mkdir -p run && cd run
    for fd in $(seq 3 255); do eval "exec $fd>&-" 2>/dev/null; done
    exec setsid -f nohup ../scripts/watch.sh >> watch.log 2>&1 < /dev/null
每 KG_INTERVAL（默认 60）秒跑一次 start.sh，flock 单实例；start.sh 自带退避（10 分钟内最多拉起 3 次，防崩溃循环，watch.log 写「退避」）。
**要真停服务**：先停看门狗——按 `run/watch.lock` 找握着它的进程（`ls -l /proc/*/fd/* 2>/dev/null | grep watch.lock`）kill 其进程组，再 `bash scripts/stop.sh`；只 stop.sh 会被看门狗拉回来。

### 6. 更新上线
新版包在开发机用 `bash scripts/build_bundle.sh` 打出后，拷到目标机解压，然后：
    bash scripts/deploy.sh --dry-run /解压路径/kg_v4_bundle/project 某标签    # 先看差异，不停服
    bash scripts/deploy.sh /解压路径/kg_v4_bundle/project 某标签
流程：停看门狗 → 停服 → 数据目录整份备份到 backups/（校验后才开始改）→ 同步 contracts entities queries routes scripts services ui setup + plan/top.zs（只覆盖/新增，数据目录多出的文件只列出不删）→ 起服等 GET / 200（且确认 server.pid 就是监听端口的进程）→ 起看门狗 → 打印迁移警告/Traceback 数、停服秒数、备份路径。停服后任何一步失败自动从本次备份还原并拉回原服务。

### 7. 备份 / 回滚
- 手工备份：`bash scripts/stop.sh` 后 `cp -a data backups/data_$(date +%F_%H%M)`；热备可用 sqlite backup API：`python -c "import sqlite3; s=sqlite3.connect('data/app.db'); d=sqlite3.connect('backups/bak.db'); s.backup(d)"`。
- 回滚某次上线：`bash scripts/stop.sh` → `cp -a backups/kg_v4_<时间>_before_<标签>/. data/` → `bash scripts/start.sh`。

## 对外服务：只监听 127.0.0.1 + 反向代理
默认 `HOST=127.0.0.1`，服务不出网。给外面人用：用 nginx/caddy 反代到 `127.0.0.1:8119`，配 HTTPS；走 HTTPS 时把 `bundle.conf` 里的 `EXTRA_ARGS` 设为 `--安全cookie`（cookie 只经 https 传）。**不要**直接 `HOST=0.0.0.0` 裸奔：这是 Flask 开发服务器，且 `--real` 模式下接口会花模型额度。反向代理层建议加访问控制（如基本认证/IP 白名单）。

## 已知限制
1. 知识图谱节点图要联网加载 3 个 CDN（unpkg 的 vue-flow 两个、cdnjs 的 dagre），断网时该块留空（页面有降级），其余功能正常；Vue 本体已本地（engine/app2/assets/）。
2. Flask 开发服务器，适合小范围（一个班/一个学校）使用，扛不了大并发。
3. wheels/ 绑定 CPython 3.13 / linux x86_64；换平台要重新 pip download（见 wheels/WHEELS.txt）。
4. 退出登录只是删 cookie：签发的令牌在过期（7 天）前一直有效，服务器无法吊销单个会话；删除/换 `data/.auth_secret` 等于让所有人重新登录。
5. 登录限流：同一用户名或同一来源连续失败 5 次锁 5 分钟（内存计数，重启清零）。
6. 本机不是 systemd 时，看门狗是 setsid 常驻进程：机器重启后要重新起（放进开机脚本或手动按第 5 步起）。
7. deploy.sh 的同步不删除数据目录里多出的文件（防误删），确认不要的文件要手动删。
8. deploy.sh 的备份是数据目录整份拷（含 app.db、uploads、web），但只在上线时做：平时请自行定期备份 data/app.db 与 data/uploads/。
XEOF_README

# ---- 7 VERSION / 权限 ----
cat > "$OUT/VERSION" <<XEOF_VERSION
包: kg_v4_bundle（engine + project + 离线依赖，可单独上线）
引擎提交: $TAG（引擎仓库 HEAD，origin/master）
打包时间: $PACK_TIME
Python: $PYVER（wheels 标签见 wheels/WHEELS.txt）
打包脚本: 引擎仓库 scripts/build_bundle.sh（本目录由它生成）
最小运行集分析: 引擎仓库 data/reports/kg_K178_glm.md（K178；方法与验证见报告）
XEOF_VERSION
chmod +x "$OUT"/scripts/*.sh
chmod 644 "$OUT/scripts/config.example.json" "$OUT/scripts/bundle.conf.example"

# ---- 8 收尾检查：密钥/数据库/开发机路径不得进包 ----
say "收尾检查"
bad=$(find "$OUT" \( -name 'config.json' -o -name '.auth_secret' -o -name '*.db' -o -name '*.db-wal' -o -name '*.db-shm' -o -name '*.pyc' \) 2>/dev/null)
[ -z "$bad" ] || { echo "!! 包里发现不该有的文件：$bad"; exit 1; }
grep -q '<填你的 API Key>' "$OUT/scripts/config.example.json" || { echo "!! config 样板里不是占位值，不能打包"; exit 1; }
# 路径检查覆盖会随包发出去的全部文本；匹配本机特征路径（/workspace、agent_mcp、/home/box）。
# engine 里泛化的文档示例（如 zcode_tool 的 /home/<user>）不算泄露。
hits=$( { grep -rIl -e '/workspace' -e 'agent_mcp' -e '/home/box' \
    "$OUT/engine" "$OUT/scripts" "$OUT/project" "$OUT/requirements.txt" "$OUT/wheels/WHEELS.txt" "$OUT/README.md" "$OUT/VERSION" 2>/dev/null || true; } | head -5 )
[ -z "$hits" ] || { echo "!! 包里有开发机绝对路径：$hits"; exit 1; }

# ---- 9 tar.gz ----
say "打 ${OUT}.tar.gz"
tar -czf "${OUT}.tar.gz" -C "$(dirname "$OUT")" "$(basename "$OUT")"
NE=$(find "$OUT/engine" -type f | wc -l); NP=$(find "$OUT/project" -type f | wc -l); NW=$( { ls "$OUT/wheels"/*.whl 2>/dev/null || true; } | wc -l )
say "完成：$OUT（engine $NE 文件 / project $NP 文件 / wheels $NW 个 / 共 $(find "$OUT" -type f | wc -l) 文件，$(du -sh "$OUT" | cut -f1)）"
say "压缩包：${OUT}.tar.gz（$(du -h "${OUT}.tar.gz" | cut -f1)，sha256 $(sha256sum "${OUT}.tar.gz" | cut -d' ' -f1)）"
