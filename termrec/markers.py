from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any

OSC_PREFIX = "\x1b]5151;termrec;"
OSC_SUFFIX = "\x07"
MARKER_RE = re.compile(
    re.escape(OSC_PREFIX) + r"([A-Za-z0-9_-]+={0,2})" + re.escape(OSC_SUFFIX)
)


@dataclass(slots=True)
class Marker:
    kind: str
    data: dict[str, Any]


def encode_marker(kind: str, **data: Any) -> str:
    payload = {"kind": kind, **data}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii")
    return f"{OSC_PREFIX}{encoded}{OSC_SUFFIX}"


def decode_payload(payload: str) -> Marker:
    padding = "=" * (-len(payload) % 4)
    raw = base64.urlsafe_b64decode(payload + padding)
    data = json.loads(raw.decode("utf-8"))
    kind = str(data.pop("kind"))
    return Marker(kind=kind, data=data)


def split_markers(text: str) -> list[str | Marker]:
    parts: list[str | Marker] = []
    last = 0

    for match in MARKER_RE.finditer(text):
        if match.start() > last:
            parts.append(text[last : match.start()])
        try:
            parts.append(decode_payload(match.group(1)))
        except Exception:
            # Preserve malformed markers as raw text instead of losing transcript data.
            parts.append(match.group(0))
        last = match.end()

    if last < len(text):
        parts.append(text[last:])

    return parts
