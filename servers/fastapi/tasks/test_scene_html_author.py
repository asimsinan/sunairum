import unittest
from unittest.mock import Mock

from tasks.scene_html_author import build_scene_author_prompt, normalize_scene_authored_html, validate_scene_authored_html
from tasks.slide_scene import resolve_slide_scene


class SceneHtmlAuthorTests(unittest.TestCase):
    def test_author_normalizes_owned_geometry_before_contract_validation(self):
        from tasks.scene_html_author import author_scene_html

        slide = {"slide": 1, "role": "title", "title": "A durable cover"}
        scene = resolve_slide_scene(slide)
        roots = "".join(
            (
                '<div data-layout-id="scene-{id}" data-layout-role="{role}" '
                'style="color:#123">Authored visual</div>'
            ).format(**region)
            for region in scene["regions"]
            if region["role"] != "footer"
        )
        raw = self._document(roots)
        authored = author_scene_html(
            slide=slide,
            scene=scene,
            design_spec_md="Editorial cover",
            design_reference_brief="",
            palette={},
            call_text=Mock(return_value=raw),
        )
        title = next(region for region in scene["regions"] if region["role"] == "title")
        expected = (
            f'position:absolute;left:{title["x"]:g}px;top:{title["y"]:g}px;'
            f'width:{title["w"]:g}px;height:{title["h"]:g}px;'
        )
        self.assertIn(expected, authored)
        self.assertEqual([], validate_scene_authored_html(authored, scene))

    def test_author_retries_contract_only_without_discarding_creative_direction(self):
        from tasks.scene_html_author import author_scene_html

        slide = {"slide": 2, "title": "A claim", "core_message": "A lede"}
        scene = resolve_slide_scene(slide)
        invalid = self._document('<div class="signature-art">creative first pass</div>')
        valid = self._document(self._roots(scene))
        call = Mock(side_effect=[invalid, valid])
        attempt = Mock()
        authored = author_scene_html(
            slide=slide,
            scene=scene,
            design_spec_md="Editorial research slide",
            design_reference_brief="",
            palette={},
            call_text=call,
            on_attempt=attempt,
        )
        self.assertEqual(2, call.call_count)
        self.assertEqual(2, attempt.call_count)
        second_prompt = call.call_args_list[1].args[1]
        self.assertIn("CONTRACT-ONLY REVISION", second_prompt)
        self.assertIn("creative first pass", second_prompt)
        self.assertEqual([], validate_scene_authored_html(authored, scene))

    def test_author_contract_error_retains_last_creative_candidate(self):
        from tasks.scene_html_author import SceneAuthorContractError, author_scene_html

        slide = {"slide": 2, "title": "A claim", "core_message": "A lede"}
        scene = resolve_slide_scene(slide)
        invalid = self._document('<div class="signature-art">keep this art</div>')
        with self.assertRaises(SceneAuthorContractError) as raised:
            author_scene_html(
                slide=slide,
                scene=scene,
                design_spec_md="Editorial research slide",
                design_reference_brief="",
                palette={},
                call_text=Mock(return_value=invalid),
            )
        self.assertIn("keep this art", raised.exception.html)
        self.assertTrue(raised.exception.issues)

    def test_normalizer_restores_owned_geometry_and_plain_formula_prose(self):
        scene = {
            "version": "scene_layout_v2",
            "regions": [{"id": "title", "role": "title", "x": 60, "y": 60, "w": 1160, "h": 56}],
        }
        html = '''<!doctype html><html><head><style>[data-layout-role]{position:absolute}</style></head><body><section class="slide"><div data-layout-id="scene-title" data-layout-role="title" style="left:1px;top:2px;width:3px;height:4px"><p>Setting \\(\\beta=\\gamma=0\\)</p></div></section></body></html>'''
        normalized, meta = normalize_scene_authored_html(html, scene)
        self.assertTrue(meta["changed"])
        self.assertIn("position:absolute;left:60px;top:60px;width:1160px;height:56px", normalized)
        self.assertIn("Setting β=γ=0", normalized)
        self.assertEqual([], validate_scene_authored_html(normalized, scene))

    def test_normalizer_marks_decorative_glyphs_accessibility_hidden_but_exportable(self):
        scene = {
            "version": "scene_layout_v2",
            "regions": [{"id": "primary", "role": "primary", "x": 60, "y": 180, "w": 1160, "h": 498}],
        }
        html = '''<!doctype html><html><head><style>.slide{width:1280px;height:720px}</style></head><body><section class="slide"><div data-layout-id="scene-primary" data-layout-role="primary" style="position:absolute;left:60px;top:180px;width:1160px;height:498px"><div class="question-mark">?</div></div></section></body></html>'''
        normalized, meta = normalize_scene_authored_html(html, scene)
        self.assertEqual(1, meta["decorations_marked"])
        self.assertIn('aria-hidden="true"', normalized)
        self.assertIn('data-pptx-kind="decoration"', normalized)
        self.assertNotIn('data-pptx-kind="ignore"', normalized)

    def test_normalizer_migrates_authored_aria_hidden_ink_but_preserves_preview_only_ignore(self):
        scene = {
            "version": "scene_layout_v2",
            "regions": [{"id": "primary", "role": "primary", "x": 60, "y": 180, "w": 1160, "h": 498}],
        }
        html = '''<!doctype html><html><head><style>.slide{width:1280px;height:720px}</style></head><body><section class="slide"><div data-layout-id="scene-primary" data-layout-role="primary" style="position:absolute;left:60px;top:180px;width:1160px;height:498px"><div class="connector" aria-hidden="true" data-pptx-kind="ignore"></div><div aria-hidden="true" data-pptx-kind="ignore" data-sunairum-chart-preview="1"></div></div></section></body></html>'''
        normalized, meta = normalize_scene_authored_html(html, scene)
        self.assertEqual(1, meta["exportable_decorations_restored"])
        self.assertIn('class="connector" aria-hidden="true" data-pptx-kind="decoration"', normalized)
        self.assertIn('data-pptx-kind="ignore" data-sunairum-chart-preview="1"', normalized)

    @staticmethod
    def _roots(scene, bodies=None):
        bodies = bodies or {}
        return "".join(
            (
                '<div data-layout-id="scene-{id}" data-layout-role="{role}" '
                'style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;">'
                + bodies.get(region["role"], '<div class="accent-mass">Authored visual</div>')
                + "</div>"
            ).format(**region)
            for region in scene["regions"]
            if region["role"] != "footer"
        )

    @staticmethod
    def _document(roots):
        return (
            '<!doctype html><html><head><style>*{box-sizing:border-box}.slide{width:1280px;height:720px;}'
            '.accent-mass{background:linear-gradient(90deg,#123,#48f);}</style></head><body>'
            '<section class="slide">' + roots + "</section></body></html>"
        )

    def test_title_prompt_excludes_narrative_copy(self):
        slide = {
            "slide": 1,
            "role": "title",
            "title": "HERO Framework",
            "authors": "A. Researcher",
            "lede": "This explanatory paragraph does not belong on a cover.",
            "core_message": "This summary must also be suppressed.",
            "bullets": ["No cover bullets"],
        }
        scene = resolve_slide_scene(slide)
        prompt = build_scene_author_prompt(
            slide=slide,
            scene=scene,
            design_spec_md="Editorial research cover",
            design_reference_brief="",
            palette={},
        )
        self.assertIn("HERO Framework", prompt)
        self.assertIn("A. Researcher", prompt)
        self.assertNotIn("This explanatory paragraph", prompt)
        self.assertNotIn("This summary must", prompt)
        self.assertNotIn("No cover bullets", prompt)

    def test_prompt_preserves_creativity_and_locks_only_region_geometry(self):
        slide = {
            "slide": 3,
            "title": "Retrieval narrows the search",
            "core_message": "Scoring remains exact.",
            "figure_id": "pdf-page-3-picture-1",
        }
        scene = resolve_slide_scene(slide)
        prompt = build_scene_author_prompt(
            slide=slide,
            scene=scene,
            design_spec_md="Visual style: editorial blueprint",
            design_reference_brief="Bold academic composition",
            palette={"primary": "#1A365D", "accent": "#3182CE"},
        )
        self.assertIn("Immutable layout", prompt)
        self.assertIn('data-layout-id="scene-<id>"', prompt)
        self.assertIn("editorial blueprint", prompt)
        self.assertIn("pdf-page-3-picture-1", prompt)

    def test_contract_accepts_creative_internals_with_exact_scene_roots(self):
        slide = {"slide": 2, "title": "A claim", "core_message": "A lede"}
        scene = resolve_slide_scene(slide)
        html = self._document(self._roots(scene))
        self.assertEqual(validate_scene_authored_html(html, scene), [])

    def test_contract_rejects_figure_host_nested_in_title(self):
        slide = {"slide": 7, "title": "HERO loop", "figure_id": "pdf-page-7-picture-1"}
        scene = resolve_slide_scene(slide)
        roots = self._roots(
            scene,
            {
                "title": '<div data-pptx="figure" data-figure-id="pdf-page-7-picture-1"></div>',
                "figure": '<div class="accent-mass">not the figure host</div>',
            },
        )
        issues = validate_scene_authored_html(self._document(roots), scene)
        self.assertIn("host_wrong_region:figure:title", issues)

    def test_contract_rejects_region_nested_inside_another_region(self):
        slide = {"slide": 2, "title": "A claim", "core_message": "A lede"}
        scene = resolve_slide_scene(slide)
        title = next(r for r in scene["regions"] if r["role"] == "title")
        lede = next(r for r in scene["regions"] if r["role"] == "lede")
        nested_lede = (
            '<div data-layout-id="scene-{id}" data-layout-role="{role}" '
            'style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;">bad</div>'
        ).format(**lede)
        roots = (
            '<div data-layout-id="scene-{id}" data-layout-role="{role}" '
            'style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;">{nested}</div>'
        ).format(**title, nested=nested_lede)
        roots += self._roots(scene, {"title": ""})
        issues = validate_scene_authored_html(self._document(roots), scene)
        self.assertTrue(any(i.startswith("region_not_direct_slide_child:scene-lede") for i in issues))

    def test_formula_fallback_is_contract_valid_and_plain_text(self):
        from tasks.scene_html_renderer import render_scene_html

        slide = {
            "slide": 4,
            "title": "One objective",
            "lede": "Distance and equity share one score.",
            "formula": r"J(R)=C(R)/C_0+\beta(1-Jain(R))+\gamma CV(R)",
            "formula_terms": "β: equity weight",
            "formula_gloss": r"Setting \(\beta=\gamma=0\) recovers cost-only repair.",
        }
        scene = resolve_slide_scene(slide)
        rendered = render_scene_html(slide=slide, scene=scene, palette={})
        self.assertEqual(validate_scene_authored_html(rendered, scene), [])
        self.assertNotIn(r"\(", rendered)
        self.assertIn("β=γ=0", rendered)

    def test_closing_region_donor_does_not_duplicate_questions_or_create_empty_panel(self):
        from tasks.scene_html_renderer import render_scene_html

        slide = {
            "slide": 14,
            "role": "closing",
            "title": "Thank you",
            "core_message": "Questions welcome",
            "authors": "A. Researcher",
        }
        scene = resolve_slide_scene(slide)
        rendered = render_scene_html(slide=slide, scene=scene, palette={})
        self.assertEqual(1, rendered.count("Questions welcome"))
        self.assertIn("scene-closing", rendered)
        self.assertNotIn("primary-card-1-body", rendered)

    def test_contract_rejects_moved_region(self):
        slide = {"slide": 1, "role": "title", "title": "Title"}
        scene = resolve_slide_scene(slide)
        html = (
            '<!doctype html><html><head><style>.slide{width:1280px;height:720px}</style></head><body>'
            '<section class="slide"><div data-layout-id="scene-title" data-layout-role="title" '
            'style="position:absolute;left:80px;top:60px;width:1160px;height:48px;">Title</div>'
            '</section></body></html>'
        )
        issues = validate_scene_authored_html(html, scene)
        self.assertTrue(any(item.startswith("geometry:scene-title:left") for item in issues))

    def test_multi_chart_contract_accepts_one_host_per_chart_region(self):
        slide = {
            "slide": 11,
            "title": "Equity gains",
            "core_message": "Three cohorts move in the same direction.",
            "visualization": "comparison_columns",
            "charts": {"c1": {}, "c2": {}, "c3": {}},
        }
        scene = resolve_slide_scene(slide)
        self.assertEqual("multi_chart", scene["composition"])
        rendered = __import__(
            "tasks.scene_html_renderer", fromlist=["render_scene_html"]
        ).render_scene_html(slide=slide, scene=scene, palette={})
        issues = validate_scene_authored_html(rendered, scene)
        self.assertEqual([], issues)


