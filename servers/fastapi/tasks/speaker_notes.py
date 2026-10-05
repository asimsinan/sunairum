"""Duration-aware spoken speaker notes: budget, generate, fit, timing."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

DEFAULT_WPM = 125
BUFFER_RATIO = 0.12
MAX_TRIM_ITERS = 2
OVER_BUDGET_TOLERANCE = 0.08

ROLE_WEIGHTS: dict[str, float] = {
    "title": 0.07,
    "agenda": 0.04,
    "content": 0.42,
    "figure": 0.17,
    "results": 0.16,
    "conclusion": 0.10,
    "thanks": 0.02,
    "backup": 0.0,
}

ROLE_CAPS: dict[str, tuple[int, int]] = {
    # (min_words, max_words) soft clamps after weighted allocate — at 15 min reference
    "title": (40, 110),
    "agenda": (20, 90),
    "content": (35, 280),
    "figure": (30, 240),
    "results": (35, 260),
    "conclusion": (25, 180),
    "thanks": (8, 40),
    "backup": (0, 0),
}

# 15 min × 125 wpm × (1 − buffer) — floors/ceilings scale against this.
REFERENCE_WORDS = int(round(15 * DEFAULT_WPM * (1.0 - BUFFER_RATIO)))

_REWRITE_SYSTEM = """You write spoken presentation speaker notes.
Return ONLY plain spoken prose (no markdown, no bullets, no stage labels, no Duration: lines).
Fit within the word budget. Keep must-keep facts (numbers, names, citations) verbatim when present.
One language. Natural transitions in the opening sentence when useful.

Title-slide rules (role=title):
- Open like a live talk: a short greeting, then (if a presenter name is supplied)
  a brief self-introduction, then what you will discuss today and why it matters.
- Match the requested tone (academic → polished, calm, professional; never slangy).
- Do not invent affiliations, titles, or credentials beyond what is supplied.
- Do not dump paper abstract text; speak to the audience."""

_BATCH_REWRITE_SYSTEM = """You write spoken presentation speaker notes for an entire deck in ONE response.
Return ONLY a JSON object mapping each slide_id (e.g. "slide_01") to a plain spoken prose string.
No markdown fences, no bullets, no stage labels, no Duration lines inside the note values.
Keep must-keep facts (numbers, names, citations) when present. One language throughout.

