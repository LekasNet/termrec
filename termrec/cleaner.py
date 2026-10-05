from __future__ import annotations

import re

# CSI sequences, including SGR, erase-line, cursor movement, etc.
CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
# OSC sequences other than termrec's private markers. Marker extraction happens first.
OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
# Other small ESC sequences.
ESC_RE = re.compile(r"\x1b[@-_]")

SCRIPT_HEADER_RE = re.compile(r"^Script started on .*\n?", re.MULTILINE)
SCRIPT_FOOTER_RE = re.compile(r"^Script done on .*\n?", re.MULTILINE)


def _apply_backspaces(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch == "\b":
            if out:
                out.pop()
        else:
            out.append(ch)
    return "".join(out)


def _normalize_carriage_returns(text: str) -> str:
    """
    Approximate terminal CR behavior line-by-line.

    PTY output commonly uses CRLF, which is a normal newline and must be preserved.
    Standalone CR is typically used by progress/redraw output; for those lines we keep
    only the last carriage-return segment because that is what remains visible.
    """
    text = text.replace("\r\n", "\n")

    lines: list[str] = []
    for line in text.split("\n"):
        if "\r" in line:
            line = line.split("\r")[-1]
        lines.append(line)
    return "\n".join(lines)


def clean_terminal_text(text: str) -> str:
    """Remove terminal presentation/control data while preserving actual command output."""
    text = SCRIPT_HEADER_RE.sub("", text)
    text = SCRIPT_FOOTER_RE.sub("", text)
    text = OSC_RE.sub("", text)
    text = CSI_RE.sub("", text)
    text = ESC_RE.sub("", text)
    text = _apply_backspaces(text)
    text = _normalize_carriage_returns(text)

    # Remove NULs and other control characters except tab/newline.
    text = "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)

    # Strip trailing spaces. Do not compact internal blank lines: they may belong to
    # actual program output and are now bounded precisely by command markers.
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip("\n")
