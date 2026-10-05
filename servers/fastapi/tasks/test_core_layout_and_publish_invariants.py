"""Invariants behind the visual-defect and publish-refusal fixes.

Each test names the user-visible symptom it prevents, because the underlying
rules are easy to re-break with a locally reasonable change.
"""

from __future__ import annotations

import os
import re
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from tasks.free_design_pipeline import _reconcile_slide_table_bindings
from tasks.html_layout_qa import audit_runtime_html_layout
from tasks.scene_local_repair import strip_owner_escaping_repairs


TABLE_CATALOG = [
    {"table_id": "src-table-003", "caption": "HNSW evaluation counts", "columns": ["method", "evals"]},
    {"table_id": "src-table-008", "caption": "Solomon equity results", "columns": ["CV", "Gini", "Jain"]},
    {"table_id": "src-table-009", "caption": "Homberger equity", "columns": ["CV", "Gini"]},
]


def _slide() -> list[dict]:
    return [{
        "role": "content", "slide": 10, "table_id": "src-table-008",
        "title": "HNSW evaluation counts per method", "bullets": ["method evals"],
    }]


class TableSelectionObedienceTests(unittest.TestCase):
    """Symptom: "Production settings not fully applied - 1 tables missing"."""

    def test_fit_rescoring_never_leaves_the_user_selection(self):
        parsed = _slide()
        warnings = _reconcile_slide_table_bindings(
            parsed, TABLE_CATALOG, selected_table_ids=["src-table-009", "src-table-008"]
        )
        self.assertEqual("src-table-008", parsed[0]["table_id"])
        self.assertEqual([], warnings)

    def test_rebinding_between_two_chosen_tables_places_both(self):
        """Re-scoring may permute chosen tables; it must not drop one."""
        catalog = [
            {"table_id": "src-table-008", "caption": "Solomon equity results",
             "columns": ["CV", "Gini", "Jain"]},
            {"table_id": "src-table-009", "caption": "Homberger equity larger instances",
             "columns": ["CV", "Gini"]},
        ]
        parsed = [
            {"role": "content", "slide": 11, "table_id": "src-table-008",
             "title": "Homberger equity larger instances",
             "bullets": ["CV Gini across larger Homberger"]},
            {"role": "content", "slide": 13, "table_id": "src-table-009",
             "title": "Solomon equity results", "bullets": ["CV Gini Jain on Solomon"]},
        ]
        _reconcile_slide_table_bindings(
            parsed, catalog, selected_table_ids=["src-table-009", "src-table-008"]
        )
        self.assertEqual(
            ["src-table-008", "src-table-009"],
            sorted(item["table_id"] for item in parsed),
        )

    def test_without_a_selection_fit_rescoring_still_corrects_a_mismatch(self):
        parsed = _slide()
        _reconcile_slide_table_bindings(parsed, TABLE_CATALOG)
        self.assertEqual("src-table-003", parsed[0]["table_id"])


class OwnerEscapeMigrationTests(unittest.TestCase):
    """Symptom: a card's ordinal numeral printed on the card above it."""

    def test_strips_baked_in_rules_that_left_the_owner(self):
        html = (
            "a > span{top:-41.00px!important;bottom:auto!important;}"
            "b > span{top:9.00px!important;bottom:auto!important;}"
            "c > span{left:-16.77px!important;right:auto!important;}"
        )
        cleaned, count = strip_owner_escaping_repairs(html)
        self.assertEqual(2, count)
        self.assertNotIn("-41.00px", cleaned)
        self.assertNotIn("-16.77px", cleaned)
        self.assertIn("top:9.00px", cleaned)


def _slide_doc(body: str, style: str = "") -> str:
    return (
        "<!doctype html><html><head><style>"
        ".slide{position:relative;width:1280px;height:720px;margin:0;background:#fff}" + style +
        "</style></head><body><section class=\"slide\">" + body + "</section></body></html>"
    )


class RuntimeLayoutCoverageTests(unittest.TestCase):
    """Symptoms QA used to report as a clean slide."""

    def test_overflowing_copy_is_measured_whatever_the_class_is_called(self):
        """A card named outside the known vocabulary was never measured."""
        doc = _slide_doc(
            '<div data-layout-id="scene-primary" style="position:absolute;left:60px;top:60px;'
            'width:600px;height:400px">'
            '<div class="zzz-unknown-name">Some copy that is far too long for the box it was '
            'given and therefore spills straight out past the bottom edge of its own panel.</div>'
            "</div>",
            ".zzz-unknown-name{position:absolute;left:0;top:0;width:200px;height:24px;"
            "background:#2F855A;color:#fff;font:16px/19px Arial}",
        )
        report = audit_runtime_html_layout(doc)
        self.assertTrue(
            any("runtime_text_overflow" in item for item in report["hard"]),
            report["hard"],
        )

    def test_display_type_glyph_ink_is_not_reported_as_overflow(self):
        """A 44px numeral reports ~5px of ink past its line box with no clipping.

        A flat threshold flagged every display-size element on every slide, which
        both mislabelled clean decks and made the repair loop shrink type that was
        already correct.
        """
        doc = _slide_doc(
            '<div data-layout-id="scene-primary" style="position:absolute;left:60px;top:60px;'
            'width:600px;height:400px">'
            '<div class="stage-number">04</div>'
            "</div>",
            ".stage-number{position:absolute;left:0;top:0;height:44px;"
            "font:700 44px/44px Georgia,serif;color:#1A365D}",
        )
        report = audit_runtime_html_layout(doc)
        self.assertEqual(
            [], [item for item in report["hard"] if "runtime_text_overflow" in item],
            report["hard"],
        )

    def test_a_hidden_but_painting_semantic_host_is_reported_as_dead(self):
        """Symptom: a ghost second copy of a formula over the authored one."""
        doc = _slide_doc(
            '<div data-layout-id="scene-formula" style="position:absolute;left:60px;top:60px;'
            'width:600px;height:200px">'
            '<div class="ghost" data-pptx="formula"><span>f(R)</span></div>'
            "</div>",
            ".ghost{position:absolute;left:0;top:0;width:400px;height:80px;opacity:.01}",
        )
        report = audit_runtime_html_layout(doc)
        dead = report["inspection"].get("deadHosts") or []
        self.assertEqual(1, len(dead), dead)
        self.assertEqual("formula", dead[0]["kind"])

    def test_a_pseudo_rule_painted_across_copy_is_reported(self):
        """Symptom: an odd vertical line straight through three copy bands."""
        doc = _slide_doc(
            '<div data-layout-id="scene-primary" style="position:absolute;left:60px;top:60px;'
            'width:600px;height:300px">'
            '<div class="zone"><p class="band">Readable body copy that the rule crosses.</p></div>'
            "</div>",
            ".zone{position:relative;width:600px;height:300px}"
            ".zone::after{content:'';position:absolute;left:120px;top:0;width:1px;height:240px;"
            "background:#63B3ED}"
            ".band{margin:0;font:18px/24px Arial}",
        )
        report = audit_runtime_html_layout(doc)
        self.assertTrue(
            any("runtime_decoration_collision" in item for item in report["hard"]),
            report["hard"],
        )


class RoundContainerTests(unittest.TestCase):
    """Symptom: "aynı adım" crossing the curve of the 66px badge it sits in."""

    def _badge(self, font_px: int) -> dict:
        doc = _slide_doc(
            '<div data-layout-id="scene-primary" style="position:absolute;left:60px;top:60px;'
            'width:600px;height:300px">'
            '<span class="badge">aynı<br>adım</span>'
            "</div>",
            # box-sizing matches what the pipeline injects for every scene root.
            ".badge{box-sizing:border-box;position:absolute;left:40px;top:40px;"
            "width:66px;height:66px;display:flex;"
            "align-items:center;justify-content:center;background:#3182CE;color:#fff;"
            "border:7px solid #EBF4FB;border-radius:50%;"
            f"font:700 {font_px}px/1.1 Georgia,serif}}",
        )
        return audit_runtime_html_layout(doc)

    def test_copy_crossing_the_circle_is_reported_with_a_remedy(self):
        report = self._badge(18)
        rounds = report["inspection"].get("roundOverflows") or []
        self.assertEqual(1, len(rounds), rounds)
        # A 52px inner circle only fits 52/sqrt2 = 36.8px of copy.
        self.assertLess(float(rounds[0]["inscribed"]), 40.0)
        self.assertLess(float(rounds[0]["suggestedFontSize"]), 18.0)
        self.assertTrue(
            any("runtime_round_container_overflow" in item for item in report["hard"]),
            report["hard"],
        )

    def test_copy_that_fits_the_inscribed_square_is_not_reported(self):
        report = self._badge(9)
        self.assertEqual([], report["inspection"].get("roundOverflows") or [])


class HostDeadSpaceTests(unittest.TestCase):
    """Symptom: a table panel padded out with empty space below its last row."""

    def test_a_table_host_much_taller_than_its_table_is_reported(self):
        doc = _slide_doc(
            '<div data-layout-id="scene-table" style="position:absolute;left:60px;top:60px;'
            'width:600px;height:420px">'
            '<div class="host" data-pptx="table" data-table-id="t1">'
            '<table><tr><td>A</td><td>1</td></tr><tr><td>B</td><td>2</td></tr></table>'
            "</div></div>",
            ".host{box-sizing:border-box;width:100%;height:338px;background:#fff}"
            "table{width:100%;border-collapse:collapse;font:14px Arial}"
            "td{padding:6px}",
        )
        report = audit_runtime_html_layout(doc)
        slack = report["inspection"].get("hostSlack") or []
        self.assertEqual(1, len(slack), slack)
        self.assertGreater(float(slack[0]["slack"]), 200.0)
        self.assertLess(float(slack[0]["suggestedHeight"]), 338.0)

    def test_a_host_that_matches_its_table_is_not_reported(self):
        doc = _slide_doc(
            '<div data-layout-id="scene-table" style="position:absolute;left:60px;top:60px;'
            'width:600px;height:420px">'
            '<div class="host" data-pptx="table" data-table-id="t1">'
            '<table><tr><td>A</td><td>1</td></tr></table>'
            "</div></div>",
            ".host{box-sizing:border-box;width:100%;background:#fff}"
            "table{width:100%;border-collapse:collapse;font:14px Arial}"
            "td{padding:6px}",
        )
        self.assertEqual([], audit_runtime_html_layout(doc)["inspection"].get("hostSlack") or [])


