from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .cleaner import clean_terminal_text
from .markers import Marker, split_markers


@dataclass(slots=True)
class CommandBlock:
    command: str
    output: str
    status: int | None = None
    cwd: str | None = None


@dataclass(slots=True)
class Segment:
    kind: str
    value: CommandBlock | Marker


def parse_transcript(raw_text: str) -> list[Segment]:
    """
    Build a semantic transcript from shell hook markers.

    Everything outside command_start/command_end is deliberately ignored. This is what
    removes Powerlevel10k, prompts, typed command echo, cursor redraws and other shell
    presentation reliably instead of trying to parse a decorated prompt.

    termrec commands are marked as internal. Their command line and normal stdout/stderr
    are ignored, while structural markers produced by them (task/sep/code/stop) are kept.
    """
    segments: list[Segment] = []

    command: str | None = None
    internal = False
    output_parts: list[str] = []
    current_cwd: object | None = None
    paused = False

    def flush(status: int | None = None) -> None:
        nonlocal command, internal, output_parts, current_cwd

        if command is not None and not internal and not paused:
            output = clean_terminal_text("".join(output_parts))
            segments.append(
                Segment(
                    "command",
                    CommandBlock(
                        command=command,
                        output=output,
                        status=status,
                        cwd=str(current_cwd) if current_cwd else None,
                    ),
                )
            )

        command = None
        internal = False
        output_parts = []
        current_cwd = None

    for part in split_markers(raw_text):
        if isinstance(part, str):
            if command is not None and not internal and not paused:
                output_parts.append(part)
            # Prompt/decorative text outside a running command is intentionally dropped.
            continue

        marker = part

        if marker.kind == "pause":
            flush()
            paused = True
            continue
        if marker.kind == "resume":
            flush()
            paused = False
            continue

        if marker.kind == "command_start":
            # Recover gracefully if a previous command never received command_end.
            flush()
            command = str(marker.data.get("command", ""))
            internal = bool(marker.data.get("internal", False))
            current_cwd = marker.data.get("cwd")
            output_parts = []
            continue

        if marker.kind == "command_end":
            raw_status = marker.data.get("status")
            try:
                status = int(raw_status) if raw_status is not None else None
            except (TypeError, ValueError):
                status = None
            flush(status)
            continue

        # Structural markers are emitted by internal `rec ...` commands and must survive
        # even though the command itself is hidden from the report.
        if marker.kind in {"task", "sep", "code", "note", "terminal_start", "stop"} and not paused:
            segments.append(Segment("marker", marker))
            continue

    # A command can be left open if the shell/process is terminated abruptly.
    flush()
    return segments


def _fence_for(content: str, minimum: int = 3) -> str:
    longest = 0
    current = 0
    for ch in content:
        if ch == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return "`" * max(minimum, longest + 1)


def _prefix_command(command: str) -> list[str]:
    lines = command.splitlines() or [""]
    return [f"$ {line}" for line in lines]


def _prefix_output(output: str) -> list[str]:
    if not output:
        return []
    # Every answer line is explicitly marked with `>` as requested.
    return [f"> {line}" if line else ">" for line in output.splitlines()]


def _console_lines(block: CommandBlock) -> list[str]:
    path = [f"# {block.cwd}"] if block.cwd else []
    return path + _prefix_command(block.command) + _prefix_output(block.output)


def _selected(segments: list[Segment], task: int | None, commands: set[int] | None) -> list[Segment]:
    selected: list[Segment] = []
    task_index = 0
    command_index = 0
    for segment in segments:
        if segment.kind == "marker" and isinstance(segment.value, Marker) and segment.value.kind == "task":
            task_index += 1
        if segment.kind == "command":
            command_index += 1
        if task is not None and task_index != task:
            continue
        if commands is not None and (segment.kind != "command" or command_index not in commands):
            continue
        selected.append(segment)
    return selected


def render_markdown(session_dir: Path, title: str, raw_text: str, *, task: int | None = None, commands: set[int] | None = None) -> str:
    out: list[str] = [f"# {title}", ""]
    console_buffer: list[str] = []

    def flush_console() -> None:
        if not console_buffer:
            return
        text = "\n".join(console_buffer)
        fence = _fence_for(text)
        out.extend([f"{fence}console", text, fence, ""])
        console_buffer.clear()

    for segment in _selected(parse_transcript(raw_text), task, commands):
        if segment.kind == "command":
            block = segment.value
            assert isinstance(block, CommandBlock)
            console_buffer.extend(_console_lines(block))
            continue

        flush_console()
        marker = segment.value
        assert isinstance(marker, Marker)

        if marker.kind == "task":
            task_title = str(marker.data.get("title", "Задание"))
            out.extend([f"## {task_title}", ""])
        elif marker.kind == "sep":
            out.extend(["---", ""])
        elif marker.kind == "note":
            out.extend([str(marker.data.get("text", "")), ""])
        elif marker.kind == "terminal_start":
            terminal = str(marker.data.get("title", "Terminal"))
            cwd = str(marker.data.get("cwd", ""))
            out.extend([f"## Terminal: {terminal}", f"_Started in `{cwd}`_" if cwd else "", ""])
        elif marker.kind == "code":
            relpath = str(marker.data.get("path", ""))
            language = str(marker.data.get("language", "text"))
            code_title = str(marker.data.get("title", "Код"))
            code_path = session_dir / relpath
            try:
                content = code_path.read_text(encoding="utf-8")
            except Exception as exc:
                content = f"[termrec: не удалось прочитать {relpath}: {exc}]"
            fence = _fence_for(content)
            out.extend(
                [
                    f"### {code_title}",
                    "",
                    f"{fence}{language}",
                    content.rstrip("\n"),
                    fence,
                    "",
                ]
            )
        elif marker.kind == "stop":
            pass

    flush_console()
    return "\n".join(out).rstrip() + "\n"


def render_text(session_dir: Path, title: str, raw_text: str, *, task: int | None = None, commands: set[int] | None = None) -> str:
    bar = "=" * 72
    dash = "-" * 72
    out: list[str] = [title, bar, ""]

    for segment in _selected(parse_transcript(raw_text), task, commands):
        if segment.kind == "command":
            block = segment.value
            assert isinstance(block, CommandBlock)
            out.extend(_console_lines(block))
            out.append("")
            continue

        marker = segment.value
        assert isinstance(marker, Marker)

        if marker.kind == "task":
            task_title = str(marker.data.get("title", "Задание"))
            out.extend([dash, task_title, dash, ""])
        elif marker.kind == "sep":
            out.extend([dash, ""])
        elif marker.kind == "note":
            out.extend([str(marker.data.get("text", "")), ""])
        elif marker.kind == "terminal_start":
            terminal = str(marker.data.get("title", "Terminal"))
            cwd = str(marker.data.get("cwd", ""))
            out.extend([dash, f"Terminal: {terminal}", cwd, dash, ""])
        elif marker.kind == "code":
            relpath = str(marker.data.get("path", ""))
            code_title = str(marker.data.get("title", "Код"))
            code_path = session_dir / relpath
            try:
                content = code_path.read_text(encoding="utf-8")
            except Exception as exc:
                content = f"[termrec: не удалось прочитать {relpath}: {exc}]"
            out.extend([f"[{code_title}]", content.rstrip("\n"), ""])
        elif marker.kind == "stop":
            pass

    return "\n".join(out).rstrip() + "\n"
