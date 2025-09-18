# endo/ai_fallback.py
from __future__ import annotations
import re
from typing import Dict, Optional
from django.conf import settings
import google.generativeai as genai
import logging
logger = logging.getLogger(__name__)

_MODEL = getattr(settings, "GEMINI_MODEL_NAME", "gemini-2.0-flash")

def _sanitize_ai_text(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.replace("\r\n", "\n").strip("`").strip()
    lines = [ln.rstrip() for ln in raw.split("\n")]

    kept = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("+ "):     # both + and ++ pass this
            kept.append(s)

    # If nothing matched, return raw (better than empty)
    if not kept:
        return raw.strip()

    # Join kept lines exactly; ensure there are at least the required blocks
    text = "\n".join(kept).strip()
    return text

def _ensure_two_blocks(text: str) -> str:
    t = text.strip()
    has_block1 = re.search(r'^\+\s*"The case evaluation isn\'t valid because .*"$', t, re.M) is not None
    has_block2 = (
        re.search(r'^\+\s*"You should either:\s*$', t, re.M) and
        re.search(r'^\+\+\s*Evaluate other teeth\s*$', t, re.M) and
        re.search(r'^\+\+\s*Evaluate the teeth again by doing the .* again"$', t, re.M)
    )
    if has_block1 and has_block2:
        return t

    # Append missing second block using a guessed test name from block1
    test = "Percussion" if "Percussion" in t else ("Cold Test" if "Cold Test" in t else "Bite Test")
    lines = []
    if has_block1:
        # keep the existing contradiction line(s)
        m = re.search(r'^\+\s*"The case evaluation isn\'t valid because .*$"', t, re.M)
        if m:
            lines.append(m.group(0))
    else:
        lines.append('+ "The case evaluation isn\'t valid because some clinical test results contradict each other."')
    lines.append('')
    lines.append('+ "You should either:')
    lines.append('++ Evaluate other teeth')
    lines.append(f'++ Evaluate the teeth again by doing the {test} again"')
    return "\n".join(lines)


def _prompt(answers: Dict[str, str], engine_version: str) -> str:
    lines = [
        "System: You are an endodontic decision-support assistant.",
        "Task: Our decision-tree app returned NO diagnosis. In ONE concise sentence, name the most relevant contradiction.",
        "",
        "STRICT OUTPUT RULES:",
        '- Output EXACTLY two blocks, in this order, nothing else.',
        '+ "The case evaluation isn\'t valid because the ..[specific test(s) + results].. contradict the ..[specific test(s) + results].."',
        '',
        '+ "You should either:',
        '++ Evaluate other teeth',
        '++ Evaluate the teeth again by doing the ...[specific test]... again"',
        '',
        "Notes:",
        "- Ignore 'Chief Complaint' and 'Toothache' as general.",
        "- Use exact test names (Cold Test, Heat Test, EPT, Palpation, Percussion, Bite Test, Swelling, Sinus Tract, Radiographic Findings, PDL widening).",
        "- Keep it brief. No extra text, no markdown, no code fences.",
        f"Engine version: {engine_version}",
        "",
        "Case evaluation:",
    ]
    for k, v in (answers or {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("Output ONLY the two blocks above. Do not add anything else.")
    return "\n".join(lines)

def _resp_text(resp) -> str:
    """
    Join all text from the top candidate's parts.
    Falls back gracefully if structure differs.
    """
    try:
        cand = resp.candidates[0]
    except Exception:
        return ""
    out = []
    try:
        for p in getattr(cand.content, "parts", []) or []:
            t = getattr(p, "text", "")
            if t:
                out.append(t)
    except Exception:
        pass
    # Some SDK versions also expose resp.text
    if not out:
        t = getattr(resp, "text", "")
        if t:
            out = [t]
    return "\n".join(out).strip()

def gemini_fallback(answers: dict, engine_version: str) -> Optional[str]:
    api_key = getattr(settings, "GOOGLE_GEMINI_API_KEY", "")
    if not api_key or genai is None:
        return None
    try:
        genai.configure(api_key=api_key) # type: ignore
        model = genai.GenerativeModel(_MODEL) # type: ignore
        resp = model.generate_content(
            _prompt(answers, engine_version),
            generation_config={"temperature": 0.2, "top_p": 0.9, "max_output_tokens": 400}, # type: ignore
        )

        text = _resp_text(resp)
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        if text.startswith("TEXT "):
            text = text[5:].lstrip()

        text = _sanitize_ai_text(text)
        text = _ensure_two_blocks(text)
        return text or None

    except Exception:
        logger.exception("Gemini fallback failed")
        return None
