"""L1 layout-faithful export is an unconditional converter contract."""

from __future__ import annotations

import os
import unittest
from unittest import mock


class LayoutFaithfulExportTests(unittest.TestCase):
    def test_compile_does_not_depend_on_layout_faithful_env(self):
        from tasks import html_to_pptx as mod

        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["env"] = kwargs.get("env") or {}
            captured["cmd"] = cmd

            class R:
                returncode = 0
                stderr = ""
                stdout = ""

            # Touch output so compile thinks success.
            out = None
            for i, tok in enumerate(cmd):
                if tok == "-o" and i + 1 < len(cmd):
                    out = cmd[i + 1]
            if out:
                os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
                with open(out, "wb") as f:
                    f.write(b"PK\x03\x04fake")
            return R()

        with mock.patch.object(mod.subprocess, "run", side_effect=fake_run):
            with mock.patch.object(mod, "list_html_slides", return_value=[
                __import__("pathlib").Path("/tmp/slide_01.html")
            ]):
                # list_html_slides is used; create a temp dir with a slide
                import tempfile
                from pathlib import Path

                with tempfile.TemporaryDirectory() as tmp:
                    html_dir = Path(tmp) / "html"
                    html_dir.mkdir()
                    (html_dir / "slide_01.html").write_text("<html></html>", encoding="utf-8")
                    out = Path(tmp) / "out.pptx"
                    mod.compile_html_dir_to_pptx(html_dir, out)
        self.assertNotIn("DECKHTML_LAYOUT_FAITHFUL", captured["env"])
        self.assertIn("--mode", captured["cmd"])
        self.assertIn("--embed-fonts", captured["cmd"])


if __name__ == "__main__":
    unittest.main()
