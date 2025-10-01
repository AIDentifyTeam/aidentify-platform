"""Diagnosis orchestration layer with AI assist and warning logic."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

from core.settings import EXCEL_CORE_PATH
from endo.ai_fallback import gemini_fallback
from endo.diagnosis_engine import DiagnosisEngine

AIProvider = Callable[[Dict[str, object], str], Optional[str]]


# ----------------------------- data objects -----------------------------

@dataclass(frozen=True)
class AssistMessage:
    """Structured message presented to clinicians alongside diagnoses."""

    type: str
    text: str


# ----------------------------- utility helpers -----------------------------

def _norm(value: object) -> str:
    return str(value or "").strip().lower()


def _parse_tooth_number(raw: object) -> Optional[int]:
    if raw is None:
        return None
    digits = "".join(ch for ch in str(raw).strip() if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _is_maxillary_posterior(tooth_num: Optional[int]) -> bool:
    if tooth_num is None:
        return False
    # FDI notation: posterior maxillary quadrants are 1 (14–18) and 2 (24–28)
    if 14 <= tooth_num <= 18 or 24 <= tooth_num <= 28:
        return True
    return False


def _pain_reported(answers: Dict[str, object]) -> bool:
    primary = _norm(answers.get("P"))
    if primary in {"yes", "positive", "present", "y"}:
        return True
    secondary = _norm(answers.get("chief_complaint"))
    return secondary in {"yes", "toothache", "pain"}


def _messages_from_context(
    *,
    answers: Dict[str, object],
    results: Iterable[Dict[str, Any]],
    result_source: str,
    ai_output: Optional[str],
) -> List[AssistMessage]:
    messages: List[AssistMessage] = []

    tooth_number_raw = (
        answers.get("tooth_number")
        or answers.get("Tooth Number")
        or answers.get("toothNumber")
        or answers.get("tooth")
    )
    tooth_num = _parse_tooth_number(tooth_number_raw)

    if _pain_reported(answers) and _is_maxillary_posterior(tooth_num):
        messages.append(
            AssistMessage(
                type="warning",
                text=(
                    "For posterior maxillary teeth, reported pain can be referred from the"
                    " mandibular arch. Confirm the source of pain before finalising treatment."
                ),
            )
        )

    if ai_output:
        messages.append(
            AssistMessage(
                type="info",
                text="AI analysis flagged inconsistencies; review the generated explanation before proceeding.",
            )
        )

    results_list = list(results)
    if not messages and results_list:
        messages.append(
            AssistMessage(
                type="info",
                text="No additional warnings detected. Findings appear consistent with the rule-based diagnosis; still confirm clinically.",
            )
        )
    elif not messages and not ai_output:
        messages.append(
            AssistMessage(
                type="warning",
                text="Automated analysis could not identify a diagnosis. Reassess tests or gather additional data.",
            )
        )

    return messages


def _summary_from_context(
    results: Iterable[Dict[str, Any]],
    result_source: str,
    ai_output: Optional[str],
) -> str:
    results_list = list(results)
    if results_list:
        if result_source == "rule_override":
            return "Heuristic override generated a provisional diagnosis; validate against clinical findings."
        return f"Rule engine produced {len(results_list)} option(s); use clinical judgement to confirm."
    if ai_output:
        return "No rule-based match. Review the AI analysis and reassess clinically."
    return "No automated match. Re-evaluate the findings and consider additional tests."


def _build_ai_assist(
    *,
    answers: Dict[str, object],
    results: Iterable[Dict[str, Any]],
    result_source: str,
    ai_output: Optional[str],
) -> Dict[str, Any]:
    results_list = list(results)
    messages = _messages_from_context(
        answers=answers,
        results=results_list,
        result_source=result_source,
        ai_output=ai_output,
    )
    summary = _summary_from_context(results_list, result_source, ai_output)

    tooth_number_raw = (
        answers.get("tooth_number")
        or answers.get("Tooth Number")
        or answers.get("toothNumber")
        or answers.get("tooth")
    )

    # derive a single overall type for frontend severity badge
    if results_list and result_source == "rules_engine" and not any(m.type in {"warning", "danger"} for m in messages):
        overall_type = "success"
    elif results_list and (result_source == "rule_override" or any(m.type == "warning" for m in messages)):
        overall_type = "warning"
    elif not results_list:
        overall_type = "danger" if (ai_output or messages) else "info"
    else:
        overall_type = "info"

    return {
        "source": "rule_assist",
        "type": overall_type,
        "summary": summary,
        "messages": [asdict(msg) for msg in messages],
        "result_source": result_source,
        "context": {
            "tooth_number": tooth_number_raw,
            "pain_reported": _pain_reported(answers),
        },
    }


# ----------------------------- service layer -----------------------------

class DiagnosisService:
    """Coordinates rule-engine results with AI fallback guidance."""

    def __init__(
        self,
        engine: Optional[DiagnosisEngine],
        ai_provider: Optional[AIProvider] = None,
        engine_init_error: Optional[Exception] = None,
    ) -> None:
        self._engine = engine
        self._ai_provider = ai_provider
        self._engine_init_error = engine_init_error

    @property
    def engine(self) -> DiagnosisEngine:
        if self._engine is None:
            raise RuntimeError("Diagnosis engine is unavailable") from self._engine_init_error
        return self._engine

    def generate_payload(
        self,
        answers: Dict[str, object],
        use_ai_fallback: bool = True,
    ) -> Dict[str, Any]:
        answers = answers or {}
        base = self.engine.run(answers)

        results: List[Dict[str, Any]] = list(base.get("results", [])) # type: ignore
        result_source = base.get("result_source", "rules_engine" if results else "none")
        response_source = base.get("source", "rules_engine" if results else "none")

        ai_output: Optional[str] = None
        if not results and use_ai_fallback and self._ai_provider is not None:
            ai_output = self._ai_provider(answers, self.engine.version)
            if ai_output:
                response_source = "ai_fallback_gemini"

        ai_assist = _build_ai_assist(
            answers=answers,
            results=results,
            result_source=result_source, # type: ignore
            ai_output=ai_output,
        )

        payload: Dict[str, Any] = {
            "source": response_source,
            "engine_version": self.engine.version,
            "results": results,
            "ai_assist": ai_assist,
        }

        if results and result_source not in {"rules_engine", "none", None}:
            payload["result_source"] = result_source

        if ai_output:
            payload["ai"] = ai_output 

        return payload


# ----------------------------- module-level singletons -----------------------------

_engine_error: Optional[Exception]
try:
    diagnosis_engine = DiagnosisEngine(EXCEL_CORE_PATH)
except Exception as exc:  # pragma: no cover - environment specific
    diagnosis_engine = None
    _engine_error = exc
else:
    _engine_error = None

diagnosis_service = DiagnosisService(
    engine=diagnosis_engine,
    ai_provider=gemini_fallback,
    engine_init_error=_engine_error,
)


def generate_diagnosis_payload(
    answers: Dict[str, object],
    use_ai_fallback: bool = True,
) -> Dict[str, Any]:
    """Convenience wrapper around the default diagnosis service instance."""

    return diagnosis_service.generate_payload(answers, use_ai_fallback=use_ai_fallback)


__all__ = [
    "AssistMessage",
    "DiagnosisService",
    "diagnosis_engine",
    "diagnosis_service",
    "generate_diagnosis_payload",
]
