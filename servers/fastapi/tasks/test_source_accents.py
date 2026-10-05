"""Spacing-accent repair for text extracted from LaTeX-produced PDFs.

Symptom: a title slide reading "S¨ uleyman Demirel University, Isparta,
T¨ urkiye" while other umlauts on the same deck were correct — the correct ones
had been written by the model, the broken ones came straight from the PDF.
"""

from __future__ import annotations

import unittest

from tasks.source_normalizer import _clean_text, _normalize_markdown, _recompose_spacing_accents


class SpacingAccentTests(unittest.TestCase):
    def test_diaeresis_before_its_letter_is_reattached(self):
        self.assertEqual(
            "Computer Engineering, Süleyman Demirel University",
            _recompose_spacing_accents("Computer Engineering, S¨ uleyman Demirel University"),
        )

    def test_capital_letter_and_dot_above_compose(self):
        """"T ¨ UB˙ ITAK" carries a space before the accent and two accent kinds."""
        self.assertEqual(
            "Research Council (TÜBİTAK)",
            _recompose_spacing_accents("Research Council (T ¨ UB˙ ITAK)"),
        )

    def test_accent_attached_without_a_space_still_composes(self):
        self.assertEqual("Türkiye", _recompose_spacing_accents("T¨urkiye"))

    def test_cedilla_and_caron_compose(self):
        self.assertEqual("Çalışma", _recompose_spacing_accents("¸Calışma"))
        self.assertEqual("Škoda", _recompose_spacing_accents("ˇSkoda"))

    def test_markdown_backtick_and_tilde_are_untouched(self):
        """They are excluded: both carry meaning in Markdown and code spans."""
        source = "use `u` for the vector and ~x for the estimate"
        self.assertEqual(source, _recompose_spacing_accents(source))

    def test_accent_that_cannot_compose_is_left_alone(self):
        """A diaeresis that is not an accent for the next letter stays put."""
        source = "the ¨ q symbol"
        self.assertEqual(source, _recompose_spacing_accents(source))

    def test_repair_runs_on_both_normalisation_funnels(self):
        self.assertIn("Türkiye", _clean_text("Isparta, T¨ urkiye"))
        self.assertIn("Süleyman", _normalize_markdown("At S¨ uleyman Demirel University"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
