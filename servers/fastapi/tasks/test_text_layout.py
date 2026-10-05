"""A slot is a box, and text is broken to fit it before it reaches the slide."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sunairum_scripts",
))

from tasks.layout_geometry import text_width_px  # noqa: E402
from tasks.text_layout import (  # noqa: E402
    layout_block,
    line_height_for,
    max_lines_in,
    slot_budget,
    tspan_markup,
    wrap,
)

BODY = (
    "The Transformer follows this overall architecture using stacked self-attention "
    "and point-wise, fully connected layers for both the encoder and decoder."
)


class Wrapping(unittest.TestCase):
    def test_every_line_measures_within_the_width(self):
        width = 420.0
        lines = wrap(BODY, width, 20.0, "Montserrat", False)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(
                text_width_px(line, 20.0, 0.0, False, "Montserrat"), width,
                f"line overruns its box: {line!r}",
            )

    def test_no_word_is_lost_or_duplicated(self):
        lines = wrap(BODY, 300.0, 18.0, "Montserrat", False)
        self.assertEqual(" ".join(lines).split(), BODY.split())

    def test_a_narrower_box_produces_more_lines(self):
        wide = wrap(BODY, 600.0, 20.0, "Montserrat", False)
        narrow = wrap(BODY, 300.0, 20.0, "Montserrat", False)
        self.assertGreater(len(narrow), len(wide))

    def test_explicit_newlines_are_honoured(self):
        lines = wrap("First line\nSecond line", 800.0, 20.0, "Montserrat", False)
        self.assertEqual(lines, ["First line", "Second line"])

    def test_a_word_wider_than_the_box_is_reported_whole(self):
        word = "Unreasonablylongheadlinewordwithnobreaks"
        lines = wrap(word, 120.0, 32.0, "Montserrat", False)
        self.assertEqual(lines, [word])
        self.assertGreater(
            text_width_px(lines[0], 32.0, 0.0, False, "Montserrat"),
            120.0,
        )

    def test_empty_text_produces_no_lines(self):
        self.assertEqual(wrap("", 400.0, 20.0, "Montserrat"), [])
        self.assertEqual(wrap("   ", 400.0, 20.0, "Montserrat"), [])

    def test_a_condensed_face_fits_more_words_per_line(self):
        montserrat = wrap(BODY, 400.0, 24.0, "Montserrat", False)
        anton = wrap(BODY, 400.0, 24.0, "Anton", False)
        self.assertLess(len(anton), len(montserrat))


class VerticalBudget(unittest.TestCase):
    """Wrapping solves width; height is the failure this has to catch."""

    def test_a_slot_one_line_tall_holds_one_line(self):
        self.assertEqual(max_lines_in(40.0, 40.0, 48.0), 1)

    def test_line_capacity_grows_with_height(self):
        self.assertEqual(max_lines_in(40.0 + 48.0 * 2, 40.0, 48.0), 3)

    def test_a_zero_height_slot_still_holds_a_line(self):
        self.assertEqual(max_lines_in(0.0, 20.0, 24.0), 1)

    def test_copy_that_wraps_past_the_box_reports_overflow(self):
        layout = layout_block(BODY, (0.0, 0.0, 300.0, 60.0), 20.0, "Montserrat")
        self.assertFalse(layout.fits)
        self.assertGreater(layout.overflow_lines, 0)

    def test_copy_that_fits_reports_no_overflow(self):
        layout = layout_block("Short title", (0.0, 0.0, 600.0, 80.0), 32.0, "Montserrat")
        self.assertTrue(layout.fits)
        self.assertEqual(layout.overflow_lines, 0)

    def test_height_is_measured_from_the_first_baseline(self):
        layout = layout_block(BODY, (0.0, 0.0, 300.0, 400.0), 20.0, "Montserrat")
        expected = layout.font_size + layout.line_height * (len(layout.lines) - 1)
        self.assertAlmostEqual(layout.height, expected, places=6)


class LineHeight(unittest.TestCase):
    def test_line_height_comes_from_the_font(self):
        montserrat = line_height_for(40.0, "Montserrat")
        self.assertGreater(montserrat, 40.0)
        self.assertLess(montserrat, 40.0 * 1.6)

    def test_an_explicit_factor_wins(self):
        self.assertAlmostEqual(line_height_for(40.0, "Montserrat", factor=1.3), 52.0, places=6)

    def test_an_absurd_factor_is_clamped(self):
        self.assertLessEqual(line_height_for(40.0, "Montserrat", factor=9.0), 40.0 * 1.6)
        self.assertGreaterEqual(line_height_for(40.0, "Montserrat", factor=0.1), 40.0 * 1.05)


class Budgets(unittest.TestCase):
    """The budget the copy editor is given must be the budget the wrapper enforces."""

    def test_text_written_to_budget_fits_the_slot(self):
        for width, height, size in (
            (400.0, 200.0, 18.0),
            (720.0, 120.0, 24.0),
            (300.0, 300.0, 14.0),
            (1120.0, 90.0, 32.0),
        ):
            with self.subTest(width=width, size=size):
                box = (0.0, 0.0, width, height)
                budget = slot_budget(box, size, "Montserrat")
                self.assertGreater(budget.max_chars, 0)
                prose = ("the quick brown fox jumps over a lazy dog " * 40)[: budget.max_chars]
                layout = layout_block(prose, box, size, "Montserrat")
                self.assertTrue(
                    layout.fits,
                    f"budget promised {budget.max_chars} chars but "
                    f"{len(layout.lines)} lines overflowed {budget.max_lines}",
                )

    def test_a_condensed_face_reports_a_larger_budget(self):
        box = (0.0, 0.0, 600.0, 200.0)
        self.assertGreater(
            slot_budget(box, 24.0, "Anton").chars_per_line,
            slot_budget(box, 24.0, "Montserrat").chars_per_line,
        )


class TspanRendering(unittest.TestCase):
    def test_the_first_row_keeps_the_designed_baseline(self):
        layout = layout_block(BODY, (40.0, 0.0, 300.0, 400.0), 20.0, "Montserrat")
        markup = tspan_markup(layout, 40.0)
        self.assertIn('<tspan x="40" dy="0">', markup)
        self.assertEqual(markup.count("<tspan"), len(layout.lines))

    def test_later_rows_advance_by_the_measured_line_height(self):
        layout = layout_block(BODY, (40.0, 0.0, 300.0, 400.0), 20.0, "Montserrat")
        markup = tspan_markup(layout, 40.0)
        self.assertIn(f'dy="{layout.line_height:g}"', markup)

    def test_markup_is_escaped(self):
        layout = layout_block("Bell & Howell <ok>", (0.0, 0.0, 900.0, 100.0), 20.0, "Montserrat")
        markup = tspan_markup(layout, 0.0)
        self.assertIn("&amp;", markup)
        self.assertIn("&lt;ok&gt;", markup)
        self.assertNotIn("<ok>", markup)


if __name__ == "__main__":
    unittest.main()
