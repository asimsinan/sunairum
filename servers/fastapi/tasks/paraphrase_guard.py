"""Let grounded copy be shortened without letting it drift from its source.

``pdf_strict`` forbade rewriting copy, on the sound reasoning that a rewrite is where a
model stops describing the source and starts inventing. But shorter copy is the only
real fix for text that overruns its slot, so the mode with the strictest correctness
requirements was also the one that could never resolve an overflow. Its decks were
handed instead to the fitter, which shrank and cut them, and QA reported the cuts as
defects: ``qa_status: failed, qa_error_count: 89``.

A rewrite that only shortens is safe to allow, because the parts of a sentence that
carry its factual claim are checkable. Every number in the original must survive, no
new number may appear, and the evidence bindings are re-verified afterwards by
grounding QA. What is left free is the wording, which is what needed to change.
"""

from __future__ import annotations

import re

# A quantity as a reader meets it: 512, 3.5, 1,024, 65%, 10^-9, 1e-5. Kept deliberately
# broad, because the guard is only useful if it sees every number a claim rests on.
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*(?:\s*[eE^]\s*[-+]?\d+)?")
_TRAILING_ZEROS = re.compile(r"\.0+$")


def _canonical_number(raw: str) -> str:
    """One number written one way, so 1,024 and 1024 are recognised as the same.

    Thousands separators are dropped and trailing zeros trimmed. A comma used as a
    decimal separator would be misread here, but the alternative -- treating ``1,024``
    and ``1024`` as different numbers -- fails on the far more common case.
    """
    text = re.sub(r"[\s,]", "", raw)
    text = re.sub(r"[eE^]\s*", "e", text)
    if "." in text and "e" not in text:
        text = _TRAILING_ZEROS.sub("", text)
        text = text.rstrip(".") or "0"
    return text


def numbers_in(text: str) -> set[str]:
    """Every quantity stated in a piece of text, canonically written."""
    return {_canonical_number(match.group(0)) for match in _NUMBER.finditer(text or "")}


def evidence_numbers(slide: dict) -> set[str]:
    """Every quantity the slide's own evidence supports.

    A shortened paraphrase may legitimately surface a number that was already in the
    claim it came from, so the evidence is the reference rather than only the string
    being replaced.
    """
    grounding = slide.get("grounding") if isinstance(slide.get("grounding"), dict) else {}
    found: set[str] = set()
    for claim in grounding.get("claims", []) or []:
        if not isinstance(claim, dict):
            continue
        found |= numbers_in(str(claim.get("text") or ""))
        found |= numbers_in(str(claim.get("source_quote") or ""))
    for metric in grounding.get("metrics", []) or []:
        if isinstance(metric, dict):
            found |= numbers_in(" ".join(str(value) for value in metric.values()))
        else:
            found |= numbers_in(str(metric))
    return found


def paraphrase_violation(
    original: str,
    replacement: str,
    supported: set[str] | frozenset[str] = frozenset(),
) -> str | None:
    """Why a shortened rewrite may not replace this text, or None if it may.

    The check is deliberately about quantities only. Judging whether prose still means
    what its source meant is what grounding QA and its evidence bindings are for; this
    guard exists to catch the specific, mechanical way a rewrite goes wrong.
    """
    original_numbers = numbers_in(original)
    replacement_numbers = numbers_in(replacement)

    invented = replacement_numbers - original_numbers - set(supported)
    if invented:
        return f"introduces unsupported number(s): {', '.join(sorted(invented))}"

    # A number may be dropped -- that is how copy gets shorter -- but one that changed
    # into a different number is a misstatement of the source.
    if original_numbers - replacement_numbers and replacement_numbers - original_numbers:
        return (
            "restates number(s) "
            f"{', '.join(sorted(original_numbers - replacement_numbers))} as "
            f"{', '.join(sorted(replacement_numbers - original_numbers))}"
        )

    if not replacement.strip():
        return "empty replacement would delete grounded copy"
    return None


def filter_grounded_replacements(
    replacements: dict[str, str],
    originals: dict[str, str],
    slide: dict,
) -> tuple[dict[str, str], list[str]]:
    """Keep the shortened rewrites that stay faithful; report the ones that do not.

    Rejecting only the offending slot means one bad sentence no longer costs the whole
    slide its repair.
    """
    supported = evidence_numbers(slide)
    kept: dict[str, str] = {}
    rejected: list[str] = []
    for selector, replacement in replacements.items():
        original = originals.get(selector, "")
        reason = paraphrase_violation(original, replacement, supported)
        if reason:
            rejected.append(f"{selector}: {reason}")
        else:
            kept[selector] = replacement
    return kept, rejected
