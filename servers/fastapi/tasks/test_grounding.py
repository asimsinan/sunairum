import json
import unittest
from decimal import Decimal

from grounded_planner import (
    allocate_section_coverage,
    apply_coverage_plan_section_ids,
    canonical_numeric_tokens,
    is_backmatter_section,
    materialize_source_tables,
    remove_unsupported_number_sentences,
    sanitize_grounded_outline,
    strip_catalog_provenance_annotations,
    validate_grounded_outline,
    validate_section_coverage,
)
from grounding_qa import run_grounding_qa


def _bundle():
    return {
        "manifest": {"bundle_sha256": "bundle"},
        "sections": {"sections": [
            {"section_id": "sec-methods", "level": 1, "title": "Methods", "evidence_ids": ["ev-methods"]},
            {"section_id": "sec-results", "level": 1, "title": "Results", "evidence_ids": ["ev-results"]},
        ]},
        "evidence": [
            {"evidence_id": "ev-methods", "text": "Methods used a controlled protocol."},
            {"evidence_id": "ev-results", "text": "HERO reduced evaluations by 1.74x."},
            {"evidence_id": "ev-table", "text": "Results table"},
        ],
        "tables": {"tables": [{
            "table_id": "table-1",
            "evidence_id": "ev-table",
            "headers": [{"cell_id": "h1", "text": "Method"}, {"cell_id": "h2", "text": "Cost"}],
            "rows": [[{"cell_id": "r1", "text": "HERO"}, {"cell_id": "r2", "text": "10"}],
                      [{"cell_id": "r3", "text": "ALNS"}, {"cell_id": "r4", "text": "12"}]],
        }]},
        "assets": {"assets": []},
        "formulas": {"formulas": []},
    }


