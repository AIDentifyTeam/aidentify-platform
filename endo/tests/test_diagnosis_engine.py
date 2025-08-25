# endo/tests/test_diagnosis_engine_flat_rows.py
import os
import re
from typing import Dict, List
from django.test import SimpleTestCase

from endo.diagnosis_engine import DiagnosisEngine


# Frontend options (for validation / fallbacks)
CLINICAL_OPTIONS = {
    "Cold Test": ["Negative", "Normal", "Hypersensitive", "Lingering Pain"],
    "Heat Test*": ["Negative", "Normal", "Hypersensitive", "Lingering Pain"],
    "EPT*": ["Negative", "Positive"],
    "Palpation": ["Negative", "Positive"],
    "Percussion": ["Negative", "Positive"],
    "Bite Test": ["Negative", "Positive"],
    "Fluctuant Swelling": ["Negative", "Positive"],
    "Sinus Tract": ["Negative", "Positive"],
}

PAGE1_COL_MAP = {
    "P": "Do you have/experienced a toothache?",
    "Q": "Does cold temperature trigger/aggravate the pain?",
    "R": "Does cold temperature alleviate the pain?",
    "S": "Does biting/chewing trigger/aggravate the pain?",
    "T": "Are you able to function (bite or chew) on the painful side?",
    "U": "Do you experience spontaneous pain?",
    "V": "Does the pain wake you up at night or interfere with sleep?",
    "W": "Does the pain have any of the following qualities:",
    "X": "Do you also feel the pain in other areas like jawbone, ear, or\n"
         "temple, or eye, or cheek?",
}

FIELD_MAP = {
    "Cold Test": "Cold Test",
    "Heat Test": "Heat Test*",
    "Electric Pulp Test (EPT)": "EPT*",
    "Palpation Test": "Palpation",
    "Percussion Test": "Percussion",
    "Bite Test": "Bite Test",
    "Swelling": "Fluctuant Swelling",
    "Sinus Tract": "Sinus Tract",
}

def _tokens(cell) -> List[str]:
    s = str(cell or "")
    if not s or s.lower() == "nan":
        return []
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out = []
    for p in parts:
        q = re.sub(r"^\s*\d+\s*-\s*", "", p)
        out.append(q.strip())
    return out

def _lower(x): return str(x or "").strip().lower()


