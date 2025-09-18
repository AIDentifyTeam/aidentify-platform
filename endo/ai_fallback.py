# endo/ai_fallback.py
from __future__ import annotations
from typing import Dict, Optional
from django.conf import settings
import google.generativeai as genai
import logging
logger = logging.getLogger(__name__)

_MODEL = getattr(settings, "GEMINI_MODEL_NAME", "gemini-2.0-flash")

def _sanitize_ai_text(raw: str) -> str:
    """
    Keep only the lines that belong to the required template:
      + "The case evaluation isn't valid because ..."
      + "You should either:
      ++ Evaluate other teeth
      ++ Evaluate the teeth again by doing the ... again"
    Strip anything before the first '+' line and drop empty noise.
    """
    if not raw:
        return ""
    # tolerate accidental code fences or prefixes
    raw = raw.strip().strip("`").replace("\r\n", "\n").strip()
    lines = [ln.rstrip() for ln in raw.split("\n")]

    # drop lines until the first that starts with '+'
    out = []
    started = False
    for ln in lines:
        if not started and ln.lstrip().startswith("+"):
            started = True
        if started:
            # keep only + / ++ lines (and closing quote mismatches are okay)
            if ln.lstrip().startswith("+"):
                out.append(ln.strip())
            # stop if model started rambling beyond template
            elif out:
                break
    # join back
    text = "\n".join(out).strip()
    # final guard: ensure it contains at least the two required blocks
    if not text.startswith('+ "The case evaluation'):
        logger.info("AI text did not match expected template; returning raw fallback")
        return raw
    return text


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


def gemini_fallback(answers: dict, engine_version: str) -> Optional[str]:
    """
    Call Gemini and return the plain text (Ramtin template).
    Return None on any failure.
    """
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
        text = (resp.candidates[0].content.parts[0].text or "").strip()
        # Tolerate ```json fences, accidental "TEXT + " prefixes, etc.
        text = text.replace("TEXT ", "", 1) if text.startswith("TEXT ") else text
        return _sanitize_ai_text(text)
    except Exception:
        logger.exception("Gemini fallback failed")
        return None