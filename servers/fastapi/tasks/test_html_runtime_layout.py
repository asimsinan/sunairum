"""Unit coverage for runtime browser-layout findings and their release contract."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from tasks.html_layout_qa import audit_runtime_html_layout


class RuntimeLayoutAuditTests(unittest.TestCase):
    def test_title_rule_clearance_is_a_hard_visual_failure(self):
        inspection = {
            "available": True,
            "elements": [],
            "wordFragments": [],
            "narrowText": [],
            "collisions": [],
            "textCollisions": [],
            "pseudoIssues": [],
            "decorationCollisions": [{
                "line": "div.baseline", "target": "h1",
                "width": 900, "height": 0, "gap": 18.8, "requiredGap": 25.6,
            }],
        }
        with patch("tasks.html_runtime_layout.inspect_html_layout", return_value=inspection):
            report = audit_runtime_html_layout("<section class='slide'></section>")
        self.assertFalse(report["ok"])
        self.assertIn("has only 18.8px clearance", report["hard"][0])

    def test_unregistered_text_node_collision_is_hard(self):
        inspection = {
            "available": True,
            "elements": [],
            "wordFragments": [],
            "narrowText": [],
            "collisions": [],
            "decorationCollisions": [],
            "pseudoIssues": [],
            "textCollisions": [{
                "a": "div.flow-label", "b": "div.boundary > span",
                "width": 72, "height": 14,
            }],
        }
        with patch("tasks.html_runtime_layout.inspect_html_layout", return_value=inspection):
            report = audit_runtime_html_layout("<section class='slide'></section>")
        self.assertFalse(report["ok"])
        self.assertIn("runtime_text_collision", report["hard"][0])
    def test_running_asyncio_loop_uses_subprocess_probe_directly(self):
        from tasks.html_runtime_layout import inspect_html_layout

        expected = {"available": True, "elements": [], "collisions": []}

        async def inspect():
            with patch(
                "tasks.html_runtime_layout._inspect_once",
                side_effect=AssertionError("sync Playwright must not run in asyncio loop"),
            ), patch(
                "tasks.html_runtime_layout._inspect_subprocess",
                return_value=expected,
            ) as subprocess_probe:
                result = inspect_html_layout("<section class='slide'></section>")
                self.assertEqual(1, subprocess_probe.call_count)
                return result

        self.assertEqual(expected, asyncio.run(inspect()))

    def test_subprocess_probe_does_not_shadow_stdlib_inspect(self):
        import json
        from pathlib import Path
        from types import SimpleNamespace

        from tasks.html_runtime_layout import _inspect_subprocess

        captured: dict[str, str] = {}

        def fake_run(command, **_kwargs):
            captured["runner"] = Path(command[1]).name
            Path(command[3]).write_text(
                json.dumps({"available": True, "elements": [], "collisions": []}),
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0, stderr="", stdout="")

        with patch("tasks.html_runtime_layout.subprocess.run", side_effect=fake_run):
            report = _inspect_subprocess(
                "<section class='slide'></section>", timeout_ms=1000
            )

        self.assertEqual("runtime_layout_probe.py", captured["runner"])
        self.assertTrue(report["available"])

    def test_detects_runtime_only_collisions_and_fragmented_words(self):
        inspection = {
            "available": True,
            "elements": [
                {
                    "id": "div.panel:0",
                    "outsidePlate": False,
                    "overflow": {"scrollX": 0, "scrollY": 0, "clippedByAncestor": False},
                },
                {
                    "id": "div.callout:1",
                    "outsidePlate": True,
                    "overflow": {"scrollX": 0, "scrollY": 14, "clippedByAncestor": True},
                },
            ],
            "wordFragments": [{"word": "Filter", "element": "span.node:-1", "lines": 5}],
            "collisions": [{"a": "div.panel:0", "b": "div.callout:1", "width": 280, "height": 50}],
        }
        with patch("tasks.html_runtime_layout.inspect_html_layout", return_value=inspection):
            report = audit_runtime_html_layout("<section class='slide'></section>")

        self.assertFalse(report["ok"])
        hard = "\n".join(report["hard"])
        self.assertIn("runtime_text_overflow", hard)
        self.assertIn("runtime_ancestor_clip", hard)
        self.assertIn("runtime_canvas_overflow", hard)
        self.assertIn("runtime_word_fragmented", hard)
        self.assertIn("runtime_sibling_collision", hard)

    def test_runtime_unavailable_always_blocks(self):
        unavailable = {"available": False, "error": "Chromium unavailable"}
        with patch("tasks.html_runtime_layout.inspect_html_layout", return_value=unavailable):
            report = audit_runtime_html_layout("<section class='slide'></section>")

        self.assertFalse(report["ok"])
        self.assertIn("runtime_layout_unavailable", report["hard"][0])

    def test_pipeline_page_number_line_box_does_not_fail_content_gate(self):
        inspection = {
            "available": True,
            "elements": [
                {
                    "id": "page-number",
                    "pageNumber": True,
                    "outsidePlate": False,
                    "overflow": {
                        "scrollX": 0,
                        "scrollY": 2,
                        "clippedByAncestor": False,
                    },
                }
            ],
            "wordFragments": [],
            "collisions": [],
        }
        with patch("tasks.html_runtime_layout.inspect_html_layout", return_value=inspection):
            report = audit_runtime_html_layout("<section class='slide'></section>")

        self.assertTrue(report["ok"])

    def test_absolute_lane_badge_can_bleed_region_when_it_stays_on_plate(self):
        inspection = {
            "available": True,
            "elements": [{
                "id": "section[scene-primary]",
                "outsidePlate": False,
                "overflow": {
                    "contentX": 0,
                    "contentY": 17,
                    "clippedByAncestor": False,
                    "targets": [{
                        "selector": ".lane-tag",
                        "overflowX": 0,
                        "overflowY": 17,
                        "position": "absolute",
                        "outsidePlate": False,
                    }],
                },
            }],
            "wordFragments": [],
            "narrowText": [],
            "collisions": [],
            "decorationCollisions": [],
            "pseudoIssues": [],
            "textCollisions": [],
        }
        with patch("tasks.html_runtime_layout.inspect_html_layout", return_value=inspection):
            report = audit_runtime_html_layout("<section class='slide'></section>")

        self.assertTrue(report["ok"])
        self.assertEqual([], report["hard"])

    def test_absolute_lane_badge_outside_plate_remains_hard(self):
        inspection = {
            "available": True,
            "elements": [{
                "id": "section[scene-primary]",
                "outsidePlate": False,
                "overflow": {
                    "contentX": 0,
                    "contentY": 17,
                    "clippedByAncestor": False,
                    "targets": [{
                        "selector": ".lane-tag",
                        "overflowX": 0,
                        "overflowY": 17,
                        "position": "absolute",
                        "outsidePlate": True,
                    }],
                },
            }],
            "wordFragments": [],
            "narrowText": [],
            "collisions": [],
            "decorationCollisions": [],
            "pseudoIssues": [],
            "textCollisions": [],
        }
        with patch("tasks.html_runtime_layout.inspect_html_layout", return_value=inspection):
            report = audit_runtime_html_layout("<section class='slide'></section>")

        self.assertFalse(report["ok"])
        self.assertIn("runtime_text_overflow", report["hard"][0])

    def test_title_glyph_ink_is_tolerated_but_pseudo_and_rule_collisions_block(self):
        inspection = {
            "available": True,
            "elements": [{
                "id": "h1.node:1",
                "sceneRole": "title",
                "outsidePlate": False,
                "typography": {"fontSize": 64, "lineHeight": 69.12},
                "overflow": {"contentX": 0, "contentY": 10, "clippedByAncestor": False},
            }],
            "wordFragments": [],
            "collisions": [],
            "decorationCollisions": [{
                "line": "div.rule:2", "target": "div.card:3", "width": 180, "height": 3,
            }],
            "pseudoIssues": [{
                "type": "text_proximity", "selector": "[data-layout-id=scene-title]",
                "pseudo": "::after", "gap": 2, "minGap": 16,
            }, {
                "type": "pseudo_text_collision", "selector": "div.thermal",
                "pseudo": "::before", "against": "p.acceptance:4",
                "overlap": {"width": 88, "height": 9},
            }],
        }
        with patch("tasks.html_runtime_layout.inspect_html_layout", return_value=inspection):
            report = audit_runtime_html_layout("<section class='slide'></section>")

        hard = "\n".join(report["hard"])
        self.assertNotIn("runtime_text_overflow", hard)
        self.assertIn("runtime_decoration_collision", hard)
        self.assertIn("runtime_text_proximity", hard)
        self.assertIn("runtime_pseudo_text_collision", hard)

    def test_nested_cover_title_ink_is_not_tripled_into_release_failures(self):
        inspection = {
            "available": True,
            "elements": [
                {
                    "id": "section[scene-title]",
                    "sceneRole": "title",
                    "outsidePlate": False,
                    "typography": {"fontSize": 64, "lineHeight": 69.12},
                    "overflow": {"contentX": 0, "contentY": 9, "clippedByAncestor": False},
                },
                {
                    "id": "div.title-copy:1",
                    "sceneRole": "title",
                    "outsidePlate": False,
                    "typography": {"fontSize": 64, "lineHeight": 69.12},
                    "overflow": {"contentX": 0, "contentY": 9, "clippedByAncestor": False},
                },
                {
                    "id": "h1.node:2",
                    "sceneRole": "title",
                    "outsidePlate": False,
                    "typography": {"fontSize": 64, "lineHeight": 69.12},
                    "overflow": {"contentX": 0, "contentY": 9, "clippedByAncestor": False},
                },
            ],
            "wordFragments": [],
            "narrowText": [],
            "collisions": [],
            "decorationCollisions": [],
            "pseudoIssues": [],
        }
        with patch("tasks.html_runtime_layout.inspect_html_layout", return_value=inspection):
            report = audit_runtime_html_layout("<section class='slide'></section>")

        self.assertTrue(report["ok"])
        self.assertEqual([], report["hard"])


if __name__ == "__main__":
    unittest.main()
