#!/usr/bin/env python3
"""One-time LibreOffice ↔ PowerPoint calibration helper.

Usage (after exporting PowerPoint PNGs for the same PPTX):

  python scripts/calibrate_pptx_fidelity.py \\
    --pptx path/to/presentation.pptx \\
    --ppt-rasters /tmp/ppt-rasters \\
    --out /tmp/calibration.json

See vendor/deckhtml/FIDELITY_CALIBRATION.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--ppt-rasters", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=Path("fidelity_calibration.json"))
    parser.add_argument("--dpi", type=int, default=96)
    args = parser.parse_args()

    # Allow running from servers/fastapi/
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from PIL import Image
    import numpy as np
    from tasks.pptx_visual_verify import (
        mean_absolute_error,
        rasterize_pptx_slides,
        ssim_grayscale,
    )

    import tempfile

    with tempfile.TemporaryDirectory(prefix="lo-cal-") as tmp:
        lo_pages = rasterize_pptx_slides(args.pptx, Path(tmp), dpi=args.dpi)

    scores = []
    for i, lo in enumerate(lo_pages):
        candidates = [
            args.ppt_rasters / f"slide-{i + 1}.png",
            args.ppt_rasters / f"slide_{i + 1:02d}.png",
            args.ppt_rasters / f"Slide{i + 1}.png",
        ]
        ppt = next((p for p in candidates if p.is_file()), None)
        if ppt is None:
            continue
        a = np.asarray(Image.open(lo).convert("RGB").resize((1280, 720)))
        b = np.asarray(Image.open(ppt).convert("RGB").resize((1280, 720)))
        scores.append(
            {
                "index": i,
                "lo": str(lo),
                "ppt": str(ppt),
                "ssim": round(ssim_grayscale(a, b), 5),
                "mae": round(mean_absolute_error(a, b), 3),
            }
        )

    if not scores:
        print("No overlapping LO/PPT rasters found", file=sys.stderr)
        return 1

    min_ssim = min(s["ssim"] for s in scores)
    max_mae = max(s["mae"] for s in scores)
    result = {
        "slides": scores,
        "min_ssim": min_ssim,
        "max_mae": max_mae,
        "recommended_ssim_floor": round(max(0.5, min_ssim - 0.02), 3),
        "recommended_mae_ceil": round(max_mae + 2.0, 2),
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
