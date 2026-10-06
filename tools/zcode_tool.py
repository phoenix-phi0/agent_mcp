"""A small, dependency-free Python wrapper around the ``zcode`` CLI."""

from __future__ import annotations

import contextlib
import json
import os
import platform
import posixpath
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Mapping, Optional, Sequence, Union


Command = Union[str, Sequence[str]]
PathArg = Union[str, os.PathLike[str]]


class ZCodeError(RuntimeError):
    """Raised when zcode cannot be started or exits unsuccessfully."""


class ZCodeJSONError(ZCodeError):
    """Raised when zcode claims to return JSON but emits invalid JSON."""


class UnsafeWorkdirError(ValueError):
    """Raised when an agent CLI would run in a directory exposing credentials."""


# An agent CLI (zcode, claude) can read -- and may upload -- everything under
# its working directory. The home directory and ``/`` hold ~/.ssh,
# ~/.git-credentials and CLI login tokens, so they are never used. Without an
# explicit cwd every call runs in a fresh empty temporary directory.
#
# Reject a workdir that is, or is inside, a directory with one of these names.
SENSITIVE_DIR_NAMES = frozenset({".ssh", ".gnupg", ".aws", ".kube", ".azure"})
# Reject a workdir that directly contains one of these (a home-like parent).
# Project-level .claude/ and .zcode/ settings are common, so only the
# credential files inside them count.
SENSITIVE_ENTRIES = (
    ".ssh", ".gnupg", ".aws", ".kube", ".azure",
    ".git-credentials", ".netrc", ".npmrc", ".pypirc",
    ".docker/config.json", ".config/gh",
    ".claude.json", ".claude/.credentials.json", ".zcode/cli",
)
WORKDIR_PREFIX = "zcode_"


def _is_home_like(p: PurePosixPath) -> bool:
    """``/``, ``/home``, ``/home/<user>``, ``/root``, ``/Users/<user>``."""
    parts = p.parts
    return (
        len(parts) <= 1
        or (parts[1] in ("home", "Users") and len(parts) <= 3)
        or (parts[1] == "root" and len(parts) == 2)
    )


def check_workdir(path: PathArg) -> str:
    """Validate an explicitly chosen working directory on this machine.

    Rejects ``~``-style paths, ``/``, the home directory and its parents,
    any ``/home/<user>`` or ``/root``, directories inside ``.ssh`` and the
    like, and directories that directly contain credentials (see
    ``SENSITIVE_ENTRIES``). A project subdirectory such as
    ``/home/alice/project`` is allowed, but the agent can then read every file
    under it, including local config files that hold API keys; only pass one
    when the task really needs the code.

    Returns the resolved absolute path.
    """
    raw = os.fspath(path).strip()
    if not raw:
        raise UnsafeWorkdirError("工作目录不能是空串；不传就用临时空目录")
    if raw.startswith("~"):
        raise UnsafeWorkdirError(
            f"工作目录不能用 ~（{raw}）：家目录下有 .ssh 等凭证；"
            "不传就用临时空目录，或传项目子目录的绝对路径")
    resolved = Path(raw).resolve()
    if not resolved.is_dir():
        raise UnsafeWorkdirError(f"工作目录不是目录：{resolved}")

    home = Path.home().resolve()
    if resolved == home or resolved in home.parents:
        raise UnsafeWorkdirError(
            f"工作目录不能是家目录或它的上级（{resolved}）：代理能读到 "
            "~/.ssh、~/.git-credentials 等凭证。不传就用临时空目录")
    if os.name != "nt" and _is_home_like(PurePosixPath(resolved.as_posix())):
        raise UnsafeWorkdirError(
            f"工作目录不能是 / 或某个用户的家目录（{resolved}）")
    inside = SENSITIVE_DIR_NAMES.intersection(resolved.parts)
    if inside:
        raise UnsafeWorkdirError(
            f"工作目录在敏感目录 {'、'.join(sorted(inside))} 里面（{resolved}）")
    found = [name for name in SENSITIVE_ENTRIES if (resolved / name).exists()]
    if found:
        raise UnsafeWorkdirError(
            f"工作目录 {resolved} 下面有 {'、'.join(found)}，像是家目录一类的"
            "父目录，代理能读到凭证。换成具体的项目子目录")
    return str(resolved)


