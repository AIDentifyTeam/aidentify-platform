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
    # Keep it short and deterministic; JSON-only output.
    lines = [
        "System: You are an endodontic decision-support assistant.",
        "Do NOT give definitive diagnoses. Provide differentials, next-step tests, and red flags.",
        "Output MUST be raw JSON exactly matching the schema. No markdown, no code fences.",
        "",
        "Schema:", _SCHEMA, "",
        f"Rules engine returned no matches. Engine version: {engine_version}.",
        "Patient questionnaire (compact keys like P..X, E..L, history, etiology):",
    ]
    for k, v in (answers or {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("Reply with JSON only.")
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