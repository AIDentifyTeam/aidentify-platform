from typing import Any, Dict

from endo.diagnosis_service import DiagnosisService


class StubEngine:
    def __init__(self, response: Dict[str, Any], version: str = "test-version"):
        self._response = response
        self.version = version
        self.calls = []

    def run(self, answers: Dict[str, Any]):
        self.calls.append(answers)
        return self._response


class StubAI:
    def __init__(self, output: str | None = None):
        self.output = output
        self.calls = []

    def __call__(self, answers: Dict[str, Any], version: str):
        self.calls.append((answers, version))
        return self.output


def _service(response: Dict[str, Any], ai_output: str | None = None):
    engine = StubEngine(response)
    ai = StubAI(ai_output) if ai_output is not None else None
    service = DiagnosisService(engine=engine, ai_provider=ai) # type: ignore
    return service, engine, ai


def test_payload_with_rules_engine_results_only():
    response = {
        "source": "rules_engine",
        "results": [
            {
                "pulp_diagnosis": "Normal Pulp",
                "periapical_disease": "Normal",
                "etiology": "Possible etiologies: Caries",
                "etiology_list": ["Caries"],
            }
        ],
    }
    service, engine, ai = _service(response)

    payload = service.generate_payload({"P": "No"})

    assert payload["source"] == "rules_engine"
    assert payload["results"] == response["results"]
    assert "ai" not in payload
    assert payload["ai_assist"]["summary"].startswith("Rule engine produced")
    assert payload["ai_assist"]["messages"][0]["type"] == "info"
    assert engine.calls
    if ai:
        assert not ai.calls


def test_payload_marks_rule_override_summary():
    response = {
        "source": "rules_engine",
        "result_source": "rule_override",
        "results": [
            {
                "pulp_diagnosis": "Symptomatic Irreversible Pulpitis",
                "periapical_disease": "Symptomatic Apical Periodontitis",
                "etiology": "Possible etiologies: Not specified",
                "etiology_list": [],
            }
        ],
    }
    service, _, _ = _service(response)

    payload = service.generate_payload({})

    assert payload["result_source"] == "rule_override"
    assert "Heuristic override" in payload["ai_assist"]["summary"]


def test_ai_fallback_invoked_when_no_matches():
    response = {"source": "none", "results": []}
    service, _, ai = _service(response, ai_output="AI says check occlusion")

    payload = service.generate_payload({"P": "Yes", "tooth_number": "UL5"})

    assert payload["source"] == "ai_fallback_gemini"
    assert payload["ai"] == "AI says check occlusion"
    types = {msg["type"] for msg in payload["ai_assist"]["messages"]}
    assert {"warning", "info"}.issubset(types)
    assert ai.calls # type: ignore


def test_ai_not_invoked_when_disabled():
    response = {"source": "none", "results": []}
    service, _, ai = _service(response, ai_output="AI output")

    payload = service.generate_payload({}, use_ai_fallback=False)

    assert payload["source"] == "none"
    assert "ai" not in payload
    assert not ai.calls # type: ignore
