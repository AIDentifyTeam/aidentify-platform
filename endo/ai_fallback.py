# endo/ai_fallback.py
from __future__ import annotations
import json
import traceback
from typing import Dict, Optional
from django.conf import settings
import google.generativeai as genai

_MODEL = getattr(settings, "GEMINI_MODEL_NAME", "gemini-1.5-pro")

_SCHEMA = """
{
  "differential_list": [{"condition": "string", "why": "string", "confidence": 0}],
  "recommended_tests": [{"test": "string", "rationale": "string"}],
  "red_flags": [{"flag": "string", "action": "string"}],
  "disclaimer": "string"
}
""".strip()

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


def gemini_fallback(answers: Dict[str, str], engine_version: str) -> Optional[Dict]:
    """Call Gemini and return parsed JSON; return None on any failure."""
    api_key = getattr(settings, "GOOGLE_GEMINI_API_KEY", "")
    print("api_key", api_key)
    if not api_key or genai is None:
        return None
    try:
        genai.configure(api_key=api_key) # type: ignore
        model = genai.GenerativeModel(_MODEL) # type: ignore
        text = model.generate_content(
            _prompt(answers, engine_version),
            generation_config={"temperature": 0.2, "top_p": 0.9, "max_output_tokens": 600}, # type: ignore
        ).candidates[0].content.parts[0].text.strip()
        print("TEXT", text)
        # tolerate accidental ```json fences
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()

        data = json.loads(text)
        required = {"differential_list", "recommended_tests", "red_flags", "disclaimer"}
        return data if required.issubset(data.keys()) else None
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        return None