Title-slide rules (role=title):
- Open like a live talk: short greeting, optional presenter intro, then what you will discuss.
- Do not invent affiliations or credentials beyond what is supplied."""


def word_budget(
    minutes: float,
    *,
    wpm: int = DEFAULT_WPM,
    buffer_ratio: float = BUFFER_RATIO,
) -> int:
    minutes = max(0.5, float(minutes))
    wpm = max(60, int(wpm))
    buffer_ratio = min(0.4, max(0.0, float(buffer_ratio)))
    return max(1, int(round(minutes * wpm * (1.0 - buffer_ratio))))


def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def estimate_seconds(text: str, *, wpm: int = DEFAULT_WPM) -> float:
    wpm = max(60, int(wpm))
    return count_words(text) * 60.0 / wpm


def extract_must_keep(text: str) -> list[str]:
    """Numbers, citations, and distinctive acronyms to preserve across rewrites."""
    if not text:
        return []
    found: list[str] = []
    patterns = [
        r"\[\d+[a-z]?\]",
        r"\b\d+(?:\.\d+)?(?:×|x|%)\b",
        r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b",
        r"\b\d+(?:\.\d+)?\b",
        r"\b(?:HNSW|ALNS|HERO|VRPTW|OR-Tools|PyVRP)\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            token = match.group(0)
            if token not in found:
                found.append(token)
    return found[:40]


def _plain_from_svg(svg: str) -> str:
    chunks: list[str] = []
    for match in re.finditer(r"<text\b[^>]*>(.*?)</text>", svg or "", flags=re.I | re.S):
        plain = re.sub(r"<[^>]+>", " ", match.group(1))
        plain = re.sub(r"\s+", " ", plain).strip()
        if not plain:
            continue
        if re.fullmatch(r"(?:P?\d{1,2})(?:\s*/\s*\d{1,2})?", plain, flags=re.I):
            continue
        if re.match(r"^P\d{2}\b", plain, flags=re.I):
            continue
        chunks.append(plain)
    return "\n".join(chunks)


def _plain_from_html(html: str) -> str:
    doc = html or ""
    doc = re.sub(r"<script\b[^>]*>.*?</script>", " ", doc, flags=re.I | re.S)
    doc = re.sub(r"<style\b[^>]*>.*?</style>", " ", doc, flags=re.I | re.S)
    chunks: list[str] = []
    for match in re.finditer(
        r"<(?:h[1-6]|p|li|td|th|div|span|figcaption)\b[^>]*>(.*?)</(?:h[1-6]|p|li|td|th|div|span|figcaption)>",
        doc,
        flags=re.I | re.S,
    ):
        plain = re.sub(r"<[^>]+>", " ", match.group(1))
        plain = re.sub(r"\s+", " ", plain).strip()
        if not plain or len(plain) < 2:
            continue
        if re.fullmatch(r"(?:P?\d{1,2})(?:\s*/\s*\d{1,2})?", plain, flags=re.I):
            continue
        chunks.append(plain)
    if chunks:
        # De-dupe while preserving order (nested tags often repeat text).
        seen: set[str] = set()
        ordered: list[str] = []
        for line in chunks:
            key = line.casefold()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(line)
        return "\n".join(ordered)
    plain = re.sub(r"<[^>]+>", " ", doc)
    return re.sub(r"\s+", " ", plain).strip()


def _title_from_html(html: str) -> str:
    for pattern in (
        r"<h1\b[^>]*>(.*?)</h1>",
        r"<h2\b[^>]*>(.*?)</h2>",
        r'<[^>]+data-sunairum-role=["\']title["\'][^>]*>(.*?)</',
    ):
        match = re.search(pattern, html or "", flags=re.I | re.S)
        if not match:
            continue
        plain = re.sub(r"<[^>]+>", " ", match.group(1))
        plain = re.sub(r"\s+", " ", plain).strip()
        if len(plain) >= 2:
            return plain
    # Cover/title pages often use a large font-size div instead of <h1>
    best = ""
    best_size = 0.0
    for match in re.finditer(
        r'<div\b([^>]*style="[^"]*font-size:\s*([\d.]+)px[^"]*"[^>]*)>(.*?)</div>',
        html or "",
        flags=re.I | re.S,
    ):
        try:
            size = float(match.group(2))
        except ValueError:
            continue
        if size < 28 or size < best_size:
            continue
        plain = re.sub(r"<[^>]+>", " ", match.group(3))
        plain = re.sub(r"\s+", " ", plain).strip()
        if len(plain) < 4 or len(plain) > 160:
            continue
        if re.fullmatch(r"(?:P?\d{1,2})(?:\s*/\s*\d{1,2})?", plain, flags=re.I):
            continue
        best_size = size
        best = plain
    return best


def _plain_from_ir(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for node in data.get("texts") or []:
        if not isinstance(node, dict):
            continue
        plain = re.sub(r"\s+", " ", str(node.get("text") or "")).strip()
        if not plain:
            continue
        if re.fullmatch(r"(?:P?\d{1,2})(?:\s*/\s*\d{1,2})?", plain, flags=re.I):
            continue
        chunks.append(plain)
    return "\n".join(chunks)


def _title_from_ir(data: dict[str, Any]) -> str:
    best = ""
    best_size = -1.0
    for node in data.get("texts") or []:
        if not isinstance(node, dict):
            continue
        plain = re.sub(r"\s+", " ", str(node.get("text") or "")).strip()
        if len(plain) < 4:
            continue
        style = node.get("style") if isinstance(node.get("style"), dict) else {}
        try:
            size = float(style.get("font_size") or style.get("fontSize") or 0)
        except (TypeError, ValueError):
            size = 0.0
        if size > best_size:
            best_size = size
            best = plain
    return best


def slide_text_from_path(path: Path) -> tuple[str, str]:
    """Return (title, plain_text) from html / ir json / legacy svg slide artifact."""
    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.casefold()
    if suffix in {".html", ".htm"}:
        return _title_from_html(raw), _plain_from_html(raw)
    if suffix == ".json":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return "", ""
        if isinstance(data, dict):
            return _title_from_ir(data), _plain_from_ir(data)
        return "", ""
    return _title_from_svg(raw), _plain_from_svg(raw)


def _title_from_svg(svg: str) -> str:
    """Join wrap lines that share the largest cover/content headline size."""
    candidates: list[tuple[float, float, str]] = []
    for match in re.finditer(r"<text\b([^>]*)>(.*?)</text>", svg or "", flags=re.I | re.S):
        attrs, body = match.group(1), match.group(2)
        fs_match = re.search(r'\bfont-size="([\d.]+)"', attrs, flags=re.I)
        y_match = re.search(r'\by="([\d.]+)"', attrs, flags=re.I)
        try:
            fs = float(fs_match.group(1)) if fs_match else 0.0
            y_pos = float(y_match.group(1)) if y_match else 0.0
        except ValueError:
            continue
        if fs < 22:
            continue
        plain = re.sub(r"<[^>]+>", " ", body)
        plain = re.sub(r"\s+", " ", plain).strip()
        if len(plain) < 4:
            continue
        candidates.append((fs, y_pos, plain))
    if not candidates:
        return ""
    best_fs = max(fs for fs, _y, _p in candidates)
    # Same-size wrap lines in the title band (covers intentional two-line titles).
    lines = [
        plain
        for fs, y_pos, plain in candidates
        if abs(fs - best_fs) <= 1.5 and y_pos <= 420
    ]
    if not lines:
        lines = [plain for fs, _y, plain in candidates if abs(fs - best_fs) <= 1.5]
    # De-dupe exact repeats while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for line in lines:
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(line)
    return " ".join(ordered)


def _is_notes_chrome_line(
    plain: str,
    *,
    presenter: str = "",
    title: str = "",
) -> bool:
    """True for presenter / affiliation / page chrome that must not pad spoken notes."""
    text = " ".join((plain or "").split())
    if not text:
        return True
    folded = text.casefold()
    if re.fullmatch(r"(?:P?\d{1,2})(?:\s*/\s*\d{1,2})?", text, flags=re.I):
        return True
    if presenter:
        pres = " ".join(presenter.split()).casefold()
        if pres and (folded == pres or pres in folded or folded in pres):
            return True
    if title:
        tit = " ".join(title.split()).casefold()
        if tit and (folded == tit or folded in tit):
            return True
    chrome_bits = (
        "university",
        "department of",
        "affiliation",
        "anonymous author",
        "isparta",
        "türkiye",
        "turkey",
        "assoc. prof",
        "assistant prof",
        "professor",
    )
    if any(bit in folded for bit in chrome_bits):
        return True
    # Bare "Dr. Name" / "Prof. Name" bylines.
    if re.match(r"^(?:assoc\.?\s*)?(?:asst\.?\s*)?(?:prof\.?|dr\.?)\b", folded):
        return True
    return False


_NOTE_STOP = frozenset(
    "a an the are is am to for of and or our your their this that with on in".split()
)


def _note_content_tokens(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", (text or "").casefold()))
    return {t for t in tokens if t not in _NOTE_STOP and len(t) > 1}


def dedupe_spoken_note(text: str, *, presenter: str = "") -> str:
    """Drop repeated presenter intros / near-duplicate clauses in spoken notes."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""
    # Also split bare stacked slogans lacking terminal punctuation.
    pieces = re.split(r"(?<=[.!?])\s+", cleaned)
    sentences: list[str] = []
    for piece in pieces:
        bit = piece.strip()
        if not bit:
            continue
        # "Thank you Questions welcome" → keep as one unit for near-dup vs earlier lines.
        sentences.append(bit)
    kept: list[str] = []
    seen: set[str] = set()
    kept_tokens: list[set[str]] = []
    union_tokens: set[str] = set()
    presenter_cf = " ".join((presenter or "").split()).casefold()
    presenter_hits = 0
    for sentence in sentences:
        plain = sentence.strip()
        if not plain:
            continue
        key = re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip()
        if key in seen:
            continue
        tokens = _note_content_tokens(plain)
        if tokens and union_tokens and tokens <= union_tokens:
            # e.g. "Thank you Questions welcome" after "Thank you." + "Questions are welcome."
            continue
        if tokens and kept_tokens:
            near = False
            for prior in kept_tokens:
                if not prior:
                    continue
                shorter, longer = (tokens, prior) if len(tokens) <= len(prior) else (prior, tokens)
                if len(shorter) >= 2 and len(shorter & longer) / len(shorter) >= 0.8:
                    near = True
                    break
            if near:
                continue
        if presenter_cf and presenter_cf in plain.casefold():
            presenter_hits += 1
            if presenter_hits > 1:
                # Keep non-intro sentences that merely mention the name? Drop pure repeats.
                if re.match(
                    r"(?i)^(i'?m|i am|my name is|this is)\b",
                    plain,
                ) or plain.casefold().startswith(presenter_cf):
                    continue
                if len(plain) < len(presenter_cf) + 24:
                    continue
        seen.add(key)
        kept_tokens.append(tokens)
        union_tokens |= tokens
        kept.append(plain if plain.endswith((".", "!", "?")) else plain)
    return " ".join(kept).strip()


