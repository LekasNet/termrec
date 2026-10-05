import json
import tempfile
import unittest
from pathlib import Path

from termrec.cli import export_one
from termrec.exporters import render_text
from termrec.markers import encode_marker


def command(text, output):
    return (
        encode_marker("command_start", command=text, internal=False)
        + output
        + encode_marker("command_end", status=0)
    )


class FeatureTests(unittest.TestCase):
    def test_pause_and_selection(self):
        raw = (
            encode_marker("task", title="First")
            + command("echo one", "one\n")
            + encode_marker("pause")
            + command("echo secret", "secret\n")
            + encode_marker("resume")
            + encode_marker("note", text="Remember this")
            + encode_marker("task", title="Second")
            + command("echo two", "two\n")
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            full = render_text(path, "Demo", raw)
            self.assertIn("Remember this", full)
            self.assertNotIn("secret", full)
            self.assertIn("echo one", render_text(path, "Demo", raw, task=1))
            self.assertNotIn("echo two", render_text(path, "Demo", raw, task=1))
            selected = render_text(path, "Demo", raw, commands={2})
            self.assertIn("echo two", selected)
            self.assertNotIn("echo one", selected)

    def test_export_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "session.json").write_text(json.dumps({"name": "Demo"}))
            (path / "session.raw").write_text(command("echo token123", "token123\n"))
            (path / "redactions.json").write_text(json.dumps([
                {"type": "literal", "value": "token123"}
            ]))
            report = export_one(path, "md").read_text()
            self.assertNotIn("token123", report)
            self.assertIn("[REDACTED]", report)

    def test_terminal_and_path_markers(self):
        raw = (
            encode_marker("terminal_start", title="Kitty — /dev/pts/4", cwd="/work")
            + encode_marker("command_start", command="pwd", internal=False, cwd="/work")
            + "/work\n"
            + encode_marker("command_end", status=0)
        )
        with tempfile.TemporaryDirectory() as tmp:
            report = render_text(Path(tmp), "Demo", raw)
            self.assertIn("Terminal: Kitty — /dev/pts/4", report)
            self.assertIn("# /work", report)


if __name__ == "__main__":
    unittest.main()