def check_wsl_workdir(path: str) -> str:
    """Validate a Linux path chosen from Windows for ``wsl.exe --cd``.

    The WSL filesystem cannot be inspected from here, so only the path itself
    is checked: it must be absolute, and must not be ``/``, ``/home``,
    ``/home/<user>``, ``/root`` or inside ``.ssh`` and the like. A project
    subdirectory is allowed with the same risk as in ``check_workdir``.
    """
    raw = (path or "").strip()
    if not raw:
        raise UnsafeWorkdirError("wsl_cwd 不能是空串；不传就用临时空目录")
    if raw.startswith("~"):
        raise UnsafeWorkdirError(
            f"wsl_cwd 不能用 ~（{raw}）：家目录下有 .ssh 等凭证；"
            "不传就用临时空目录，或传项目子目录的绝对路径")
    if not raw.startswith("/"):
        raise UnsafeWorkdirError(f"wsl_cwd 必须是 WSL 绝对路径：{raw}")
    normalized = PurePosixPath(posixpath.normpath(raw))
    if _is_home_like(normalized):
        raise UnsafeWorkdirError(
            f"wsl_cwd 不能是 / 或某个用户的家目录（{normalized}）：代理能读到 "
            "~/.ssh 等凭证。不传就用临时空目录")
    inside = SENSITIVE_DIR_NAMES.intersection(normalized.parts)
    if inside:
        raise UnsafeWorkdirError(
            f"wsl_cwd 在敏感目录 {'、'.join(sorted(inside))} 里面（{normalized}）")
    return str(normalized)


@contextlib.contextmanager
def agent_workdir(cwd: Optional[PathArg] = None) -> Iterator[str]:
    """Yield the directory an agent CLI should run in.

    ``None`` creates a fresh empty temporary directory and removes it on exit;
    anything else goes through ``check_workdir``.
    """
    if cwd is not None:
        yield check_workdir(cwd)
        return
    with tempfile.TemporaryDirectory(prefix=WORKDIR_PREFIX) as tmp:
        yield tmp


# Without wsl_cwd, run inside a fresh ``mktemp -d`` directory in WSL and
# remove it afterwards. No ``exec``: the EXIT trap must run after zcode exits.
_WSL_TMP_SCRIPT = (
    'd=$(mktemp -d "${TMPDIR:-/tmp}/zcode_XXXXXX") || exit 92; '
    "trap 'rm -rf \"$d\"' EXIT; "
    'cd "$d" || exit 92; '
    '"$@"'
)


