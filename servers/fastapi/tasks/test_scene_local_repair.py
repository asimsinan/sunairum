import re
import unittest

from tasks.scene_local_repair import repair_scene_html_layout


class SceneLocalRepairTests(unittest.TestCase):
    def test_moves_large_title_up_to_clear_decorative_rule(self):
        html = '''<!doctype html><html><head><style>.slide{width:1280px;height:720px}h1{margin-top:22px}</style></head><body><section class="slide"><div data-layout-id="scene-title"><h1>Title</h1><div class="baseline"></div></div></section></body></html>'''
        ledger = {"regions": {"title": {
            "role": "title", "issues": ["runtime_decoration_collision"], "components": [],
            "decoration_repairs": [{
                "targetSelector": "h1", "strategy": "shift_target_up", "suggestedMarginTop": 15.18,
            }],
        }}}
        repaired, meta = repair_scene_html_layout(html, ledger)
        self.assertTrue(meta["changed"])
        self.assertIn("h1{margin-top:15.18px!important;}", repaired)

    def test_repairs_only_measured_region_and_keeps_root_geometry(self):
        html = '''<!doctype html><html><head><style>.slide{width:1280px;height:720px}</style></head><body><section class="slide">
        <div data-layout-id="scene-title" style="position:absolute;left:60px;top:60px;width:900px;height:100px"><h1 style="font-size:60px;line-height:1.3">Title</h1></div>
        <div data-layout-id="scene-lede" style="position:absolute;left:60px;top:180px;width:900px;height:48px"><p style="font-size:24px;gap:20px">Lede</p></div>
        </section></body></html>'''
        ledger = {"regions": {"lede": {"role": "lede", "issues": ["runtime_text_overflow"], "components": [{"box": {"width": 900, "height": 48}, "overflow": {"contentY": 12}}]}}}
        repaired, meta = repair_scene_html_layout(html, ledger)
        self.assertTrue(meta["changed"])
        self.assertIn("font-size:19.20px", repaired)
        self.assertIn("left:60px;top:60px;width:900px;height:100px", repaired)
        self.assertIn("font-size:60px", repaired)

    def test_collapses_empty_marker_grid_with_only_small_type_tightening(self):
        html = '''<!doctype html><html><head><style>.slide{width:1280px;height:720px}.stage{display:grid;grid-template-columns:36px 1fr}</style></head><body><section class="slide"><div data-layout-id="scene-primary" style="position:absolute;left:60px;top:200px;width:500px;height:400px"><div class="stage"><div><span style="font-size:17px">Full copy</span></div></div></div></section></body></html>'''
        ledger = {"regions": {"primary": {"role": "primary", "issues": ["runtime_narrow_text"], "components": [], "grid_repairs": [{"selector": "div.stage", "strategy": "collapse_empty_track", "directChildren": 1, "columns": "36px 450px"}]}}}
        repaired, meta = repair_scene_html_layout(html, ledger)
        self.assertTrue(meta["changed"])
        self.assertIn("grid-template-columns:minmax(0,1fr)!important", repaired)
        self.assertIn("font-size:15.98px", repaired)

    def test_applies_semantic_caption_and_absolute_clearance_without_broad_tag_rules(self):
        html = '''<!doctype html><html><head><style>.slide{width:1280px;height:720px}</style></head><body><section class="slide"><div data-layout-id="scene-figure" style="position:absolute;left:640px;top:260px;width:580px;height:418px"><div class="stage"><div data-pptx="figure"></div><div class="note">Caption</div></div></div></section></body></html>'''
        ledger = {"regions": {"figure": {
            "role": "figure", "issues": ["runtime_sibling_collision"], "components": [],
            "collision_repairs": [
                {"targetSelector": "div.stage > div[figure]", "strategy": "reserve_semantic_bottom", "suggestedBottom": 46},
                {"targetSelector": "div.stage > div.note", "strategy": "set_absolute_top", "suggestedTop": 24},
            ],
        }}}
        repaired, meta = repair_scene_html_layout(html, ledger)
        self.assertTrue(meta["changed"])
        self.assertIn("div.stage > div[figure]{bottom:46.00px!important;}", repaired)
        self.assertIn("div.stage > div.note{top:24.00px!important;bottom:auto!important;}", repaired)
        self.assertNotIn(" span{font-size", repaired)

    def test_never_moves_a_component_outside_its_owner(self):
        """A negative offset lifts an element clear of the box it belongs to.

        The card's ordinal numeral then prints on the card above it, which reads
        as mislabelled content rather than as a resolved overlap.
        """
        html = '''<!doctype html><html><head><style>.slide{width:1280px;height:720px}</style></head><body><section class="slide"><div data-layout-id="scene-primary" style="position:absolute;left:60px;top:260px;width:580px;height:418px"><article class="card"><span class="scope-mark">02</span></article></div></section></body></html>'''
        ledger = {"regions": {"primary": {
            "role": "primary", "issues": ["runtime_sibling_collision"], "components": [],
            "collision_repairs": [
                {"targetSelector": "article.card > span.scope-mark", "strategy": "set_absolute_top", "suggestedTop": -41},
            ],
            "decoration_repairs": [
                {"targetSelector": "article.card > span.scope-mark", "strategy": "move_decoration_absolute", "suggestedTop": -20},
            ],
        }}}
        repaired, _meta = repair_scene_html_layout(html, ledger)
        self.assertNotIn("top:-41.00px", repaired)
        self.assertNotIn("top:-20.00px", repaired)

    def test_marker_gutter_is_reserved_against_spacing_tightening(self):
        """Padding a bullet lives in is structure, not slack to reclaim."""
        html = '''<!doctype html><html><head><style>.slide{width:1280px;height:720px}</style></head><body><section class="slide"><div data-layout-id="scene-primary" style="position:absolute;left:60px;top:200px;width:500px;height:400px"><ul class="claims"><li>Copy</li></ul></div></section></body></html>'''
        ledger = {"regions": {"primary": {
            "role": "primary", "issues": ["runtime_text_overflow"],
            "components": [{
                "layout_candidates": [
                    {"selector": "ul.claims > li", "paddingLeft": 24.0, "reservePaddingLeft": 16.0},
                ],
                "overflow": {"contentY": 40.0},
                "box": {"width": 500, "height": 400},
            }],
        }}}
        repaired, _meta = repair_scene_html_layout(html, ledger)
        match = re.search(r"ul\.claims > li\{padding-left:([0-9.]+)px", repaired)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(float(match.group(1)), 16.0)

    def test_moves_textual_pseudo_to_measured_free_side(self):
        html = '''<!doctype html><html><head><style>.slide{width:1280px;height:720px}.thermal::before{content:"normalized objective";position:absolute;bottom:13px}</style></head><body><section class="slide"><div data-layout-id="scene-secondary" style="position:absolute;left:656px;top:212px;width:564px;height:466px"><p>Acceptance copy</p><div class="thermal"></div></div></section></body></html>'''
        ledger = {"regions": {"secondary": {
            "role": "secondary", "issues": ["runtime_pseudo_text_collision"], "components": [],
            "pseudo_repairs": [{
                "selector": "div.thermal", "pseudo": "::before",
                "strategy": "set_top", "suggestedTop": 12,
            }],
        }}}
        repaired, meta = repair_scene_html_layout(html, ledger)
        self.assertTrue(meta["changed"])
        self.assertIn(
            "div.thermal::before{top:12.00px!important;bottom:auto!important;}",
            repaired,
        )

    def test_moves_only_colliding_absolute_text_label_horizontally(self):
        html = '''<!doctype html><html><head><style>.slide{width:1280px;height:720px}.flow-label{position:absolute;left:770px}.boundary span{position:absolute;left:12px}</style></head><body><section class="slide"><div data-layout-id="scene-primary" style="position:absolute;left:60px;top:200px;width:1160px;height:470px"><div class="flow-label">Explicit decision</div><div class="boundary"><span>Exact feasibility boundary</span></div></div></section></body></html>'''
        ledger = {"regions": {"primary": {
            "role": "process", "issues": ["runtime_text_collision"], "components": [],
            "text_collision_repairs": [{
                "targetSelector": "div.flow-label", "strategy": "set_absolute_left",
                "suggestedLeft": 932,
            }],
        }}}
        repaired, meta = repair_scene_html_layout(html, ledger)
        self.assertTrue(meta["changed"])
        self.assertIn("div.flow-label{left:932.00px!important;right:auto!important;}", repaired)
        self.assertIn(".boundary span{position:absolute;left:12px}", repaired)

    def test_auxiliary_panel_note_can_shrink_below_body_floor(self):
        html = '''<!doctype html><html><head><style>.panel-note{font-size:14px}</style></head><body><section class="slide"><div data-layout-id="scene-primary"><aside><p class="panel-note">Supporting note</p></aside></div></section></body></html>'''
        ledger = {"regions": {"primary": {
            "role": "process", "issues": ["runtime_text_overflow"],
            "components": [{
                "box": {"width": 282, "height": 252},
                "overflow": {"contentY": 49, "targets": [{
                    "selector": "aside > p.panel-note",
                    "fontSize": 14,
                    "lineHeight": 20,
                }]},
            }],
        }}}
        repaired, meta = repair_scene_html_layout(html, ledger)
        self.assertTrue(meta["changed"])
        self.assertIn("aside > p.panel-note{font-size:11.00px!important", repaired)


if __name__ == "__main__":
    unittest.main()
