from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from . import __version__
from .exporters import CommandBlock, parse_transcript, render_markdown, render_text
from .markers import encode_marker
from .runner import run_posix_pty

DEFAULT_ROOT = Path.home() / "Documents" / "LinuxWorks"


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def active_dir(required: bool = True) -> Path | None:
    value = os.environ.get("TERMREC_SESSION_DIR")
    if value:
        return Path(value).expanduser().resolve()
    if required:
        eprint("termrec: активная запись не найдена")
        raise SystemExit(2)
    return None


def load_meta(session_dir: Path) -> dict:
    path = session_dir / "session.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_meta(session_dir: Path, data: dict) -> None:
    (session_dir / "session.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def slugify(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[^\w.-]+", "-", name, flags=re.UNICODE)
    name = name.strip("-._")
    return name or "session"


def unique_dir(base: Path) -> Path:
    if not base.exists():
        return base
    index = 2
    while True:
        candidate = base.with_name(f"{base.name}-{index}")
        if not candidate.exists():
            return candidate
        index += 1


def cmd_prepare(args: argparse.Namespace) -> int:
    root = Path(os.environ.get("TERMREC_ROOT", str(DEFAULT_ROOT))).expanduser()
    date_dir = root / datetime.now().strftime("%Y-%m-%d")
    session_dir = unique_dir(date_dir / slugify(args.name))
    (session_dir / "code").mkdir(parents=True, exist_ok=True)
    session_dir.chmod(0o700)

    meta = {
        "name": args.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "recording",
        "tasks": 0,
        "code_blocks": 0,
        "include_path": bool(getattr(args, "include_path", False)),
        "include_terminals": bool(getattr(args, "include_terminals", False)),
        "terminals": [],
    }
    save_meta(session_dir, meta)
    print(session_dir)
    return 0


def find_finished_session(spec: str) -> Path | None:
    candidate = Path(spec).expanduser()
    if (candidate / "session.json").is_file():
        return candidate.resolve()

    root = Path(os.environ.get("TERMREC_ROOT", str(DEFAULT_ROOT))).expanduser()
    matches: list[Path] = []
    for meta_path in root.glob("*/*/session.json"):
        meta = load_meta(meta_path.parent)
        if meta.get("name") == spec and meta.get("status") == "finished":
            matches.append(meta_path.parent)
    return max(matches, key=lambda path: path.stat().st_mtime) if matches else None


def terminal_title() -> str:
    program = os.environ.get("TERM_PROGRAM")
    if not program and os.environ.get("WT_SESSION"):
        program = "Windows Terminal"
    if not program and os.environ.get("VTE_VERSION"):
        program = "GNOME Terminal"
    if not program:
        program = os.environ.get("TERM", "terminal")
    try:
        tty = os.ttyname(sys.stdout.fileno())
    except OSError:
        tty = "unknown tty"
    return f"{program} — {tty}"


def register_terminal(session_dir: Path, *, primary: bool) -> tuple[str, Path]:
    meta = load_meta(session_dir)
    terminals = list(meta.get("terminals", []))
    terminal_id = uuid4().hex[:8]
    relpath = "session.raw" if primary else f"terminals/{len(terminals) + 1:03d}-{terminal_id}.raw"
    raw_path = session_dir / relpath
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    terminals.append(
        {
            "id": terminal_id,
            "path": relpath,
            "title": terminal_title(),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "cwd": str(Path.cwd()),
            "primary": primary,
        }
    )
    meta["terminals"] = terminals
    meta["status"] = "recording"
    save_meta(session_dir, meta)
    return terminal_id, raw_path


def emit_marker(kind: str, **data: object) -> None:
    sys.stdout.write(encode_marker(kind, **data))
    sys.stdout.flush()


def is_internal_command(command: str) -> bool:
    # User-facing termrec control commands must never appear in exported transcripts.
    return re.match(r"^\s*rec(?:\s|$)", command) is not None


def cmd_command_start(args: argparse.Namespace) -> int:
    session_dir = active_dir()
    meta = load_meta(session_dir)
    cwd = Path(args.cwd).expanduser().resolve() if args.cwd else None
    shown_cwd = None
    if meta.get("include_path") and cwd is not None and cwd != Path.home().resolve():
        shown_cwd = str(cwd)
    emit_marker(
        "command_start",
        command=args.command_text,
        internal=is_internal_command(args.command_text),
        cwd=shown_cwd,
    )
    return 0


def cmd_command_end(args: argparse.Namespace) -> int:
    active_dir()
    emit_marker("command_end", status=args.status)
    return 0


