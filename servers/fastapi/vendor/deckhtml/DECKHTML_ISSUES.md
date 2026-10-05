# DeckHTML fidelity issues

Tracker for converter bugs found while exporting constrained HTML decks to PPTX.
Upstream: https://github.com/deckflow/deckhtml

## Fixed

| ID | Issue | Fix location |
|----|--------|----------------|
| F1 | Z-order / paint order wrong with global z-index sort | `generator.ts`, `inspector.ts` (`paintOrder`) |
| F2 | Shapes spill past slide (`overflow:hidden` ignored) | `converter.ts` `getBaseProperties` clamp |
| F3 | Formula `object-fit:contain` double-paint / overflow | `converter.ts` letterbox; `image-sizing-xml.ts` |
| F4 | Circle / flex glyph badges left-aligned | `inspector.ts` canvas bake (`flex-icon-badge`) |
| F5 | Complex table chrome vs native editability | Native table + chrome shape; screenshot only if forced raster marker |
| F6 | Title/subtitle under later opaque panels | `utils/occlusion-repair.ts` (opt-in via `repairTextOcclusions`) |
| O1 | Figure doesn’t fit in padded host | `forceObjectFitContain` for figure hosts/ancestors + `object-fit:contain` |
| O2 | Text metrics tighter than HTML (near-collisions) | `converter.ts` line-height 1.2× / multi-line 1.35× + px `lineSpacing` |
| O3 | Non-badge flex-centered icons drift | Extended flex icon canvas bake (≤64px, FA, rounded square) |
| O4 | Native tables lose CSS chrome / stretched rows | Chrome shape + native table; clamp inflated `rowH`; host `flex:none` |
| O4b | Table chrome missed HTML rounded card | Full-host plate; true CSS radius; outer shadow; corner chips clip native table |
| O4c | Large tables overflow host/slide | Clamp to `[data-pptx=table]` host; scale `rowH` + fonts; slide-edge clamp |
| O4d | Table cells glued / wrong fonts | Capture CSS padding → `tcPr` mar*; slide-space font pt; stop forcing mar=0 |
| O4e | box-shadow parse dropped card elevation | Multi-layer / unitless 0 / optional spread in `parseBoxShadowParts` |
| O4f | Overflow tables still don’t fit card | Uniform host-fit: `rowH` + fonts + margins × s; renormalize to hostH |
| O5 | Flex/grid empty wrapper mis-emission | Skip transparent flex/grid wrappers with single text child |
| O6 | Formulas are PNG, not editable | MathML inject + MathML→OMML |
| O6b | `\hat{}` accents float too high (`limUpp` not `acc`) | `normalizeMoverDotAccentForOmml` + `rewriteLimUppAccentsToOmmlAcc` |
| O6c | Formula too small vs plate | Layout host=`[data-pptx=formula]`; scale `sz` from host height (no ×0.77 dampen) |
| O7 | Charts not native editable | `data-chart-payload` → pptxgen `addChart` |
| O8 | Fidelity suppressions (font ×0.922, tracking ×1.35, effect caps, occlusion nudge) | Uncapped in `style.ts` / `converter.ts`; occlusion opt-in default off |
| O9 | Outline / flex-item chips: text wider than pill border (HTML≠PPT) | `isInlinePillBox` covers outline+compact flex chips; slide-space insets; spatial pill font; `fitPillFontSizeToBox`; hollow fill |
| O10 | space-between chip: text shifts left of outline (`algn=r`) | Do not stamp/apply `flexItemTextAlign` on bordered/filled boxes; pills force center |
| O11 | Multi-line body clips card bottom (lineSpacing taller than box) | `pxToSlidePointsY` for px line-height; clamp N×spcPts to content box height |
| O12 | Filled chips look too tight (padding collapsed) | `layoutPillBoxForText`: grow box before shrink font; keep vertical padding air |
| O13 | `<br>` callouts spill below box (extra PPT wraps) | Exclude multi-line from pill/`wrap:none`; `fitTextBoxToIntentionalLines` widens/tallens |
| O14 | Short flex chips (HNSW/LNS, w/h&lt;2.2) missed pill path | `isInlinePillBox` compact ≤56×220 path (flex/block chips) |
| O15 | Chip grow overlapped flex-row neighbors | `layoutPillBoxForText` sibling bounds + `beginSlide` HTML peers |
| O16 | Negative `letter-spacing` became positive tracking (title wrap) | `parseLetterSpacing` preserves CSS sign for OOXML `spc` |
| O18 | Wrapping titles grow into right-column panels | `fitWrappedTextBox` column walls; prefer shrink |
| O19 | Unicode flex badges empty (Arial `fillText`) | Ink check + symbol fonts + element screenshot |
| O20 | Parent `overflow:hidden` ignored for text | `overflowClipRect` ∩ `getBaseProperties` |
| O21 | CSS border triangles dropped | Screenshot 0-size chevrons |
| O22 | Title underline / accent bar through serif descenders (q/g) | `converter.ts`: seed `textBands` from HTML; 12px descender clear; thin bottom-border margin + decoration offset |
| O23 | Callout text drifts left of fill / through left accent bar | L1 freezes rounded-box fit; `preferGrowRight` for left-border; border decorations use emitted box |
| O24 | Equation (esp. fractions) overflows formula plate | `fitMathFontSizePx` by fraction depth + padding air; plate margins on OMML box |
| O25 | Content drift + page number collision with bottom-right callouts | HTML `_html_page_number_inset` lifts/shifts `n/N`; deckhtml `chromeBands` + `clampBoxAwayFromChrome` |
| O26 | VT/\x0b glues words (`Inserthere`); short chips wrap awkwardly | `sanitizeTextForXml` → space; short labels stay pill+grow; HTML `sanitize_html_control_chars` |
| O27 | In-card charts overlap body text; Cost/CV mixed scale hides CV | `clampChartAwayFromTextBands`; `prepareChartPayload` dual-axis; `showValue`; HTML mixed-scale preview |

## Systemic (L1)

| ID | Issue | Fix location |
|----|--------|----------------|
| L1 | PPT re-wrap / box grow / split inline spans cause drift | `layout-faithful.ts`, inspector line boxes, frozen emission (`wrap:none` + Chromium `<a:br/>`, **no** `normAutofit`). See [LAYOUT_FAITHFUL.md](./LAYOUT_FAITHFUL.md). |
| L2 | Font substitution reflows frozen boxes | `deck-font-embedder.ts` (`embedDeckFonts`) + local `--embed-fonts` unlocked |
| L3 | No HTML↔PPTX visual feedback loop | `pptx_visual_verify.py` + `.shape-map.json` + [FIDELITY_CALIBRATION.md](./FIDELITY_CALIBRATION.md) |

## Notes

- Formula path: TeX → MathJax `SerializedMmlVisitor` MathML → HTML `<math>` host → deckhtml OMML. No SVG/PNG primary path.
- Charts: attach `data-chart-payload` when filling chart hosts; preview bars use `data-pptx-kind="ignore"`.
  Mixed Cost/CV scales use dual-axis in PPTX (`prepareChartPayload`); HTML preview uses independent bar weight + labels.
- Tables: prefer native cells; force raster only when chrome cannot be approximated.

## Rebuild

```bash
cd servers/fastapi/vendor/deckhtml && npm run build
# then re-convert html_output → exports/presentation.pptx
```
