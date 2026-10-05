# L1 — Layout-faithful text (PowerPoint-canonical)

Sunairum fidelity contract for editable PPTX text. Tracker ID: **L1**.

## Laws (export time)

1. **PowerPoint is canonical** (Microsoft PowerPoint on macOS/Windows). LibreOffice is the automated render gate, calibrated against PowerPoint (see [FIDELITY_CALIBRATION.md](./FIDELITY_CALIBRATION.md)).
2. **Geometry is frozen.** Chromium border-box ∩ supported rectangular clip ∩ slide `10in × 5.625in`. Never grow/move a text box to “make text fit.”
3. **No PowerPoint re-wrap for eligible text.** Emit `wrap:none` with Chromium line breaks as `<a:br/>`. Do **not** emit `<a:normAutofit/>` — PowerPoint must not re-solve layout.
4. **Inline flow stays one object.** Adjacent inline spans are rich runs in one semantic shape. Separate painted children use their own measured rect.
5. **Text stays native/editable.** No screenshot fallback for ordinary body/title text.
6. **Font closure is mandatory in strict mode.** Exact face/weight/style must resolve; silent substitution is forbidden. Local convert embeds resolvable deck faces via `embedDeckFonts`.
7. **Post-edit reflow is out of contract.** After a user changes text length, PowerPoint may overflow or reflow. Initial export fidelity remains the law.

## Tolerances

| Metric | Limit |
|--------|--------|
| Geometry (x/y/w/h) vs Chromium | ≤ 1 CSS source pixel after EMU conversion |
| Bounded font shrink (frozen path) | ≤ 8% of source font size, reported |
| Overlap of distinct text hosts | Forbidden |
| Slide overflow (`x+w` / `y+h` past slide) | Forbidden |
| Pixel antialiasing Chromium vs PPT | Not asserted (below calibration noise floor) |
| Visual SSIM (HTML preview vs LO raster) | ≥ calibrated floor (default 0.92) |

## Supported text matrix (frozen path)

Eligible when all of:

- Horizontal writing mode (`horizontal-tb` / empty)
- No skew/perspective/nonuniform scale transform (rotation alone is OK)
- Clip ancestors are axis-aligned rectangles (optional corner radius on the host shape itself)
- Base direction LTR (RTL/bidi classified unsupported until dedicated support)
- Not a formula/table/chart/math host, not a pill chip that uses the pill layout path
- Line/run mapping reconstructed from Chromium equals normalized DOM text

## Unsupported (structured reason; no silent raster)

- `vertical-rl` / `vertical-lr` / sideways writing modes
- RTL / `unicode-bidi` isolation requiring paragraph RTL ownership
- Non-rectangular clip intersecting text ink
- Unsupported transform matrices
- Ambiguous line↔run mapping (ligature/bidi/pseudo failure)

## Mode

| Env / option | Behavior |
|--------------|----------|
| unset / `layoutFaithful: true` | Frozen emission for eligible text; always enabled |
| `layoutFaithful: 'strict'` | Frozen + hard fail on unresolved fonts / unsupported mandatory text |
| `DECKHTML_LAYOUT_FAITHFUL=strict` | Strict frozen path |

## Stop conditions (closed-loop)

Production default is on when:

1. L1 multi-line text emits `wrap="none"` + `<a:br/>` and **no** `<a:normAutofit/>`.
2. Deck fonts are present under `ppt/fonts/*.fntdata` + `p:embeddedFontLst`.
3. `pptx_visual_verify` semantic and raster gates pass the current corpus against HTML previews; release is blocked on failure.
