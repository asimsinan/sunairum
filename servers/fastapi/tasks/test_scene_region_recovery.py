import unittest

from tasks.scene_region_recovery import recover_scene_regions
from tasks.html_constitution import validate_slide_html


class SceneRegionRecoveryTests(unittest.TestCase):
    def test_never_replaces_authored_region(self):
        creative = '''<!doctype html><html><head><style>h1{font-size:64px}</style></head><body><section class="slide">
        <div data-layout-id="scene-title" data-layout-role="title">creative title</div>
        <div data-layout-id="scene-primary" data-layout-role="primary">broken creative panel</div>
        </section></body></html>'''
        fallback = '''<!doctype html><html><head><style>.scene-panel h2{font-size:18px}.slide{background:red}</style></head><body><section class="slide">
        <div data-layout-id="scene-title" data-layout-role="title">plain title</div>
        <div class="scene-panel" data-layout-id="scene-primary" data-layout-role="primary"><h2>measured panel</h2></div>
        </section></body></html>'''
        hybrid, meta = recover_scene_regions(creative, fallback, ["primary"])
        self.assertFalse(meta["changed"])
        self.assertIn("creative title", hybrid)
        self.assertNotIn("plain title", hybrid)
        self.assertNotIn("measured panel", hybrid)
        self.assertIn("broken creative panel", hybrid)
        self.assertNotIn('data-sunairum-region-recovery="1"', hybrid)
        self.assertNotIn("background:red", hybrid)
        self.assertEqual(1, hybrid.casefold().count("<style"))
        self.assertTrue(validate_slide_html(hybrid).ok)
        self.assertEqual("authored_dom_immutable", meta["blocked"])


if __name__ == "__main__":
    unittest.main()