@dataclass(frozen=True)
class ZCodeResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class ZCodeTool:
    """Call zcode safely without invoking a shell.

    Args:
        command: Executable name, path, or a command prefix such as
            ``["zcode", "run"]``.
        prompt_arg: Option placed before the prompt, for example ``"--prompt"``.
            Keep it as ``None`` when zcode accepts the prompt positionally.
        cwd: Default working directory for calls, checked by
            ``check_workdir``. ``None`` runs every call in a fresh empty
            temporary directory that is removed afterwards.
        env: Environment variables added to the current process environment.
        timeout: Default timeout in seconds. ``None`` disables it.
    """

    BUILTIN_TOOLS = (
        "Read",
        "Grep",
        "Glob",
        "Bash",
        "Edit",
        "Write",
        "WebFetch",
        "WebSearch",
        "TodoWrite",
        "Agent",
        "Skill",
    )

    WINDOWS_RUNTIME_RELPATH = Path("Programs/ZCode/resources/glm/zcode.cjs")

    def __init__(
        self,
        command: Optional[Command] = None,
        *,
        prompt_arg: Optional[str] = "-p",
        cwd: Optional[Union[str, os.PathLike[str]]] = None,
        env: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = 900,
    ) -> None:
        self.command = self._normalize_command(
            command if command is not None else self._default_command()
        )
        self.prompt_arg = prompt_arg
        self.cwd = Path(check_workdir(cwd)) if cwd is not None else None
        self.env = dict(env or {})
        self.timeout = timeout

    @staticmethod
    def _normalize_command(command: Command) -> tuple[str, ...]:
        parts = tuple(shlex.split(command)) if isinstance(command, str) else tuple(command)
        if not parts or any(not isinstance(part, str) or not part for part in parts):
            raise ValueError("command must contain at least one non-empty string")
        return parts

    @classmethod
    def _default_command(cls) -> Command:
        """Resolve a command that launches the real CLI, not the desktop app.

        On Windows a bare ``zcode`` is resolved to ``ZCode.exe`` (the Electron
        desktop app) by CreateProcess extension matching, so invoke the agent
        runtime through node explicitly when it is installed.
        """
        if platform.system() == "Windows":
            local_app = os.environ.get("LOCALAPPDATA")
            if local_app:
                runtime = Path(local_app) / cls.WINDOWS_RUNTIME_RELPATH
                if runtime.is_file():
                    return ["node", str(runtime)]
        return "zcode"

    def is_available(self) -> bool:
        """Return whether the configured executable can be found."""
        executable = self.command[0]
        return Path(executable).is_file() or shutil.which(executable) is not None

    def build_command(
        self, prompt: Optional[str] = None, extra_args: Iterable[str] = ()
    ) -> list[str]:
        args = [*self.command, *extra_args]
        if prompt is not None:
            if self.prompt_arg:
                args.append(self.prompt_arg)
            args.append(prompt)
        return args

    def run(
        self,
        prompt: Optional[str] = None,
        *,
        extra_args: Iterable[str] = (),
        input_text: Optional[str] = None,
        cwd: Optional[Union[str, os.PathLike[str]]] = None,
        timeout: Optional[float] = None,
        check: bool = True,
    ) -> ZCodeResult:
        """Run zcode once and return its captured output."""
        args = self.build_command(prompt, extra_args)
        try:
            with self._workdir(cwd) as workdir:
                completed = subprocess.run(
                    args,
                    input=input_text,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    cwd=workdir,
                    env=self._build_env(),
                    timeout=self.timeout if timeout is None else timeout,
                    shell=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
        except FileNotFoundError as exc:
            raise ZCodeError(f"zcode executable not found: {args[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ZCodeError(f"zcode timed out after {exc.timeout} seconds") from exc

        result = ZCodeResult(tuple(args), completed.returncode, completed.stdout, completed.stderr)
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "no output"
            raise ZCodeError(f"zcode exited with code {result.returncode}: {detail}")
        return result

    def run_json(
        self,
        prompt: str,
        *,
        extra_args: Iterable[str] = (),
        cwd: Optional[Union[str, os.PathLike[str]]] = None,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        """Run one headless ZCode request and always return a JSON-safe dict.

        ZCode is asked for JSON through ``--json``. A non-zero
        CLI exit is represented by ``ok: false`` rather than being raised, so
        API callers can use one stable response shape.
        """
        args = [*extra_args, "--json"]
        try:
            result = self.run(
                prompt,
                extra_args=args,
                cwd=cwd,
                timeout=timeout,
                check=False,
            )
        except ZCodeError as exc:
            return {
                "ok": False,
                "returncode": None,
                "result": None,
                "stderr": str(exc),
            }

        parsed: Any = None
        parse_error: Optional[str] = None
        if result.stdout.strip():
            try:
                parsed = self._parse_json_output(result.stdout)
            except ZCodeJSONError as exc:
                parse_error = str(exc)

        ok = result.returncode == 0 and parse_error is None
        response: dict[str, Any] = {
            "ok": ok,
            "returncode": result.returncode,
            "result": parsed,
            "stderr": result.stderr.strip(),
        }
        if parse_error is not None:
            response["parse_error"] = parse_error
            response["raw_stdout"] = result.stdout
        return response

    def write_code_json(
        self,
        task: str,
        *,
        cwd: Optional[Union[str, os.PathLike[str]]] = None,
        mode: str = "yolo",
        disallowed_tools: Iterable[str] = (),
        timeout: Optional[float] = None,
        indent: Optional[int] = 2,
    ) -> str:
        """Ask ZCode to implement a coding task and return a JSON string.

        ``yolo`` is the practical default for a non-interactive coding request,
        because permission prompts cannot be answered through captured stdio.
        Pass a dedicated project directory and choose ``build`` instead when a
        human will handle permissions through an interactive ZCode session.
        """
        if not task.strip():
            raise ValueError("task must not be empty")
        if mode not in {"build", "edit", "plan", "yolo"}:
            raise ValueError("mode must be one of: build, edit, plan, yolo")

        selected_cwd = check_workdir(cwd) if cwd is not None else self.cwd
        if selected_cwd is None:
            raise ValueError("cwd is required for write_code_json")

        extra_args = ["--mode", mode]
        denied = [name for name in disallowed_tools if name]
        if denied:
            extra_args.extend(["--disallowedTools", *denied])

        prompt = (
            "Implement the following coding task in the current project. "
            "Inspect the existing code, make only relevant changes, run suitable "
            "verification, and summarize the result.\n\nTask:\n" + task.strip()
        )
        response = self.run_json(
            prompt,
            extra_args=extra_args,
            cwd=selected_cwd,
            timeout=timeout,
        )
        return json.dumps(response, ensure_ascii=False, indent=indent)

    def generate_code_text(
        self,
        task: str,
        *,
        language: Optional[str] = None,
        context: Optional[str] = None,
        allowed_tools: Iterable[str] = ("Read", "Grep", "Glob"),
        cwd: Optional[Union[str, os.PathLike[str]]] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Generate code through ZCode and return only the code string.

        ``allowed_tools`` selects which builtin tools the agent may use. The
        CLI's ``--allowed-tools`` option is broken in runtime 0.16.5, so the
        selection is enforced through ``--disallowedTools`` with the inverse
        list. It defaults to the read-only ``Read``, ``Grep``, and ``Glob``
        tools. ZCode's JSON output envelope is parsed internally and Markdown
        code fences are removed.
        """
        if not task.strip():
            raise ValueError("task must not be empty")

        allowed = self._normalize_allowed_tools(allowed_tools)

        extra_args = ["--mode", "build"]
        denied = [name for name in self.BUILTIN_TOOLS if name not in allowed]
        if denied:
            extra_args.extend(["--disallowedTools", *denied])

        prompt = self._code_generation_prompt(task, language, context)
        response = self.run_json(
            prompt,
            extra_args=extra_args,
            cwd=cwd,
            timeout=timeout,
        )
        return self._code_from_response(response)

    def generate_code_text_wsl(
        self,
        task: str,
        *,
        wsl_cwd: Optional[str] = None,
        distribution: Optional[str] = None,
        user: Optional[str] = None,
        zcode_command: str = "zcode",
        language: Optional[str] = None,
        context: Optional[str] = None,
        allowed_tools: Optional[Union[str, Iterable[str]]] = None,
        mode: str = "yolo",
        timeout: Optional[float] = None,
    ) -> str:
        """Call ZCode installed in WSL from Windows and return code text.

        Without ``wsl_cwd`` ZCode runs in a fresh empty ``mktemp -d``
        directory inside WSL that is removed when it exits. The home directory
        is never used: ZCode can read and upload everything under its working
        directory, and ``~`` holds ``.ssh``, ``.git-credentials`` and login
        tokens. ``wsl_cwd`` may be an absolute Linux project path such as
        ``/home/alice/project`` when the task needs to read the code (checked
        by ``check_wsl_workdir``); ZCode can then read every file under it,
        including local config files with API keys. A project-level
        ``.zcode/config.json`` under that directory is loaded normally,
        including its MCP configuration.

        ``allowed_tools=None`` enables every known builtin tool. An empty
        iterable or empty string disables all builtins; otherwise pass tool
        names as an iterable or a comma/space-separated string.

        This selects a working directory but is not a filesystem sandbox. Use
        Docker or bubblewrap when ZCode must be unable to access other WSL
        paths.
        """
        if not task.strip():
            raise ValueError("task must not be empty")
        if wsl_cwd is not None:
            wsl_cwd = check_wsl_workdir(wsl_cwd)
        if not zcode_command.strip():
            raise ValueError("zcode_command must not be empty")
        if mode not in {"build", "edit", "plan", "yolo"}:
            raise ValueError("mode must be one of: build, edit, plan, yolo")

        allowed = self._normalize_allowed_tools(allowed_tools)

        extra_args = ["--mode", mode]
        denied = [name for name in self.BUILTIN_TOOLS if name not in allowed]
        if denied:
            extra_args.extend(["--disallowedTools", *denied])

        command = ["wsl.exe"]
        if distribution:
            command.extend(["--distribution", distribution])
        if user:
            command.extend(["--user", user])
        # Interactive WSL sessions commonly add npm/NVM binaries in ~/.bashrc.
        # ``wsl.exe zcode ...`` skips that file, so run an interactive Bash and
        # forward every ZCode argument through "$@". The command string is
        # constant; prompts remain separate argv entries and cannot become
        # shell syntax.
        if wsl_cwd is None:
            command.extend(["--cd", "/tmp", "--exec", "bash", "-ic", _WSL_TMP_SCRIPT])
        else:
            command.extend(["--cd", wsl_cwd, "--exec", "bash", "-ic", 'exec "$@"'])
        command.extend(["zcode", zcode_command.strip()])

        wsl_tool = ZCodeTool(
            command=command,
            prompt_arg="-p",
            timeout=self.timeout if timeout is None else timeout,
        )
        # The Windows-side cwd of wsl.exe is irrelevant (--cd decides), so the
        # local default temporary directory is fine.
        response = wsl_tool.run_json(
            self._code_generation_prompt(task, language, context),
            extra_args=extra_args,
            timeout=timeout,
        )
        return self._code_from_response(response)

    @classmethod
    def _normalize_allowed_tools(
        cls,
        allowed_tools: Optional[Union[str, Iterable[str]]],
    ) -> list[str]:
        """Normalize, deduplicate, and validate a builtin tool selection."""
        if allowed_tools is None:
            return list(cls.BUILTIN_TOOLS)

        if isinstance(allowed_tools, str):
            value = allowed_tools.strip()
            if value == "*":
                return list(cls.BUILTIN_TOOLS)
            names = value.replace(",", " ").split()
        else:
            names = [name.strip() for name in allowed_tools if name.strip()]

        selected = list(dict.fromkeys(names))
        unknown = sorted(set(selected) - set(cls.BUILTIN_TOOLS))
        if unknown:
            raise ValueError("unknown ZCode tools: " + ", ".join(unknown))
        return selected

    @staticmethod
    def _code_generation_prompt(
        task: str, language: Optional[str], context: Optional[str]
    ) -> str:
        language_hint = f" The programming language is {language}." if language else ""
        context_block = f"\n\nAdditional context:\n{context.strip()}" if context else ""
        return (
            "Write code that satisfies the following request."
            f"{language_hint} Return only the complete code text without "
            "Markdown fences, explanations, or surrounding JSON."
            f"\n\nRequest:\n{task.strip()}{context_block}"
        )

    def _code_from_response(self, response: Mapping[str, Any]) -> str:
        if not response["ok"]:
            detail = (
                response.get("stderr")
                or response.get("parse_error")
                or response.get("raw_stdout")
                or "unknown ZCode error"
            )
            raise ZCodeError(f"code generation failed: {detail}")

        code = self._extract_text(response.get("result"))
        if not code:
            raise ZCodeJSONError("ZCode JSON output did not contain assistant text")
        return self._strip_code_fence(code)

    @classmethod
    def _extract_text(cls, value: Any) -> Optional[str]:
        if isinstance(value, str):
            return value.strip() or None
        if isinstance(value, dict):
            for key in ("text", "output", "response", "result", "message", "content"):
                if key in value:
                    found = cls._extract_text(value[key])
                    if found:
                        return found
            return None
        if isinstance(value, list):
            # JSONL output often contains events; the final assistant/result
            # event is normally the last item carrying text.
            for item in reversed(value):
                found = cls._extract_text(item)
                if found:
                    return found
        return None

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        stripped = text.strip()
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return stripped

    @staticmethod
    def _parse_json_output(output: str) -> Any:
        text = output.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as whole_error:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            try:
                values = [json.loads(line) for line in lines]
            except json.JSONDecodeError as line_error:
                raise ZCodeJSONError(
                    f"invalid JSON output at line {line_error.lineno}, "
                    f"column {line_error.colno}: {line_error.msg}"
                ) from whole_error
            return values

    def stream(
        self,
        prompt: Optional[str] = None,
        *,
        extra_args: Iterable[str] = (),
        input_text: Optional[str] = None,
        cwd: Optional[Union[str, os.PathLike[str]]] = None,
        check: bool = True,
    ) -> Iterator[str]:
        """Yield combined stdout/stderr lines as zcode produces them."""
        args = self.build_command(prompt, extra_args)
        with self._workdir(cwd) as workdir:
            try:
                process = subprocess.Popen(
                    args,
                    stdin=subprocess.PIPE if input_text is not None else None,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    cwd=workdir,
                    env=self._build_env(),
                    shell=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except FileNotFoundError as exc:
                raise ZCodeError(f"zcode executable not found: {args[0]}") from exc

            assert process.stdout is not None
            if input_text is not None:
                assert process.stdin is not None
                process.stdin.write(input_text)
                process.stdin.close()

            try:
                yield from process.stdout
            finally:
                process.stdout.close()
                if process.poll() is None:
                    process.terminate()
                returncode = process.wait()

        if check and returncode != 0:
            raise ZCodeError(f"zcode exited with code {returncode}")

    def _workdir(self, cwd: Optional[PathArg]) -> contextlib.AbstractContextManager[str]:
        """Working directory for one call: explicit, default, or a fresh temp dir."""
        return agent_workdir(cwd if cwd is not None else self.cwd)

    def _build_env(self) -> dict[str, str]:
        return {**os.environ, **self.env}


if __name__ == "__main__":
    tool = ZCodeTool()
    for output_line in tool.stream("请分析当前项目并给出改进建议"):
        print(output_line, end="")