def cmd_task(args: argparse.Namespace) -> int:
    session_dir = active_dir()
    meta = load_meta(session_dir)
    meta["tasks"] = int(meta.get("tasks", 0)) + 1
    save_meta(session_dir, meta)
    emit_marker("task", title=args.title)
    print(f"\n── {args.title} ──\n")
    return 0


def cmd_sep(args: argparse.Namespace) -> int:
    active_dir()
    emit_marker("sep")
    print("\n" + "─" * 64 + "\n")
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    active_dir()
    emit_marker("note", text=args.text)
    print(f"[termrec] заметка: {args.text}")
    return 0


def cmd_pause(args: argparse.Namespace) -> int:
    active_dir()
    emit_marker("pause")
    print("[termrec] экспорт приостановлен; исходный session.raw продолжает записываться")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    active_dir()
    emit_marker("resume")
    print("[termrec] экспорт возобновлён")
    return 0


def cmd_code(args: argparse.Namespace) -> int:
    session_dir = active_dir()
    source = Path(args.file).expanduser().resolve()
    if not source.is_file():
        eprint(f"termrec: файл не найден: {source}")
        return 2

    meta = load_meta(session_dir)
    index = int(meta.get("code_blocks", 0)) + 1
    meta["code_blocks"] = index
    save_meta(session_dir, meta)

    safe_name = slugify(source.name)
    destination = session_dir / "code" / f"{index:03d}-{safe_name}"
    shutil.copy2(source, destination)

    language = args.language or guess_language(source)
    title = args.title or source.name
    relative = destination.relative_to(session_dir).as_posix()

    emit_marker("code", path=relative, language=language, title=title)
    print(f"\n[termrec] сохранён блок кода: {title} ({relative})\n")
    return 0


def guess_language(path: Path) -> str:
    mapping = {
        ".py": "python",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "zsh",
        ".lua": "lua",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".jsx": "jsx",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".md": "markdown",
        ".xml": "xml",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".rs": "rust",
        ".zig": "zig",
        ".conf": "text",
    }
    return mapping.get(path.suffix.lower(), "text")


def read_raw(session_dir: Path) -> str:
    meta = load_meta(session_dir)
    terminal_paths = [str(item.get("path", "")) for item in meta.get("terminals", [])]
    if not terminal_paths:
        terminal_paths = ["session.raw"]

    chunks: list[str] = []
    seen: set[str] = set()
    for relative in terminal_paths:
        if relative in seen:
            continue
        seen.add(relative)
        raw = session_dir / relative
        if raw.is_file():
            chunks.append(raw.read_text(encoding="utf-8", errors="replace"))
    return "".join(chunks)


def redact(text: str, session_dir: Path) -> str:
    path = session_dir / "redactions.json"
    if not path.exists():
        return text
    rules = json.loads(path.read_text(encoding="utf-8"))
    for rule in rules:
        if rule["type"] == "literal":
            text = text.replace(rule["value"], "[REDACTED]")
        else:
            text = re.sub(rule["value"], "[REDACTED]", text)
    return text


def export_one(session_dir: Path, fmt: str, *, task: int | None = None, commands: set[int] | None = None) -> Path:
    meta = load_meta(session_dir)
    title = str(meta.get("name", session_dir.name))
    raw_text = read_raw(session_dir)

    suffix = f"-task-{task}" if task is not None else ("-selection" if commands else "")
    if fmt == "md":
        path = session_dir / f"{slugify(title)}{suffix}.md"
        path.write_text(redact(render_markdown(session_dir, title, raw_text, task=task, commands=commands), session_dir), encoding="utf-8")
        return path
    if fmt == "txt":
        path = session_dir / f"{slugify(title)}{suffix}.txt"
        path.write_text(redact(render_text(session_dir, title, raw_text, task=task, commands=commands), session_dir), encoding="utf-8")
        return path
    raise ValueError(fmt)


def cmd_export(args: argparse.Namespace) -> int:
    session_dir = active_dir(required=False)
    if session_dir is None:
        if args.session:
            session_dir = Path(args.session).expanduser().resolve()
        else:
            eprint("termrec: укажи --session или выполняй команду во время записи")
            return 2

    formats = ["md", "txt"] if args.format == "all" else [args.format]
    commands = None
    if args.commands:
        try:
            commands = {int(item) for item in args.commands.split(",")}
            if not commands or min(commands) < 1:
                raise ValueError
        except ValueError:
            eprint("termrec: --commands ожидает номера через запятую, начиная с 1")
            return 2
    if args.task is not None and args.task < 1:
        eprint("termrec: --task ожидает номер от 1")
        return 2
    if args.task is not None and commands is not None:
        eprint("termrec: выбери --task или --commands")
        return 2
    for fmt in formats:
        path = export_one(session_dir, fmt, task=args.task, commands=commands)
        print(path)
    return 0


