"""Build a local, architecture-independent Debian package using the Python stdlib."""

from __future__ import annotations

import argparse
import gzip
import io
import re
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "dist"


def version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
    if not match:
        raise ValueError("Cannot read project version")
    return match.group(1)


def tar_gz(files: dict[str, tuple[bytes, int]]) -> bytes:
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w") as archive:
            for name, (data, mode) in sorted(files.items()):
                info = tarfile.TarInfo("./" + name)
                info.size = len(data)
                info.mode = mode
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                archive.addfile(info, io.BytesIO(data))
    return stream.getvalue()


def ar_member(name: str, data: bytes) -> bytes:
    if len(name) > 15:
        raise ValueError(name)
    header = (
        f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n"
    ).encode("ascii")
    assert len(header) == 60
    return header + data + (b"\n" if len(data) % 2 else b"")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default="1")
    args = parser.parse_args()
    release = f"{version()}-{args.revision}"

    files: dict[str, tuple[bytes, int]] = {}
    for path in sorted((ROOT / "termrec").glob("*")):
        if path.suffix in {".py", ".bash", ".zsh"}:
            files[f"usr/lib/termrec/termrec/{path.name}"] = (path.read_bytes(), 0o644)
    for command in ("rec", "termrec"):
        files[f"usr/bin/{command}"] = ((ROOT / "packaging" / "bin" / command).read_bytes(), 0o755)
    files["usr/share/doc/termrec/README.md"] = ((ROOT / "README.md").read_bytes(), 0o644)
    files["usr/share/doc/termrec/copyright"] = ((ROOT / "LICENSE").read_bytes(), 0o644)

    installed_size = (sum(len(data) for data, _ in files.values()) + 1023) // 1024
    control = (
        "Package: termrec\n"
        f"Version: {release}\n"
        "Architecture: all\n"
        "Maintainer: lekasnet <lekasnet@users.noreply.github.com>\n"
        "Depends: python3 (>= 3.10), bash\n"
        "Recommends: zsh\n"
        f"Installed-Size: {installed_size}\n"
        "Section: utils\n"
        "Priority: optional\n"
        "Description: Interactive terminal session recorder\n"
        " Records Bash or zsh sessions and exports Markdown or plain text reports.\n"
    ).encode("utf-8")

    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"termrec_{release}_all.deb"
    target.write_bytes(
        b"!<arch>\n"
        + ar_member("debian-binary", b"2.0\n")
        + ar_member("control.tar.gz", tar_gz({"control": (control, 0o644)}))
        + ar_member("data.tar.gz", tar_gz(files))
    )
    print(target)


if __name__ == "__main__":
    main()
