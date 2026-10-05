import unittest

from tasks.scene_layout_ledger import build_scene_layout_ledger


class SceneLayoutLedgerTests(unittest.TestCase):
    def test_attributes_overflow_and_collision_to_scene_owners(self):
        scene = {
            "regions": [
                {"id": "title", "role": "title", "x": 60, "y": 48, "w": 700, "h": 90},
                {"id": "lede", "role": "lede", "x": 60, "y": 150, "w": 700, "h": 50},
            ]
        }
        runtime = {
            "hard": ["runtime_text_overflow: section[scene-lede] scrolls (0.0px x, 12.0px y)"],
            "inspection": {
                "elements": [
                    {"id": "section[scene-title]", "box": {"left": 60, "top": 48, "width": 700, "height": 90}},
                    {"id": "section[scene-lede]", "box": {"left": 60, "top": 150, "width": 700, "height": 50}, "overflow": {"contentY": 12}},
                ],
                "collisions": [{"a": "section[scene-title]", "b": "section[scene-lede]", "width": 5, "height": 3}],
            },
        }
        ledger = build_scene_layout_ledger(scene, runtime)
        self.assertEqual(ledger["regions"]["lede"]["issues"], runtime["hard"])
        self.assertEqual(ledger["collisions"][0]["owners"], ["title", "lede"])
        self.assertEqual(ledger["unowned_issues"], [])
        self.assertEqual("object", ledger["findings"][0]["repair_scope"])

    def test_carries_precise_collision_and_decoration_repairs(self):
        scene = {"regions": [{"id": "primary", "role": "primary", "x": 60, "y": 180, "w": 600, "h": 480}]}
        runtime = {
                "hard": [
                "runtime_sibling_collision: div.note:1 overlaps div[figure] by 100.0×10.0px",
                "runtime_decoration_collision: div.rule:2 crosses div.card:3 by 200.0×3.0px",
            ],
            "inspection": {
                "elements": [
                    {"id": "div.note:1", "box": {"left": 80, "top": 600, "width": 200, "height": 20}},
                    {"id": "div[figure]", "box": {"left": 70, "top": 250, "width": 500, "height": 380}},
                ],
                "collisions": [{
                    "a": "div.note:1", "b": "div[figure]", "width": 100, "height": 10,
                    "repair": {"sceneOwner": "primary", "targetSelector": "div.note", "strategy": "set_absolute_top", "suggestedTop": 330},
                }],
                "decorationCollisions": [{
                    "line": "div.rule:2", "target": "div.card:3", "sceneOwner": "primary",
                    "targetSelector": "div.card", "strategy": "shift_target_down",
                    "shiftY": 11, "currentMarginTop": 4, "suggestedMarginTop": 15,
                }],
                "pseudoIssues": [{
                    "type": "pseudo_text_collision", "selector": "div.thermal",
                    "pseudo": "::before", "sceneOwner": "primary",
                    "against": "p.acceptance:4", "overlap": {"width": 88, "height": 9},
                    "strategy": "set_top", "suggestedTop": 12,
                }],
                "textCollisions": [{
                    "a": "div.flow-label", "b": "div.boundary > span",
                    "sceneOwner": "primary", "width": 72, "height": 14,
                    "repair": {
                        "sceneOwner": "primary", "targetSelector": "div.flow-label",
                        "strategy": "set_absolute_left", "suggestedLeft": 932,
                    },
                }],
            },
        }
        runtime["hard"].append(
            "runtime_text_collision: div.flow-label overlaps div.boundary > span by 72.0×14.0px"
        )
        ledger = build_scene_layout_ledger(scene, runtime)
        primary = ledger["regions"]["primary"]
        self.assertEqual(primary["collision_repairs"][0]["suggestedTop"], 330)
        self.assertEqual(primary["decoration_repairs"][0]["suggestedMarginTop"], 15)
        self.assertEqual(primary["pseudo_repairs"][0]["suggestedTop"], 12)
        self.assertEqual(primary["pseudo_repairs"][0]["against"], "p.acceptance:4")
        self.assertEqual(primary["text_collision_repairs"][0]["suggestedLeft"], 932)
        self.assertEqual(ledger["unowned_issues"], [])


if __name__ == "__main__":
    unittest.main()
