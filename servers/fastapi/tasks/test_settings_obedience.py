"""settings_obedience records selected vs delivered Production Settings."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class SettingsObedienceTests(unittest.TestCase):
    def test_notes_budget_mismatch_is_flagged(self):
        from tasks.free_design_pipeline import write_settings_obedience

        root = Path(tempfile.mkdtemp())
        validation = root / "validation"
        validation.mkdir()
        with mock.patch(
            "tasks.speaker_notes.resolve_duration_settings", return_value=(10, 140)
        ), mock.patch("tasks.speaker_notes.animations_enabled", return_value=False):
            # target_words = 10 * 140 * 0.88 = 1232; 100 words is far under budget
            report = write_settings_obedience(
                storage_dir=str(root),
                validation_dir=str(validation),
                result_data={
                    "selected_figure_ids": [],
                    "selected_table_ids": [],
                    "proactive_speaker_notes": True,
                },
                placement={"figures": [], "tables": [], "errors": []},
                notes_result={"status": "generated", "actual_words": 100},
            )
        self.assertFalse(report["speaker_notes"]["budget_ok"])
        self.assertIn("notes_budget_mismatch", report["warnings"])
        self.assertFalse(report["ok"])
        saved = json.loads((validation / "settings_obedience.json").read_text(encoding="utf-8"))
        self.assertEqual(100, saved["speaker_notes"]["actual_words"])

    def test_placed_assets_clear_missing(self):
        from tasks.free_design_pipeline import write_settings_obedience

        root = Path(tempfile.mkdtemp())
        validation = root / "validation"
        validation.mkdir()
        with mock.patch(
            "tasks.speaker_notes.resolve_duration_settings", return_value=(5, 140)
        ), mock.patch("tasks.speaker_notes.animations_enabled", return_value=True):
            report = write_settings_obedience(
                storage_dir=str(root),
                validation_dir=str(validation),
                result_data={
                    "selected_figure_ids": ["fig-1"],
                    "selected_table_ids": ["tbl-1"],
                    "proactive_speaker_notes": False,
                },
                placement={
                    "figures": [{"figure_id": "fig-1"}],
                    "tables": [{"table_id": "tbl-1"}],
                    "errors": [],
                },
                notes_result=None,
            )
        self.assertEqual([], report["missing_figure_ids"])
        self.assertEqual([], report["missing_table_ids"])
        self.assertTrue(report["ok"])
        self.assertTrue(report["animations_requested"])

    def test_final_html_figures_clear_missing_when_placement_events_are_empty(self):
        from tasks.free_design_pipeline import write_settings_obedience

        root = Path(tempfile.mkdtemp())
        validation = root / "validation"
        html_dir = root / "html_output"
        validation.mkdir()
        html_dir.mkdir()
        (html_dir / "slide_05.html").write_text(
            '<div data-pptx="figure" data-figure-id="fig-1">'
            '<img data-sunairum-figure-id="fig-1" src="data:image/png;base64,abc">'
            "</div>",
            encoding="utf-8",
        )
        with mock.patch(
            "tasks.speaker_notes.resolve_duration_settings", return_value=(5, 140)
        ), mock.patch("tasks.speaker_notes.animations_enabled", return_value=False):
            report = write_settings_obedience(
                storage_dir=str(root),
                validation_dir=str(validation),
                result_data={
                    "selected_figure_ids": ["fig-1", "fig-other"],
                    "selected_table_ids": [],
                    "proactive_speaker_notes": False,
                },
                placement={"figures": [], "tables": [], "errors": []},
                notes_result=None,
            )

        self.assertEqual(["fig-1"], report["placed_figure_ids"])
        self.assertEqual(["fig-other"], report["missing_figure_ids"])
        self.assertFalse(report["ok"])

    def test_status_reconciliation_repairs_stale_placement_report(self):
        from tasks.settings_obedience_artifacts import reconcile_settings_obedience

        root = Path(tempfile.mkdtemp())
        html_dir = root / "html_output"
        html_dir.mkdir()
        (html_dir / "slide_01.html").write_text(
            '<img data-sunairum-figure-id="fig-1" src="figure.png">',
            encoding="utf-8",
        )
        report = reconcile_settings_obedience(
            {
                "selected_figure_ids": ["fig-1"],
                "selected_table_ids": [],
                "placed_figure_ids": [],
                "placed_table_ids": [],
                "missing_figure_ids": ["fig-1"],
                "missing_table_ids": [],
                "speaker_notes": {"budget_ok": True},
                "ok": False,
            },
            root,
        )
        self.assertEqual([], report["missing_figure_ids"])
        self.assertTrue(report["ok"])

    def test_figure_detection_requires_exact_id_and_nonempty_source(self):
        from tasks.settings_obedience_artifacts import delivered_asset_ids_from_html

        figures, _tables = delivered_asset_ids_from_html(
            '<img data-sunairum-figure-id="fig-right" src="figure.png">'
            '<img data-sunairum-figure-id="fig-empty" src="">'
        )
        self.assertEqual({"fig-right"}, figures)


if __name__ == "__main__":
    unittest.main()


class LanguageObedienceTests(unittest.TestCase):
    """The confirmed deck language is a setting, and it must be verified.

    A slide in the wrong language passes every geometry and fidelity gate: it is
    laid out perfectly, just unreadable to the audience the brief names. The
    reported case was a Turkish deck whose cover kept the paper's English title.
    """

    def _project(self, root, slides):
        html = Path(root) / "html_output"
        html.mkdir(parents=True, exist_ok=True)
        for index, text in enumerate(slides, 1):
            (html / f"slide_{index:02d}.html").write_text(
                f"<html><body><h1>{text}</h1></body></html>", encoding="utf-8"
            )
        return root

    def _plan(self, root, cover_content):
        validation = Path(root) / "validation"
        validation.mkdir(parents=True, exist_ok=True)
        (validation / "grounded_plan.json").write_text(
            json.dumps({
                "slides": [{
                    "visual_plan": {"archetype": "hero"},
                    "content": cover_content,
                }]
            }),
            encoding="utf-8",
        )

    def test_english_copy_the_deck_wrote_itself_is_reported(self):
        from tasks.settings_obedience_artifacts import language_obedience

        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp, [
                # Not quoted from anywhere: the deck composed this itself.
                "This slide explains the retrieval step and the scoring rule for each candidate",
                "VRPTW’de düşük toplam mesafe, sürücüler arasında dengeli iş yükü "
                "anlamına gelmez ve bu yüzden maliyet ile denge birlikte ölçülür",
                "HERO, aday konumlarını seçme ile seçilen konumları puanlama işlerini "
                "birbirinden ayırır ve bu ayrım için ortak bir özellik uzayı kullanır",
            ])
            report = language_obedience(tmp, "tr")
            self.assertFalse(report["ok"])
            self.assertEqual(len(report["off_language_slides"]), 1)
            finding = report["off_language_slides"][0]
            self.assertEqual(finding["slide"], "slide_01")
            self.assertEqual(finding["detected"], "en")

    def test_the_papers_own_title_is_quoted_not_translated(self):
        """A published title is how the work is cited and found.

        Translating it produces a title that exists nowhere, so the cover keeps
        the source's language — and this check must not report it, or the reader
        learns to ignore the check.
        """
        from tasks.settings_obedience_artifacts import language_obedience

        title = "HNSW Guided Large Neighborhood Search for Equitable Vehicle Routing"
        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp, [
                title,
                "VRPTW’de düşük toplam mesafe, sürücüler arasında dengeli iş yükü "
                "anlamına gelmez ve bu yüzden maliyet ile denge birlikte ölçülür",
            ])
            self._plan(tmp, {
                "TITLE": title,
                "AFFILIATIONS": "Department of Computer Engineering, "
                                "Süleyman Demirel University, Isparta, Türkiye",
            })
            report = language_obedience(tmp, "tr")
            self.assertTrue(report["ok"], report)

    def test_an_unquoted_english_line_beside_the_title_is_still_reported(self):
        """The exemption is for quotations only, not for the cover slide."""
        from tasks.settings_obedience_artifacts import language_obedience

        title = "HNSW Guided Large Neighborhood Search for Equitable Vehicle Routing"
        with tempfile.TemporaryDirectory() as tmp:
            html = Path(tmp) / "html_output"
            html.mkdir(parents=True, exist_ok=True)
            (html / "slide_01.html").write_text(
                f"<html><body><h1>{title}</h1>"
                "<p>An overview of the method and the experiments that follow it</p>"
                "</body></html>",
                encoding="utf-8",
            )
            self._plan(tmp, {"TITLE": title})
            report = language_obedience(tmp, "tr")
            self.assertFalse(report["ok"], report)
            self.assertIn(
                "overview", report["off_language_slides"][0]["sample"].casefold()
            )

    def test_a_turkish_deck_in_turkish_passes(self):
        from tasks.settings_obedience_artifacts import language_obedience

        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp, [
                "Eşitlik duyarlı onarım için HNSW rehberli arama ve bu yaklaşımın "
                "kapsamı ile sınırlılıkları",
                "VRPTW’de düşük toplam mesafe, sürücüler arasında dengeli iş yükü "
                "anlamına gelmez ve bu yüzden maliyet ile denge birlikte ölçülür",
            ])
            report = language_obedience(tmp, "tr")
            self.assertTrue(report["ok"], report)

    def test_technical_english_nouns_do_not_trip_a_turkish_deck(self):
        from tasks.settings_obedience_artifacts import language_obedience

        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp, [
                "HNSW Index ve Feature Encoder bileşenleri için aday erişimi, "
                "route cost ve equity gradient değerleri ile birlikte ölçülür",
                "ALNS Core döngüsünde destroy ve repair operatörleri, HNSW-Guided "
                "Repair Operator ile birlikte bu özellik uzayını kullanır",
            ])
            report = language_obedience(tmp, "tr")
            self.assertTrue(report["ok"], report)

    def test_a_language_we_do_not_profile_is_skipped_not_guessed(self):
        from tasks.settings_obedience_artifacts import language_obedience

        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp, ["hello world"])
            report = language_obedience(tmp, "fi")
            self.assertTrue(report["ok"])
            self.assertEqual(report["skipped"], "language_not_profiled")


class LanguageGateAtAuthoringTime(unittest.TestCase):
    """The deck language is enforced while a retry can still fix the slide.

    Detecting it afterwards is not enough: the cover shipped reading "ACADEMIC
    BLUEPRINT · VEHICLE ROUTING" over Turkish body copy, and by the time the
    obedience report said so the deck was already in the reader's hands.
    """

    TITLE = "HNSW Guided Large Neighborhood Search for Equitable Vehicle Routing"

    def _cover(self, kicker):
        return (
            "<html><body>"
            f"<p class='kicker'>{kicker}</p>"
            f"<h1>{self.TITLE}</h1>"
            "<p>VRPTW icin dusuk toplam mesafe, suruculer arasinda dengeli is "
            "yuku anlamina gelmez ve birlikte olculur</p>"
            "</body></html>"
        )

    def test_author_invented_english_is_a_contract_issue(self):
        from tasks.scene_html_author import off_language_authored_copy

        issues = off_language_authored_copy(
            self._cover("ACADEMIC BLUEPRINT PLUS VEHICLE ROUTING AND CANDIDATE SPACE"),
            "tr",
            quoted=[self.TITLE],
        )
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("off_language_copy", issues[0])
        # The retry needs to know which string to rewrite.
        self.assertIn("ACADEMIC BLUEPRINT", issues[0])

    def test_the_quoted_paper_title_is_not_a_violation(self):
        from tasks.scene_html_author import off_language_authored_copy

        issues = off_language_authored_copy(
            self._cover("ORTAK TEMSIL VE ERISIM ICIN DEGERLENDIRME"),
            "tr",
            quoted=[self.TITLE],
        )
        self.assertEqual(issues, [], issues)

    def test_the_gate_and_the_report_share_one_implementation(self):
        """They must agree, or the report contradicts the gate meant to prevent it."""
        from tasks.scene_html_author import off_language_authored_copy
        from tasks.settings_obedience_artifacts import off_language_fragments

        html = self._cover("ACADEMIC BLUEPRINT PLUS VEHICLE ROUTING AND CANDIDATE SPACE")
        gate = off_language_authored_copy(html, "tr", quoted=[self.TITLE])
        report = off_language_fragments(html, "tr", quoted=[self.TITLE])
        self.assertEqual(len(gate), len(report))
        self.assertIn(str(report[0]["sample"])[:40], gate[0])

    def test_an_english_deck_is_not_flagged(self):
        from tasks.scene_html_author import off_language_authored_copy

        self.assertEqual(
            off_language_authored_copy(
                self._cover("ACADEMIC BLUEPRINT PLUS VEHICLE ROUTING"),
                "en",
                quoted=[self.TITLE],
            ),
            [],
        )