class DecorationAcrossTextTests(unittest.TestCase):
    """Symptom: a title underline left at a fixed offset while the title wrapped."""

    def test_a_thin_horizontal_rule_crossing_a_heading_is_reported(self):
        doc = _slide_doc(
            '<div data-layout-id="scene-title" style="position:absolute;left:60px;top:40px;'
            'width:900px;height:240px">'
            '<div class="wrap"><h1>A title long enough to wrap onto three separate '
            'lines inside its own box</h1></div>'
            "</div>",
            ".wrap{position:relative}"
            ".wrap::after{content:'';position:absolute;left:0;top:80px;width:74px;height:1px;"
            "background:#63B3ED}"
            "h1{margin:0;font:700 44px/1.1 Georgia,serif}",
        )
        report = audit_runtime_html_layout(doc)
        self.assertTrue(
            any("runtime_decoration_collision" in item for item in report["hard"]),
            report["hard"],
        )


class ContinuationDegradationTests(unittest.TestCase):
    """Symptom: one over-long slide aborted a run that had 12 finished slides."""

    def test_over_long_copy_renders_what_fits_instead_of_raising(self):
        from tasks.scene_html_renderer import render_scene_html

        slide = {"slide": 13, "title": "T", "lede": "L",
                 "bullets": [f"point {index}" for index in range(1, 15)]}
        scene = {"ok": True, "composition": "body", "regions": [
            {"id": "title", "role": "title", "x": 60, "y": 60, "w": 1160, "h": 60},
            {"id": "lede", "role": "lede", "x": 60, "y": 130, "w": 1160, "h": 50},
            {"id": "primary", "role": "primary", "x": 60, "y": 200, "w": 1160, "h": 460},
        ]}
        doc = render_scene_html(slide=slide, scene=scene, palette={})
        self.assertIn('data-sunairum-scene-card-overflow="6"', doc)
        self.assertIn("point 1", doc)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class FontPolicyInvariants(unittest.TestCase):
    """A deck may only name faces the exporter can embed.

    Three renderers measure a deck — Chromium for previews and layout QA,
    LibreOffice for the PDF, PowerPoint on the reader's machine. An Office face
    name resolves differently in each, so the reader sees line breaks nobody
    verified and text lands on top of its neighbour.
    """

    def test_office_faces_resolve_to_shipped_families(self):
        from tasks.font_policy import (
            EMBEDDABLE_FAMILIES,
            MONO_FAMILY,
            SANS_FAMILY,
            SERIF_FAMILY,
            normalize_font_stack,
        )

        self.assertEqual(
            normalize_font_stack('Arial, "Microsoft YaHei", sans-serif'),
            f"'{SANS_FAMILY}', sans-serif",
        )
        self.assertEqual(
            normalize_font_stack('Georgia, "Microsoft YaHei", serif'),
            f"'{SERIF_FAMILY}', serif",
        )
        # The mono face is staged by the image build, so what a code stack
        # resolves to depends on the environment — but it must always be a
        # family this environment can embed.
        from tasks.font_policy import available_families

        code_stack = normalize_font_stack('"SF Mono", Consolas, monospace')
        self.assertIn(
            code_stack.split(",")[0].strip().strip("'"), available_families() | {MONO_FAMILY}
        )
        self.assertTrue(code_stack.endswith("monospace"))
        # An unknown face keeps the generic the author asked for.
        self.assertEqual(
            normalize_font_stack("Whatever Display, serif"),
            f"'{SERIF_FAMILY}', serif",
        )
        # A family we ship *and* have on disk is left as the author named it.
        for family in EMBEDDABLE_FAMILIES & available_families():
            self.assertIn(family, normalize_font_stack(f"{family}, sans-serif"))

    def test_authored_html_is_rewritten_before_measurement(self):
        from tasks.html_pipeline import normalize_html_font_families

        html = (
            "<style>body{font-family:Arial,'PingFang SC',sans-serif}"
            ".t{font:36px/44px Georgia,serif}"
            "code{font-family:Consolas,monospace}</style>"
            "<p style=\"font-family:Helvetica Neue, sans-serif\">x</p>"
        )
        from tasks.font_policy import available_families

        out, meta = normalize_html_font_families(html)
        self.assertTrue(meta["changed"])
        self.assertEqual(meta["stacks"], 4)
        for banned in ("Arial", "Georgia", "Consolas", "Helvetica"):
            self.assertNotIn(banned, out)
        self.assertIn("Source Sans 3", out)
        self.assertIn("Source Serif 4", out)
        for stack in re.findall(r"font-family:\s*'?([^,';}\"]+)", out):
            self.assertIn(stack.strip(), available_families())

    def test_shipped_stack_is_left_alone(self):
        from tasks.html_pipeline import normalize_html_font_families

        html = "<style>body{font-family:'Source Sans 3', sans-serif}</style>"
        out, meta = normalize_html_font_families(html)
        self.assertFalse(meta["changed"])
        self.assertEqual(out, html)

    def test_unembedded_text_face_is_a_reported_defect(self):
        import zipfile

        from tasks.pptx_visual_verify import unembedded_typefaces

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deck.pptx"
            with zipfile.ZipFile(path, "w") as bundle:
                bundle.writestr(
                    "ppt/slides/slide1.xml",
                    '<p:sld><a:latin typeface="Source Sans 3"/>'
                    '<a:latin typeface="Consolas"/>'
                    '<a:latin typeface="Wingdings"/></p:sld>',
                )
                bundle.writestr("ppt/fonts/font1.fntdata", b"\x00")
                bundle.writestr(
                    "ppt/presentation.xml",
                    '<p:presentation><p:embeddedFontLst><p:embeddedFont>'
                    '<p:font typeface="Source Sans 3"/></p:embeddedFont>'
                    "</p:embeddedFontLst></p:presentation>",
                )
            # Consolas is named but not carried; the symbol face is structural.
            self.assertEqual(unembedded_typefaces(path), ["Consolas"])


class TextDriftInvariants(unittest.TestCase):
    """No re-flow, no fused words: what Chromium laid out is what ships."""

    def test_trailing_punctuation_gets_air_before_the_next_word(self):
        from tasks.html_pipeline import normalize_inline_text_boundaries

        out, meta = normalize_inline_text_boundaries(
            "<div><em>Interpretation:</em>candidate reduction</div>"
        )
        self.assertEqual(meta["boundaries"], 1)
        self.assertIn("</em> candidate", out)

    def test_existing_spacing_and_punctuation_tails_are_untouched(self):
        from tasks.html_pipeline import normalize_inline_text_boundaries

        for markup in ("<div><em>note</em> spaced</div>", "<div><em>see</em>, then</div>"):
            _out, meta = normalize_inline_text_boundaries(markup)
            self.assertEqual(meta["boundaries"], 0, markup)


class FontAvailabilityInvariants(unittest.TestCase):
    """A family we cannot embed here must never reach the authored CSS."""

    def test_missing_family_degrades_to_one_we_ship(self):
        from tasks import font_policy

        font_policy.available_families.cache_clear()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                # Only the sans face exists in this environment.
                Path(tmp, "source-sans-3-400.ttf").write_bytes(b"\x00")
                with unittest.mock.patch.object(
                    font_policy, "_font_dirs", lambda: [Path(tmp)]
                ):
                    font_policy.available_families.cache_clear()
                    self.assertEqual(
                        font_policy.available_families(), frozenset({font_policy.SANS_FAMILY})
                    )
                    # Code would otherwise name a mono face nothing carries, and
                    # the reader's renderer would re-measure every code run.
                    self.assertEqual(
                        font_policy.normalize_font_stack("Consolas, monospace"),
                        f"'{font_policy.SANS_FAMILY}', monospace",
                    )
                    self.assertEqual(
                        font_policy.normalize_font_stack("Georgia, serif"),
                        f"'{font_policy.SANS_FAMILY}', serif",
                    )
        finally:
            font_policy.available_families.cache_clear()

    def test_shipped_repo_carries_the_families_the_defaults_name(self):
        from tasks.font_policy import SANS_FAMILY, SERIF_FAMILY, available_families

        # These two are committed; the mono face is staged by the image build.
        self.assertIn(SANS_FAMILY, available_families())
        self.assertIn(SERIF_FAMILY, available_families())