class DiagnosisEngineFlatRowTests(SimpleTestCase):
    """
    For EACH row in the sheet, synthesize one (or minimal) flat answer dict
    that should match that row based on the sheet's own tokens, then assert
    diagnose() returns a record whose (Pulp Dx, Periapical Dx, Etiology)
    equals that row's triple.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = DiagnosisEngine("endo/data/pulp.xlsx")

    def setUp(self):
        if getattr(self, "engine", None) is None:
            self.skipTest(getattr(self, "skip_reason", "Excel not available"))

    def _answers_from_row(self, row) -> Dict[str, object]:
        """
        Build a single flat answer set that should satisfy this row.
        - Chief Complaint -> 'Yes' (to allow diagnoses)
        - Endo history inferred from 'Previously treated' / 'Previously initiated'
        - Etiology Assessment: choose one etiology from the row (or 'Not sure' if wildcard)
        - For every question column (P..X and clinicals), pick ONE token present in the cell.
          If the cell is blank, omit the field (wildcard).
        """
        answers: Dict[str, object] = {"Chief Complaint": "Yes"}

        # Endo history
        prev_tr = _lower(row.get("Previously treated", ""))
        prev_in = _lower(row.get("Previously initiated", ""))
        if "positive" in prev_tr:
            answers["Endodontic Treatment History"] = "Previously treated"
        elif "positive" in prev_in:
            answers["Endodontic Treatment History"] = "Previously initiated"
        else:
            answers["Endodontic Treatment History"] = "No previous endodontics treatment"

        # Etiology Assessment
        etiologies = _tokens(row.get("Etiology", ""))
        if not etiologies or _lower(row.get("Etiology", "")) in {"none", "any", "all"}:
            answers["Etiology Assessment"] = ["Not sure"]
        else:
            # choose ONE of the etiologies from the cell
            answers["Etiology Assessment"] = [etiologies[0]]

        # P..X
        for qid, col in PAGE1_COL_MAP.items():
            if col in self.engine.df.columns:
                toks = _tokens(row.get(col, ""))
                if toks:  # pick one
                    answers[qid] = toks[0]

        # Clinicals
        for qid, col in FIELD_MAP.items():
            if col in self.engine.df.columns:
                toks = _tokens(row.get(col, ""))
                if toks:
                    # pick the first token that exists in our frontend option set (if known)
                    wanted = toks[0]
                    opts = CLINICAL_OPTIONS.get(col)
                    if opts and all(_lower(wanted) != _lower(o) for o in opts):
                        # try to find a close match ignoring casing/spacing
                        for o in opts:
                            if _lower(o) in _lower(",".join(toks)):
                                wanted = o
                                break
                    answers[qid] = wanted

        return answers

    def test_each_row_yields_matching_diagnosis_triple(self):
        """
        For every row, construct answers from that row and assert there is at least one
        diagnose() result with an exact triple match on:
          Pulp Dx, Periapical Dx, Etiology
        """
        df = self.engine.df.reset_index(drop=True)
        tested = 0
        for i, row in df.iterrows():
            pulp = str(row.get("Pulp Dx", "")).strip()
            periap = str(row.get("Periapical Dx", "")).strip()
            etio = str(row.get("Etiology", "")).strip()

            if not pulp or not periap or not etio:
                continue  # engine already drops rows without these; skip defensively

            answers = self._answers_from_row(row)

            out = self.engine.diagnose(answers)
            self.assertIsInstance(out, list)

            # Exact triple present?
            got_match = any(
                str(r.get("pulp_diagnosis", "")).strip() == pulp and
                str(r.get("periapical_disease", "")).strip() == periap and
                str(r.get("etiology", "")).strip() == etio
                for r in out
            )

            self.assertTrue(
                got_match,
                msg=(
                    f"Row {i} not reproduced by diagnose().\n"
                    f"Answers built: {answers}\n"
                    f"Expected triple: (Pulp Dx='{pulp}', Periapical Dx='{periap}', Etiology='{etio}')\n"
                    f"Got: {out}"
                ),
            )
            tested += 1

        self.assertGreater(tested, 0, "No rows tested—check the sheet content")

    def test_specific_case_expected_pairs(self):
        # Inputs from the screenshot/case
        answers = {
            "chief_complaint": "No",
            "P": "Yes",
            "Q": "Longer than few seconds",
            "R": "No",
            "S": "Yes",
            "T": "No",
            "U": "Yes",
            "V": "Yes",
            "W": "Sharp",
            "X": "Yes",
            "etiology_assessment": ["Vertical root fracture"],  # user may toggle; engine still can return multiple matches
            "endo_history": "No previous endodontics treatment",
            "E": "Hypersensitive",
            "F": "Hypersensitive",
            "G": "Positive",
            "H": "Positive",
            "I": "Positive",
            "J": "Positive",
            "K": "Negative",
            "L": "Negative",
            "radiographic_findings": "PDL widening",
        }

        def norm(s: object) -> str:
            import re as _re
            return _re.sub(r"\s+", " ", str(s or "")).strip().lower()

        out = self.engine.diagnose(answers)
        self.assertIsInstance(out, list)
        self.assertGreater(len(out), 0, f"No diagnosis returned. Got: {out}")

        got = {
            (
                norm(r.get("pulp_diagnosis")),
                norm(r.get("periapical_disease")),
                norm(r.get("etiology")),
            )
            for r in out
        }

        expected = {
            (
                "irreversible pulpitis (symptomatic)",
                "symptomatic apical periodontitis",
                "vertical root fracture",
            ),
        }

        missing = expected - got
        self.assertFalse(
            missing,
            f"Expected pairs not found.\nMissing: {missing}\nGot: {got}\nRaw: {out}",
        )
