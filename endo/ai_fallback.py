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
    """
    Build a prompt that asks Gemini to produce a compact, human-readable
    contradiction/explanation + suggestions in the exact +/- template.

    IMPORTANT: This version no longer asks for JSON. Your caller should treat
    the model output as plain text (no json.loads).
    """
    lines: list[str] = []

    # Role + task
    lines += [
        "System: You are an endodontic decision-support assistant.",
        "Task: Our endodontic diagnostic app (a comprehensive decision tree of all plausible scenarios) "
        "returned NO diagnosis for the following case. Identify, in ONE concise sentence, the core reason "
        "the evaluation appears invalid or internally inconsistent by citing SPECIFIC tests/results that "
        "contradict each other. Then provide two short actionable suggestions.",
        "",
        "Critical rules:",
        "- Do NOT give a definitive diagnosis.",
        "- Focus on contradictions/inconsistencies among clinical/subj. findings.",
        "- Ignore 'Chief Complaint' and 'Toothache' for contradiction purposes (they are general).",
        "- Keep the reason to ONE sentence and as short as possible.",
        "- Use EXACT output template below (quotes and plus signs included).",
        "- No extra commentary before or after the template; no markdown/code fences.",
        "",
        "Allowed test names to reference verbatim (choose those that apply):",
        "Cold Test, Heat Test, EPT, Palpation, Percussion, Bite Test, Swelling, Sinus Tract, Radiographic Findings, PDL widening, Etiology Assessment, Endodontic Treatment History, Pain quality, Referred pain, Sleep impact, Spontaneous pain.",
        "",
        "Exact OUTPUT TEMPLATE (must match exactly):",
        '+ "The case evaluation isn\'t valid because the ..[specific test(s) and corresponding results].. contradict the ..[specific test(s) and corresponding results].."',
        "",
        '+ "You should either:',
        '++ Evaluate other teeth',
        '++ Evaluate the teeth again by doing the ...[specific test]... again"',
        "",
        "Notes:",
        "- Replace the bracketed parts with concrete, specific contradictions and a concrete test to repeat (e.g., Cold Test, Percussion, Bite Test, EPT, or Radiographic assessment).",
        "- Keep everything brief and clinical. No hedging language or extra sentences.",
        "",
        f"Engine version: {engine_version}",
        "",
        "Case evaluation (verbatim key-value pairs):",
    ]

    # Include all answers verbatim so the model can spot contradictions
    for k, v in (answers or {}).items():
        lines.append(f"- {k}: {v}")

    # Final hard stop instruction
    lines += [
        "",
        "Output ONLY the exact template lines above with your filled-in content. "
        "Do not add any other lines, bullets, or text."
    ]

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