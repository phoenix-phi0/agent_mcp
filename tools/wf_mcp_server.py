"""流程管理 MCP 基础设施。

范围/输入拒绝统一抛 workflow_ctl.ControlError，工具装饰器原样保留；
鉴权失败及非业务异常抛 fastmcp.exceptions.ToolError。
"""
import argparse
from dataclasses import dataclass
from functools import wraps
import hmac
import os
from pathlib import Path
import re
import shlex
import sys
from types import SimpleNamespace

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from starlette.requests import Request
from starlette.responses import Response

from tools import workflow_ctl as wc
from tools import trace_server
from tools.workflow_ctl import ControlError

ROOT = Path(__file__).resolve().parents[1]


class StartupError(Exception):
    """配置不足或口令无效，不能启动服务。"""


def _encodable(value):
    if not isinstance(value, str):
        return False
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        return False
    return True


def load_key(env=None, home=None):
    """优先读取 WF_MCP_KEY，其次读取用户配置文件；错误不泄露密钥。"""
    env = os.environ if env is None else env
    path = Path.home() if home is None else Path(home)
    path = path / '.config/agent_mcp/wf_mcp.key'
    key = env.get('WF_MCP_KEY')
    if key is None:
        try:
            key = path.read_text(encoding='utf-8').strip()
        except (OSError, UnicodeError):
            key = None
    if not _encodable(key) or len(key) < 16:
        # 路径只用于给出可执行的生成命令，不输出配置值或底层异常。
        raise StartupError(
            'WF_MCP_KEY 缺失或无效（至少 16 位）。生成命令：'
            'python -c "import secrets;print(secrets.token_urlsafe(24))" > '
            + shlex.quote(str(path)) + ' && chmod 600 ' + shlex.quote(str(path)))
    return key


def load_trace_token(env=None):
    """读取 TRACE_TOKEN：至少 16 位 ASCII 字母、数字、下划线或短横线。"""
    env = os.environ if env is None else env
    token = env.get('TRACE_TOKEN')
    if not isinstance(token, str) or re.fullmatch(r'[A-Za-z0-9_-]{16,}', token) is None:
        raise StartupError('TRACE_TOKEN 缺失或无效：至少 16 位，只能含字母数字 _ -')
    return token


def _path_input(value):
    if not _encodable(value) or not value or '\x00' in value or '\\' in value:
        raise ControlError('路径无效')
    path = Path(value)
    if '..' in path.parts:
        raise ControlError('路径不能含 ..')
    return path


def parse_workdirs(env):
    """读取相对项目根的 WF_WORKDIRS 白名单，保留首个目录的顺序。"""
    raw = env.get('WF_WORKDIRS', 'workflow_demo')
    if not isinstance(raw, str):
        raise ControlError('WF_WORKDIRS 无效')
    result = []
    for item in raw.split(','):
        name = item.strip()
        path = _path_input(name)
        if path.is_absolute():
            raise ControlError('工作目录必须相对项目根')
        if name not in result:
            result.append(name)
    return result


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    base: str
    write: bool
    # repr 不包含密钥和查看器口令，避免意外日志泄漏。
    root: Path
    workdirs: tuple[Path, ...]


def resolve_workdir(workdir, cfg):
    """缺省选首个白名单目录；显式目录必须与白名单目录一致。"""
    if workdir is None:
        return cfg.workdirs[0]
    path = _path_input(workdir)
    try:
        path = (cfg.root / path).resolve()
    except (OSError, ValueError, RuntimeError):
        raise ControlError('工作目录无效') from None
    if path not in cfg.workdirs:
        raise ControlError('工作目录不在白名单')
    return path


def resolve_run(run, cfg):
    """解析运行文件名或相对项目根路径，并拒绝越界、逃逸及非 JSON 文件。"""
    path = _path_input(run)
    candidate = cfg.workdirs[0] / 'runs' / path if len(path.parts) == 1 else cfg.root / path
    try:
        resolved = candidate.resolve()
        allowed = any(resolved.parent == wd / 'runs' for wd in cfg.workdirs)
        if not allowed or resolved.suffix != '.json' or not resolved.is_file():
            raise ControlError('不是白名单 runs/ 下的已有 .json 文件')
    except (OSError, ValueError, RuntimeError):
        raise ControlError('运行路径无效') from None
    return resolved