def _probe_slide(body: str, extra_css: str = "") -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=1280">
<style>
 html,body{{margin:0;width:1280px;height:720px;background:#fff;font-family:Arial,sans-serif}}
 .slide{{position:relative;width:1280px;height:720px}}
 {extra_css}
</style></head><body><div class="slide">
 <section style="position:absolute;left:60px;top:60px;width:600px;height:400px;"
   data-layout-id="scene-primary" data-layout-role="primary">{body}</section>
</div></body></html>"""


def _probe_lede_slide(body: str, extra_css: str = "", lane_height: int = 27) -> str:
    """A one-line lede lane, the shape a Scene contract actually hands out."""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=1280">
<style>
 html,body{{margin:0;width:1280px;height:720px;background:#fff;font-family:Arial,sans-serif}}
 .slide{{position:relative;width:1280px;height:720px}}
 {extra_css}
</style></head><body><div class="slide">
 <section style="position:absolute;left:60px;top:130px;width:1160px;height:{lane_height}px;"
   data-layout-id="scene-lede" data-layout-role="lede">{body}</section>
</div></body></html>"""


class OverlapDetectionInvariants(unittest.TestCase):
    """Real text-on-text is reported; ordinary tight typography is not.

    Glyph ink crosses a flow boundary whenever line-height is tighter than the
    face's natural extent — a 21px serif on a 22px line box puts its descenders
    into the leading below. Comparing ink rects called that a collision on every
    metric row of a slide, twice over, and the repair pushed the rows apart until
    the card overflowed. Suppressing it must not cost a real overlap.
    """

    def _collisions(self, html: str) -> list[str]:
        report = audit_runtime_html_layout(html)
        inspection = report.get("inspection") or {}
        if not inspection.get("available"):
            self.skipTest(f"Chromium unavailable: {report.get('issues')}")
        return [item for item in report.get("hard") or [] if "collision" in item]

    def test_tight_line_height_between_stacked_blocks_is_not_a_collision(self):
        html = _probe_slide(
            '<div class="row"><strong>Toplam rota mesafesi</strong>'
            "<span>Temel verimlilik olcutudur bu satir</span></div>",
            ".row{display:flex;flex-direction:column}"
            ".row strong{font-size:21px;line-height:22px;font-family:Georgia,serif}"
            ".row span{font-size:15px;line-height:18px}",
        )
        self.assertEqual(self._collisions(html), [])

    def test_absolutely_positioned_copy_dropped_on_copy_is_reported(self):
        html = _probe_slide(
            '<p style="position:absolute;left:0;top:0;width:400px;font-size:18px">'
            "Bir uzun paragraf metni burada yer alir ve devam eder</p>"
            '<p style="position:absolute;left:0;top:8px;width:400px;font-size:18px">'
            "Ikinci paragraf tam ustune binmis durumda duruyor</p>"
        )
        self.assertTrue(self._collisions(html))

    def test_a_negative_margin_pulling_text_onto_text_is_reported(self):
        html = _probe_slide(
            '<p style="font-size:20px;line-height:26px;margin:0">'
            "Ilk satir burada duruyor ve uzundur</p>"
            '<p style="font-size:20px;line-height:26px;margin:-22px 0 0 0">'
            "Ikinci satir yukariya bindi</p>"
        )
        self.assertTrue(self._collisions(html))

    def test_a_formulas_own_stacking_is_not_a_collision(self):
        """A sum's limits sit under and over its operator by design.

        The formula also leaves as one exported object (OMML), so its interior is
        not subject to the deck's collision rules — measuring it reported
        "∑ overlaps =" and "min overlaps ∈" as slide defects.
        """
        html = _probe_slide(
            '<div class="formula-host" data-pptx="formula" data-formula-id="f1">'
            '<math xmlns="http://www.w3.org/1998/Math/MathML" display="block"'
            ' style="font-size:24px">'
            "<munderover><mo>∑</mo>"
            "<mrow><mi>j</mi><mo>=</mo><mn>1</mn></mrow>"
            "<mrow><mi>m</mi></mrow></munderover>"
            "<mi>c</mi><mo>(</mo><msub><mi>R</mi><mi>j</mi></msub><mo>)</mo>"
            "</math></div>",
            ".formula-host{position:relative;width:520px;height:120px}",
        )
        self.assertEqual(self._collisions(html), [])

    def test_a_corner_tick_is_not_measured_as_a_bullet_gutter(self):
        """A compact ::after pinned to a panel's right edge is decoration.

        Measured as a bullet marker it reported the whole panel width as an
        overlap (433px on a real slide) and asked for a matching padding-left,
        which would have emptied the panel.
        """
        html = _probe_slide(
            '<aside class="panel"><p>Panel govdesi burada yer alir ve okunur</p></aside>',
            ".panel{position:relative;width:520px;padding:16px}"
            '.panel::after{content:"";position:absolute;right:12px;left:auto;top:10px;'
            "width:14px;height:14px;background:#3182CE}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        self.assertEqual(
            [item for item in report.get("hard") or [] if "marker_gutter" in item], []
        )


class RepairSafetyInvariants(unittest.TestCase):
    """A repair must not create the defect it was called to fix."""

    def test_shrink_is_bounded_by_the_authored_size(self):
        """Each pass measures what the last one produced, so it compounds.

        A display number authored at 104px was taken to 74.9 → 53.9 → 38.8 →
        28.0 → 20.1 → 14.5px over six passes: a 7x cut that is no longer the
        design, and with its tracking no longer legible.
        """
        from tasks.scene_local_repair import (
            _MAX_CUMULATIVE_FONT_SHRINK,
            _authored_font_size,
        )

        html = (
            "<style>.anchor-number{font-size:104px;letter-spacing:-5px}\n"
            '[data-layout-id="scene-primary"] aside.anchor > div.anchor-number'
            "{font-size:74.88px!important;}</style>"
        )
        selector = '[data-layout-id="scene-primary"] aside.anchor > div.anchor-number'
        # The author's own declaration is found through the element's class, so
        # a later pass cannot mistake an already-shrunk size for the original.
        self.assertEqual(_authored_font_size(html, selector), 104.0)
        self.assertGreater(104.0 * _MAX_CUMULATIVE_FONT_SHRINK, 50.0)

    def test_letter_spacing_scales_with_the_font(self):
        from tasks.scene_local_repair import repair_scene_html_layout

        html = (
            "<html><body><section data-layout-id=\"scene-primary\">"
            '<div class="big">14</div></section>'
            "<style>.big{font-size:100px;letter-spacing:-5px}</style></body></html>"
        )
        ledger = {
            "regions": {
                "primary": {
                    "role": "primary",
                    "issues": ["runtime_text_overflow: div.big scrolls (0.0px x, 40.0px y)"],
                    "components": [{
                        "id": "div.big:1",
                        "selector": "div.big",
                        "overflow": {"targets": [{
                            "selector": "div.big",
                            "overflowY": 40.0,
                            "fontSize": 100.0,
                            "lineHeight": 84.0,
                            "letterSpacing": -5.0,
                            "position": "static",
                        }]},
                    }],
                }
            }
        }
        out, meta = repair_scene_html_layout(html, ledger)
        if not meta.get("changed"):
            self.skipTest("repair declined; bound already reached")
        emitted = re.findall(r"font-size:([\d.]+)px[^}]*?letter-spacing:(-?[\d.]+)px", out)
        self.assertTrue(emitted, f"no scaled tracking emitted: {out[-400:]}")
        size, tracking = (float(value) for value in emitted[0])
        # Tracking keeps its ratio to the em (-5/100 = -0.05).
        self.assertAlmostEqual(tracking / size, -0.05, places=2)

    def test_a_single_line_keeps_the_line_height_that_centres_it(self):
        """A badge centres "01" in a 28px circle with line-height:24px.

        Scaling that with the font (right for flowing copy, where it is the
        pitch) lifted every number off the centre of its circle.
        """
        html = _probe_slide(
            '<span class="node">01</span><p class="copy">Bir paragraf metni burada '
            "akar ve birkac satira boluner boyunca devam eder</p>",
            ".node{display:inline-block;width:28px;height:28px;border:2px solid #63B3ED;"
            "border-radius:50%;font-size:15px;line-height:24px;text-align:center}"
            ".copy{width:200px;font-size:16px;line-height:24px}",
        )
        report = audit_runtime_html_layout(html)
        inspection = report.get("inspection") or {}
        if not inspection.get("available"):
            self.skipTest("Chromium unavailable")
        flags = {}
        for element in inspection.get("elements") or []:
            typography = element.get("typography") or {}
            if "centersWithLineHeight" in typography:
                flags[str(element.get("id"))] = typography["centersWithLineHeight"]
        multi = [key for key, value in flags.items() if "copy" in key and value is False]
        self.assertTrue(multi, f"a wrapped paragraph must not be treated as centred: {flags}")

    def test_a_thin_rule_crossing_a_sentence_is_reported(self):
        """`isComponent` needs 8px in both axes, so a 3px rule was never measured.

        A 78x3px accent bar was drawn straight through the second line of a
        note, and the pass whose whole purpose is to keep rules off the copy
        could not see a single rule.
        """
        html = _probe_slide(
            '<p class="note">HERO, arama yukunu azaltip esitligi iyilestirir; dengeli '
            'ozel cozuculer ise bu veri kumesinde kalite sinirini belirler.</p>'
            '<div class="micro-rule" aria-hidden="true" data-pptx-kind="decoration"></div>',
            ".note{width:420px;font-size:17px;line-height:24px;margin:0}"
            ".micro-rule{position:absolute;left:24px;top:38px;width:78px;height:3px;"
            "background:#3182CE}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        crossings = [item for item in report.get("hard") or [] if "decoration_collision" in item]
        self.assertTrue(crossings, f"rule through copy not reported: {report.get('hard')}")

    def test_a_frozen_editor_height_cannot_crush_its_own_copy(self):
        from tasks.html_pipeline import relax_frozen_text_heights

        html = (
            "<html><body>"
            '<div data-sun-freeform="1" style="position: absolute; left: 24px; '
            'top: 51px; width: 188px; height: 16px; box-sizing: border-box;">14</div>'
            '<div data-sun-freeform="1" style="position:absolute;left:0;top:0;'
            'width:80px;height:3px;background:#3182CE"></div>'
            "</body></html>"
        )
        out, meta = relax_frozen_text_heights(html)
        self.assertTrue(meta["changed"])
        self.assertEqual(meta["boxes"], 1, "only the box that owns copy is relaxed")
        self.assertIn("min-height:16px", out)
        self.assertIn("height:auto", out)
        # A decoration keeps its exact frozen height: it has no copy to crush.
        self.assertIn("height:3px", out)


class FrozenGeometryInvariants(unittest.TestCase):
    """The editor's freeform freeze must not outlive the layout it measured."""

    def test_a_freeze_smaller_than_its_own_type_is_discarded(self):
        """A single line cannot be shorter than its font, so this freeze is corrupt.

        The numeral was pinned at height:16px while a fit pass had it down at
        14px. Relaxing only the height left the stale `top` behind, and the
        repair then had to move the number below the copy it labels — legible,
        not overlapping, and in the wrong reading order.
        """
        from tasks.html_pipeline import relax_frozen_text_heights

        html = (
            "<html><head><style>.anchor-number{font-size:104px;margin-top:48px}"
            "</style></head><body>"
            '<div class="anchor-number" data-sun-freeform="1" style="position: absolute;'
            ' left: 24px; top: 51px; width: 188px; height: 16px; margin:0.00px;'
            ' box-sizing: border-box; max-width: none;">14</div>'
            "</body></html>"
        )
        out, meta = relax_frozen_text_heights(html)
        self.assertEqual(meta["restored_to_flow"], 1)
        self.assertEqual(meta["boxes"], 0)
        for stale in ("position", "top:", "left:", "height:", "margin:", "max-width"):
            self.assertNotIn(stale, out.split("<body>")[1], stale)
        # The author's own rule is what places it again.
        self.assertIn("margin-top:48px", out)

    def test_a_legitimate_freeze_keeps_its_placement(self):
        from tasks.html_pipeline import relax_frozen_text_heights

        html = (
            "<html><head><style>.label{font-size:13px}</style></head><body>"
            '<div class="label" data-sun-freeform="1" style="position:absolute;'
            'left:24px;top:51px;width:188px;height:18px;">Etiket metni</div>'
            "</body></html>"
        )
        out, meta = relax_frozen_text_heights(html)
        self.assertEqual(meta["restored_to_flow"], 0)
        self.assertEqual(meta["boxes"], 1)
        # Dragged position survives; only the cage becomes a floor.
        self.assertIn("top:51px", out)
        self.assertIn("min-height:18px", out)
        self.assertIn("height:auto", out)

    def test_a_rule_with_nowhere_clear_to_go_is_hidden_not_drawn_on_copy(self):
        """An accent bar drawn through a sentence is worse than no accent bar.

        Moving the copy instead pushes it further out of a region that may
        already be overflowing, which is why the copy-side repair kept being
        measured as no improvement and rejected.
        """
        html = _probe_slide(
            '<p class="label">OKUMA</p>'
            '<p class="note">HERO, arama yukunu azaltip esitligi iyilestirir; dengeli '
            'ozel cozuculer ise bu veri kumesinde kalite sinirini belirler.</p>'
            '<div class="micro-rule" aria-hidden="true" data-pptx-kind="decoration"></div>',
            ".label{margin:0;font-size:13px;line-height:18px}"
            ".note{width:420px;font-size:17px;line-height:24px;margin:0}"
            ".micro-rule{position:absolute;left:24px;top:44px;width:78px;height:3px;"
            "background:#3182CE}",
        )
        report = audit_runtime_html_layout(html)
        inspection = report.get("inspection") or {}
        if not inspection.get("available"):
            self.skipTest("Chromium unavailable")
        collisions = inspection.get("decorationCollisions") or []
        self.assertTrue(collisions, "rule through copy not detected")
        strategies = {str(item.get("ruleStrategy") or "") for item in collisions}
        # The rule is moved when the owner has a clear band and dropped when it
        # does not — either way the sentence is never struck through.
        self.assertTrue(
            strategies <= {"set_rule_top", "set_rule_bottom", "hide_decoration"},
            strategies,
        )
        self.assertTrue(all(item.get("ruleSelector") for item in collisions))


class ListMarkerInvariants(unittest.TestCase):
    """A leading number is content until proved otherwise.

    Stripping the character class `[\\s...\\d.)(]+` off a bullet line walks past
    the marker and into the sentence: "1. 1,74x fewer evaluations" reached the
    slide as ",74x", a figure quietly changed by a factor of a hundred.
    """

    def test_a_measurement_after_a_marker_keeps_its_leading_digit(self):
        from tasks.asset_narrative import strip_list_marker

        self.assertEqual(
            strip_list_marker("1. 1,74x daha az mesafe degerlendirmesi."),
            "1,74x daha az mesafe degerlendirmesi.",
        )

    def test_markers_are_still_stripped(self):
        from tasks.asset_narrative import strip_list_marker

        for line, expected in (
            ("- 61,3% CV azalmasi", "61,3% CV azalmasi"),
            ("\u2022 HNSW hizlandirir", "HNSW hizlandirir"),
            ("2) 2019 yilinda", "2019 yilinda"),
            ("3. 3 adimda kurulum", "3 adimda kurulum"),
        ):
            self.assertEqual(strip_list_marker(line), expected)

    def test_a_line_with_no_marker_is_untouched(self):
        from tasks.asset_narrative import strip_list_marker

        self.assertEqual(strip_list_marker("1.74x faster"), "1.74x faster")

    def test_the_real_card_line_keeps_its_measurement(self):
        # The exact line the strategist wrote for the deck that surfaced this.
        # Its own output was always right; the parse is what lost the digit.
        from tasks.asset_narrative import strip_list_marker

        cleaned = strip_list_marker("  - **1,74x:** Daha az mesafe degerlendirmesi.")
        self.assertTrue(cleaned.startswith("**1,74x"), cleaned)

    def test_no_parser_strips_leading_digits_wholesale(self):
        """No fourth copy of the blunt character class.

        Three separate parsers each carried
        `re.sub(r"^[\\s...\\d.)(]+", "", line)`, and fixing two of them left the
        third -- the one that actually builds the cards -- still eating the
        digit. The class is the defect, wherever it appears.
        """
        import pathlib
        import re as _re

        tasks_dir = pathlib.Path(__file__).resolve().parent
        offenders = []
        pattern = _re.compile(r"""sub\(\s*r["']\^\[[^]]*\\d[^]]*\]\+""")
        for path in sorted(tasks_dir.glob("*.py")):
            if path.name.startswith("test_"):
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if pattern.search(line):
                    offenders.append(f"{path.name}:{number}: {line.strip()}")
        self.assertEqual(
            offenders,
            [],
            "a parser strips leading digits wholesale; use strip_list_marker:\n"
            + "\n".join(offenders),
        )


class GridItemInvariants(unittest.TestCase):
    """A grid container's ::before is a grid item; `children` does not list it.

    A bullet row authored as `24px 1fr` with the dot as ::before *and* a blank
    spacer span has three items for two tracks, so the sentence wraps onto a
    second row and lands in the 24px decoration column -- nine characters to
    the line beside a dot.
    """

    def _row(self, markup: str) -> dict:
        html = _probe_slide(
            f'<ul class="evidence">{markup}</ul>',
            ".evidence{margin:0;padding:0;list-style:none}"
            ".evidence li{display:grid;grid-template-columns:24px 1fr;column-gap:12px;"
            "align-items:start;padding:15px 0;font-size:17px;line-height:1.32}"
            '.evidence li::before{content:"";width:10px;height:10px;background:#3182CE}',
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        return report

    def test_a_blank_spacer_beside_a_generated_dot_is_reported(self):
        report = self._row(
            "<li><span> </span><div>Solomon orneklerinde degerlendirme "
            "sayisini 1,74 kat azaltir.</div></li>"
        )
        found = [
            item
            for item in (report.get("inspection") or {}).get("gridItemOverflow") or []
            if isinstance(item, dict)
        ]
        self.assertTrue(found, "three items in a two-track grid not reported")
        self.assertTrue(str(found[0]["spareSelector"]).endswith("span"))
        self.assertEqual(found[0]["items"], 3)
        self.assertEqual(found[0]["columns"], 2)

    def test_a_row_whose_items_match_its_tracks_is_left_alone(self):
        report = self._row(
            "<li><div>Solomon orneklerinde degerlendirme sayisini azaltir.</div></li>"
        )
        self.assertFalse((report.get("inspection") or {}).get("gridItemOverflow"))

    def test_an_item_that_carries_content_is_never_the_one_dropped(self):
        # Three items, two tracks, and nothing empty: the row is over-packed
        # with real content, which is a different problem and must not be
        # "fixed" by hiding a sentence.
        report = self._row(
            "<li><span>01</span><div>Birinci bulgu</div><div>Ikinci bulgu</div></li>"
        )
        for item in (report.get("inspection") or {}).get("gridItemOverflow") or []:
            self.fail(f"offered to drop a content item: {item}")


class RepairBoundInvariants(unittest.TestCase):
    """A repair that is not bounded is not a repair.

    `margin-bottom: -overrun` with no cap emitted -527px, hauling one bullet's
    text bodily up through the list and across the summary line beneath it.
    """

    def test_the_negative_pull_is_capped(self):
        from tasks.scene_local_repair import _MAX_NEGATIVE_PULL

        self.assertLessEqual(_MAX_NEGATIVE_PULL, 24.0)

    def test_a_large_overrun_declines_instead_of_pulling(self):
        from tasks.scene_local_repair import _MAX_NEGATIVE_PULL, repair_scene_html_layout

        ledger = {
            "regions": {
                "primary": {
                    "role": "primary",
                    "issues": ["runtime_region_overrun: p.copy"],
                    "components": [],
                    "region_overrun_repairs": [
                        {
                            "selector": "p.copy",
                            "deepestSelector": "p.copy",
                            "strategy": "reclaim_region_overrun",
                            "overrun": 527.25,
                            "paddingTop": 0,
                            "paddingBottom": 0,
                        }
                    ],
                }
            }
        }
        html = _probe_slide('<p class="copy">Bir cumle</p>', ".copy{margin:0}")
        out = repair_scene_html_layout(html, ledger)
        repaired = out[0] if isinstance(out, tuple) else out
        self.assertNotIn("margin-bottom:-527", repaired.replace(" ", ""))
        # And a small one is still reclaimed.
        ledger["regions"]["primary"]["region_overrun_repairs"][0]["overrun"] = (
            _MAX_NEGATIVE_PULL - 4.0
        )
        out = repair_scene_html_layout(html, ledger)
        repaired = out[0] if isinstance(out, tuple) else out
        self.assertIn("margin-bottom:-", repaired)


class FigureHostPlacementInvariants(unittest.TestCase):
    """A figure goes in a region, or it does not go on the slide.

    The old fallback dropped an unhosted figure before the *first* </section>
    at a hard-coded left:640px;top:140px, assuming the right half was free.
    When the right half is the table region, the figure lands on the table:
    two pieces of bound content stacked, and no layout repair can separate
    them, because neither is misplaced -- the placement was invented.
    """

    def test_a_slide_whose_regions_are_all_occupied_gets_no_invented_host(self):
        from tasks.html_pipeline import _figure_host_region

        html = (
            '<section data-layout-id="scene-title" data-layout-role="title">'
            "<h1>Baslik</h1></section>"
            '<section data-layout-id="scene-table" data-layout-role="table">'
            '<div data-pptx="table"></div></section>'
        )
        self.assertIsNone(_figure_host_region(html))

    def test_a_figure_region_is_preferred_when_present(self):
        from tasks.html_pipeline import _figure_host_region

        html = (
            '<section data-layout-id="scene-primary" data-layout-role="primary">'
            "</section>"
            '<section data-layout-id="scene-figure" data-layout-role="figure">'
            "</section>"
        )
        spot = _figure_host_region(html)
        self.assertIsNotNone(spot)
        self.assertIn("scene-figure", html[: spot[0]].rsplit("<section", 1)[-1])

    def test_a_bound_asset_with_no_region_is_named_by_the_scene(self):
        from tasks.slide_scene import resolve_slide_scene

        scene = resolve_slide_scene(
            {
                "title": "Gercekci asimetrik orneklerde kapsam netlesir",
                "table_id": "src-table-006",
                "figure_id": "pdf-page-5-picture-2",
            }
        )
        # One asset lane per slide: the table wins the composition and the
        # figure keeps a binding with nowhere to live. Saying so while the
        # scene is still numbers is the only point where it can be fixed by
        # binding rather than by guessing a position.
        self.assertEqual(scene["unhosted_assets"], ["figure"])

    def test_an_unhosted_asset_does_not_condemn_the_slide(self):
        """A binding with nowhere to go is not a broken scene.

        `issues` means the geometry is unusable and the renderer refuses the
        scene outright. An unhosted asset is not that: every box is sound and
        the slide renders as designed. Folding it into `issues` cleared `ok`,
        and authoring aborted for the whole slide -- a far worse outcome than
        the misplacement it was meant to prevent.
        """
        from tasks.slide_scene import resolve_slide_scene

        scene = resolve_slide_scene(
            {"title": "Olcek", "table_id": "src-table-006", "figure_id": "pdf-5-pic-2"}
        )
        self.assertTrue(scene["ok"], scene["issues"])
        self.assertEqual(scene["issues"], [])
        self.assertTrue(scene["unhosted_assets"])

    def test_a_single_bound_asset_is_hosted_and_clean(self):
        from tasks.slide_scene import resolve_slide_scene

        scene = resolve_slide_scene({"title": "Olcek", "table_id": "src-table-006"})
        self.assertEqual(scene["unhosted_assets"], [])
        self.assertTrue(scene["ok"])


class OcclusionInvariants(unittest.TestCase):
    """An opaque surface hides what it covers, across its whole box.

    Collisions were measured ink-to-ink, which is right for two sentences -- a
    paragraph's border box spans a column while its text occupies half a line.
    It is wrong for an element that paints an opaque background: the surface is
    what it covers. An opaque band laid 40px over a navy strip reported 1.3px,
    the width of the sliver where the two sentences happened to graze, while
    the reader saw a sentence cut in half.
    """

    def _report(self, band_css: str) -> dict:
        html = _probe_slide(
            '<div class="terms"><span class="terms-label">TERM DEFINITIONS</span>'
            '<span class="terms-copy">C(R) = total route distance; CV(R) = '
            "coefficient of variation of nonempty route distances.</span></div>"
            '<div class="band"><em>DECISION EFFECT</em> Increasing the equity '
            "weights accepts more distance.</div>",
            ".terms{position:relative;margin-top:120px;background:#1A365D;color:#fff;"
            "padding:14px 24px;font-size:16px;line-height:1.3}"
            ".terms-label{color:#63B3ED;font-size:13px;margin-right:16px}"
            f".band{{{band_css}}}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        return report

    def test_an_opaque_band_over_text_is_measured_by_its_box(self):
        report = self._report(
            "position:absolute;left:0;right:0;top:150px;background:#F5F7FA;"
            "color:#1A365D;padding:10px 18px;font-size:18px;line-height:1.15"
        )
        occlusions = [
            item
            for item in (report.get("inspection") or {}).get("collisions") or []
            if isinstance(item, dict) and item.get("occlusion")
        ]
        self.assertTrue(occlusions, "opaque band over copy not reported as occlusion")
        # The covered height is the boxes' overlap, not the sliver where the two
        # sentences graze each other.
        self.assertGreater(max(float(item["height"]) for item in occlusions), 12.0)

    def test_a_transparent_band_over_text_is_still_judged_on_ink(self):
        # Nothing is hidden: whatever the boxes do, the reader sees both
        # sentences. Measuring this by the box would manufacture overlaps
        # between copy and every annotation laid beside it.
        report = self._report(
            "position:absolute;left:0;right:0;top:150px;background:transparent;"
            "color:#1A365D;padding:10px 18px;font-size:18px;line-height:1.15"
        )
        self.assertFalse(
            [
                item
                for item in (report.get("inspection") or {}).get("collisions") or []
                if isinstance(item, dict) and item.get("occlusion")
            ]
        )


class SeverityInvariants(unittest.TestCase):
    """Hidden text must outrank overflowing text.

    Scored as equals, the repair loop preferred hiding a sentence to letting it
    overflow: un-pinning a band traded five occlusions for six overruns and was
    rejected as "worse". A reader can read text a little past a boundary; text
    under an opaque sheet is not there at all.
    """

    def test_one_occlusion_outweighs_several_overflows(self):
        from tasks.scene_local_repair import _layout_score

        occluding = {
            "hard": ["a", "b", "c", "d", "e"],
            "inspection": {
                "collisions": [{"occlusion": True} for _ in range(5)],
            },
        }
        overflowing = {
            "hard": ["a", "b", "c", "d", "e", "f"],
            "inspection": {"collisions": []},
        }
        self.assertGreater(
            _layout_score(occluding),
            _layout_score(overflowing),
            "the loop would rather hide a sentence than overflow it",
        )

    def test_fewer_plain_findings_still_scores_better(self):
        from tasks.scene_local_repair import _layout_score

        self.assertLess(
            _layout_score({"hard": ["a"], "inspection": {"collisions": []}}),
            _layout_score({"hard": ["a", "b"], "inspection": {"collisions": []}}),
        )


class PinnedBandInvariants(unittest.TestCase):
    """An absolutely-pinned block reserves no space, so the flow grows into it.

    Padding cannot reserve the lane inside a Scene region: the region's height
    is the contract and a paragraph's height comes from its own text, so
    padding-bottom just moves the edge the copy overflows past.
    """

    def test_a_bottom_pinned_summary_under_a_grown_list_is_unpinned(self):
        # The band's offsetParent is the Scene region itself, whose height is
        # the layout contract -- the shape this arises in.
        items = "".join(
            f"<li>Bulgu {index} biraz uzun bir cumle olarak yazilmistir.</li>"
            for index in range(1, 9)
        )
        html = _probe_slide(
            f'<ul class="items">{items}</ul>'
            '<p class="synthesis">Ozet: retrieval arama alanini daraltir.</p>',
            ".items{margin:0;padding:0;list-style:none;font-size:17px;line-height:24px}"
            ".items li{padding:14px 0}"
            ".synthesis{position:absolute;left:16px;right:16px;bottom:16px;margin:0;"
            "font-size:16px;line-height:21px;background:#EBF4FB}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        repairs = [
            (collision.get("repair") or {}).get("strategy")
            for collision in (report.get("inspection") or {}).get("collisions") or []
            if isinstance(collision, dict)
        ]
        self.assertIn(
            "unpin_band_into_flow",
            repairs,
            f"pinned summary under a grown list not un-pinned: {repairs}",
        )


class UnfittableOwnerInvariants(unittest.TestCase):
    """An owner smaller than its child is an anchor, not a container.

    A caption centred over a 42px connector arrow is wider and taller than the
    arrow by design. Reporting that as an escape produced a hard finding no
    repair could ever clear -- "put it back inside" names a box that could not
    hold it -- and the deck could not ship.
    """

    def test_a_label_larger_than_its_anchor_is_not_an_escape(self):
        html = _probe_slide(
            '<div class="flow"><div class="connector">'
            '<span class="connector-label">aday kumesi</span></div></div>',
            ".flow{position:relative;padding:60px 0 0 40px}"
            ".connector{position:relative;width:42px;height:3px;background:#63B3ED}"
            ".connector-label{position:absolute;left:21px;top:-27px;transform:translateX(-50%);"
            "white-space:nowrap;font-size:11px;color:#1A202C}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        self.assertFalse([item for item in report.get("hard") or [] if "owner_escape" in item])

    def test_a_badge_that_does_fit_but_sits_outside_is_still_an_escape(self):
        # The exemption is about impossibility, not about badges in general: a
        # small badge has a place inside its card, so drifting off it is a
        # defect and stays reported.
        html = _probe_slide(
            '<div class="card"><span class="badge">01</span><p>Yontem</p></div>',
            ".card{position:relative;width:260px;height:150px;background:#EBF4FB}"
            ".badge{position:absolute;left:-90px;top:8px;width:34px;height:20px;"
            "background:#3182CE;color:#fff;font-size:12px}"
            "p{margin:0;padding-top:40px;font-size:16px;line-height:22px}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        escapes = [
            item
            for item in (report.get("inspection") or {}).get("elements") or []
            if isinstance(item, dict) and item.get("escapesOwner")
        ]
        self.assertTrue(escapes, "a badge that fits its card but sits off it must still report")


class LaneDecorationInvariants(unittest.TestCase):
    """In a lane sized for one line, a hairline accent is the whole overflow.

    The lede lane is one line tall by contract. A 1px rule with a 7px margin
    above the sentence costs 8px the lane does not have, so the sentence is
    pushed out of its own region -- by ornament that carries nothing.
    """

    def test_a_hairline_above_a_single_line_lede_is_lifted_out_of_flow(self):
        html = _probe_lede_slide(
            '<div class="lede-rule"></div>'
            '<p class="lede-copy">HNSW degerlendirme yukunu azaltir.</p>',
            ".lede-rule{height:1px;margin:0 0 7px;background:#3182CE}"
            ".lede-copy{margin:0;font-size:18px;line-height:27px}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        found = [
            item
            for item in (report.get("inspection") or {}).get("regionOverruns") or []
            if isinstance(item, dict) and item.get("strategy") == "lift_decoration_out_of_flow"
        ]
        self.assertTrue(found, "hairline crowding a one-line lane not reported")
        self.assertTrue(str(found[0]["selector"]).endswith("lede-rule"))

    def test_a_lift_that_would_strike_through_the_copy_is_declined(self):
        # Taking the rule out of flow pulls the sentence up into the band the
        # rule keeps painting in. Trading an overflow for a strikethrough is not
        # a repair, so the lift is only offered when the copy provably clears.
        html = _probe_lede_slide(
            '<div class="lede-rule"></div>'
            '<p class="lede-copy">Sorularinizi memnuniyetle yanitlarim</p>',
            ".lede-rule{height:2px;margin:14px 0 7px;background:#3182CE}"
            ".lede-copy{margin:0;font-size:26px;line-height:27px}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        for item in (report.get("inspection") or {}).get("regionOverruns") or []:
            if not isinstance(item, dict):
                continue
            self.assertNotEqual(
                item.get("strategy"),
                "lift_decoration_out_of_flow",
                "offered a lift that would lay the rule across the sentence",
            )


class ConvergenceInvariants(unittest.TestCase):
    """A repair either resolves the defect or declines. It never converges.

    Each of these was a repair that re-fired on every pass without ever
    arriving: the gap shrank 42 -> 31.2px across five stacked blocks, a margin
    was "corrected" to the value it already had, and a height override was
    outranked by the min-height underneath it.
    """

    def test_percentage_tracks_plus_a_gap_are_refitted_not_nibbled(self):
        html = _probe_slide(
            '<div class="split"><div class="a"><p>Sol</p></div><div class="b"><p>Sag</p></div></div>',
            ".split{display:grid;grid-template-columns:59% 41%;column-gap:42px;width:1160px}"
            ".a,.b{min-width:0}"
            "p{margin:0;font-size:16px;line-height:22px}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        found = [
            item
            for item in (report.get("inspection") or {}).get("gridTrackOverflow") or []
            if isinstance(item, dict)
        ]
        self.assertTrue(found, "tracks + gap over the container not reported")
        item = found[0]
        # The overflow is the gap: the tracks already claim the whole container.
        self.assertAlmostEqual(float(item["overflow"]), float(item["gap"]), delta=1.0)
        # fr keeps the author's proportion and resolves after gaps are removed.
        self.assertIn("fr", item["suggestedColumns"])
        shares = [float(part.replace("fr", "")) for part in item["suggestedColumns"].split()]
        self.assertAlmostEqual(shares[0] / sum(shares), 0.59, places=2)

    def test_tracks_that_already_fit_are_left_alone(self):
        html = _probe_slide(
            '<div class="split"><div><p>Sol</p></div><div><p>Sag</p></div></div>',
            ".split{display:grid;grid-template-columns:1fr 1fr;column-gap:42px;width:1160px}"
            "p{margin:0;font-size:16px;line-height:22px}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        self.assertFalse((report.get("inspection") or {}).get("gridTrackOverflow"))

    def test_a_crowded_title_moves_the_rule_not_the_sentence(self):
        html = _probe_slide(
            '<div class="wrap"><h1 class="title-copy">Olcek</h1>'
            '<div class="title-rule" aria-hidden="true" data-pptx-kind="decoration"></div></div>',
            ".wrap{position:relative;height:200px}"
            ".title-copy{margin:0;font-size:40px;line-height:44px;width:520px;white-space:nowrap}"
            ".title-rule{position:absolute;left:0;top:50px;width:400px;height:2px;background:#3182CE}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        found = [
            item
            for item in (report.get("inspection") or {}).get("decorationCollisions") or []
            if isinstance(item, dict)
            and str(item.get("targetSelector") or "").endswith("h1.title-copy")
        ]
        self.assertTrue(found, "crowded title rule not reported")
        item = found[0]
        # The rule carries no content, so it is the term that gives -- and the
        # suggestion must name the rule, never the sentence being crowded.
        self.assertEqual(item.get("strategy"), "move_decoration_absolute")
        self.assertTrue(str(item.get("ruleSelector") or "").endswith("div.title-rule"))

    def test_a_no_op_margin_is_never_suggested(self):
        # A title already at margin-top:0 cannot be pulled up. Suggesting 0
        # changes nothing and the finding returns on the next pass forever.
        html = _probe_slide(
            '<div class="wrap"><h1 class="title-copy">Daha buyuk orneklerde azaltim</h1>'
            '<div class="title-rule" aria-hidden="true" data-pptx-kind="decoration"></div></div>',
            ".wrap{position:relative;overflow:hidden;height:96px}"
            ".title-copy{margin:0;font-size:56px;line-height:60px;width:800px}"
            ".title-rule{position:static;margin-top:6px;width:690px;height:2px;background:#3182CE}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        for item in (report.get("inspection") or {}).get("decorationCollisions") or []:
            if not isinstance(item, dict) or item.get("strategy") != "shift_target_up":
                continue
            self.assertGreater(
                float(item.get("suggestedMarginTop") or 0),
                0.0,
                "shift_target_up suggested a margin the element already has",
            )


class ContrastRecolourInvariants(unittest.TestCase):
    """Ink at 1.6:1 is not a palette choice.

    A body grey dropped on a navy panel leaves the sentence on the slide and out
    of the reader's reach. Hue and saturation stay the author's; lightness is
    walked away from the surface until the sentence can be read.
    """

    def test_grey_on_navy_is_lifted_to_the_floor(self):
        from tasks.scene_local_repair import (
            _contrast_ratio,
            _legible_against,
            _parse_css_rgb,
        )

        ink = _parse_css_rgb("rgb(74, 85, 104)")
        surface = _parse_css_rgb("rgb(26, 54, 93)")
        self.assertLess(_contrast_ratio(ink, surface), 2.0)
        corrected = _parse_css_rgb(_legible_against(ink, surface))
        self.assertIsNotNone(corrected)
        self.assertGreaterEqual(_contrast_ratio(corrected, surface), 3.0)

    def test_the_authors_hue_survives_the_correction(self):
        import colorsys

        from tasks.scene_local_repair import _legible_against, _parse_css_rgb

        ink = _parse_css_rgb("rgb(74, 85, 104)")
        surface = _parse_css_rgb("rgb(26, 54, 93)")
        corrected = _parse_css_rgb(_legible_against(ink, surface))
        hue_before = colorsys.rgb_to_hls(*[c / 255.0 for c in ink])[0]
        hue_after = colorsys.rgb_to_hls(*[c / 255.0 for c in corrected])[0]
        self.assertAlmostEqual(hue_before, hue_after, places=2)

    def test_ink_that_already_reads_is_left_alone(self):
        from tasks.scene_local_repair import _legible_against, _parse_css_rgb

        self.assertIsNone(
            _legible_against(_parse_css_rgb("rgb(255,255,255)"), _parse_css_rgb("rgb(26,54,93)"))
        )


class ChartPreviewInvariants(unittest.TestCase):
    """The preview has to show the chart that will be exported.

    The export has always understood `line`; the preview drew columns for it. An
    author who asked for a trend and saw bars concluded the host could not do it
    and drew the trend by hand -- which is how rotated rules ended up standing in
    for a plot.
    """

    def test_a_line_host_previews_as_a_trend(self):
        from tasks.html_pipeline import _render_chart_html

        html = _render_chart_html(
            {
                "type": "line",
                "categories": ["2019", "2020", "2021", "2022"],
                "series": [{"name": "CV", "values": [1.2, 1.0, 0.8, 0.7]}],
            }
        )
        self.assertIn("<polyline", html)
        # The preview is never converted: the export reads data-chart-payload.
        self.assertIn('data-pptx-kind="ignore"', html)

    def test_a_column_host_still_previews_as_columns(self):
        from tasks.html_pipeline import _render_chart_html

        html = _render_chart_html(
            {"type": "column", "categories": ["A", "B"], "series": [{"name": "x", "values": [1, 2]}]}
        )
        self.assertNotIn("<polyline", html)
        self.assertIn("chart-preview", html)

    def test_two_metrics_orders_of_magnitude_apart_both_stay_readable(self):
        from tasks.html_pipeline import _render_chart_html

        html = _render_chart_html(
            {
                "type": "line",
                "categories": ["A", "B", "C"],
                "series": [
                    {"name": "CV", "values": [1.2, 1.0, 0.8]},
                    {"name": "Cost", "values": [210000.0, 190000.0, 205000.0]},
                ],
            }
        )
        # Two plotted series, not one line and one flat rule pinned to the axis.
        self.assertEqual(html.count("<polyline"), 2)
        ys = [
            float(point.split(",")[1])
            for block in html.split('points="')[1:]
            for point in block.split('"')[0].split(" ")
        ]
        self.assertGreater(max(ys) - min(ys), 20.0, "one series collapsed onto the axis")


class FreehandChartInvariants(unittest.TestCase):
    """A quantitative figure has to come from its data.

    Without a chart host the author reaches for coloured rules rotated to an
    arbitrary angle to fake a trend line. That geometry answers to nothing: the
    lines ran outside their own axes and across the callout beneath them, and
    nothing ties the slope to the numbers it claims to show.
    """

    def test_rotated_rules_inside_an_axis_are_reported(self):
        html = _probe_slide(
            '<div class="axis" aria-hidden="true" data-pptx-kind="decoration">'
            '<i class="trend-cv"></i><i class="trend-cost"></i></div>',
            ".axis{position:absolute;left:60px;top:60px;width:360px;height:200px;"
            "border-bottom:2px solid #2D3748;border-left:2px solid #2D3748}"
            ".trend-cv{position:absolute;left:4px;bottom:40px;width:330px;height:3px;"
            "background:#2F855A;transform:rotate(-18deg);transform-origin:left center}"
            ".trend-cost{position:absolute;left:4px;bottom:90px;width:330px;height:3px;"
            "background:#C05621;transform:rotate(17deg);transform-origin:left center}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        found = [item for item in report.get("issues") or [] if "freehand_chart" in item]
        self.assertTrue(found, f"hand-drawn plot not reported: {report.get('issues')}")

    def test_tilted_ornament_without_an_axis_is_left_alone(self):
        # The same rotated rule, drawn as ornament on a cover. Nothing about it
        # claims to carry a number, so reporting it would be taste, not measurement.
        html = _probe_slide(
            '<p class="copy">Yontem</p>'
            '<i class="route-a" aria-hidden="true" data-pptx-kind="decoration"></i>'
            '<i class="route-b" aria-hidden="true" data-pptx-kind="decoration"></i>',
            ".copy{margin:0;font-size:17px;line-height:24px}"
            ".route-a{position:absolute;left:600px;top:120px;width:280px;height:2px;"
            "background:#63B3ED;transform:rotate(-24deg);transform-origin:left center}"
            ".route-b{position:absolute;left:600px;top:200px;width:280px;height:2px;"
            "background:#90CDF4;transform:rotate(19deg);transform-origin:left center}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        self.assertFalse([item for item in report.get("issues") or [] if "freehand_chart" in item])


class AmbientDecorationInvariants(unittest.TestCase):
    """Decoration has to mean something on the slide it is on.

    Generic circles, orbits and rings behind copy read as decorated rather than
    authored: a reader asks what the shape denotes and there is no answer.
    """

    def test_a_large_empty_circle_is_reported(self):
        html = _probe_slide(
            '<p class="copy">Ekleme karari, normalize edilmis maliyet ile is yuku '
            'esitligi terimlerinin agirlikli bilesimine gore verilir.</p>'
            '<div class="orbit" aria-hidden="true" data-pptx-kind="decoration"></div>',
            ".copy{width:420px;font-size:17px;line-height:24px;margin:0}"
            ".orbit{position:absolute;right:20px;top:20px;width:238px;height:238px;"
            "border:2px solid #63B3ED;border-radius:50%}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        ambient = [item for item in report.get("issues") or [] if "ambient" in item]
        self.assertTrue(ambient, f"ambient circle not reported: {report.get('issues')}")
        # Advisory: it does not break the layout, so it must not fail the gate.
        self.assertFalse([item for item in report.get("hard") or [] if "ambient" in item])

    def test_a_round_shape_that_holds_something_is_not_ambient(self):
        html = _probe_slide(
            '<div class="avatar"><svg width="40" height="40"><circle cx="20" cy="20" r="18"/></svg></div>'
            '<div class="badge">01</div>',
            ".avatar{position:absolute;left:20px;top:20px;width:120px;height:120px;"
            "border-radius:50%;background:#EBF4FB}"
            ".badge{position:absolute;left:200px;top:20px;width:120px;height:120px;"
            "border-radius:50%;background:#1A365D;color:#fff;line-height:120px;"
            "text-align:center;font-size:40px}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        # One hosts artwork, the other counts — neither is ambient.
        self.assertEqual([item for item in report.get("issues") or [] if "ambient" in item], [])

    def test_a_percentage_radius_is_resolved_against_the_box(self):
        """`border-radius:50%` stays a percentage in computed style.

        Read as 50px it failed the roundness test for every shape wider than
        125px — which is every shape this check exists to find.
        """
        html = _probe_slide(
            '<p class="copy">Bir paragraf metni burada akar ve devam eder boyunca</p>'
            '<div class="ring" aria-hidden="true" data-pptx-kind="decoration"></div>',
            ".copy{width:300px;font-size:16px;line-height:24px;margin:0}"
            ".ring{position:absolute;right:10px;top:10px;width:330px;height:330px;"
            "border:1px solid rgba(99,179,237,.28);border-radius:50%}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        ambient = [item for item in report.get("issues") or [] if "ambient" in item]
        self.assertTrue(ambient, "a 330px ring must be recognised as round")
        # The reported diameter is the border box, so 330px + 1px of border each side.
        diameter = float(re.search(r"is a ([\d.]+)px", ambient[0]).group(1))
        self.assertAlmostEqual(diameter, 332.0, delta=3.0)


class TypeScaleInvariants(unittest.TestCase):
    """Everything that must move with a font-size change, in one place.

    Each of these was forgotten by one emitter while another had it right, which
    is why every font-size change now routes through a single helper.
    """

    def test_tracking_keeps_its_ratio_to_the_em(self):
        from tasks.scene_local_repair import _scaled_type_declaration

        # A display numeral: -5px at 104px is -0.048em and must stay that.
        css = _scaled_type_declaration(
            from_size=104, to_size=57, line_height=87.4,
            letter_spacing=-5, centers_with_line_height=False,
        )
        tracking = float(re.search(r"letter-spacing:(-?[\d.]+)px", css).group(1))
        size = float(re.search(r"font-size:([\d.]+)px", css).group(1))
        self.assertAlmostEqual(tracking / size, -5 / 104, places=3)

    def test_a_centring_line_height_is_left_alone(self):
        from tasks.scene_local_repair import _scaled_type_declaration

        css = _scaled_type_declaration(
            from_size=28, to_size=18, line_height=28,
            letter_spacing=-0.5, centers_with_line_height=True,
        )
        self.assertNotIn("line-height", css)
        self.assertIn("letter-spacing", css)

    def test_a_flowing_line_height_scales(self):
        from tasks.scene_local_repair import _scaled_type_declaration

        css = _scaled_type_declaration(
            from_size=20, to_size=14, line_height=24,
            letter_spacing=0, centers_with_line_height=False,
        )
        self.assertIn("line-height:16.80px", css)
        self.assertNotIn("letter-spacing", css)

    def test_a_round_badge_shrink_carries_its_tracking(self):
        """The badge path forgot tracking while the overflow path had it.

        A percentage inside a circle ("61,3%") came out as one blot because this
        emitter set only font-size and line-height.
        """
        from tasks.scene_local_repair import repair_scene_html_layout

        html = (
            "<html><body><section data-layout-id=\"scene-primary\">"
            '<div class="stat">61,3%</div></section>'
            "<style>.stat{width:120px;height:120px;border-radius:50%;"
            "font-size:40px;line-height:120px;letter-spacing:-2px}</style>"
            "</body></html>"
        )
        ledger = {
            "regions": {
                "primary": {
                    "role": "primary",
                    "issues": ["runtime_round_container_overflow: div.stat copy needs 120px"],
                    "round_repairs": [{
                        "selector": "div.stat",
                        "strategy": "shrink_to_inscribed",
                        "suggestedFontSize": 26.0,
                        "fontSize": 40.0,
                        "lineHeight": 120.0,
                        "letterSpacing": -2.0,
                        "centersWithLineHeight": True,
                        "inscribed": 84.0,
                    }],
                }
            }
        }
        out, meta = repair_scene_html_layout(html, ledger)
        self.assertTrue(meta.get("changed"), meta)
        rule = re.search(r"div\.stat\{([^}]*)\}", out.split("</section>")[-1])
        self.assertIsNotNone(rule, out[-400:])
        body = rule.group(1)
        self.assertIn("font-size:26.00px", body)
        tracking = float(re.search(r"letter-spacing:(-?[\d.]+)px", body).group(1))
        self.assertAlmostEqual(tracking, -2.0 * 26 / 40, places=2)
        # The circle still centres its single line, so that stays as authored.
        self.assertNotIn("line-height", body)


class InkBleedInvariants(unittest.TestCase):
    """Adjacent lines of type share ink. That is not a collision.

    Ink reaching past a line box — the ascender above, the descender below — is
    how type sits. Three perfectly stacked rows on one slide were reported as
    collisions of 28.7, 140.3 and 126.0 x 5.0px because the allowance took a
    fraction of *one* face's em (0.16em of 21px = 3.36px) and compared it with
    the overshoot of *two* faces (3px descender + 2px ascender = 5px). The
    allowance is now measured from both faces, capped at the share of an em a
    face can actually place outside its line box.
    """

    def test_normal_stacked_type_is_not_a_collision(self):
        html = _probe_slide(
            '<div class="row"><strong class="s">Toplam rota mesafesi</strong>'
            '<span class="p">temel verimlilik olcutudur ve karsilastirilir</span></div>',
            ".row{display:flex;flex-direction:column}"
            ".s{font-size:21px;line-height:22px;font-weight:700;margin:0}"
            ".p{font-size:15px;line-height:18px;margin:0}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        collisions = [item for item in report.get("hard") or [] if "collision" in item]
        self.assertEqual(collisions, [], f"stacked type reported as colliding: {collisions}")

    def test_pathological_leading_still_collides(self):
        """The cap is what keeps this a defect: 0.3 line-height really does print
        a 104px numeral over the sentence beneath it."""
        html = _probe_slide(
            '<div class="num">14</div>'
            '<p class="txt">Bu satir sayinin altinda kalir ve uzerine binilir</p>',
            ".num{font-size:104px;line-height:.3;font-weight:700;margin:0}"
            ".txt{font-size:18px;line-height:26px;margin:0}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        self.assertTrue(report.get("hard"), "pathological leading must be reported")

    def test_a_real_overlap_is_still_reported(self):
        html = _probe_slide(
            '<p class="a">Ilk paragraf metni burada akar ve devam eder boyunca</p>'
            '<p class="b">Ikinci paragraf tam ustune biner ve okunamaz hale gelir</p>',
            ".a{position:absolute;left:20px;top:140px;width:400px;font-size:20px;line-height:28px}"
            ".b{position:absolute;left:20px;top:150px;width:400px;font-size:20px;line-height:28px}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        collisions = [item for item in report.get("hard") or [] if "collision" in item]
        self.assertTrue(collisions, "two paragraphs 10px apart must collide")

    def test_display_ink_is_not_an_overflow(self):
        """A 57px numeral overshoots its box by 15px — 0.26em, inside the face.

        The old bound was 0.16em under a flat 12px ceiling, and the ceiling is
        what misfired: every display-size element read as overflowing.
        """
        from tasks.html_layout_qa import audit_runtime_html_layout as audit

        html = _probe_slide(
            '<div class="big">14</div>',
            ".big{font-size:57px;line-height:.84;font-weight:700;margin:0;height:48px}",
        )
        report = audit(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        # Body copy keeps a tight bound: 16px type still reports a 10px overrun.
        tight = _probe_slide(
            '<div class="box"><p>Bir paragraf metni burada akar ve birkac satira '
            "boluner boyunca devam eder ve tasar</p></div>",
            ".box{width:200px;height:24px;font-size:16px;line-height:24px;overflow:hidden}"
            ".box p{margin:0}",
        )
        tight_report = audit(tight)
        self.assertTrue(
            tight_report.get("hard"),
            "a clipped 16px paragraph must still be reported",
        )


class RepairReachInvariants(unittest.TestCase):
    """Every finding needs an owner and a strategy, or it can never be fixed.

    Each of these three was reported on every compile and repaired on none: one
    had no owning region, one had no strategy for its shape, and one was not a
    text problem at all.
    """

    def test_a_narrow_text_finding_reaches_its_region(self):
        """It stayed in `unowned_issues`, so no region was ever visited for it.

        The finding names a synthesized id ("span.mini:-1") that matches no
        measured component, and only the *repair* was being attributed — not the
        issue that makes the repair pass visit the region.
        """
        from tasks.scene_layout_ledger import build_scene_layout_ledger

        scene = {
            "version": "scene_layout_v2",
            "regions": [{"id": "secondary", "role": "secondary", "x": 640, "y": 200, "w": 560, "h": 400}],
        }
        issue = "runtime_narrow_text: span.mini:-1 lays out 4 lines in 91.3px (12.0 chars/line): x"
        qa = {
            "hard": [issue],
            "inspection": {
                "elements": [],
                "narrowText": [{
                    "element": "span.mini:-1",
                    "sceneOwner": "secondary",
                    "width": 91.3,
                    "lines": 4,
                    "gridRepair": None,
                }],
            },
        }
        ledger = build_scene_layout_ledger(scene, qa)
        self.assertEqual(ledger["unowned_issues"], [], "the finding must have an owner")
        self.assertIn(issue, ledger["regions"]["secondary"]["issues"])

    def test_a_starved_grid_track_can_be_widened(self):
        from tasks.scene_local_repair import repair_scene_html_layout

        ledger = {
            "regions": {
                "secondary": {
                    "role": "secondary",
                    "issues": ["runtime_narrow_text: span.mini:-1 lays out 4 lines in 91.3px"],
                    "grid_repairs": [{
                        "selector": "div.metric-flow",
                        "strategy": "widen_narrow_track",
                        "suggestedColumns": "170.85px 315.15px",
                    }],
                }
            }
        }
        html = (
            "<html><head><style>.metric-flow{display:grid}</style></head><body>"
            '<section data-layout-id="scene-secondary">'
            '<div class="metric-flow"><span class="mini">x</span><div class="metric-stack">y</div>'
            "</div></section></body></html>"
        )
        out, meta = repair_scene_html_layout(html, ledger)
        self.assertTrue(meta.get("changed"))
        self.assertIn("grid-template-columns:170.85px 315.15px", out)
        # The old fallback collapsed a deliberate two-column figure to one.
        self.assertNotIn("grid-template-columns:minmax(0,1fr)", out)

    def test_an_overrun_is_reclaimed_from_padding_before_type(self):
        from tasks.scene_local_repair import repair_scene_html_layout

        ledger = {
            "regions": {
                "table": {
                    "role": "table",
                    "issues": ["runtime_text_overflow: section[scene-table] scrolls (0.0px x, 10.0px y)"],
                    "components": [{
                        "id": "aside.takeaway:1",
                        "selector": "aside.takeaway",
                        "overflow": {"targets": [{
                            "selector": "aside.takeaway",
                            "overflowY": 10.0,
                            "fontSize": 14.83,
                            "lineHeight": 20.0,
                            "paddingTop": 16.0,
                            "paddingBottom": 14.0,
                            "position": "relative",
                        }]},
                    }],
                }
            }
        }
        html = (
            "<html><head><style>.takeaway{padding:16px 18px 14px 20px}</style></head><body>"
            '<section data-layout-id="scene-table">'
            '<aside class="takeaway">note</aside></section></body></html>'
        )
        out, meta = repair_scene_html_layout(html, ledger)
        self.assertTrue(meta.get("changed"))
        self.assertIn("padding-top:11.00px", out)
        self.assertIn("padding-bottom:9.00px", out)
        # Padding is the cheapest room: the type must be left alone.
        self.assertNotIn("font-size:", out.split("aside.takeaway")[-1])


class VerticalRuleAndRegionFitInvariants(unittest.TestCase):
    """Two defects the detector could not see, and one repair it could not reach."""

    def test_a_vertical_accent_bar_over_copy_is_reported(self):
        """The rule test demanded a wide, short box, so a 6x64px bar was invisible
        to the one pass whose job is keeping rules off the copy — it printed
        through the first letter of a byline ("Doç" reading as "oç")."""
        html = _probe_slide(
            '<div class="mark" aria-hidden="true" data-pptx-kind="decoration"></div>'
            '<p class="author">Doç. Dr. Asım Sinan Yüksel</p>',
            ".mark{position:absolute;left:0;top:0;width:6px;height:64px;background:#3182CE}"
            ".author{position:absolute;left:0;top:6px;margin:0;width:400px;"
            "font-size:22px;line-height:30px;font-weight:700}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        crossings = [item for item in report.get("hard") or [] if "decoration_collision" in item]
        self.assertTrue(crossings, f"vertical bar over copy not reported: {report.get('hard')}")

    def test_a_bar_beside_its_copy_is_not_reported(self):
        """A left accent bar is a normal device; only ink it covers is a defect."""
        html = _probe_slide(
            '<div class="mark" aria-hidden="true" data-pptx-kind="decoration"></div>'
            '<p class="author">Doç. Dr. Asım Sinan Yüksel</p>',
            ".mark{position:absolute;left:0;top:0;width:6px;height:64px;background:#3182CE}"
            ".author{position:absolute;left:20px;top:6px;margin:0;width:400px;"
            "font-size:22px;line-height:30px;font-weight:700}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        self.assertEqual(
            [item for item in report.get("hard") or [] if "decoration_collision" in item], []
        )

    def test_every_repair_channel_is_registered_as_repairable(self):
        """A channel missing from the gate is built and never reached.

        `region_overrun_repairs` was added, populated, and ignored: the region
        was not counted as repairable, so the loop that emits them never ran.
        """
        import inspect

        from tasks import scene_local_repair

        source = inspect.getsource(scene_local_repair.repair_scene_html_layout)
        gate = source.split("repaired.append(")[0]
        channels = set(re.findall(r'entry\.get\("(\w+_repairs)"\)', source))
        self.assertTrue(channels, "no repair channels found")
        for channel in sorted(channels):
            self.assertIn(
                channel,
                gate,
                f"{channel} is emitted but not in the repairable gate, so it never runs",
            )


class GradientStopInvariants(unittest.TestCase):
    """A gradient's stop positions decide what it paints.

    `linear-gradient(90deg, #1A365D 0 14px, #FFFFFF 14px 100%)` is a 14px navy
    edge stripe. The XML emitter read percentages only, so both of those
    positions were dropped and the normalizer spread the stops evenly — the
    stripe exported as a navy half-slide fading to white, painted over the
    title, and the cover was unreadable.
    """

    def test_length_stops_keep_their_position(self):
        from tasks.html_runtime_layout import inspect_html_layout  # noqa: F401  (module guard)

        # Exercised through the vendored converter, which owns the emitter.
        import json
        import subprocess

        script = (
            "const { parseGradientFull } = require('./dist/utils/style.js');"
            "const box = {width:1280, height:720};"
            "console.log(JSON.stringify(parseGradientFull("
            "'linear-gradient(90deg, #1A365D 0 14px, #FFFFFF 14px 100%)', box, 'auto')));"
        )
        root = Path(__file__).resolve().parents[1] / "vendor" / "deckhtml"
        if not (root / "dist" / "utils" / "style.js").exists():
            self.skipTest("deckhtml dist not built")
        out = subprocess.run(
            ["node", "-e", script], cwd=root, capture_output=True, text=True, check=False
        )
        self.assertEqual(out.returncode, 0, out.stderr[:400])
        data = json.loads(out.stdout.strip())
        positions = [stop["position"] for stop in data["stops"]]
        # 14px of 1280 is 1.09%, not 33%.
        self.assertAlmostEqual(positions[1], 14 / 1280 * 100, places=2)
        self.assertEqual(positions[0], 0)
        self.assertEqual(positions[-1], 100)
        colours = [stop["color"] for stop in data["stops"]]
        self.assertEqual(colours[0], "1A365D")
        self.assertEqual(colours[-1], "FFFFFF")


class SemanticHostFitInvariants(unittest.TestCase):
    """A host's height is a guess; the content it receives is real."""

    def test_a_formula_taller_than_its_host_is_reported(self):
        html = _probe_slide(
            '<div class="fhost" data-pptx="formula">'
            '<math xmlns="http://www.w3.org/1998/Math/MathML" display="block">'
            "<munderover><mo>&#x2211;</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow>"
            "<mrow><mi>m</mi></mrow></munderover><mi>c</mi>"
            "</math></div>",
            ".fhost{position:absolute;left:20px;top:40px;width:400px;height:24px;"
            "font-size:30px;background:#EBF4FB}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        shortfall = [item for item in report.get("hard") or [] if "host_shortfall" in item]
        self.assertTrue(shortfall, f"a host too short for its math: {report.get('hard')}")

    def test_a_host_that_fits_is_not_reported(self):
        html = _probe_slide(
            '<div class="fhost" data-pptx="formula">'
            '<math xmlns="http://www.w3.org/1998/Math/MathML" display="block"><mi>c</mi></math>'
            "</div>",
            ".fhost{position:absolute;left:20px;top:40px;width:400px;height:120px;"
            "font-size:20px;background:#EBF4FB}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        self.assertEqual(
            [item for item in report.get("hard") or [] if "host_shortfall" in item], []
        )


class LegibilityInvariants(unittest.TestCase):
    """Every other gate measures geometry. This one asks whether it can be read.

    A full-width sentence laid across a floating dark panel is grey on navy at
    1.6:1; an injected formula that imposes the palette ink on a dark region is
    navy on navy at 1.00:1. Both are invisible and both passed every geometric
    check on their slide.
    """

    def test_copy_crossing_a_dark_panel_is_reported(self):
        html = _probe_slide(
            '<article class="panel"></article>'
            '<p class="gloss">HNSW hangi adaylarin incelenecegini belirler ve bu karar '
            "birlesik skor ile verilir.</p>",
            ".panel{position:absolute;left:320px;top:0;width:280px;height:200px;"
            "background:#1A365D}"
            ".gloss{position:absolute;left:0;top:60px;width:580px;margin:0;"
            "font-size:17px;line-height:24px;color:#4A5568}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        low = [item for item in report.get("hard") or [] if "text_contrast" in item]
        self.assertTrue(low, f"grey copy over a navy panel not reported: {report.get('hard')}")

    def test_white_on_its_own_dark_card_is_fine(self):
        """The element's own background is the surface under its glyphs.

        Excluding it made every white-on-navy table header read as
        white-on-white — 39 findings on one deck, nearly all false.
        """
        html = _probe_slide(
            '<div class="card">Beyaz metin lacivert kart uzerinde okunur</div>',
            ".card{position:absolute;left:20px;top:40px;width:420px;padding:16px;"
            "background:#1A365D;color:#FFFFFF;font-size:18px;line-height:26px}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        self.assertEqual(
            [item for item in report.get("hard") or [] if "text_contrast" in item], []
        )

    def test_a_translucent_veil_is_composited_not_taken_at_face_value(self):
        """`rgba(255,255,255,0.08)` over navy is still navy behind the glyphs."""
        html = _probe_slide(
            '<div class="card"><div class="veil">Beyaz metin ince bir tul altinda</div></div>',
            ".card{position:absolute;left:20px;top:40px;width:420px;padding:16px;"
            "background:#1A365D}"
            ".veil{background:rgba(255,255,255,0.08);color:#FFFFFF;font-size:18px;"
            "line-height:26px;padding:8px}",
        )
        report = audit_runtime_html_layout(html)
        if not (report.get("inspection") or {}).get("available"):
            self.skipTest("Chromium unavailable")
        self.assertEqual(
            [item for item in report.get("hard") or [] if "text_contrast" in item], []
        )

    def test_a_formula_inherits_its_host_colour(self):
        """Imposing the palette ink is what made a formula navy-on-navy.

        The container already knows which ink its surface needs.
        """
        from tasks.formula_math_render import mathml_host_inner_html

        out = mathml_host_inner_html({"mathml": "<math><mi>C</mi></math>"}, color="#1A365D")
        self.assertNotIn("mathcolor", out)
        self.assertIn("data-sunairum-formula", out)
