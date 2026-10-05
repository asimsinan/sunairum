"""Deck furniture LLM normalize/apply + figure placement already-check."""

from __future__ import annotations

import re
import unittest

from tasks.deck_furniture import (
    affiliation_from_instructions,
    apply_furniture_to_title_html,
    apply_furniture_to_title_svg,
    extract_deck_furniture,
    furniture_for_title_reinject,
    merge_furniture_into_identity,
    normalize_furniture,
    resolve_deck_furniture,
)


class DeckFurnitureTests(unittest.TestCase):
    def test_normalize_keeps_known_fields_only(self):
        self.assertEqual(
            normalize_furniture(
                {
                    "presenter": "  Asım Sinan Yüksel ",
                    "affiliation": "SDÜ Computer Engineering",
                    "tone": "academic",
                    "extra": "ignore",
                }
            ),
            {
                "presenter": "Asım Sinan Yüksel",
                "affiliation": "SDÜ Computer Engineering",
            },
        )

    def test_affiliation_from_instructions_keeps_full_ieee_blob(self):
        instructions = (
            "Use suitable tone for IEEE conference. The presenter is "
            "Assoc. Prof. Dr. Asım Sinan Yüksel. Affiliation: Süleyman Demirel "
            "University Department of Computer Engineering, Isparta, Türkiye, "
            "32200, Tel: +905433608390"
        )
        aff = affiliation_from_instructions(instructions)
        self.assertIn("Department of Computer Engineering", aff)
        self.assertIn("Isparta", aff)
        self.assertIn("Tel: +905433608390", aff)
        short = furniture_for_title_reinject(
            {"presenter": "Assoc. Prof. Dr. Asım Sinan Yüksel",
             "affiliation": "Süleyman Demirel University"},
            instructions,
        )
        self.assertEqual(aff, short["affiliation"])
        self.assertIn("Tel:", short["affiliation"])

    def test_reinject_prefers_raw_affiliation_over_short_authored(self):
        affiliation = (
            "Süleyman Demirel University Department of Computer Engineering, "
            "Isparta, Türkiye, 32200, Tel: +905433608390"
        )
        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="78" y="616" font-size="15">'
            "<tspan>Assoc. Prof. Dr. Asım Sinan Yüksel * "
            "Süleyman Demirel University</tspan></text>"
            '<text data-sunairum-page-number="1" x="1220" y="698">01 / 14</text>'
            "</svg>"
        )
        out = apply_furniture_to_title_svg(
            svg,
            {
                "presenter": "Assoc. Prof. Dr. Asım Sinan Yüksel",
                "affiliation": affiliation,
            },
        )
        self.assertIn("Tel: +905433608390", out)
        self.assertIn("Department of Computer Engineering", out)
        self.assertIn("Assoc. Prof. Dr. Asım Sinan Yüksel", out)
        # Short university-only star suffix removed from presenter line.
        self.assertNotIn(
            "Asım Sinan Yüksel * Süleyman Demirel University",
            re.sub(r"<[^>]+>", "", out),
        )

    def test_extract_uses_llm_not_regex(self):
        calls: list[tuple[str, str]] = []

        def fake_json(system: str, prompt: str) -> dict:
            calls.append((system, prompt))
            self.assertIn("sunucu", prompt.casefold())
            return {
                "presenter": "Asım Sinan Yüksel",
                "affiliation": "SDÜ Computer Engineering",
                "date": "",
                "occasion": "",
            }

        furniture = extract_deck_furniture(
            "akademik ton kullan; sunucu Asım Sinan Yüksel, kurum SDÜ Computer Engineering",
            call_json=fake_json,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(furniture.get("presenter"), "Asım Sinan Yüksel")
        self.assertEqual(furniture.get("affiliation"), "SDÜ Computer Engineering")

    def test_extract_returns_empty_when_llm_fails(self):
        def boom(_system: str, _prompt: str) -> dict:
            raise RuntimeError("offline")

        self.assertEqual(
            extract_deck_furniture("Presenter is Ada", call_json=boom),
            {},
        )

    def test_resolve_uses_cache_without_calling_llm(self):
        called = {"n": 0}

        def fake_json(_system: str, _prompt: str) -> dict:
            called["n"] += 1
            return {"presenter": "Should Not Run"}

        data = {
            "additional_instructions": "sunucu Someone",
            "deck_furniture": {"presenter": "Cached Name"},
        }
        furniture = resolve_deck_furniture(data, call_json=fake_json)
        self.assertEqual(furniture, {"presenter": "Cached Name"})
        self.assertEqual(called["n"], 0)

    def test_merge_overrides_anonymous(self):
        identity = {
            "paper_title": "A Paper",
            "authors": "Anonymous Author(s)",
            "affiliations": "Affiliation withheld for double-anonymous review",
        }
        furniture = {"presenter": "Assoc. Prof. Dr. Asım Sinan Yüksel"}
        merged = merge_furniture_into_identity(identity, furniture)
        self.assertEqual(merged["authors"], "Assoc. Prof. Dr. Asım Sinan Yüksel")

    def test_apply_furniture_rewrites_title_svg(self):
        svg = (
            '<svg><text x="297" y="553">Anonymous Author(s)</text>'
            "<text>Affiliation withheld for double-anonymous review</text></svg>"
        )
        out = apply_furniture_to_title_svg(
            svg,
            {
                "presenter": "Assoc. Prof. Dr. Asım Sinan Yüksel",
                "affiliation": "Süleyman Demirel University",
            },
        )
        self.assertIn("Assoc. Prof. Dr. Asım Sinan Yüksel", out)
        self.assertNotIn("Anonymous Author(s)", out)
        self.assertIn("Süleyman Demirel University", out)
        # Centered / mid-canvas bylines stay put — only rail collisions move.

    def test_apply_furniture_injects_presenter_above_affiliation(self):
        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="60" y="200" font-size="40">Some Title</text>'
            '<text x="60" y="553">SDÜ Computer Engineering</text>'
            '<text x="1220" y="698">01 / 14</text>'
            "</svg>"
        )
        out = apply_furniture_to_title_svg(
            svg,
            {
                "presenter": "Asım Sinan Yüksel",
                "affiliation": "SDÜ Computer Engineering",
            },
        )
        self.assertIn("Asım Sinan Yüksel", out)
        self.assertLess(out.index("Asım Sinan Yüksel"), out.index("SDÜ Computer Engineering"))

    def test_apply_furniture_skips_reinject_when_affiliation_soft_wrapped(self):
        """Resume used to re-inject because tspans broke raw-string membership."""
        affiliation = (
            "Süleyman Demirel University Department of Computer Engineering, "
            "Isparta, Türkiye, 32200, Tel: +905433608390"
        )
        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="640" y="256" text-anchor="middle" font-size="52">'
            "HNSW Guided Large Neighborhood Search</text>"
            '<text x="640" y="486" text-anchor="middle" font-size="24">'
            "Assoc. Prof. Dr. Asım Sinan Yüksel</text>"
            '<text x="100" y="508" font-size="14" fill="#7A8494">'
            '<tspan x="100" dy="0">Süleyman Demirel University Department of '
            "Computer Engineering, Isparta, Türkiye, 32200,</tspan>"
            '<tspan x="100" dy="18">Tel: +905433608390</tspan></text>'
            "</svg>"
        )
        out = apply_furniture_to_title_svg(
            svg,
            {
                "presenter": "Assoc. Prof. Dr. Asım Sinan Yüksel",
                "affiliation": affiliation,
            },
        )
        self.assertEqual(out.count("Tel: +905433608390"), 1)
        self.assertEqual(out.count("Süleyman Demirel University"), 1)

    def test_apply_furniture_dedupes_injected_copy_beside_authored_byline(self):
        affiliation = (
            "Süleyman Demirel University Department of Computer Engineering, "
            "Isparta, Türkiye, 32200, Tel: +905433608390"
        )
        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="640" y="486" text-anchor="middle" font-size="24">'
            "Assoc. Prof. Dr. Asım Sinan Yüksel</text>"
            '<text x="100" y="508" font-size="14" font-weight="500" fill="#7A8494">'
            '<tspan x="100" dy="0">Süleyman Demirel University Department of '
            "Computer Engineering, Isparta, Türkiye, 32200,</tspan>"
            '<tspan x="100" dy="18">Tel: +905433608390</tspan></text>'
            '<text x="640" y="550" text-anchor="middle" font-size="17" fill="#475569">'
            "Süleyman Demirel University Department of Computer Engineering</text>"
            '<text x="640" y="574" text-anchor="middle" font-size="17" fill="#475569">'
            "Isparta, Türkiye, 32200 * Tel: +905433608390</text>"
            "</svg>"
        )
        out = apply_furniture_to_title_svg(
            svg,
            {
                "presenter": "Assoc. Prof. Dr. Asım Sinan Yüksel",
                "affiliation": affiliation,
            },
        )
        self.assertNotIn("#7A8494", out)
        self.assertIn('text-anchor="middle"', out)
        self.assertIn("Isparta, Türkiye, 32200 * Tel:", out)

    def test_apply_furniture_to_title_html_injects_ieee_byline(self):
        affiliation = (
            "Süleyman Demirel University Department of Computer Engineering, "
            "Isparta, Türkiye, 32200, Tel: +905433608390"
        )
        html = (
            '<section class="slide" style="width:1280px;height:720px;position:relative;">'
            "<h1>HNSW Guided Large Neighborhood Search</h1>"
            "<p>A search framework that connects fast neighborhood discovery.</p>"
            "</section>"
        )
        out = apply_furniture_to_title_html(
            html,
            {
                "presenter": "Assoc. Prof. Dr. Asım Sinan Yüksel",
                "affiliation": affiliation,
            },
        )
        self.assertIn("Assoc. Prof. Dr. Asım Sinan Yüksel", out)
        self.assertIn("Tel: +905433608390", out)
        self.assertIn('data-sunairum-furniture="byline"', out)
        self.assertLess(out.index("Yüksel"), out.index("</section>"))

    def test_apply_furniture_to_title_html_skips_when_complete(self):
        affiliation = (
            "Süleyman Demirel University Department of Computer Engineering, "
            "Isparta, Türkiye, 32200, Tel: +905433608390"
        )
        html = (
            '<section class="slide">'
            f"<div>Assoc. Prof. Dr. Asım Sinan Yüksel</div>"
            f"<div>{affiliation}</div>"
            "</section>"
        )
        out = apply_furniture_to_title_html(
            html,
            {
                "presenter": "Assoc. Prof. Dr. Asım Sinan Yüksel",
                "affiliation": affiliation,
            },
        )
        self.assertEqual(out.count("Tel: +905433608390"), 1)
        self.assertNotIn('data-sunairum-furniture="byline"', out)


