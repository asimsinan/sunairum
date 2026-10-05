# Retired SVG freehand + Slide IR stacks

Product path is **Constrained HTML → deckhtml PPTX** only (`html_output/` SoT).

**Do not recreate `svg_output/` or `ir/`.** New runs must not author into those folders.

## Current path

- Flag `html_sot_enabled()` always returns `True` (`tasks/html_flags.py`)
- Job A: `html_pipeline.materialize_html_slide` → `html_output/` + `preview/`
- Job B: `html_to_pptx.finalize_compile_html` via `generator_agent.finalize_compile`
- Editor: `HtmlEditorShell` (HTML `SlideStage`)
- PDF: `html_pdf.pdf_from_html_dir` (hi-DPI); Impress fallback

## Naming

Former `html_ir_*` modules are now `html_pipeline` / `html_flags`.
Marker file: `validation/html_sot.json` (`source_of_truth: html_output`).
Release mode: `html_deckhtml`.

## Do not revive

SVG authoring, Slide IR measure/compile (`slide_ir` / `ir_to_pptx` / `html_measure`),
or IR DeckEditor canvases.