def cmd_redact(args: argparse.Namespace) -> int:
    session_dir = active_dir(required=False) or (Path(args.session).expanduser().resolve() if args.session else None)
    if session_dir is None or not (session_dir / "session.json").is_file():
        eprint("termrec: укажи активную или существующую сессию через --session")
        return 2
    path = session_dir / "redactions.json"
    rules = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if args.list:
        for index, rule in enumerate(rules, 1):
            print(f"{index}. {rule['type']} rule")
        return 0
    if args.remove is not None:
        if args.remove < 1 or args.remove > len(rules):
            eprint("termrec: неверный номер правила")
            return 2
        rules.pop(args.remove - 1)
    else:
        value = getpass.getpass("Строка или шаблон для скрытия: ")
        if not value:
            eprint("termrec: пустое правило не допускается")
            return 2
        if args.regex:
            try:
                re.compile(value)
            except re.error as exc:
                eprint(f"termrec: неверный шаблон: {exc}")
                return 2
        rules.append({"type": "regex" if args.regex else "literal", "value": value})
    path.write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    print(f"Правила сохранены: {path}; повтори rec export для обновления отчёта")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    root = Path(os.environ.get("TERMREC_ROOT", str(DEFAULT_ROOT))).expanduser()
    for path in sorted(root.glob("*/*/session.json"), reverse=True):
        meta = load_meta(path.parent)
        print(f"{path.parent}\t{meta.get('status', '?')}\t{meta.get('name', path.parent.name)}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    session_dir = Path(args.session).expanduser().resolve()
    if not (session_dir / "session.json").is_file():
        eprint("termrec: сессия не найдена")
        return 2
    print(json.dumps(load_meta(session_dir), ensure_ascii=False, indent=2))
    for index, segment in enumerate((s for s in parse_transcript(read_raw(session_dir)) if s.kind == "command"), 1):
        block = segment.value
        assert isinstance(block, CommandBlock)
        print(f"{index:3}  $ {redact(block.command, session_dir)}")
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    session_dir = Path(args.session).expanduser().resolve()
    if not (session_dir / "session.json").is_file():
        eprint("termrec: сессия не найдена")
        return 2
    # Raw output has no timing information; playback displays the original presentation.
    sys.stdout.write(read_raw(session_dir))
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    session_dir = Path(args.session).expanduser().resolve()
    meta = load_meta(session_dir)
    meta["status"] = "finished"
    meta["finished_at"] = datetime.now().isoformat(timespec="seconds")
    save_meta(session_dir, meta)

    md = export_one(session_dir, "md")
    txt = export_one(session_dir, "txt")
    print(f"termrec: запись завершена\n  MD:  {md}\n  TXT: {txt}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    session_dir = active_dir(required=False)
    if session_dir is None:
        print("○ Recording: no")
        return 0

    meta = load_meta(session_dir)
    print("● Recording: yes")
    print(f"Session: {meta.get('name', session_dir.name)}")
    print(f"Started: {meta.get('created_at', '?')}")
    print(f"Directory: {session_dir}")
    print(f"Tasks: {meta.get('tasks', 0)}")
    print(f"Code blocks: {meta.get('code_blocks', 0)}")
    return 0


def cmd_marker_stop(args: argparse.Namespace) -> int:
    active_dir()
    emit_marker("stop")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="termrec")
    parser.add_argument("--version", action="version", version=f"termrec {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("_prepare", help=argparse.SUPPRESS)
    p.add_argument("name")
    p.add_argument("--include-path", action="store_true")
    p.add_argument("--include-terminals", action="store_true")
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("_finalize", help=argparse.SUPPRESS)
    p.add_argument("session")
    p.set_defaults(func=cmd_finalize)

    p = sub.add_parser("_command-start", help=argparse.SUPPRESS)
    p.add_argument("command_text")
    p.add_argument("--cwd")
    p.set_defaults(func=cmd_command_start)

    p = sub.add_parser("_command-end", help=argparse.SUPPRESS)
    p.add_argument("status", type=int)
    p.set_defaults(func=cmd_command_end)

    p = sub.add_parser("_stop-marker", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_marker_stop)

    p = sub.add_parser("task", help="Declare a task/section")
    p.add_argument("title")
    p.set_defaults(func=cmd_task)

    p = sub.add_parser("sep", help="Insert a separator")
    p.set_defaults(func=cmd_sep)

    for name, func in (("note", cmd_note), ("pause", cmd_pause), ("resume", cmd_resume)):
        p = sub.add_parser(name)
        if name == "note":
            p.add_argument("text")
        p.set_defaults(func=func)

    p = sub.add_parser("code", help="Save a file as a separate code block")
    p.add_argument("file")
    p.add_argument("language", nargs="?")
    p.add_argument("title", nargs="?")
    p.set_defaults(func=cmd_code)

    p = sub.add_parser("status", help="Show current recording status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("export", help="Export current or selected session")
    p.add_argument("format", choices=["md", "txt", "all"])
    p.add_argument("--session")
    p.add_argument("--task", type=int)
    p.add_argument("--commands", help="Comma-separated command numbers")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("redact", help="Manage export redaction rules")
    p.add_argument("--regex", action="store_true")
    p.add_argument("--list", action="store_true")
    p.add_argument("--remove", type=int)
    p.add_argument("--session")
    p.set_defaults(func=cmd_redact)

    p = sub.add_parser("list", help="List saved sessions")
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("show", help="Show session details and commands")
    p.add_argument("session")
    p.set_defaults(func=cmd_show)
    p = sub.add_parser("replay", help="Display original terminal recording")
    p.add_argument("session")
    p.set_defaults(func=cmd_replay)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


def module_env() -> dict[str, str]:
    env = os.environ.copy()
    module_root = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = module_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def create_session(name: str, *, include_path: bool, include_terminals: bool) -> Path:
    env = module_env()
    command = [sys.executable, "-m", "termrec.cli", "_prepare", name]
    if include_path:
        command.append("--include-path")
    if include_terminals:
        command.append("--include-terminals")
    prepared = subprocess.run(command, capture_output=True, text=True, env=env)
    if prepared.returncode:
        eprint(prepared.stderr.rstrip())
        raise SystemExit(prepared.returncode)
    return Path(prepared.stdout.strip())


def choose_shell(value: str | None) -> str:
    shell = value or Path(os.environ.get("SHELL", "bash")).name
    if shell not in {"bash", "zsh"} or not shutil.which(shell):
        eprint("termrec: укажи установленную оболочку: --shell bash или --shell zsh")
        raise SystemExit(2)
    return shell


def run_interactive_session(session_dir: Path, shell: str, *, primary: bool) -> int:
    env = module_env()
    terminal_id, raw_path = register_terminal(session_dir, primary=primary)
    meta = load_meta(session_dir)
    terminal = next(item for item in meta["terminals"] if item["id"] == terminal_id)
    marker: dict[str, object] = {"id": terminal_id}
    if meta.get("include_terminals"):
        marker["title"] = terminal["title"]
    if meta.get("include_path") and terminal["cwd"] != str(Path.home().resolve()):
        marker["cwd"] = terminal["cwd"]
    with raw_path.open("ab") as raw:
        if len(marker) > 1:
            raw.write(encode_marker("terminal_start", **marker).encode("utf-8"))

    with tempfile.TemporaryDirectory(prefix="termrec-shell-") as tmp:
        tmp_dir = Path(tmp)
        integration = Path(__file__).with_name(f"termrec.{shell}")
        if shell == "zsh":
            original_rc = Path(os.environ.get("ZDOTDIR", str(Path.home()))).expanduser() / ".zshrc"
            rc = tmp_dir / ".zshrc"
            rc.write_text(
                f"[[ -f {shlex.quote(str(original_rc))} ]] && source {shlex.quote(str(original_rc))}\n"
                "unsetopt PROMPT_SP\n"
                f"source {shlex.quote(str(integration))}\n",
                encoding="utf-8",
            )
            argv = ["zsh", "-i"]
            env["ZDOTDIR"] = tmp
        else:
            original_rc = Path.home() / ".bashrc"
            rc = tmp_dir / "bashrc"
            rc.write_text(
                f"[[ -f {shlex.quote(str(original_rc))} ]] && source {shlex.quote(str(original_rc))}\n"
                f"source {shlex.quote(str(integration))}\n",
                encoding="utf-8",
            )
            argv = ["bash", "--noprofile", "--rcfile", str(rc), "-i"]
        env.update(TERMREC_ACTIVE="1", TERMREC_SESSION_DIR=str(session_dir), TERMREC_PYTHON=sys.executable)
        result_code = run_posix_pty(argv, env, raw_path, append=True)

    meta = load_meta(session_dir)
    for item in meta.get("terminals", []):
        if item.get("id") == terminal_id:
            item["finished_at"] = datetime.now().isoformat(timespec="seconds")
            break
    save_meta(session_dir, meta)
    if primary:
        cmd_finalize(argparse.Namespace(session=str(session_dir)))
    else:
        export_one(session_dir, "md")
        export_one(session_dir, "txt")
        print(f"termrec: терминал отключён; сессия: {session_dir}")
    return result_code


def rec_main() -> None:
    """Entry point available immediately after package installation."""
    if len(sys.argv) == 2 and sys.argv[1] == "--version":
        print(f"rec {__version__}")
        return
    if len(sys.argv) < 2 or sys.argv[1] in {"help", "-h", "--help"}:
        print("rec start <name> [--continue] [-path] [-terms] [--shell bash|zsh] | rec attach | rec run <name> -- <command> | task | sep | note | pause | resume | code | status | export | redact | list | show | replay")
        return

    if sys.argv[1] == "start":
        start_parser = argparse.ArgumentParser(prog="rec start")
        start_parser.add_argument("name")
        start_parser.add_argument("--shell", choices=["bash", "zsh"])
        start_parser.add_argument("--continue", dest="continue_session", action="store_true")
        start_parser.add_argument("-path", "--path", dest="include_path", action="store_true")
        start_parser.add_argument("-terms", "--terms", dest="include_terminals", action="store_true")
        start_args = start_parser.parse_args(sys.argv[2:])
        if os.name == "nt":
            eprint("termrec: интерактивная запись Windows требует ConPTY backend; используй rec run <name> -- <command>")
            raise SystemExit(2)
        if os.environ.get("TERMREC_ACTIVE"):
            eprint("termrec: запись уже активна")
            raise SystemExit(2)
        shell = choose_shell(start_args.shell)
        if start_args.continue_session:
            session_dir = find_finished_session(start_args.name)
            if session_dir is None:
                eprint("termrec: завершённая сессия не найдена; укажи её путь или точное имя")
                raise SystemExit(2)
            meta = load_meta(session_dir)
            meta["status"] = "recording"
            meta["continued_at"] = datetime.now().isoformat(timespec="seconds")
            if start_args.include_path:
                meta["include_path"] = True
            if start_args.include_terminals:
                meta["include_terminals"] = True
            save_meta(session_dir, meta)
        else:
            session_dir = create_session(
                start_args.name,
                include_path=start_args.include_path,
                include_terminals=start_args.include_terminals,
            )
        print(f"termrec: recording -> {session_dir}\ntermrec: use 'rec stop' to finish\n", flush=True)
        raise SystemExit(run_interactive_session(session_dir, shell, primary=True))

    if sys.argv[1] == "attach":
        if os.name == "nt":
            eprint("termrec: подключение терминала Windows пока недоступно")
            raise SystemExit(2)
        session_dir = active_dir(required=False)
        if session_dir is None or not (session_dir / "session.json").is_file():
            eprint("termrec: открой этот терминал из активной сессии и запусти rec attach")
            raise SystemExit(2)
        if load_meta(session_dir).get("status") != "recording":
            eprint("termrec: сессия уже завершена; используй rec start <имя> --continue")
            raise SystemExit(2)
        attach_parser = argparse.ArgumentParser(prog="rec attach")
        attach_parser.add_argument("--shell", choices=["bash", "zsh"])
        attach_args = attach_parser.parse_args(sys.argv[2:])
        raise SystemExit(run_interactive_session(session_dir, choose_shell(attach_args.shell), primary=False))

    if sys.argv[1] == "run":
        if len(sys.argv) < 5 or sys.argv[3] != "--":
            eprint("usage: rec run <name> -- <command> [arguments]")
            raise SystemExit(2)
        name, command = sys.argv[2], sys.argv[4:]
        env = os.environ.copy()
        module_root = str(Path(__file__).resolve().parent.parent)
        env["PYTHONPATH"] = module_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        prepare = subprocess.run([sys.executable, "-m", "termrec.cli", "_prepare", name], capture_output=True, text=True, env=env)
        if prepare.returncode:
            eprint(prepare.stderr.rstrip())
            raise SystemExit(prepare.returncode)
        session_dir = Path(prepare.stdout.strip())
        raw = session_dir / "session.raw"
        raw.write_bytes(encode_marker("command_start", command=" ".join(command), internal=False).encode("utf-8"))
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with raw.open("ab") as fh:
            fh.write(result.stdout)
            fh.write(encode_marker("command_end", status=result.returncode).encode("utf-8"))
        subprocess.run([sys.executable, "-m", "termrec.cli", "_finalize", str(session_dir)], check=False, env=env)
        raise SystemExit(result.returncode)

    if sys.argv[1] == "stop":
        eprint("termrec: stop доступен внутри записываемой bash или zsh")
        raise SystemExit(2)
    main()


if __name__ == "__main__":
    main()
