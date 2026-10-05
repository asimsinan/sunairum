"""Timing contract shared by the API and the worker.

The API decides a run is dead when its status file goes quiet; the worker decides
how long a phase may hold that file. Those two numbers only make sense relative to
each other, and when they were defined separately they drifted into being equal --
so a repair phase that used its whole budget was reported to the user as
"exceeded the operation deadline" while the worker was still working.

This module holds no state and imports nothing, so both sides can read it.
"""

from __future__ import annotations

import os

# The worker's longest single silent phase: the final repair pass.
FINAL_REPAIR_TIMEOUT_SECONDS = int(os.environ.get("FINAL_REPAIR_TIMEOUT_SECONDS", "900"))

# Margin between the worker's longest legitimate silence and the API calling it
# dead. It absorbs a slow compile or a paused container without accusing a healthy
# run of missing a deadline.
STALE_STATUS_MARGIN_SECONDS = int(os.environ.get("STALE_STATUS_MARGIN_SECONDS", "300"))


def stale_status_seconds() -> int:
    """How long a status file may be quiet before its run is presumed dead."""
    return max(15 * 60, FINAL_REPAIR_TIMEOUT_SECONDS + STALE_STATUS_MARGIN_SECONDS)
