import unittest

from tasks.layout_findings import (
    classify_runtime_finding,
    native_fidelity_remediation_plan,
)


class LayoutFindingTests(unittest.TestCase):
    def test_minor_runtime_overflow_is_object_repairable(self):
        finding = classify_runtime_finding(
            "runtime_text_overflow: h1.title-copy:1 scrolls (0.0px x, 9.0px y)"
        )
        self.assertEqual("repairable", finding["severity"])
        self.assertEqual("object", finding["repair_scope"])

    def test_canvas_overflow_escalates_only_to_region(self):
        finding = classify_runtime_finding(
            "runtime_canvas_overflow: ul.claims:9 paints outside the slide plate"
        )
        self.assertEqual("region_blocking", finding["severity"])
        self.assertEqual("region", finding["repair_scope"])

    def test_native_fidelity_plan_is_object_first_and_never_whole_slide(self):
        report = {
            "failures": [
                {
                    "stem": "slide_02",
                    "semantic": {
                        "ok": False,
                        "geometry_failures": [
                            {"type": "text_line_count_drift", "elementId": "lede-copy"}
                        ],
                        "typography_failures": [],
                        "ownership_failures": [],
                        "missing_element_ids": [],
                    },
                }
            ]
        }
        plan = native_fidelity_remediation_plan(report)
        self.assertFalse(plan["ok"])
        self.assertFalse(plan["whole_slide_fallback_allowed"])
        self.assertEqual("object", plan["findings"][0]["repair_scope"])
        self.assertEqual("lede-copy", plan["findings"][0]["element_id"])


if __name__ == "__main__":
    unittest.main()
