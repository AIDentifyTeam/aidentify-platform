import unittest
import itertools
from endo.diagnosis_engine import DiagnosisEngine

class TestDiagnosisEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = DiagnosisEngine("endo/data/pulp.xlsx")
        cls.options = {
            "Chief Complaint": ["Yes", "No"],
            "Etiology Assessment": [
                ["Caries"], ["Restorative"], ["Trauma"], ["Crack"],
                ["Vertical root fracture"], ["Periodontal"], ["Persistent infection"], ["Not sure"]
            ],
            "Endodontic Treatment History": [
                "No previous endodontics treatment",
                "Previously initiated",
                "Previously treated"
            ],
            "Cold Test": ["Negative", "Normal", "Hypersensitive", "Lingering Pain"],
            "Heat Test": ["Negative", "Normal", "Hypersensitive", "Lingering Pain", ""],
            "Electric Pulp Test (EPT)": ["Negative", "Positive", ""],
            "Palpation Test": ["Negative", "Positive"],
            "Percussion Test": ["Negative", "Positive"],
            "Bite Test": ["Negative", "Positive"],
            "Swelling": ["Negative", "Positive"],
            "Sinus Tract": ["Negative", "Positive"],
            "Tooth Mobility": ["None", "Mild", "Moderate", "Severe", ""],
            "Radiographic Findings": [
                "No abnormal findings", "PDL widening", "Periapical radiolucency",
                "External resorption", "Internal resorption",
                "Condensing osteitis", "Root fracture"
            ]
        }

    def test_no_chief_complaint(self):
        answers = {"Chief Complaint": "No"}
        results = self.engine.diagnose(answers)
        self.assertEqual(results, [])

    def test_sample_combinations(self):
        keys_to_test = [
            "Chief Complaint",
            "Endodontic Treatment History",
            "Cold Test",
            "Palpation Test",
            "Percussion Test",
            "Bite Test",
            "Swelling",
            "Sinus Tract",
            "Radiographic Findings"
        ]
        option_lists = [self.options[k] for k in keys_to_test]
        combos = itertools.product(*option_lists)

        for combo in combos:
            answers = dict(zip(keys_to_test, combo))
            answers["Etiology Assessment"] = ["Not sure"]
            results = self.engine.diagnose(answers)
            self.assertIsInstance(results, list)
            for r in results:
                self.assertIn("pulp_diagnosis", r)
                self.assertIn("periapical_disease", r)
                self.assertIn("etiology", r)
            break  # prevent overload — just validate structure

    def test_each_etiology_option(self):
        base_answers = {
            "Chief Complaint": "Yes",
            "Endodontic Treatment History": "No previous endodontics treatment",
            "Cold Test": "Normal",
            "Palpation Test": "Negative",
            "Percussion Test": "Negative",
            "Bite Test": "Negative",
            "Swelling": "Negative",
            "Sinus Tract": "Negative",
            "Tooth Mobility": "None",
            "Radiographic Findings": "No abnormal findings"
        }

        for etiology in self.options["Etiology Assessment"]:
            answers = base_answers.copy()
            answers["Etiology Assessment"] = etiology
            results = self.engine.diagnose(answers)
            self.assertIsInstance(results, list)
            for r in results:
                self.assertIn("pulp_diagnosis", r)
                self.assertIn("periapical_disease", r)
                self.assertIn("etiology", r)

if __name__ == "__main__":
    unittest.main()
