# Fidelity calibration — LibreOffice gate vs PowerPoint canonical

Closed-loop visual verify rasterizes the immutable released `presentation.pptx` with
**LibreOffice Impress headless** and diffs against Chromium HTML previews.
PowerPoint on macOS/Windows remains the **canonical** visual target; LibreOffice
is the automated gate everywhere (CI, Docker, local).

## Noise floor (defaults)

| Metric | Default | Env override |
|--------|---------|--------------|
| SSIM (grayscale, global) | **0.92** | `PPTX_FIDELITY_SSIM_FLOOR` |
| Mean absolute error (0–255) | **18.0** | `PPTX_FIDELITY_MAE_CEIL` |

These values absorb:

- LibreOffice vs PowerPoint antialiasing / ClearType differences
- Sub-pixel glyph hinting
- JPEG/PNG resampling from PDF at 192 dpi → 1280×720

They do **not** absorb font substitution, text reflow, or shape overlay —
those drop SSIM well below 0.92 and MAE above 18.

### Historical baseline (proj_3bhlq, 2026-08-14)

After embedDeckFonts + L1 `wrap:none`, slide_01 HTML preview vs LibreOffice
PPTX raster (1280×720): **SSIM ≈ 0.63, MAE ≈ 11**. MAE already clears the
ceil; SSIM is below the aspirational 0.92 floor — expected while remaining
editable-conversion gaps (chrome, charts, LO≠Chromium paint) are open. The
This baseline predates the Scene-v2 semantic geometry gate and is retained only
as calibration history. Current releases fail closed on semantic or raster drift.

## Calibrate on this Mac (one-time)

1. Build a known-good PPTX from a corpus deck (`html_output/` → deckhtml).
2. Export slide PNGs from **Microsoft PowerPoint** (File → Export → PNG, or
   AppleScript/Automator) into `/tmp/ppt-rasters/slide-N.png` at 1280×720.
3. Raster the same PPTX with LibreOffice:

```bash
cd servers/fastapi
python - <<'PY'
from pathlib import Path
from tasks.pptx_visual_verify import rasterize_pptx_slides, compare_slide_pair, ssim_grayscale, mean_absolute_error
from PIL import Image
import numpy as np

pptx = Path("storage/.../exports/releases/<release-id>/presentation.pptx")
lo_dir = Path("/tmp/lo-rasters")
pages = rasterize_pptx_slides(pptx, lo_dir, dpi=96)
ppt_dir = Path("/tmp/ppt-rasters")
scores = []
for i, lo in enumerate(pages):
    ppt = ppt_dir / f"slide-{i+1}.png"
    if not ppt.is_file():
        continue
    a = np.asarray(Image.open(lo).convert("RGB").resize((1280, 720)))
    b = np.asarray(Image.open(ppt).convert("RGB").resize((1280, 720)))
    scores.append((ssim_grayscale(a, b), mean_absolute_error(a, b)))
print(scores)
print("min_ssim", min(s for s,_ in scores), "max_mae", max(m for _,m in scores))
PY
```

4. Set the floor to **min_ssim − 0.02** (margin) and MAE ceil to
   **max_mae + 2**, then export:

```bash
export PPTX_FIDELITY_SSIM_FLOOR=0.90
export PPTX_FIDELITY_MAE_CEIL=20
```

Update the defaults in this file and in `tasks/pptx_visual_verify.py` once
the corpus is measured.

## Gate contract

- Every production release requires HTML preview PNGs.
- Every Scene region must have a matching named PPTX shape within tolerance.
- Semantic or raster failure blocks publication; there is no warn-only or repair-retry mode.
- `fidelity_verify=False` exists only as an explicit isolated-test hook.

## Artifacts

- `exports/releases/<release-id>/presentation.pptx.shape-map.json` — HTML AABB → PPTX inches
- `exports/fidelity_report.json` — per-slide SSIM/MAE + attributed regions