def thanks_closing_fallback(*, slide_text: str = "", budget: int = 24) -> str:
    """Short closing note — never echo the slide slogan twice."""
    blob = " ".join((slide_text or "").split()).casefold()
    wants_questions = any(
        bit in blob for bit in ("question", "q&a", "qa", "welcome")
    )
    if wants_questions:
        note = "Thank you. Questions are welcome."
    else:
        note = "Thank you for your attention."
    return compress_extractive(note, max(6, budget))


def classify_slide_role(
    *,
    svg: str = "",
    title: str,
    index: int,
    total: int,
    slide_text: str = "",
) -> str:
    plain = slide_text or (_plain_from_svg(svg) if svg else "")
    blob = f"{title}\n{plain}".lower()
    markup = (svg or "").lower()
    if index <= 1 and any(k in blob for k in ("thank", "agenda", "outline", "overview")) is False:
        if any(k in blob for k in ("hero", "title", "equitable vehicle", "presentation")):
            # first slide often title-ish if short
            if count_words(blob) < 80:
                return "title"
    if any(k in blob for k in ("thank you", "questions?", "q&a", "teşekkür")):
        return "thanks"
    if any(k in blob for k in ("agenda", "outline", "today we", "roadmap")):
        return "agenda"
    if any(k in blob for k in ("conclusion", "takeaway", "summary", "limitations", "future work")):
        return "conclusion"
    if any(k in blob for k in ("result", "ablation", "benchmark", "mean cost", "evaluation", "experiment")):
        return "results"
    if (
        "<image" in markup
        or "<img" in markup
        or 'data-pptx="figure"' in markup
        or "data-pptx='figure'" in markup
        or "figure" in blob
    ):
        return "figure"
    if index == total:
        return "thanks"
    if index == 1:
        return "title"
    return "content"


def scaled_role_caps(target_words: int) -> dict[str, tuple[int, int]]:
    """Scale ROLE_CAPS mins/maxes with deck target so 5m floors do not force ~490 words."""
    scale = max(0.25, min(2.5, float(target_words) / float(REFERENCE_WORDS or 1)))
    out: dict[str, tuple[int, int]] = {}
    for role, (lo, hi) in ROLE_CAPS.items():
        if hi <= 0:
            out[role] = (0, 0)
            continue
        # Keep tiny thanks floors usable; never leave content mins above ~share of target.
        new_lo = max(0, int(round(lo * scale)))
        new_hi = max(new_lo, int(round(hi * scale)))
        if role == "thanks":
            new_lo = max(4, new_lo) if target_words >= 200 else max(2, new_lo)
        out[role] = (new_lo, new_hi)
    return out


def allocate_budgets(
    roles: list[str],
    total_words: int,
    *,
    caps: dict[str, tuple[int, int]] | None = None,
) -> list[int]:
    if not roles:
        return []
    role_caps = caps or scaled_role_caps(total_words)
    weights = [ROLE_WEIGHTS.get(role, ROLE_WEIGHTS["content"]) for role in roles]
    weight_sum = sum(weights) or 1.0
    raw = [total_words * (w / weight_sum) for w in weights]
    budgets: list[int] = []
    for role, value in zip(roles, raw):
        lo, hi = role_caps.get(role, (20, 200))
        if hi <= 0:
            budgets.append(0)
            continue
        budgets.append(int(max(lo, min(hi, round(value)))))
    # Renormalize lightly toward total while respecting caps.
    current = sum(budgets) or 1
    if current != total_words and current > 0:
        scale = total_words / current
        adjusted: list[int] = []
        for role, value in zip(roles, budgets):
            lo, hi = role_caps.get(role, (20, 200))
            if hi <= 0:
                adjusted.append(0)
                continue
            adjusted.append(int(max(lo, min(hi, round(value * scale)))))
        budgets = adjusted
    # Fix residual: prefer content-heavy roles; allow soft max overflow for residual only.
    residual = total_words - sum(budgets)
    if residual != 0 and budgets:
        order = sorted(
            range(len(budgets)),
            key=lambda i: ROLE_WEIGHTS.get(roles[i], 0.0),
            reverse=True,
        )
        for idx in order:
            lo, hi = role_caps.get(roles[idx], (20, 200))
            if hi <= 0:
                continue
            # Allow up to 1.35× soft max when soaking residual so deck hits target.
            hard_hi = int(hi * 1.35) if residual > 0 else hi
            nxt = max(lo, min(hard_hi, budgets[idx] + residual))
            residual -= nxt - budgets[idx]
            budgets[idx] = nxt
            if residual == 0:
                break
    return budgets


