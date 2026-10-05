"""LLM copy recovery for Scene Layout v2 after measured fit failures."""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Callable


SYSTEM = """You shorten audience-facing slide copy to fit an existing measured layout.
Return only JSON. Preserve every factual claim, number, symbol, qualification, and conclusion.
Do not add facts, labels, examples, or planning language. Prefer direct wording and remove redundancy.
"""


def _extract_json(value: str) -> dict[str, Any] | None:
    text = str(value or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def recover_scene_copy(
    *,
    slide: dict[str, Any],
    scene: dict[str, Any],
    diagnostics: list[str],
    call_text: Callable[[str, str], str],
) -> dict[str, Any] | None:
    """Return a shortened slide copy variant or ``None`` on unsafe output."""
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    source_cards = slide.get("cards") if isinstance(slide.get("cards"), list) else []
    if len(source_cards) > 8:
        return None
    composition = str(scene.get("composition") or "body")
    body_limit = 120 if composition in {"process", "multi_chart"} else 180
    payload = {
        "title": str(slide.get("title") or content.get("TITLE") or ""),
        "lede": str(
            slide.get("lede")
            or slide.get("subtitle")
            or slide.get("core_message")
            or content.get("SUBTITLE")
            or ""
        ),
        "cards": [
            {
                "title": str(card.get("title") or ""),
                "body": str(card.get("body") or card.get("text") or ""),
            }
            for card in source_cards
            if isinstance(card, dict)
        ],
    }
    prompt = (
        f"Composition: {composition}\n"
        f"Measured failures: {json.dumps(diagnostics, ensure_ascii=False)}\n"
        "Hard budgets: title <= 90 characters; lede <= 180 characters; "
        f"card title <= 48 characters; card body <= {body_limit} characters; "
        "keep the same card count and order.\n"
        "Return {\"title\": string, \"lede\": string, "
        "\"cards\": [{\"title\": string, \"body\": string}]}.\n"
        f"Source copy: {json.dumps(payload, ensure_ascii=False)}"
    )
    recovered = _extract_json(call_text(SYSTEM, prompt))
    if not recovered:
        return None
    title = str(recovered.get("title") or "").strip()
    lede = str(recovered.get("lede") or "").strip()
    cards = recovered.get("cards") if isinstance(recovered.get("cards"), list) else []
    if not title or len(title) > 90 or len(lede) > 180 or len(cards) != len(payload["cards"]):
        return None
    normalized_cards: list[dict[str, str]] = []
    for card in cards:
        if not isinstance(card, dict):
            return None
        card_title = str(card.get("title") or "").strip()
        card_body = str(card.get("body") or "").strip()
        if len(card_title) > 48 or len(card_body) > body_limit:
            return None
        normalized_cards.append({"title": card_title, "body": card_body})

    output = copy.deepcopy(slide)
    output["title"] = title
    output["core_message"] = lede
    output["subtitle"] = lede
    output["cards"] = normalized_cards
    if isinstance(output.get("content"), dict):
        output["content"]["TITLE"] = title
        output["content"]["SUBTITLE"] = lede
    return output
