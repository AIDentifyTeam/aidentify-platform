# diagnosis_engine.py
from django.conf import settings
import pandas as pd
import os

# Load once
df = pd.read_excel(os.path.join(settings.BASE_DIR, "endo/data/pulp.xlsx"))

def calculate_diagnosis(answers: dict):
    if answers.get("Chief complaint", "").strip().lower() == "no":
        return {"skip_reason": "Chief complaint is No. Skipping diagnosis."}

    selected_etiologies = answers.get("Etiology assessment", [])
    if isinstance(selected_etiologies, str):
        selected_etiologies = [selected_etiologies]

    match_results = []

    for _, row in df.iterrows():
        match = True

        # If etiology is not 'Not sure', filter
        if "Not sure" not in selected_etiologies:
            if row["Etiology"] not in selected_etiologies:
                continue

        for column in df.columns[4:13]:  # Q4 to Q13 columns
            expected_values = [x.strip().split('- ')[-1] for x in str(row[column]).split(',') if pd.notna(x)]
            user_answer = answers.get(column.strip(), '').strip()
            if user_answer and user_answer not in expected_values:
                match = False
                break

        if match:
            match_results.append({
                "pulp_diagnosis": row["Pulp Dx"],
                "periapical_diagnosis": row["Periapical Dx"],
                "etiology": row["Etiology"]
            })

    if not match_results:
        return {"results": [{
                "pulp_diagnosis": "Not possible to determine",
                "periapical_diagnosis": "Not possible to determine",
                "etiology": "Not possible to determine"
            }]}

    return {"results": match_results}