class GroundingTests(unittest.TestCase):
    def _slide(self, grounding, content=None):
        return {
            "title": "Grounded slide",
            "layout": "02_title_content.svg",
            "content": content or {},
            "grounding": grounding,
        }

    def test_fixed_slide_coverage_groups_sections(self):
        plan = allocate_section_coverage(_bundle(), 1)
        self.assertEqual(1, len(plan))
        self.assertEqual({"sec-methods", "sec-results"}, set(plan[0]["section_ids"]))

    def test_fixed_slide_count_is_preserved_when_count_exceeds_sections(self):
        plan = allocate_section_coverage(_bundle(), 4)
        self.assertEqual(4, len(plan))
        self.assertTrue(all(item["section_ids"] for item in plan))

    def test_unknown_evidence_is_rejected(self):
        outline = {
            "slides": [{
                "title": "Results",
                "layout": "20_table_summary.svg",
                "content": {},
                "grounding": {
                    "section_ids": ["sec-results"],
                    "evidence_ids": ["missing"],
                    "claims": [], "metrics": [], "table_bindings": [],
                    "figure_bindings": [], "formula_bindings": [],
                },
            }]
        }
        parsed, errors = validate_grounded_outline(outline, _bundle())
        self.assertIsNone(parsed)
        self.assertTrue(any("no-evidence" not in error and "missing" in error for error in errors))

    def test_source_table_cells_replace_model_table_content(self):
        outline = {
            "slides": [{
                "title": "Results",
                "layout": "20_table_summary.svg",
                "content": {"table": {"columns": ["invented"], "rows": [["bad"]]}},
                "grounding": {
                    "section_ids": ["sec-results"],
                    "evidence_ids": ["ev-table"],
                    "claims": [], "metrics": [],
                    "table_bindings": [{
                        "table_id": "table-1", "slide_id": "slide-1",
                        "selected_columns": ["Method", "Cost"], "selected_rows": [],
                        "transform": "source_full", "evidence_ids": ["ev-table"],
                    }],
                    "figure_bindings": [], "formula_bindings": [],
                },
            }]
        }
        parsed, errors = validate_grounded_outline(outline, _bundle())
        self.assertIsNotNone(parsed, errors)
        result = materialize_source_tables(parsed, _bundle())
        self.assertEqual("HERO", result["slides"][0]["content"]["table"]["rows"][0][0]["text"])
        self.assertNotEqual("invented", result["slides"][0]["content"]["table"]["columns"][0]["text"])
        # This used to add content["SOURCE"] = "PDF p. 3", which the renderer then
        # printed on the slide. Page provenance is audit data, not slide copy.
        content = result["slides"][0]["content"]
        self.assertNotIn("SOURCE", content)
        self.assertNotIn("PDF p.", json.dumps(result, ensure_ascii=False))

    def test_section_coverage_reports_missing_major_section(self):
        outline = {
            "slides": [{
                "title": "Methods",
                "layout": "02_title_content.svg",
                "content": {},
                "grounding": {
                    "section_ids": ["sec-methods"],
                    "evidence_ids": ["ev-methods"],
                    "claims": [], "metrics": [], "table_bindings": [],
                    "figure_bindings": [], "formula_bindings": [],
                },
            }]
        }
        parsed, errors = validate_grounded_outline(outline, _bundle())
        self.assertIsNotNone(parsed, errors)
        self.assertEqual(["section-coverage-missing:sec-results"], validate_section_coverage(parsed, _bundle()))

    def test_apply_coverage_plan_stamps_omitted_trailing_sections(self):
        """Model omitted Discussion/Conclusion IDs; allocation still owns them."""
        outline = {
            "slides": [
                {
                    "title": "Title",
                    "layout": "01_title_slide.svg",
                    "content": {},
                    "grounding": {
                        "section_ids": ["sec-methods"],
                        "evidence_ids": ["ev-methods"],
                        "claims": [], "metrics": [], "table_bindings": [],
                        "figure_bindings": [], "formula_bindings": [],
                    },
                },
                {
                    "title": "Wrap-up",
                    "layout": "02_title_content.svg",
                    "content": {},
                    "grounding": {
                        "section_ids": ["sec-results"],
                        "evidence_ids": ["ev-results"],
                        "claims": [], "metrics": [], "table_bindings": [],
                        "figure_bindings": [], "formula_bindings": [],
                    },
                },
            ]
        }
        coverage_plan = [
            {"slide_id": "slide-1", "section_ids": ["sec-methods"], "coverage_mode": "title"},
            {
                "slide_id": "slide-2",
                "section_ids": ["sec-results", "sec-discussion", "sec-conclusion"],
                "coverage_mode": "compressed",
            },
        ]
        stamped = apply_coverage_plan_section_ids(outline, coverage_plan)
        self.assertEqual(
            ["sec-results", "sec-discussion", "sec-conclusion"],
            stamped["slides"][1]["grounding"]["section_ids"],
        )
        bundle = _bundle()
        bundle["sections"]["sections"].extend([
            {
                "section_id": "sec-discussion",
                "level": 1,
                "title": "VII. DISCUSSION AND LIMITATIONS",
                "evidence_ids": ["ev-results"],
            },
            {
                "section_id": "sec-conclusion",
                "level": 1,
                "title": "VIII. CONCLUSION",
                "evidence_ids": ["ev-results"],
            },
        ])
        parsed, errors = validate_grounded_outline(stamped, bundle)
        self.assertIsNotNone(parsed, errors)
        self.assertEqual([], validate_section_coverage(parsed, bundle))

    def test_missing_sections_not_required_when_absent_from_paper(self):
        """Papers without Discussion/Conclusion do not invent those requirements."""
        outline = {
            "slides": [{
                "title": "Whole paper",
                "layout": "02_title_content.svg",
                "content": {},
                "grounding": {
                    "section_ids": ["sec-methods", "sec-results"],
                    "evidence_ids": ["ev-methods", "ev-results"],
                    "claims": [], "metrics": [], "table_bindings": [],
                    "figure_bindings": [], "formula_bindings": [],
                },
            }]
        }
        parsed, errors = validate_grounded_outline(outline, _bundle())
        self.assertIsNotNone(parsed, errors)
        self.assertEqual([], validate_section_coverage(parsed, _bundle()))

    def test_backmatter_sections_are_optional_for_coverage(self):
        self.assertTrue(is_backmatter_section({
            "section_id": "sec-acknowledgment-016", "title": "ACKNOWLEDGMENT", "level": 1,
        }))
        self.assertTrue(is_backmatter_section({
            "section_id": "sec-references-017", "title": "REFERENCES", "level": 1,
        }))
        self.assertFalse(is_backmatter_section({
            "section_id": "sec-viii-conclusion-015", "title": "VIII. CONCLUSION", "level": 1,
        }))
        bundle = _bundle()
        bundle["sections"]["sections"].extend([
            {
                "section_id": "sec-acknowledgment-016",
                "level": 1,
                "title": "ACKNOWLEDGMENT",
                "evidence_ids": ["ev-ack"],
            },
            {
                "section_id": "sec-references-017",
                "level": 1,
                "title": "REFERENCES",
                "evidence_ids": ["ev-ref"],
            },
        ])
        bundle["evidence"].extend([
            {"evidence_id": "ev-ack", "text": "Thanks."},
            {"evidence_id": "ev-ref", "text": "Author, Title."},
        ])
        outline = {
            "slides": [{
                "title": "Whole paper",
                "layout": "02_title_content.svg",
                "content": {},
                "grounding": {
                    "section_ids": ["sec-methods", "sec-results"],
                    "evidence_ids": ["ev-methods", "ev-results"],
                    "claims": [], "metrics": [], "table_bindings": [],
                    "figure_bindings": [], "formula_bindings": [],
                },
            }]
        }
        parsed, errors = validate_grounded_outline(outline, bundle)
        self.assertIsNotNone(parsed, errors)
        self.assertEqual([], validate_section_coverage(parsed, bundle))
        plan = allocate_section_coverage(bundle, 2)
        allocated = {sid for item in plan for sid in item["section_ids"]}
        self.assertNotIn("sec-acknowledgment-016", allocated)
        self.assertNotIn("sec-references-017", allocated)

    def test_supported_source_paraphrase_passes(self):
        outline = {"slides": [self._slide({
            "section_ids": ["sec-results"],
            "evidence_ids": ["ev-results"],
            "claims": [{
                "claim_id": "claim-1",
                "text": "HERO reduced evaluations by 1.74x.",
                "support_type": "source_paraphrase",
                "evidence_ids": ["ev-results"],
            }],
            "metrics": [], "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
        })]}
        parsed, errors = validate_grounded_outline(outline, _bundle())
        self.assertIsNotNone(parsed, errors)
        self.assertEqual([], errors)

    def test_direct_support_type_alias_normalizes_to_source_paraphrase(self):
        outline = {"slides": [self._slide({
            "section_ids": ["sec-results"],
            "evidence_ids": ["ev-results"],
            "claims": [{
                "claim_id": "claim-direct",
                "text": "HERO reduced evaluations by 1.74x.",
                "support_type": "direct",
                "evidence_ids": ["ev-results"],
            }],
            "metrics": [], "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
        })]}
        parsed, errors = validate_grounded_outline(outline, _bundle())
        self.assertIsNotNone(parsed, errors)
        self.assertEqual([], errors)
        self.assertEqual(
            "source_paraphrase",
            parsed.slides[0].grounding.claims[0].support_type,
        )

    def test_unknown_support_type_soft_coerces_to_source_paraphrase(self):
        outline = {"slides": [self._slide({
            "section_ids": ["sec-results"],
            "evidence_ids": ["ev-results"],
            "claims": [{
                "claim_id": "claim-citation",
                "text": "HERO reduced evaluations by 1.74x.",
                "support_type": "citation",
                "evidence_ids": ["ev-results"],
            }],
            "metrics": [], "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
        })]}
        parsed, errors = validate_grounded_outline(outline, _bundle())
        self.assertIsNotNone(parsed, errors)
        self.assertEqual([], errors)
        self.assertEqual(
            "source_paraphrase",
            parsed.slides[0].grounding.claims[0].support_type,
        )

    def test_calculated_support_type_alias_normalizes_to_derived(self):
        outline = {"slides": [self._slide({
            "section_ids": ["sec-results"],
            "evidence_ids": ["ev-results"],
            "claims": [{
                "claim_id": "claim-calculated",
                "text": "HERO reduced evaluations by 1.74x.",
                "support_type": "calculated",
                "evidence_ids": ["ev-results"],
            }],
            "metrics": [], "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
        })]}
        parsed, errors = validate_grounded_outline(outline, _bundle())
        self.assertIsNotNone(parsed, errors)
        self.assertEqual([], errors)
        self.assertEqual(
            "derived",
            parsed.slides[0].grounding.claims[0].support_type,
        )

    def test_missing_claim_metadata_is_filled_without_relaxing_evidence_checks(self):
        outline = {"slides": [self._slide({
            "section_ids": ["sec-results"],
            "evidence_ids": ["ev-results"],
            "claims": [{
                "text": "HERO reduced evaluations by 1.74x.",
                "evidence_ids": ["ev-results"],
            }],
            "metrics": [], "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
        })]}
        parsed, errors = validate_grounded_outline(outline, _bundle())
        self.assertIsNotNone(parsed, errors)
        self.assertEqual([], errors)
        self.assertEqual("claim-slide-01-01", parsed.slides[0].grounding.claims[0].claim_id)
        self.assertEqual("source_paraphrase", parsed.slides[0].grounding.claims[0].support_type)

    def test_external_claim_with_valid_id_is_rejected(self):
        outline = {"slides": [self._slide({
            "section_ids": ["sec-results"],
            "evidence_ids": ["ev-results"],
            "claims": [{
                "claim_id": "claim-external",
                "text": "External randomized trials prove this policy works everywhere.",
                "support_type": "source_paraphrase",
                "evidence_ids": ["ev-results"],
            }],
            "metrics": [], "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
        })]}
        parsed, errors = validate_grounded_outline(outline, _bundle())
        self.assertIsNone(parsed)
        self.assertTrue(any("weak-claim-support:claim-external" in error for error in errors))

    def test_exact_source_quote_can_support_a_low_overlap_paraphrase(self):
        outline = {"slides": [self._slide({
            "section_ids": ["sec-results"],
            "evidence_ids": ["ev-results"],
            "claims": [{
                "claim_id": "claim-quoted",
                "text": "The result is efficient.",
                "support_type": "source_paraphrase",
                "source_quote": "HERO reduced evaluations by 1.74x.",
                "evidence_ids": ["ev-results"],
            }],
            "metrics": [], "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
        })]}

        parsed, errors = validate_grounded_outline(outline, _bundle())

        self.assertIsNotNone(parsed, errors)
        self.assertEqual([], errors)

    def test_source_quote_must_be_present_in_referenced_evidence(self):
        outline = {"slides": [self._slide({
            "section_ids": ["sec-results"],
            "evidence_ids": ["ev-results"],
            "claims": [{
                "claim_id": "claim-wrong-quote",
                "text": "HERO reduced evaluations by 1.74x.",
                "support_type": "source_verbatim",
                "source_quote": "This quote is not in the source.",
                "evidence_ids": ["ev-results"],
            }],
            "metrics": [], "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
        })]}

        parsed, errors = validate_grounded_outline(outline, _bundle())

        self.assertIsNone(parsed)
        self.assertTrue(any("claim-quote-not-found:claim-wrong-quote" in error for error in errors))

    def test_integer_metrics_survive_float_coercion(self):
        bundle = _bundle()
        bundle["evidence"].extend([
            {"evidence_id": "ev-dimension", "text": "Each insertion position uses a 14-dimensional vector."},
            {"evidence_id": "ev-iterations", "text": "The experiment runs for 500 iterations."},
        ])
        outline = {"slides": [self._slide({
            "section_ids": ["sec-results"],
            "evidence_ids": ["ev-dimension", "ev-iterations"],
            "claims": [],
            "metrics": [
                {"metric_id": "metric-dimension", "label": "Feature dimensions", "value": 14.0, "evidence_ids": ["ev-dimension"]},
                {"metric_id": "metric-iterations", "label": "Iterations", "value": 500.0, "evidence_ids": ["ev-iterations"]},
            ],
            "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
        })]}

        parsed, errors = validate_grounded_outline(outline, bundle)

        self.assertIsNotNone(parsed, errors)
        self.assertEqual([], errors)

    def test_range_and_unicode_multiplier_numbers_are_canonicalized(self):
        bundle = _bundle()
        bundle["evidence"].extend([
            {"evidence_id": "ev-range", "text": "The benchmark covers n = 300–400 customers."},
            {"evidence_id": "ev-speedup", "text": "HNSW reduces repair evaluations by about 1.74×."},
        ])
        outline = {"slides": [self._slide({
            "section_ids": ["sec-results"],
            "evidence_ids": ["ev-range", "ev-speedup"],
            "claims": [],
            "metrics": [{"metric_id": "metric-speedup", "label": "Reduction", "value": 1.74, "unit": "x", "evidence_ids": ["ev-speedup"]}],
            "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
        }, {"BODY": "The benchmark covers n = 300–400 customers."})]}

        parsed, errors = validate_grounded_outline(outline, bundle)

        self.assertIsNotNone(parsed, errors)
        self.assertEqual([], errors)

    def test_unsupported_number_and_numeric_substrings_remain_blocking(self):
        bundle = _bundle()
        bundle["evidence"].append({"evidence_id": "ev-large", "text": "The larger experiment uses 1300 customers."})
        for value in ("300", "300 customers"):
            outline = {"slides": [self._slide({
                "section_ids": ["sec-results"],
                "evidence_ids": ["ev-large"],
                "claims": [], "metrics": [], "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
            }, {"BODY": value})]}
            parsed, errors = validate_grounded_outline(outline, bundle)
            self.assertIsNone(parsed)
            self.assertTrue(any("unsupported-number:300" in error for error in errors))

    def test_catalog_evidence_ids_are_not_numeric_claims(self):
        """Digits inside ev-page-02-block-024 are addresses, not research quantities."""
        formula = (
            "Delta f(p) = Delta distance(p) + beta * Delta equity(p) "
            "(evidence=ev-page-02-block-024; ev-page-02-block-025; ev-page-03-block-041)"
        )
        tokens = {value for value, _unit in canonical_numeric_tokens(formula)}
        self.assertFalse(tokens & {Decimal(n) for n in ("2", "3", "24", "25", "41")})
        cleaned = strip_catalog_provenance_annotations(formula)
        self.assertNotIn("evidence=", cleaned)
        self.assertIn("Delta f(p)", cleaned)

        bundle = _bundle()
        bundle["evidence"].append({
            "evidence_id": "ev-page-02-block-024",
            "text": "We use a normalized weighted sum for the insertion objective.",
        })
        outline = {"slides": [self._slide({
            "section_ids": ["sec-methods"],
            "evidence_ids": ["ev-page-02-block-024"],
            "claims": [], "metrics": [], "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
        }, {"TITLE": "Equity-Guided Insertion", "BODY": "", "FORMULA": formula})]}
        sanitized = sanitize_grounded_outline(outline, bundle)
        parsed, errors = validate_grounded_outline(sanitized, bundle)
        self.assertIsNotNone(parsed, errors)
        self.assertFalse(any("unsupported-number:" in error for error in errors))
        self.assertNotIn("evidence=", sanitized["slides"][0]["content"]["FORMULA"])

    def test_provenance_scrubber_handles_nested_and_split_annotations(self):
        from tasks.grounded_planner import scrub_content_provenance

        payload = {
            "cards": [
                {"body": "Mapped to a vector. (evidence=ev-page-03-block-031"},
                {"body": "ev-page-03-block-034)"},
            ],
            "evidence_ids": ["ev-page-03-block-031"],
        }
        cleaned = scrub_content_provenance(payload)
        self.assertEqual("Mapped to a vector.", cleaned["cards"][0]["body"])
        self.assertEqual("", cleaned["cards"][1]["body"])
        self.assertEqual(["ev-page-03-block-031"], cleaned["evidence_ids"])

    def test_spoken_note_removes_internal_evidence_clause(self):
        from tasks.speaker_notes import _clean_spoken_note

        note = (
            "The vector carries workload context, as documented in evidence objects "
            "ev-page-03-block-031 and ev-page-03-block-034. Next, retrieval narrows the set, "
            "as reported in ev-page-03-block-032."
        )
        cleaned = _clean_spoken_note(note)
        self.assertEqual(
            "The vector carries workload context. Next, retrieval narrows the set.",
            cleaned,
        )

    def test_real_unsupported_number_beside_evidence_annotation_still_detected(self):
        """Scrubbing catalog noise must not hide invented quantities in the same field."""
        bundle = _bundle()
        bundle["evidence"].append({
            "evidence_id": "ev-page-02-block-024",
            "text": "We use a normalized weighted sum for the insertion objective.",
        })
        outline = {"slides": [self._slide({
            "section_ids": ["sec-methods"],
            "evidence_ids": ["ev-page-02-block-024"],
            "claims": [], "metrics": [], "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
        }, {
            "BODY": "Latency drops to 322 ms (evidence=ev-page-02-block-024).",
        })]}
        _parsed, errors = validate_grounded_outline(outline, bundle)
        self.assertTrue(any("unsupported-number:322" in error for error in errors))
        sanitized = sanitize_grounded_outline(outline, bundle)
        self.assertNotIn("322", sanitized["slides"][0]["content"].get("BODY", ""))

    def test_affiliation_postal_code_stripped_not_blocking(self):
        """Deck furniture postal codes must not fail-close free_design grounding."""
        bundle = _bundle()
        outline = {"slides": [self._slide({
            "section_ids": ["sec-results"],
            "evidence_ids": ["ev-results"],
            "claims": [], "metrics": [], "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
        }, {
            "TITLE": "HERO",
            "BODY": "",
            "SUBTITLE": "Assoc. Prof. Dr. X · University, Isparta, Turkey, 32200",
            "AUTHORS": "Assoc. Prof. Dr. X",
            "AFFILIATIONS": "University, Isparta, Turkey, 32200",
        })]}
        cleaned = sanitize_grounded_outline(outline, bundle)
        parsed, errors = validate_grounded_outline(cleaned, bundle)
        self.assertIsNotNone(parsed, errors)
        self.assertFalse(any("32200" in error for error in errors))
        aff = cleaned["slides"][0]["content"]["AFFILIATIONS"]
        self.assertNotIn("32200", aff)
        self.assertIn("Turkey", aff)

    def test_derived_percentage_requires_and_checks_denominator(self):
        base_grounding = {
            "section_ids": ["sec-results"],
            "evidence_ids": ["ev-results"],
            "claims": [],
            "table_bindings": [], "figure_bindings": [], "formula_bindings": [],
        }
        missing_denominator = {"slides": [self._slide({
            **base_grounding,
            "metrics": [{
                "metric_id": "metric-missing-denominator",
                "label": "Success",
                "value": 25,
                "unit": "%",
                "evidence_ids": ["ev-results"],
                "derivation": {"operation": "percentage", "numerator": 1},
            }],
        })]}
        parsed, errors = validate_grounded_outline(missing_denominator, _bundle())
        self.assertIsNone(parsed)
        self.assertTrue(any("metric-derivation-denominator-missing" in error for error in errors))

        valid = {"slides": [self._slide({
            **base_grounding,
            "metrics": [{
                "metric_id": "metric-valid",
                "label": "Success",
                "value": 25,
                "unit": "%",
                "evidence_ids": ["ev-results"],
                "derivation": {"operation": "percentage", "numerator": 1, "denominator": 4},
            }],
        })]}
        parsed, errors = validate_grounded_outline(valid, _bundle())
        self.assertIsNotNone(parsed, errors)
        self.assertEqual([], errors)

        invalid = {"slides": [self._slide({
            **base_grounding,
            "metrics": [{
                "metric_id": "metric-invalid",
                "label": "Success",
                "value": 30,
                "unit": "%",
                "evidence_ids": ["ev-results"],
                "derivation": {"operation": "percentage", "numerator": 1, "denominator": 4},
            }],
        })]}
        parsed, errors = validate_grounded_outline(invalid, _bundle())
        self.assertIsNone(parsed)
        self.assertTrue(any("metric-derivation-invalid:metric-invalid" in error for error in errors))

    def test_malformed_source_table_spans_are_blocking(self):
        bundle = _bundle()
        bundle["tables"]["tables"][0]["rows"][0][0]["rowspan"] = 0
        outline = {"slides": [self._slide({
            "section_ids": ["sec-results"],
            "evidence_ids": ["ev-table"],
            "claims": [], "metrics": [], "figure_bindings": [], "formula_bindings": [],
            "table_bindings": [{
                "table_id": "table-1", "slide_id": "slide-1",
                "selected_columns": [], "selected_rows": [],
                "transform": "source_full", "evidence_ids": ["ev-table"],
            }],
        }, {"table": {"columns": [], "rows": []}})]}
        parsed, errors = validate_grounded_outline(outline, bundle)
        self.assertIsNone(parsed)
        self.assertTrue(any("source-table-span-invalid:table-1" in error for error in errors))

    def test_figure_page_and_formula_rendering_mismatches_are_blocking(self):
        bundle = _bundle()
        bundle["evidence"].extend([
            {"evidence_id": "ev-figure", "text": "Figure source"},
            {"evidence_id": "ev-formula", "text": "x = y"},
        ])
        bundle["assets"]["assets"] = [{
            "asset_id": "asset-1", "page": 2, "caption_evidence_id": "ev-figure",
        }]
        bundle["formulas"]["formulas"] = [{
            "formula_id": "formula-1", "evidence_id": "ev-formula", "page": 3,
            "latex": "x = y", "rendering_status": "needs_review",
        }]
        outline = {"slides": [self._slide({
            "section_ids": ["sec-results"],
            "evidence_ids": ["ev-results"],
            "claims": [], "metrics": [], "table_bindings": [],
            "figure_bindings": [{
                "asset_id": "asset-1", "slide_id": "slide-1", "citation_pages": [1],
                "evidence_ids": ["ev-figure"],
            }],
            "formula_bindings": [{
                "formula_id": "formula-1", "slide_id": "slide-1",
                "render_policy": "source_latex", "evidence_ids": ["ev-formula"],
            }],
        })]}
        parsed, errors = validate_grounded_outline(outline, bundle)
        self.assertIsNone(parsed)
        self.assertTrue(any("figure-page-mismatch" in error for error in errors))
        self.assertTrue(any("formula-rendering-unavailable" in error for error in errors))

    def test_grounding_qa_allows_ai_visuals_but_rejects_figure_page_mismatch(self):
        # pdf_strict gates claims/evidence, not decorative AI/stock visuals.
        bundle = _bundle()
        bundle["assets"]["assets"] = [{"asset_id": "asset-1", "page": 2}]
        slides = [{
            "grounding": {
                "evidence_ids": ["ev-results"],
                "claims": [], "metrics": [], "table_bindings": [],
                "figure_bindings": [{
                    "asset_id": "asset-1", "citation_pages": [1], "evidence_ids": ["ev-results"],
                }],
                "formula_bindings": [],
            },
            "content": {},
        }]
        result = run_grounding_qa(slides, [{"primary_visual_source": "ai"}], bundle, "pdf_strict")
        categories = {issue["category"] for issue in result["issues"]}
        self.assertEqual("failed", result["status"])
        self.assertNotIn("unsupported-generated-content", categories)
        self.assertIn("figure-page-mismatch", categories)


if __name__ == "__main__":
    unittest.main()
