# endo/tests/test_diagnosis_engine_and_visits.py
import re
from pathlib import Path
from typing import Dict, List

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model
from endo.models import Patient, VisitHistory
from endo.diagnosis_engine import DiagnosisEngine


# ====== Helpers (shared) ======

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

def _lower(x): 
    return str(x or "").strip().lower()


# Match the engine’s mapping, including Radiographic (N)
FIELD_ID_TO_COL = {
    "E": "Cold Test",
    "F": "Heat Test*",
    "G": "EPT*",
    "H": "Palpation",
    "I": "Percussion",
    "J": "Bite Test",
    "K": "Fluctuant Swelling",
    "L": "Sinus Tract",
    "N": "Periapical status",
}

PAGE1_ID_TO_COL = {
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

# Frontend-visible / friendly options (used only to pick a compatible value if needed)
CLINICAL_OPTIONS = {
    "Cold Test": ["Negative", "Normal", "Hypersensitive", "Lingering Pain"],
    "Heat Test*": ["Negative", "Normal", "Hypersensitive", "Lingering Pain"],
    "EPT*": ["Negative", "Positive"],
    "Palpation": ["Negative", "Positive"],
    "Percussion": ["Negative", "Positive"],
    "Bite Test": ["Negative", "Positive"],
    "Fluctuant Swelling": ["Negative", "Positive"],
    "Sinus Tract": ["Negative", "Positive"],
    # Periapical status isn’t shown in FE CLINICAL_OPTIONS here; we’ll use sheet tokens.
}


# ========= DB-FREE ENGINE TESTS =========

class DiagnosisEngineFlatRowTests(SimpleTestCase):
    """
    For EACH row in the sheet, synthesize a minimal flat answers dict that should
    match that row and assert diagnose() returns a triple equal to the row.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Resolve Excel path robustly
        base = Path(getattr(settings, "BASE_DIR", Path.cwd()))
        # Adjust if your xlsx lives somewhere else:
        xlsx = base / "endo" / "data" / "pulp.xlsx"
        cls.engine = DiagnosisEngine(str(xlsx))

    def setUp(self):
        if getattr(self, "engine", None) is None:
            self.skipTest("DiagnosisEngine not initialized (missing Excel).")

    def _answers_from_row(self, row) -> Dict[str, object]:
        """
        Build a single flat answer set that should satisfy this row.
        - Chief Complaint: 'Yes'
        - Endo history inferred from 'Previously treated' / 'Previously initiated'
        - Etiology Assessment: choose one etiology from the row (or 'Not sure' if wildcard)
        - For P..X and E..L,N: pick ONE token present in the cell (omit if blank)
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
            answers["Etiology Assessment"] = [etiologies[0]]

        # P..X history answers
        for qid, col in PAGE1_ID_TO_COL.items():
            if col in self.engine.df.columns:
                toks = _tokens(row.get(col, ""))
                if toks:
                    answers[qid] = toks[0]

        # Clinical / Radiographic answers (E..L + N)
        for fid, col in FIELD_ID_TO_COL.items():
            if col not in self.engine.df.columns:
                continue
            toks = _tokens(row.get(col, ""))
            if not toks:
                continue
            wanted = toks[0]
            # If FE option set differs slightly, try to pick a compatible FE string
            opts = CLINICAL_OPTIONS.get(col)
            if opts and all(_lower(wanted) != _lower(o) for o in opts):
                for o in opts:
                    if _lower(o) in ",".join(_lower(t) for t in toks):
                        wanted = o
                        break
            answers[fid] = wanted

        return answers

    def test_each_row_yields_matching_diagnosis_triple(self):
        df = self.engine.df.reset_index(drop=True)
        tested = 0

        for i, row in df.iterrows():
            pulp = str(row.get("Pulp Dx", "")).strip()
            periap = str(row.get("Periapical Dx", "")).strip()
            etio = str(row.get("Etiology", "")).strip()
            if not pulp or not periap or not etio:
                continue  # engine drops these; skip defensively

            answers = self._answers_from_row(row)
            out = self.engine.diagnose(answers)
            self.assertIsInstance(out, list)

            got_match = any(
                str(r.get("pulp_diagnosis", "")).strip() == pulp and
                str(r.get("periapical_disease", "")).strip() == periap and
                str(r.get("etiology", "")).strip() == etio
                for r in out
            )
            self.assertTrue(
                got_match,
                msg=(
                    f"Row {i} not reproduced.\n"
                    f"Answers: {answers}\n"
                    f"Expected: (Pulp Dx='{pulp}', Periapical Dx='{periap}', Etiology='{etio}')\n"
                    f"Got: {out}"
                ),
            )
            tested += 1

        self.assertGreater(tested, 0, "No rows tested—check the sheet content")

    def test_specific_case_expected_pairs(self):
        answers = {
            "chief_complaint": "No",   # ✅ allowed, no early exit
            "P": "Yes",
            "Q": "Longer than few seconds",
            "R": "No",
            "S": "Yes",
            "T": "No",
            "U": "Yes",
            "V": "Yes",
            "W": "Sharp",
            "X": "Yes",
            "etiology_assessment": ["Vertical root fracture"],
            "endo_history": "No previous endodontics treatment",
            "E": "Hypersensitive",
            "F": "Hypersensitive",
            "G": "Positive",
            "H": "Positive",
            "I": "Positive",
            "J": "Positive",
            "K": "Negative",
            "L": "Negative",
            "N": "PDL widening",
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
        self.assertFalse(missing, f"Missing: {missing}\nGot: {got}\nRaw: {out}")



# ========= DB + API PERMISSION TESTS =========

class VisitPermissionsTests(TestCase):
    """
    Uses DRF APIClient with real DB. Ensures:
      • Owner can PATCH/DELETE
      • Other doctor cannot access/modify
      • Cannot create a visit for someone else’s patient
    """

    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        # two doctors
        self.doc1 = User.objects.create_user(email="doc1@example.com", password="pass1234", first_name="A", last_name="Doc") # type: ignore
        self.doc2 = User.objects.create_user(email="doc2@example.com", password="pass1234", first_name="B", last_name="Doc") # type: ignore

        # patients (each belongs to a different doctor)
        self.p1 = Patient.objects.create(doctor=self.doc1, first_name="Alice", last_name="Smith", patient_id="P0001")
        self.p2 = Patient.objects.create(doctor=self.doc2, first_name="Bob", last_name="Brown", patient_id="P0002")

        # one visit owned by doc1
        self.visit = VisitHistory.objects.create(
            patient=self.p1,
            doctor=self.doc1,
            tooth_number="12",
            answers={"chief_complaint": "Yes"},
            results=[],
            case_id="P0001-CID0000001",
        )

    def test_owner_can_patch_and_delete(self):
        self.client.force_authenticate(self.doc1) # type: ignore
        r = self.client.patch(f"/api/visits/{self.visit.id}/", {"tooth_number": "11"}, format="json") # type: ignore
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data.get("tooth_number"), "11") # type: ignore

        r = self.client.delete(f"/api/visits/{self.visit.id}/") # type: ignore
        self.assertIn(r.status_code, (204, 200), r.content)

    def test_other_doctor_cannot_access(self):
        self.client.force_authenticate(self.doc2) # type: ignore

        # retrieve should be blocked (404 due to queryset filtering or 403 if you add object permission)
        r = self.client.get(f"/api/visits/{self.visit.id}/") # type: ignore
        self.assertIn(r.status_code, (404, 403), r.content)

        r = self.client.patch(f"/api/visits/{self.visit.id}/", {"tooth_number": "10"}, format="json") # type: ignore
        self.assertIn(r.status_code, (404, 403), r.content)

        r = self.client.delete(f"/api/visits/{self.visit.id}/") # type: ignore
        self.assertIn(r.status_code, (404, 403), r.content)

    def test_cannot_create_for_foreign_patient(self):
        # doc2 tries to create visit for doc1's patient
        self.client.force_authenticate(self.doc2) # type: ignore
        r = self.client.post(
            "/api/visits/",
            {"patient": self.p1.id, "tooth_number": "22"}, # type: ignore
            format="json",
        )
        # Expect 403 from perform_create guard
        self.assertEqual(r.status_code, 403, r.content)