def compress_extractive(text: str, max_words: int) -> str:
    """Deterministic trim: keep early sentences / must-keep lines within budget."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text or max_words <= 0:
        return ""
    if count_words(text) <= max_words:
        return text
    must = set(extract_must_keep(text))
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept: list[str] = []
    for sentence in sentences:
        candidate = " ".join(kept + [sentence]).strip()
        if count_words(candidate) <= max_words:
            kept.append(sentence)
            continue
        break
    out = " ".join(kept).strip()
    if not out:
        words = text.split()
        out = " ".join(words[:max_words])
    # Append missing must-keep tokens if space allows.
    missing = [token for token in must if token not in out]
    if missing:
        addon = " (" + ", ".join(missing[:8]) + ")"
        if count_words(out + addon) <= max_words + 6:
            out = (out.rstrip(".") + addon).strip()
    return out


def expand_extractive(
    text: str,
    slide_text: str,
    target_words: int,
    *,
    role: str = "content",
    presenter: str = "",
    title: str = "",
) -> str:
    """Pad short notes toward a target using unused slide sentences (no LLM)."""
    base = re.sub(r"\s+", " ", (text or "").strip())
    if target_words <= 0:
        return base
    if count_words(base) >= target_words:
        return compress_extractive(base, target_words)
    # Title/thanks chrome is not spoken padding — it creates slogan repeats.
    if role in {"title", "thanks"}:
        out = base
        if role == "title" and count_words(out) < 28:
            filler = (
                "I'll keep this opening brief and then move into the motivation, "
                "method, and the main experimental takeaways."
            )
            candidate = f"{out} {filler}".strip()
            if count_words(candidate) <= target_words + 12:
                out = candidate
        if role == "thanks" and count_words(out) < 6:
            out = thanks_closing_fallback(slide_text=slide_text, budget=target_words)
        return dedupe_spoken_note(out, presenter=presenter)

    extras: list[str] = []
    # Prefer line-aware split first so SVG bylines stay atomic.
    raw_chunks = [ln.strip() for ln in (slide_text or "").splitlines() if ln.strip()]
    if len(raw_chunks) <= 1:
        raw_chunks = re.split(
            r"(?<=[.!?])\s+",
            re.sub(r"\s+", " ", (slide_text or "").strip()),
        )
    for sentence in raw_chunks:
        plain = sentence.strip()
        if len(plain) < 20:
            continue
        if _is_notes_chrome_line(plain, presenter=presenter, title=title):
            continue
        if plain.casefold() in base.casefold():
            continue
        extras.append(plain if plain.endswith((".", "!", "?")) else plain + ".")
    out = base
    for sentence in extras:
        candidate = f"{out} {sentence}".strip()
        if count_words(candidate) > target_words:
            # Take a word-trimmed prefix of the next sentence if still under.
            room = target_words - count_words(out)
            if room >= 6:
                words = sentence.split()
                out = f"{out} {' '.join(words[:room])}".strip()
            break
        out = candidate
        if count_words(out) >= target_words:
            break
    if count_words(out) < max(8, int(target_words * 0.55)):
        # Last resort spoken padding so Fit never no-ops on short notes.
        filler = (
            "Let me expand on this point for the audience, connecting it to the "
            "overall argument and what it implies for the next slides."
        )
        while count_words(out) < target_words:
            nxt = f"{out} {filler}".strip()
            if count_words(nxt) > target_words + 8:
                room = target_words - count_words(out)
                if room > 0:
                    out = f"{out} {' '.join(filler.split()[:room])}".strip()
                break
            out = nxt
    return dedupe_spoken_note(out, presenter=presenter)


def facts_preserved(original: str, rewritten: str) -> list[str]:
    missing: list[str] = []
    for token in extract_must_keep(original):
        if token.lower() not in (rewritten or "").lower():
            # Allow dropping tiny bare integers that are noise
            if re.fullmatch(r"\d{1,2}", token):
                continue
            missing.append(token)
    return missing


def _tone_from_instructions(instructions: str) -> str:
    text = (instructions or "").lower()
    if "academic" in text or "formal" in text:
        return "academic"
    if "casual" in text or "informal" in text:
        return "casual"
    return "professional"


def title_opening_fallback(
    *,
    slide_title: str,
    slide_text: str,
    presenter: str = "",
    core_message: str = "",
    tone: str = "academic",
    budget: int = 80,
) -> str:
    """Deterministic spoken opener when the LLM is unavailable."""
    title = " ".join((slide_title or "").split()) or "this work"
    # Prefer a short subtitle/hook from slide body (skip brand/eyebrow/furniture).
    hook = ""
    for line in (slide_text or "").splitlines():
        plain = " ".join(line.split())
        if len(plain) < 28 or "<" in plain or "xmlns" in plain.casefold():
            continue
        if _is_notes_chrome_line(plain, presenter=presenter, title=title):
            continue
        if plain.isupper() and len(plain) < 40:
            continue
        hook = plain
        break
    if not hook:
        hook = " ".join((core_message or "").split())
        if _is_notes_chrome_line(hook, presenter=presenter, title=title):
            hook = ""

    if tone == "casual":
        greeting = "Hello everyone."
    else:
        greeting = "Good morning, everyone."

    parts = [greeting]
    if presenter:
        parts.append(f"I'm {presenter}.")
    parts.append(f"Today I'll present {title}.")
    if hook:
        parts.append(hook if hook.endswith((".", "!", "?")) else hook + ".")
    if tone == "academic":
        parts.append(
            "I'll keep the focus on the method, the experimental evidence, "
            "and what the results imply for practice."
        )
    else:
        parts.append("I'll walk through the key ideas and what the results show.")
    return dedupe_spoken_note(
        compress_extractive(" ".join(parts), max(12, budget)),
        presenter=presenter,
    )


def _call_llm_rewrite(
    *,
    slide_text: str,
    prior_notes: str,
    budget: int,
    must_keep: list[str],
    role: str,
    call_text: Any | None,
    context: dict[str, str] | None = None,
) -> str:
    if call_text is None:
        try:
            from llm_client import call_llm_text

            call_text = call_llm_text
        except ImportError:
            return ""

    ctx = context or {}
    extra = ""
    if role == "title":
        extra = (
            "\nTitle-slide context:\n"
            f"- Tone: {ctx.get('tone') or 'academic'}\n"
            f"- Presenter (use verbatim if non-empty): {ctx.get('presenter') or '(none)'}\n"
            f"- Core message: {ctx.get('core_message') or '(none)'}\n"
            "Begin with a greeting and a natural 'today I will…' framing.\n"
        )

    user = (
        f"Role: {role}\n"
        f"Target length: about {budget} words (stay within ±12%; do not undershoot by half).\n"
        f"Must-keep facts: {', '.join(must_keep) if must_keep else '(none)'}\n"
        f"{extra}\n"
        f"Visible slide text:\n{slide_text[:4000]}\n\n"
        f"Existing notes (may be too long or too short — rewrite as spoken notes):\n"
        f"{(prior_notes or '')[:5000]}\n"
    )
    try:
        raw = str(call_text(_REWRITE_SYSTEM, user) or "").strip()
    except Exception as error:
        print(f"[speaker_notes] LLM rewrite failed: {error}")
        return ""
    raw = re.sub(r"^```(?:\w+)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = re.sub(r"^#+\s.*$", "", raw, flags=re.M)
    raw = re.sub(r"^\s*[-*•]\s+", "", raw, flags=re.M)
    return re.sub(r"\s+", " ", raw).strip()


def _clean_spoken_note(raw: str) -> str:
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:\w+)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = re.sub(r"^#+\s.*$", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.M)
    # Remove spoken clauses whose only purpose is to cite internal catalog
    # addresses.  Stripping the IDs alone leaves phrases such as
    # "as documented in evidence objects and", which sounds broken in the
    # embedded notes even though the slide itself is clean.
    catalog = r"`?(?:ev-page-\d+-(?:block|table)-\d+|src-table-\d+|pdf-page-\d+-picture-\d+)`?"
    text = re.sub(
        rf"\s*,?\s*as\s+(?:documented|reported|shown|supported|listed)\s+in\s+"
        rf"(?:the\s+)?(?:evidence\s+(?:objects?|records?)\s+)?{catalog}"
        rf"(?:\s*(?:,|and|;)\s*{catalog})*",
        "",
        text,
        flags=re.I,
    )
    try:
        from tasks.grounded_planner import strip_catalog_provenance_annotations
    except ImportError:  # pragma: no cover
        from grounded_planner import strip_catalog_provenance_annotations  # type: ignore
    text = strip_catalog_provenance_annotations(text)
    text = re.sub(
        r"\s*,?\s*as\s+(?:documented|reported|shown|supported|listed)\s+in\s+"
        r"(?:the\s+)?(?:evidence\s+(?:objects?|records?)\s*)?(?:and\s*)?(?=[.,;]|$)",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def _call_llm_batch_notes(
    *,
    slides: list[dict[str, Any]],
    call_text: Any | None,
    context: dict[str, str] | None = None,
) -> dict[str, str]:
    """One LLM call → map of slide_id → spoken notes. Empty dict on failure."""
    if not slides:
        return {}
    if call_text is None:
        try:
            from llm_client import call_llm_text

            call_text = call_llm_text
        except ImportError:
            return {}

    ctx = context or {}
    payload = []
    for item in slides:
        payload.append(
            {
                "slide_id": item["slide_id"],
                "role": item["role"],
                "title": item["title"],
                "word_budget": item["budget"],
                "slide_text": str(item.get("slide_text") or "")[:1800],
            }
        )
    user = (
        f"Tone: {ctx.get('tone') or 'academic'}\n"
        f"Presenter (use verbatim if non-empty): {ctx.get('presenter') or '(none)'}\n"
        f"Core message: {ctx.get('core_message') or '(none)'}\n\n"
        "Write spoken notes for every slide below. Respect each word_budget (±12%).\n"
        f"Slides JSON:\n{json.dumps(payload, ensure_ascii=False)}\n"
    )
    try:
        raw = str(call_text(_BATCH_REWRITE_SYSTEM, user) or "").strip()
    except Exception as error:
        print(f"[speaker_notes] batch LLM rewrite failed: {error}")
        return {}
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Tolerate a leading/trailing prose wrapper around the object.
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            print("[speaker_notes] batch LLM returned non-JSON")
            return {}
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            print("[speaker_notes] batch LLM JSON parse failed")
            return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in data.items():
        slide_id = str(key).strip()
        note = _clean_spoken_note(value if isinstance(value, str) else str(value or ""))
        if slide_id and note:
            out[slide_id] = note
    return out


def rewrite_to_budget(
    *,
    slide_text: str,
    prior_notes: str,
    budget: int,
    role: str,
    call_text: Any | None = None,
    preserve_facts: bool = True,
    context: dict[str, str] | None = None,
    slide_title: str = "",
    prefer_llm: bool = True,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    source = prior_notes.strip() if prior_notes.strip() else slide_text
    must_keep = extract_must_keep(source) if preserve_facts else []
    if budget <= 0:
        return "", warnings

    ctx = context or {}
    # compress mode stays extractive so Fit to duration is interactive; regenerate uses the LLM.
    note = ""
    if prefer_llm:
        note = _call_llm_rewrite(
            slide_text=slide_text,
            prior_notes=prior_notes or slide_text,
            budget=budget,
            must_keep=must_keep,
            role=role,
            call_text=call_text,
            context=ctx,
        )
    if not note:
        if role == "title":
            resolved_title = slide_title or next(
                (ln.strip() for ln in (slide_text or "").splitlines() if len(ln.strip()) > 12),
                "this work",
            )
            note = title_opening_fallback(
                slide_title=resolved_title,
                slide_text=slide_text,
                presenter=str(ctx.get("presenter") or ""),
                core_message=str(ctx.get("core_message") or ""),
                tone=str(ctx.get("tone") or "academic"),
                budget=budget,
            )
        elif role == "thanks":
            seed = dedupe_spoken_note(prior_notes or slide_text)
            if count_words(seed) >= 4 and "thank" in seed.casefold():
                note = compress_extractive(seed, budget)
            else:
                note = thanks_closing_fallback(slide_text=slide_text, budget=budget)
            note = dedupe_spoken_note(note)
        else:
            note = compress_extractive(source, budget)

    # Title slides that still lack a greeting get a deterministic opener grafted in.
    if role == "title" and note and not re.search(
        r"(?i)^\s*(good\s+(morning|afternoon|evening)|hello|hi\b|welcome)\b",
        note,
    ):
        opener = title_opening_fallback(
            slide_title=slide_title,
            slide_text=slide_text,
            presenter=str(ctx.get("presenter") or ""),
            core_message=str(ctx.get("core_message") or ""),
            tone=str(ctx.get("tone") or "academic"),
            budget=min(budget, max(40, budget // 2)),
        )
        # Prefer the crafted opener when the model skipped the greeting.
        note = opener if count_words(opener) >= 20 else note

    for _ in range(MAX_TRIM_ITERS):
        words = count_words(note)
        if words <= budget * (1.0 + OVER_BUDGET_TOLERANCE):
            break
        surplus = words - budget
        if prefer_llm:
            note = _call_llm_rewrite(
                slide_text=slide_text,
                prior_notes=note,
                budget=max(8, budget - int(surplus * 0.5)),
                must_keep=must_keep,
                role=role,
                call_text=call_text,
                context=ctx,
            ) or (
                title_opening_fallback(
                    slide_title=slide_title,
                    slide_text=slide_text,
                    presenter=str(ctx.get("presenter") or ""),
                    core_message=str(ctx.get("core_message") or ""),
                    tone=str(ctx.get("tone") or "academic"),
                    budget=budget,
                )
                if role == "title"
                else compress_extractive(note, budget)
            )
        if count_words(note) > budget:
            note = compress_extractive(note, budget)

    # Expand thin notes toward the slide budget so duration Fit can lengthen.
    if count_words(note) < max(8, int(budget * 0.85)):
        if prefer_llm:
            richer = _call_llm_rewrite(
                slide_text=slide_text,
                prior_notes=note or prior_notes or slide_text,
                budget=budget,
                must_keep=must_keep,
                role=role,
                call_text=call_text,
                context=ctx,
            )
            if richer and count_words(richer) > count_words(note):
                note = richer
        if count_words(note) < max(8, int(budget * 0.85)):
            note = expand_extractive(
                note,
                slide_text,
                budget,
                role=role,
                presenter=str(ctx.get("presenter") or ""),
                title=slide_title,
            )

    note = dedupe_spoken_note(note, presenter=str(ctx.get("presenter") or ""))
    if preserve_facts and role != "title":
        missing = facts_preserved(source, note)
        if missing:
            warnings.append(f"missing facts after compress: {', '.join(missing[:8])}")
    return note, warnings


def delete_orphan_notes(project_dir: Path) -> list[str]:
    """Remove notes/slide_*.md whose stem is not backed by a live slide artifact."""
    root = Path(project_dir)
    notes_dir = root / "notes"
    if not notes_dir.is_dir():
        return []
    live = {p.stem for p in list_slide_svgs(root)}
    removed: list[str] = []
    for path in sorted(notes_dir.glob("slide_*.md")):
        if path.stem not in live:
            try:
                path.unlink()
                removed.append(path.name)
            except OSError:
                continue
    return removed


def choose_fit_mode(
    *,
    actual_words: int,
    target_words: int,
    requested: str,
) -> str:
    """Pick compress vs regenerate from deck-level word delta."""
    mode = (requested or "auto").strip().lower()
    if mode in {"compress", "regenerate"}:
        return mode
    if target_words <= 0:
        return "compress"
    ratio = actual_words / float(target_words)
    if ratio > 1.08:
        return "compress"
    # Under budget / near budget: regenerate (or expand) — compress cannot lengthen.
    if ratio < 0.85 or abs(ratio - 1.0) > 0.12:
        return "regenerate"
    return "compress"


def list_slide_svgs(project_dir: Path) -> list[Path]:
    """Slide artifacts for notes via shared discovery (html → ir → preview → svg)."""
    from tasks.slide_artifacts import list_slide_artifacts

    return list_slide_artifacts(project_dir)


def notes_path_for_svg(project_dir: Path, svg_path: Path) -> Path:
    stem = svg_path.stem  # slide_01
    return project_dir / "notes" / f"{stem}.md"


def read_note(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def note_is_usable(text: str) -> bool:
    """True when a note file has enough spoken content to keep on resume."""
    words = count_words(text or "")
    return words >= 4


def missing_note_numbers(project_dir: Path | str) -> list[int]:
    """Slide numbers that have a slide artifact but no usable notes/*.md (resume gaps)."""
    root = Path(project_dir)
    missing: list[int] = []
    for svg_path in list_slide_svgs(root):
        match = re.search(r"(\d+)$", svg_path.stem)
        if not match:
            continue
        number = int(match.group(1))
        note = read_note(notes_path_for_svg(root, svg_path))
        if not note_is_usable(note):
            missing.append(number)
    return missing


def notes_complete_for_svgs(project_dir: Path | str) -> bool:
    """True when every authored slide artifact has a usable speaker-note file."""
    root = Path(project_dir)
    svgs = list_slide_svgs(root)
    if not svgs:
        return False
    return not missing_note_numbers(root)


def write_note(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((text or "").rstrip() + "\n", encoding="utf-8")


def backup_notes(project_dir: Path) -> Path | None:
    notes_dir = project_dir / "notes"
    if not notes_dir.is_dir():
        return None
    files = [p for p in notes_dir.glob("slide_*.md") if p.is_file()]
    if not files:
        return None
    backup_dir = notes_dir / "_backup"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in files:
        shutil.copy2(path, backup_dir / path.name)
    timing = notes_dir / "timing.json"
    if timing.is_file():
        shutil.copy2(timing, backup_dir / "timing.json")
    return backup_dir


def restore_notes_backup(project_dir: Path) -> bool:
    backup_dir = project_dir / "notes" / "_backup"
    if not backup_dir.is_dir():
        return False
    notes_dir = project_dir / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    for path in backup_dir.glob("slide_*.md"):
        shutil.copy2(path, notes_dir / path.name)
    timing = backup_dir / "timing.json"
    if timing.is_file():
        shutil.copy2(timing, notes_dir / "timing.json")
    return True


def clear_notes(project_dir: Path) -> None:
    notes_dir = project_dir / "notes"
    if not notes_dir.is_dir():
        return
    for path in notes_dir.glob("slide_*.md"):
        path.unlink(missing_ok=True)
    timing = notes_dir / "timing.json"
    if timing.is_file():
        timing.unlink()


def load_confirm_prefs(project_dir: Path | str) -> dict[str, Any]:
    result_path = Path(project_dir) / "confirm_ui" / "result.json"
    if not result_path.is_file():
        return {}
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def notes_enabled(project_dir: Path | str) -> bool:
    prefs = load_confirm_prefs(project_dir)
    value = prefs.get("proactive_speaker_notes", True)
    if isinstance(value, dict):
        return bool(value.get("value", True))
    return bool(value)


def _unwrap_pref(value: Any, default: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value", default)
    return default if value is None else value


def resolve_duration_settings(project_dir: Path | str) -> tuple[float, int]:
    prefs = load_confirm_prefs(project_dir)
    minutes = _unwrap_pref(prefs.get("target_duration_minutes", 15), 15)
    wpm = _unwrap_pref(prefs.get("notes_wpm", DEFAULT_WPM), DEFAULT_WPM)
    try:
        minutes_f = float(minutes)
    except (TypeError, ValueError):
        minutes_f = 15.0
    try:
        wpm_i = int(wpm)
    except (TypeError, ValueError):
        wpm_i = DEFAULT_WPM
    return max(1.0, minutes_f), max(60, wpm_i)


def animations_enabled(project_dir: Path | str) -> bool:
    prefs = load_confirm_prefs(project_dir)
    value = _unwrap_pref(prefs.get("proactive_custom_animations", False), False)
    return bool(value)


def resolve_slide_transition(project_dir: Path | str) -> str | None:
    """Deckhtml transition token for compile, or None when animations are off."""
    from tasks.slide_transitions import normalize_slide_transition

    prefs = load_confirm_prefs(project_dir)
    enabled = bool(_unwrap_pref(prefs.get("proactive_custom_animations", False), False))
    effect = _unwrap_pref(prefs.get("custom_animation_effect"), None)
    return normalize_slide_transition(
        enabled, str(effect) if effect is not None else None
    )


def build_timing_report(
    *,
    slides: list[dict[str, Any]],
    target_minutes: float,
    wpm: int,
    target_words: int,
    mode_used: str | None = None,
    changed_slides: int | None = None,
    orphan_notes_removed: list[str] | None = None,
) -> dict[str, Any]:
    actual_words = sum(int(s.get("word_count") or 0) for s in slides)
    est_seconds = sum(float(s.get("estimated_seconds") or 0) for s in slides)
    budget_ok = (
        target_words > 0
        and abs(actual_words - target_words) / float(target_words) <= 0.12
    )
    report: dict[str, Any] = {
        "schema_version": "sunairum.notes-timing/v1",
        "target_duration_minutes": target_minutes,
        "wpm": wpm,
        "buffer_ratio": BUFFER_RATIO,
        "target_words": target_words,
        "actual_words": actual_words,
        "estimated_seconds_total": round(est_seconds, 1),
        "estimated_minutes_total": round(est_seconds / 60.0, 2),
        "budget_ok": budget_ok,
        "slides": slides,
        "warnings": [
            w
            for s in slides
            for w in (s.get("warnings") or [])
        ],
    }
    if mode_used is not None:
        report["mode_used"] = mode_used
    if changed_slides is not None:
        report["changed_slides"] = changed_slides
    if orphan_notes_removed is not None:
        report["orphan_notes_removed"] = orphan_notes_removed
    return report


def compute_timing_from_disk(
    project_dir: Path,
    *,
    target_minutes: float | None = None,
    wpm: int | None = None,
) -> dict[str, Any]:
    minutes, default_wpm = resolve_duration_settings(project_dir)
    if target_minutes is not None:
        minutes = float(target_minutes)
    if wpm is None:
        wpm = default_wpm
    target = word_budget(minutes, wpm=wpm)
    svgs = list_slide_svgs(project_dir)
    slides: list[dict[str, Any]] = []
    for index, svg_path in enumerate(svgs, start=1):
        title, slide_text = slide_text_from_path(svg_path)
        raw = ""
        try:
            raw = svg_path.read_text(encoding="utf-8")
        except OSError:
            raw = ""
        role = classify_slide_role(
            svg=raw,
            title=title,
            index=index,
            total=len(svgs),
            slide_text=slide_text,
        )
        note = read_note(notes_path_for_svg(project_dir, svg_path))
        words = count_words(note)
        slides.append(
            {
                "slide_id": svg_path.stem,
                "filename": svg_path.name,
                "role": role,
                "title": title,
                "word_count": words,
                "estimated_seconds": round(estimate_seconds(note, wpm=wpm), 1),
                "notes_preview": note[:240],
            }
        )
    return build_timing_report(
        slides=slides,
        target_minutes=minutes,
        wpm=wpm,
        target_words=target,
    )


def fit_notes_to_duration(
    project_dir: Path | str,
    *,
    target_duration_minutes: float | None = None,
    wpm: int | None = None,
    preserve_facts: bool = True,
    mode: str = "auto",
    call_text: Any | None = None,
    backup: bool = True,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Rewrite notes/*.md to fit a speak-time budget. mode: auto|compress|regenerate.

    Regenerates with **one** batched LLM call (not N per-slide calls). Compress
    stays extractive (0 LLM). Reads html_output / ir / legacy svg; never writes them.
    """
    root = Path(project_dir)
    minutes, default_wpm = resolve_duration_settings(root)
    if target_duration_minutes is not None:
        minutes = float(target_duration_minutes)
    if wpm is None:
        wpm = default_wpm
    target = word_budget(minutes, wpm=wpm)
    svgs = list_slide_svgs(root)
    if not svgs:
        raise FileNotFoundError(
            "No slide artifacts found (html_output/, preview/, or svg_output/)"
        )

    if backup:
        backup_notes(root)

    orphan_removed = delete_orphan_notes(root)

    from tasks.deck_furniture import normalize_furniture, resolve_deck_furniture

    prefs = load_confirm_prefs(root)
    # Prefer cached furniture from Job A — never pay for a second extract mid-notes.
    cached = prefs.get("deck_furniture") if isinstance(prefs, dict) else None
    furniture = normalize_furniture(cached) if isinstance(cached, dict) else {}
    if not furniture:
        furniture = resolve_deck_furniture(prefs if isinstance(prefs, dict) else {})
    note_context = {
        "presenter": str(furniture.get("presenter") or ""),
        "tone": _tone_from_instructions(str(prefs.get("additional_instructions") or "")),
        "core_message": str(prefs.get("core_message") or ""),
    }

    roles: list[str] = []
    slide_meta: list[dict[str, Any]] = []
    prior_words_total = 0
    for index, svg_path in enumerate(svgs, start=1):
        title, slide_text = slide_text_from_path(svg_path)
        raw = ""
        try:
            raw = svg_path.read_text(encoding="utf-8")
        except OSError:
            raw = ""
        role = classify_slide_role(
            svg=raw,
            title=title,
            index=index,
            total=len(svgs),
            slide_text=slide_text,
        )
        if index == 1:
            role = "title"
        roles.append(role)
        prior = read_note(notes_path_for_svg(root, svg_path))
        prior_words_total += count_words(prior)
        slide_meta.append(
            {
                "svg_path": svg_path,
                "slide_id": svg_path.stem,
                "title": title,
                "role": role,
                "slide_text": slide_text,
                "prior_raw": prior,
                "prior_words": count_words(prior),
            }
        )

    effective_mode = choose_fit_mode(
        actual_words=prior_words_total,
        target_words=target,
        requested=mode,
    )
    # Compress stays extractive. Do not escalate compress→regenerate (that
    # reintroduced N LLM calls). Pipeline regenerate uses one batch call.
    modes_to_try = [effective_mode]

    caps = scaled_role_caps(target)
    budgets = allocate_budgets(roles, target, caps=caps)
    out_slides: list[dict[str, Any]] = []
    notes_dir = root / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    changed_slides = 0
    mode_used = effective_mode
    total_slides = len(slide_meta)
    batch_notes: dict[str, str] = {}

    for attempt_mode in modes_to_try:
        mode_used = attempt_mode
        out_slides = []
        changed_slides = 0
        batch_notes = {}
        if attempt_mode == "regenerate":
            batch_payload = [
                {
                    "slide_id": meta["slide_id"],
                    "role": meta["role"],
                    "title": meta["title"],
                    "budget": budget,
                    "slide_text": meta["slide_text"],
                }
                for meta, budget in zip(slide_meta, budgets)
            ]
            batch_notes = _call_llm_batch_notes(
                slides=batch_payload,
                call_text=call_text,
                context=note_context,
            )

        for index, (meta, budget) in enumerate(zip(slide_meta, budgets), start=1):
            prior_raw = meta["prior_raw"]
            warnings: list[str] = []
            note = ""
            if attempt_mode == "regenerate" and meta["slide_id"] in batch_notes:
                note = batch_notes[meta["slide_id"]]
                # Soft trim only — no second LLM round-trip.
                if count_words(note) > budget * (1.0 + OVER_BUDGET_TOLERANCE):
                    note = compress_extractive(note, budget)
                if count_words(note) < max(8, int(budget * 0.85)):
                    note = expand_extractive(
                        note,
                        meta["slide_text"],
                        budget,
                        role=str(meta["role"] or "content"),
                        presenter=str(note_context.get("presenter") or ""),
                        title=str(meta.get("title") or ""),
                    )
                note = dedupe_spoken_note(
                    note, presenter=str(note_context.get("presenter") or "")
                )
            else:
                note, warnings = rewrite_to_budget(
                    slide_text=meta["slide_text"],
                    prior_notes=prior_raw or meta["slide_text"],
                    budget=budget,
                    role=meta["role"],
                    call_text=call_text,
                    preserve_facts=preserve_facts,
                    context=note_context,
                    slide_title=meta["title"],
                    prefer_llm=False,
                )
            if preserve_facts and meta["role"] != "title" and note:
                missing = facts_preserved(prior_raw or meta["slide_text"], note)
                if missing:
                    warnings.append(f"missing facts after compress: {', '.join(missing[:8])}")
            note_path = notes_path_for_svg(root, meta["svg_path"])
            if note.strip() != (prior_raw or "").strip():
                changed_slides += 1
            write_note(note_path, note)
            if progress_callback is not None:
                try:
                    progress_callback(index, total_slides)
                except Exception:
                    pass
            words = count_words(note)
            out_slides.append(
                {
                    "slide_id": meta["slide_id"],
                    "filename": meta["svg_path"].name,
                    "role": meta["role"],
                    "title": meta["title"],
                    "word_budget": budget,
                    "word_count": words,
                    "estimated_seconds": round(estimate_seconds(note, wpm=wpm), 1),
                    "notes": note,
                    "warnings": warnings,
                }
            )
        break

    report = build_timing_report(
        slides=out_slides,
        target_minutes=minutes,
        wpm=wpm,
        target_words=target,
        mode_used=mode_used,
        changed_slides=changed_slides,
        orphan_notes_removed=orphan_removed,
    )
    report["llm_calls"] = 1 if mode_used == "regenerate" and batch_notes else 0
    (notes_dir / "timing.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Persist chosen duration on confirm prefs when provided explicitly.
    prefs_path = root / "confirm_ui" / "result.json"
    if prefs_path.is_file() and target_duration_minutes is not None:
        try:
            prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
            if isinstance(prefs, dict):
                prefs["target_duration_minutes"] = minutes
                prefs["notes_wpm"] = wpm
                prefs_path.write_text(
                    json.dumps(prefs, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        except (OSError, json.JSONDecodeError):
            pass

    return report


def maybe_generate_speaker_notes_for_project(
    project_dir: Path | str,
    *,
    call_text: Any | None = None,
    progress_callback: Any | None = None,
    keep_existing: bool = False,
) -> dict[str, Any]:
    """Pipeline hook: generate+fit when notes enabled; clear when disabled.

    When ``keep_existing`` (resume), skip regeneration if every slide artifact
    already has a usable note; otherwise regenerate the full deck so budgets
    stay coherent.
    """
    root = Path(project_dir)
    if not notes_enabled(root):
        clear_notes(root)
        return {"status": "disabled", "cleared": True}

    missing_before = missing_note_numbers(root)
    if keep_existing and notes_complete_for_svgs(root):
        timing = load_timing(root)
        return {
            "status": "kept",
            "timing": timing,
            "missing_notes": [],
            "kept_existing": True,
        }

    minutes, wpm = resolve_duration_settings(root)
    report = fit_notes_to_duration(
        root,
        target_duration_minutes=minutes,
        wpm=wpm,
        preserve_facts=True,
        mode="regenerate",
        call_text=call_text,
        backup=True,
        progress_callback=progress_callback,
    )
    target = int(report.get("target_words") or 0)
    actual = int(report.get("actual_words") or 0)
    # Extractive compress only when badly over — never a second LLM regenerate.
    if target > 0 and actual > target * 1.35:
        report = fit_notes_to_duration(
            root,
            target_duration_minutes=minutes,
            wpm=wpm,
            preserve_facts=True,
            mode="compress",
            call_text=None,
            backup=False,
            progress_callback=progress_callback,
        )
    missing_after = missing_note_numbers(root)
    status = "generated" if not missing_after else "incomplete"
    return {
        "status": status,
        "timing": report,
        "missing_notes": missing_after,
        "missing_notes_before": missing_before,
    }


def load_timing(project_dir: Path | str) -> dict[str, Any]:
    root = Path(project_dir)
    timing_path = root / "notes" / "timing.json"
    if timing_path.is_file():
        try:
            data = json.loads(timing_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("slides"):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return compute_timing_from_disk(root)
