# endo/tests/test_diagnosis_engine.py

from django.test import TestCase
from endo.diagnosis_engine import calculate_diagnosis
import pandas as pd
import os
from django.conf import settings


class DiagnosisEngineTest(TestCase):
    def setUp(self):
        excel_path = os.path.join(settings.BASE_DIR, 'endo/data/pulp.xlsx')
        self.df = pd.read_excel(excel_path)
        self.df = self.df[self.df['Possibility'] == 'Yes']

    def test_all_possible_combinations(self):
        total = 0
        matched = 0

        for _, row in self.df[self.df["Etiology"].notna()].iterrows():
            total += 1

            # Build input dict simulating answers
            answers = {
                "Chief complaint": "Yes",  # To pass initial check
                "Etiology assessment": (
                    [str(row["Etiology"])] if pd.notna(row["Etiology"]) else ["Not sure"]
                ),
            }

            # Add all clinical and radiographic answers (columns E to L, then N)
            for column in self.df.columns[4:13]:  # E to L
                if pd.notna(row[column]):
                    val = row[column].split(',')[0].split('- ')[-1].strip()
                    answers[column.strip()] = val

                    result = calculate_diagnosis(answers)

                    print("=" * 60)
                    print("Input:", answers)
                    print("Output:", result)

                    if "results" in result:
                        for r in result["results"]:
                            if isinstance(r, dict):
                                if (
                                    r.get("pulp_diagnosis") == row["Pulp Dx"]
                                    and r.get("periapical_diagnosis") == row["Periapical Dx"]
                                    and r.get("etiology") == row["Etiology"]
                                ):
                                    matched += 1
                                    print("✅ Match found\n")
                                    break
                        else:
                            print(f"❌ Mismatch: Expected [{row['Pulp Dx']} / {row['Periapical Dx']} / {row['Etiology']}]\n")
                    else:
                        print(f"❌ No result for: {row['Pulp Dx']} / {row['Periapical Dx']} / {row['Etiology']}\n")


        print(f"Matched {matched}/{total} combinations.")

        self.assertEqual(matched, total, "Some expected diagnoses did not match.")