class FigureAlreadyPlacedTests(unittest.TestCase):
    def test_slot_attr_alone_is_not_placed(self):
        import re

        figure_id = "pdf-page-4-picture-2"
        dest_name = "pdf_pdf-page-4-picture-2.png"
        svg = (
            f'<g data-sunairum-figure-slot="1" data-sunairum-figure-id="{figure_id}">'
            '<rect width="760" height="465" fill="none"/></g>'
        )
        already = bool(
            re.search(
                rf'<image\b[^>]*\bdata-sunairum-figure-id="{re.escape(figure_id)}"',
                svg,
                flags=re.I,
            )
            or re.search(
                rf'<image\b[^>]*\b(?:href|xlink:href)="[^"]*{re.escape(dest_name)}"',
                svg,
                flags=re.I,
            )
        )
        self.assertFalse(already)

    def test_real_image_counts_as_placed(self):
        import re

        figure_id = "pdf-page-4-picture-2"
        dest_name = "pdf_pdf-page-4-picture-2.png"
        svg = (
            f'<image href="../images/{dest_name}" x="10" y="10" width="100" height="100" '
            f'data-sunairum-figure-id="{figure_id}"/>'
        )
        already = bool(
            re.search(
                rf'<image\b[^>]*\bdata-sunairum-figure-id="{re.escape(figure_id)}"',
                svg,
                flags=re.I,
            )
            or re.search(
                rf'<image\b[^>]*\b(?:href|xlink:href)="[^"]*{re.escape(dest_name)}"',
                svg,
                flags=re.I,
            )
        )
        self.assertTrue(already)


if __name__ == "__main__":
    unittest.main()
