# diagnosis_engine.py
from django.conf import settings
import pandas as pd
import os

# Load once
df = pd.read_excel(os.path.join(settings.BASE_DIR, "endo/data/pulp.xlsx"))
# df = df[df['Possibility'] == 'Yes']  # Use only valid rules

def calculate_diagnosis(answers: dict):
    for _, row in df.iterrows():
        match = True
        for column in df.columns[5:]:  # Start from 'Cold Test'
            rule_answer = row[column]
            if pd.isna(rule_answer): # type: ignore
                continue
            # Remove prefix like '1- ' or '2- ' before comparing
            expected = rule_answer.split('- ', 1)[-1].strip()
            user_answer = answers.get(column.strip(), '').strip()
            if expected != user_answer:
                match = False
                break
        if match:
            return {
                "pulp_diagnosis": row["Pulp Dx"],
                "periapical_disease": row["Periapical Disease"],
                "etiology": row["Etiology"]
            }
    return {
        "pulp_diagnosis": "Test goes wrong! it doesn't match with the logic!",
        "periapical_disease": "Test goes wrong! it doesn't match with the logic!",
        "etiology": "Test goes wrong! it doesn't match with the logic!"
    }
