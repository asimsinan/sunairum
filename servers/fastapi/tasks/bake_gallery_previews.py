#!/usr/bin/env python3
"""Bake examples/*/preview/*.png from svg_final (gallery SoT for zero-SVG home)."""

from __future__ import annotations

import sys

from tasks.template_catalog import bake_all_pack_previews


def main() -> int:
    force = "--force" in sys.argv or "-f" in sys.argv
    stats = bake_all_pack_previews(force=force)
    total = sum(stats.values())
    print(f"baked {len(stats)} packs, {total} slides")
    for tid, count in sorted(stats.items()):
        print(f"  {tid}: {count}")
    return 0 if stats else 1


if __name__ == "__main__":
    raise SystemExit(main())