def check_entry(workdir, entry):
    """校验工作目录下已有的 .zs 文件名，返回原文件名。"""
    path = _path_input(entry)
    if path.is_absolute() or '/' in entry or path.suffix != '.zs':
        raise ControlError('entry 必须是不含路径的 .zs 文件名')
    try:
        wd = Path(workdir).resolve()
        resolved = (wd / path).resolve()
        if resolved.parent != wd or not resolved.is_file():
            raise ControlError('entry 必须是工作目录下已有的 .zs 文件')
    except (OSError, ValueError, RuntimeError):
        raise ControlError('entry 无效') from None
    return entry


def build_server(host, port, base, write, key, token, root=None, workdirs=None):
    """构建可直接调用的工具和 FastMCP，不启动网络服务。"""
    key = load_key({'WF_MCP_KEY': key})
    token = load_trace_token({'TRACE_TOKEN': token})
    root = ROOT if root is None else Path(root).resolve()
    if workdirs is None:
        workdirs = parse_workdirs(os.environ)
    if not workdirs:
        raise ControlError('工作目录白名单不能为空')
    dirs = []
    for name in workdirs:
        path = _path_input(os.fspath(name))
        if path.is_absolute():
            raise ControlError('工作目录必须相对项目根')
        try:
            wd = (root / path).resolve()
        except (OSError, ValueError, RuntimeError):
            raise ControlError('工作目录无效') from None
        if not wd.is_relative_to(root):
            raise ControlError('工作目录不能逃逸项目根')
        if wd not in dirs:
            dirs.append(wd)
    cfg = Config(host, port, base, write, root, tuple(dirs))
    svc = SimpleNamespace(mcp=FastMCP('workflow'), tools={}, cfg=cfg)

    @svc.mcp.custom_route(base.rstrip('/') + '/{path:path}', methods=['GET', 'POST'])
    async def viewer_route(request: Request) -> Response:
        # FastMCP 把 MCP 端点排在 custom_route 前，/mcp 仍由协议层处理。
        body = bytearray()
        if request.method == 'POST':
            checked = trace_server.validate_post_request(
                request.url.path, request.headers, token, base, write)
            if not isinstance(checked, int):
                code, headers, data = checked
                return Response(content=data, status_code=code, headers=headers)
            # 不信任声明长度：chunked 或少报长度也必须受累计上限约束。
            async for chunk in request.stream():
                if len(body) + len(chunk) > trace_server._MAX_BODY:
                    code, headers, data = trace_server.respond_json(
                        {"ok": False, "error": "请求体太大或没有长度"}, 413)
                    return Response(content=data, status_code=code, headers=headers)
                body.extend(chunk)
        code, headers, body = trace_server.route(
            cfg.workdirs[0] / 'runs', request.method, request.url.path,
            request.scope['query_string'].decode('latin-1'), request.headers,
            body, token, base, write)
        return Response(content=body, status_code=code, headers=headers)

    def register(fn):
        @wraps(fn)
        def guarded(key=None, *args, **kwargs):
            if not _encodable(key) or not hmac.compare_digest(key.encode('utf-8'), secret):
                raise ToolError('鉴权失败')
            try:
                return fn(key, *args, **kwargs)
            except ControlError:
                raise
            except Exception as error:
                message = str(error)
                for credential in (configured_key, token):
                    message = message.replace(credential, '[已隐藏]')
                raise ToolError(f'内部错误：{type(error).__name__}: {message}') from None
        svc.tools[fn.__name__] = guarded
        svc.mcp.tool(guarded)
        return guarded

    configured_key = key
    secret = key.encode('utf-8')

    @register
    def runs(key: str = None, workdir: str = None) -> list:
        """列出白名单工作目录的流程运行，每项含 name 文件名。key 为访问密钥，workdir 缺省选首个目录。"""
        directory = resolve_workdir(workdir, cfg)
        return [dict(row, name=Path(row['run']).name) for row in wc.list_runs(directory)]

    def check_text(value):
        # 模型和角色覆盖等嵌套输入也必须能安全写入 UTF-8 控制文件。
        if isinstance(value, str) and not _encodable(value):
            raise ControlError('输入必须是有效的 UTF-8 文本')
        if isinstance(value, dict):
            for name, item in value.items():
                check_text(name)
                check_text(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                check_text(item)

    def truncate(value):
        if isinstance(value, str) and len(value) > 20000:
            return value[:20000] + f'（已截断，共 {len(value)} 字）'
        if isinstance(value, dict):
            return {name: truncate(item) for name, item in value.items()}
        if isinstance(value, list):
            return [truncate(item) for item in value]
        return value

    @register
    def start(key: str, workdir: str, entry: str, mode: str = 'step',
              stop_roles: list[str] = None, confirm_before: list[str] = None,
              confirm_after: list[str] = None, max_attempts: int = None,
              models: dict[str, str] = None, roles: dict[str, str] = None) -> dict:
        """启动流程并立即返回状态。key 为访问密钥；workdir 为白名单工作目录，entry 为其中已有的 .zs 文件名。
        mode 为 step 或 auto；stop_roles/confirm_before 为开始前确认规则（同一设置），confirm_after 为结束后确认规则；
        max_attempts 为尝试上限，models/roles 为按角色名指定的模型/角色卡覆盖。推进使用 wait=False。
        """
        directory = resolve_workdir(workdir, cfg)
        entry = check_entry(directory, entry)
        check_text([mode, stop_roles, confirm_before, confirm_after, models, roles])
        return wc.start(directory, entry=entry, mode=mode, stop_roles=stop_roles,
                        confirm_before=confirm_before, confirm_after=confirm_after,
                        max_attempts=max_attempts, models=models, roles=roles, wait=False)

    @register
    def status(key: str, run: str, detail: bool = False) -> dict:
        """读取流程状态。key 为访问密钥，run 为运行文件名或白名单内相对路径。
        detail=True 时包含完整 pending 和步骤结果，长文本各保留前 20000 字并标注原长度。
        """
        result = wc.status(resolve_run(run, cfg), detail=detail)
        return truncate(result) if detail else result

    @register
    def submit(key: str, run: str, result: dict | str, step: int = None) -> dict:
        """提交当前步骤的外部结果并立即推进。run 为运行文件名或相对路径，result 按步骤格式校验，step 可校验当前步号。"""
        path = resolve_run(run, cfg)
        check_text([result, step])
        return wc.submit(path, result=result, step=step, wait=False)

    @register
    def execute(key: str, run: str, model: str = None, role: str = None,
                step: int = None, note: str = None) -> dict:
        """执行当前步骤并立即返回状态。run 指定运行；model/role 覆盖本次模型和角色卡，step 校验步号，note 添加说明。"""
        path = resolve_run(run, cfg)
        check_text([model, role, step, note])
        return wc.execute(path, model=model, role=role, step=step, note=note, wait=False)

    @register
    def approve(key: str, run: str, attempt: int, result: dict | str = None,
                note: str = None, step: int = None, item_controls: list[dict] = None) -> dict:
        """通过结束后确认并立即推进。run 指定运行；attempt 必填且须匹配当前尝试；result 可修订结果，note 为说明，
        step 校验步号，item_controls 设置分配清单逐项控制；返回状态并保留 cost_preview。
        """
        path = resolve_run(run, cfg)
        if attempt is None:
            raise ControlError('attempt 必填')
        check_text([attempt, result, note, step, item_controls])
        return wc.approve(path, attempt=attempt, result=result, note=note, step=step,
                          item_controls=item_controls, wait=False)

    @register
    def reject(key: str, run: str, attempt: int, note: str, role: str = None,
               model: str = None, step: int = None) -> dict:
        """打回当前结果并立即重跑（wait=False），返回底层当前状态。run 指定运行；attempt 必填且须匹配；
        note 为非空意见，role/model 指定重做覆盖，step 校验步号；配置结束后确认时，重跑成功停在新尝试的 after 确认。"""
        path = resolve_run(run, cfg)
        if attempt is None:
            raise ControlError('attempt 必填')
        if not isinstance(note, str) or not note.strip():
            raise ControlError('打回要写意见')
        check_text([attempt, note, role, model, step])
        return wc.reject(path, attempt=attempt, note=note, role=role, model=model,
                         step=step, wait=False)

    @register
    def edit_plan(key: str, run: str, tasks: list[dict] = None,
                  item_controls: list[dict] = None, record: str = None) -> dict:
        """编辑分配清单并返回状态及 cost_preview。run 指定运行；tasks 替换任务清单，item_controls 设置逐项控制，record 选择清单记录。"""
        path = resolve_run(run, cfg)
        check_text([tasks, item_controls, record])
        return wc.edit_plan(path, tasks=tasks, item_controls=item_controls, record=record)

    @register
    def pause(key: str, run: str) -> dict:
        """将 run 指定的运行切换为逐步模式，返回状态；run 为运行文件名或白名单内相对路径。"""
        return wc.pause(resolve_run(run, cfg))

    @register
    def resume(key: str, run: str) -> dict:
        """恢复 run 指定运行的自动推进并立即返回状态；run 为运行文件名或白名单内相对路径。"""
        return wc.resume(resolve_run(run, cfg), wait=False)

    @register
    def abort(key: str, run: str) -> dict:
        """中止 run 指定的运行并返回状态；run 为运行文件名或白名单内相对路径。"""
        return wc.abort(resolve_run(run, cfg))

    @register
    def configure(key: str, run: str, stop_roles: list[str] = None,
                  confirm_before: list[str] = None, confirm_after: list[str] = None,
                  max_attempts: int = None, models: dict[str, str] = None,
                  roles: dict[str, str] = None) -> dict:
        """配置 run 的后续步骤并返回状态。stop_roles/confirm_before 为开始前规则，confirm_after 为结束后规则，
        max_attempts 为尝试上限，models/roles 为角色的模型和角色卡覆盖；None 保持设置，空列表或字典清空。
        """
        path = resolve_run(run, cfg)
        check_text([stop_roles, confirm_before, confirm_after, max_attempts, models, roles])
        return wc.configure(path, stop_roles=stop_roles, confirm_before=confirm_before,
                            confirm_after=confirm_after, max_attempts=max_attempts,
                            models=models, roles=roles)

    @register
    def rewind(key: str, run: str, step: int) -> dict:
        """将 run 回退到 step 指定的步骤并返回待执行状态；run 为运行文件名或相对路径，step 从 1 开始。"""
        path = resolve_run(run, cfg)
        check_text(step)
        return wc.rewind(path, step=step)

    @register
    def plan(key: str, run: str, record: str = None) -> dict:
        """只读查询分配清单、逐项状态及成本。key 为访问密钥，run 为运行文件名或相对路径；
        record 为清单记录名，省略时由 workflow_ctl 选择唯一清单。
        """
        path = resolve_run(run, cfg)
        check_text(record)
        return wc.plan(path, record=record)

    @register
    def agents(key: str, workdir: str = None) -> list:
        """列出角色卡的 name、model、cost、description。key 为访问密钥；
        workdir 为白名单工作目录，省略时使用第一个目录，读取其 agents/。
        """
        return trace_server.read_agents({'workdir': str(resolve_workdir(workdir, cfg))})

    @register
    def viewer(key: str, run: str = None) -> dict:
        """返回含查看口令的 url。key 为访问密钥；可选 run 为运行文件名或白名单内相对路径，
        提供时追加 #run=文件名。基址优先使用 WF_PUBLIC_URL，否则使用服务的 host、port、base。
        """
        path = resolve_run(run, cfg) if run is not None else None
        base_url = os.environ.get('WF_PUBLIC_URL') or f'http://{host}:{port}{base}'
        url = base_url.rstrip('/') + f'/{token}/'
        if path is not None:
            url += f'#run={path.name}'
        return {'url': url}

    return svc


def make_app(svc):
    """构建同一进程的 MCP 和查看器 ASGI 应用，不监听端口。"""
    return svc.mcp.http_app(path=svc.cfg.base.rstrip('/') + '/mcp')


def main(argv=None):
    """解析启动配置并在指定的 host、port 上运行 HTTP 服务。"""
    parser = argparse.ArgumentParser(description='流程管理 MCP')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--base', default='/trace')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)
    try:
        key = load_key()
        token = load_trace_token()
        svc = build_server(args.host, args.port, args.base, args.write, key, token)
    except (StartupError, ControlError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    svc.mcp.run(transport='http', host=args.host, port=args.port,
                path=args.base.rstrip('/') + '/mcp')
    return svc


if __name__ == '__main__':
    main()
