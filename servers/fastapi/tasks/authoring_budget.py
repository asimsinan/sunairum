"""Shared LLM call ceiling across content + aesthetic + storyboard agents."""

from __future__ import annotations

import os
import threading
from typing import Any, Callable


def _default_limit() -> int:
    outline = int(os.environ.get("OUTLINE_MODEL_CALL_BUDGET", "8"))
    return int(os.environ.get("AUTHORING_MODEL_CALL_BUDGET", str(outline)))


class AuthoringBudget:
    """One counter for all authoring-stage model calls in a run."""

    def __init__(self, limit: int | None = None) -> None:
        self.limit = int(limit if limit is not None else _default_limit())
        self.calls_spent = 0
        self.errors: list[str] = []
        self._lock = threading.Lock()

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self.limit - self.calls_spent)

    @property
    def exhausted(self) -> bool:
        with self._lock:
            return self.calls_spent >= self.limit

    def wrap(self, call_json: Callable[..., Any]) -> Callable[..., Any]:
        budget = self

        def _wrapped(instruction: str, prompt: str, *args: Any, **kwargs: Any) -> Any:
            with budget._lock:
                if budget.calls_spent >= budget.limit:
                    budget.errors.append(
                        f"authoring model-call budget exhausted ({budget.limit})"
                    )
                    raise RuntimeError(budget.errors[-1])
                budget.calls_spent += 1
                call_n = budget.calls_spent
            try:
                return call_json(instruction, prompt, *args, **kwargs)
            except Exception as error:
                with budget._lock:
                    budget.errors.append(f"authoring call {call_n} failed: {error}")
                raise

        return _wrapped
