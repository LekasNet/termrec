"""Platform recording backends.

The POSIX backend records only bytes emitted by the child pseudo-terminal. It does not
log stdin, so applications that turn terminal echo off do not leak typed passwords into
``session.raw``.
"""

from __future__ import annotations

import os
import select
import sys
from pathlib import Path


def run_posix_pty(
    argv: list[str], env: dict[str, str], output: Path, *, append: bool = False
) -> int:
    """Run *argv* in a PTY, mirror its output, and save output bytes only."""
    import pty

    pid, master_fd = pty.fork()
    if pid == 0:
        os.execvpe(argv[0], argv, env)

    status = 1
    with output.open("ab" if append else "wb") as recording:
        stdin_fd = sys.stdin.fileno()
        stdout_fd = sys.stdout.fileno()
        try:
            while True:
                readable, _, _ = select.select([master_fd, stdin_fd], [], [])
                if master_fd in readable:
                    try:
                        data = os.read(master_fd, 4096)
                    except OSError:
                        data = b""
                    if not data:
                        break
                    recording.write(data)
                    recording.flush()
                    os.write(stdout_fd, data)
                if stdin_fd in readable:
                    data = os.read(stdin_fd, 1024)
                    if not data:
                        break
                    os.write(master_fd, data)
        finally:
            os.close(master_fd)
            _, status = os.waitpid(pid, 0)

    return os.waitstatus_to_exitcode(status)
