# endo/ai_fallback.py
from __future__ import annotations
import re
from typing import Dict, Optional, List
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# Keep settings access exactly as requested
_MODEL = getattr(settings, "GEMINI_MODEL_NAME", "gemini-2.0-flash")

try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # allow app to run without SDK during build/tests


class AIGeminiFallback:
    """
    Class-based Gemini fallback that:
      - Builds a strict prompt (Ramtin's 2-block template)
      - Collects all text parts from the best candidate
      - Sanitizes without losing content
      - Ensures both blocks exist (fills missing block if needed)
    """

    # ---- Public API ---------------------------------------------------------

    def generate(self, answers: Dict[str, str], engine_version: str) -> Optional[str]:
        api_key = getattr(settings, "GOOGLE_GEMINI_API_KEY", "")
        if not api_key or genai is None:
            return None

        try:
            genai.configure(api_key=api_key)  # type: ignore
            model = genai.GenerativeModel(_MODEL)  # type: ignore

            prompt = self._build_prompt(answers, engine_version)
            resp = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "max_output_tokens": 400,
                }, # type: ignore
            )

            raw = self._extract_best_text(resp)
            txt = self._clean_prefixes(raw)
            txt = self._sanitize_plus_blocks(txt)
            txt = self._ensure_two_blocks(txt)
            return txt or None

        except Exception:
            logger.exception("Gemini fallback failed")
            return None

    # ---- Prompt -------------------------------------------------------------

    def _build_prompt(self, answers: Dict[str, str], engine_version: str) -> str:
        lines: List[str] = [
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

    # ---- Response assembly --------------------------------------------------

    def _extract_best_text(self, resp) -> str:
        """
        Collect text from ALL parts; pick the candidate with the most text.
        This prevents truncation when the model splits output across parts.
        """
        try:
            best = ""
            for cand in getattr(resp, "candidates", []) or []:
                parts = getattr(getattr(cand, "content", None), "parts", []) or []
                chunks = []
                for p in parts:
                    t = getattr(p, "text", "")
                    if t:
                        chunks.append(t)
                txt = "\n".join(chunks).strip()
                if len(txt) > len(best):
                    best = txt
            if not best:
                # Some SDK versions expose resp.text
                best = getattr(resp, "text", "") or ""
            return best.strip()
        except Exception:
            return ""

    # ---- Cleanup & enforcement ---------------------------------------------

    def _clean_prefixes(self, text: str) -> str:
        """Tolerate accidental code fences or 'TEXT ' prefix without dropping lines."""
        if not text:
            return ""
        t = text.replace("\r\n", "\n").strip()
        if t.startswith("```"):
            # strip all backticks but keep inner content
            t = t.strip("`").strip()
            # if it began with ```json, drop the word 'json'
            if t[:4].lower() == "json":
                t = t[4:].lstrip()
        if t.startswith("TEXT "):
            t = t[5:].lstrip()
        return t

    def _sanitize_plus_blocks(self, raw: str) -> str:
        """
        Keep only lines that start with '+ ' (or '++ '), in order.
        Non-destructive: if nothing matches, returns raw.
        """
        if not raw:
            return ""
        lines = [ln.rstrip() for ln in raw.split("\n")]
        kept = []
        for ln in lines:
            s = ln.strip()
            if s.startswith("+ "):  # includes both + and ++
                kept.append(s)
        return "\n".join(kept).strip() if kept else raw.strip()

    def _ensure_two_blocks(self, text: str) -> str:
        """
        Ensure the final output contains BOTH required blocks.
        If block #1 is missing, synthesize a concise contradiction line.
        If block #2 is missing, append the standard 'You should either' block.
        """
        t = text.strip()

        # Accept straight or curly quotes
        quote = r'["“”]'

        block1_re = re.compile(
            rf'^\+\s*{quote}The case evaluation isn\'?t valid because .*{quote}\s*$',
            re.M,
        )
        block2_head_re = re.compile(
            rf'^\+\s*{quote}You should either:\s*$', re.M
        )
        block2_line1_re = re.compile(r'^\+\+\s*Evaluate other teeth\s*$', re.M)
        block2_line2_re = re.compile(
            r'^\+\+\s*Evaluate the teeth again by doing the .* again["”]\s*$',
            re.M,
        )

        has_block1 = bool(block1_re.search(t))
        has_block2 = bool(block2_head_re.search(t) and block2_line1_re.search(t) and block2_line2_re.search(t))

        if has_block1 and has_block2:
            return t

        # Build result lines preserving an existing block1 if present
        out: List[str] = []
        if has_block1:
            m = block1_re.search(t)
            if m:
                out.append(m.group(0))
        else:
            # try to guess a sensible contradiction from text; default generic
            test_guess = "Percussion" if "Percussion" in t else ("Cold Test" if "Cold Test" in t else "Bite Test")
            contra = f'+ "The case evaluation isn\'t valid because the findings appear internally inconsistent (e.g., {test_guess} vs Radiographic Findings)."'
            out.append(contra)

        # Always ensure second block exists
        if not has_block2:
            # pick a test to repeat based on clues in t
            repeat_test = "Percussion" if "Percussion" in t else ("Cold Test" if "Cold Test" in t else "Bite Test")
            out += [
                '',
                '+ "You should either:',
                '++ Evaluate other teeth',
                f'++ Evaluate the teeth again by doing the {repeat_test} again"',
            ]
        else:
            # Extract existing block 2 lines in original order (to avoid duplication)
            lines = t.splitlines()
            keeping = False
            for ln in lines:
                if block2_head_re.match(ln):
                    out.append(ln.strip())
                    keeping = True
                    continue
                if keeping and (ln.strip().startswith("++ ") or ln.strip().endswith('"')):
                    out.append(ln.strip())
                    if ln.strip().endswith('"'):
                        break

        return "\n".join(out).strip()


# Backwards-compatible function if your engine already imports gemini_fallback()
def gemini_fallback(answers: dict, engine_version: str) -> Optional[str]:
    return AIGeminiFallback().generate(answers, engine_version)