if __name__ == "__main__":
    unittest.main()


class LanguageContractIsEnforcedWhileAuthoring(unittest.TestCase):
    """A wrong-language slide is rejected and retried, not shipped and reported.

    The prompt already named the deck language; nothing checked the answer. A
    Turkish deck's cover therefore shipped reading "ACADEMIC BLUEPRINT ·
    VEHICLE ROUTING" over Turkish body copy, and the obedience report only said
    so once the reader had the file.
    """

    TITLE = "HNSW Guided Large Neighborhood Search for Equitable Vehicle Routing"

    def _document(self, body: str) -> str:
        return (
            "<!doctype html><html lang=\"tr\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=1280\"><style>"
            "html,body{margin:0;width:1280px;height:720px}</style></head>"
            f"<body><main class=\"slide\">{body}</main></body></html>"
        )

    def _roots(self, scene, copy_by_role):
        return "".join(
            (
                '<div data-layout-id="scene-{id}" data-layout-role="{role}">{copy}</div>'
            ).format(copy=copy_by_role.get(region["role"], "Yerlestirilmis gorsel"), **region)
            for region in scene["regions"]
            if region["role"] != "footer"
        )

    def test_off_language_authored_copy_is_retried_with_the_offending_string(self):
        from tasks.scene_html_author import author_scene_html

        # A content slide, because that is where the author writes prose of its
        # own; a cover has only a title region and a footer.
        slide = {"slide": 2, "title": self.TITLE, "core_message": "Bir lede"}
        scene = resolve_slide_scene(slide)
        english = self._document(self._roots(scene, {
            "title": f"<h1>{self.TITLE}</h1>",
            "lede": "<p>An overview of the method and the experiments that follow it</p>",
        }))
        turkish = self._document(self._roots(scene, {
            "title": f"<h1>{self.TITLE}</h1>",
            "lede": "<p>Yontemin ve ardindan gelen deneylerin genel gorunumu burada</p>",
        }))
        call = Mock(side_effect=[english, turkish])
        authored = author_scene_html(
            slide=slide,
            scene=scene,
            design_spec_md="Editorial cover",
            design_reference_brief="",
            palette={},
            call_text=call,
            primary_language="tr",
        )
        # The first answer was rejected: the gate ran while a retry was possible.
        self.assertEqual(call.call_count, 2)
        # And the retry prompt named the string to rewrite.
        retry_prompt = call.call_args_list[1].args[1]
        self.assertIn("off_language_copy", retry_prompt)
        self.assertIn("An overview of the method", retry_prompt)
        self.assertIn("Yontemin ve ardindan", authored)

    def test_the_quoted_paper_title_does_not_trigger_a_retry(self):
        """The cover keeps the paper's own English title; that is not a violation."""
        from tasks.scene_html_author import author_scene_html

        slide = {"slide": 2, "title": self.TITLE, "core_message": "Bir lede"}
        scene = resolve_slide_scene(slide)
        document = self._document(self._roots(scene, {
            "title": f"<h1>{self.TITLE}</h1>",
            "lede": "<p>Yontemin ve ardindan gelen deneylerin genel gorunumu burada</p>",
        }))
        call = Mock(return_value=document)
        author_scene_html(
            slide=slide,
            scene=scene,
            design_spec_md="Editorial cover",
            design_reference_brief="",
            palette={},
            call_text=call,
            primary_language="tr",
        )
        self.assertEqual(call.call_count, 1, "a quoted title must not cost a retry")
