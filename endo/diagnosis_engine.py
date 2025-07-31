import pandas as pd
import os


# Show all rows and columns
pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)

# Show full content of each cell
pd.set_option("display.max_colwidth", None)

# Avoid line wrapping
pd.set_option("display.expand_frame_repr", False)


class DiagnosisEngine:
    def __init__(self, excel_path: str):
        if not os.path.exists(excel_path):
            raise FileNotFoundError(f"Excel file not found: {excel_path}")
        self.df = pd.read_excel(excel_path, sheet_name="pulp_periapical_etiology_combin")
        # Keep only columns up to and including 'O' (15 columns)
        self.df = self.df.iloc[:, :15]
        # Normalize column names
        self.df.columns = [str(c).strip() for c in self.df.columns]
        # Clean ghost content
        self.df = self.df.dropna(axis=1, how="all")
        # Only consider rows where possibility is Yes
        if "Possibility" in self.df.columns:
            self.df = self.df[self.df["Possibility"].astype(str).str.strip().str.lower() != "no"]
        self.df = self.df.dropna(subset=["Pulp Dx", "Periapical Dx", "Etiology"])

        # ✅ Drop rows with missing or empty Etiology
        if "Etiology" in self.df.columns:
            self.df = self.df[self.df["Etiology"].notna()]
            self.df = self.df[self.df["Etiology"].astype(str).str.strip().str.lower() != "none"]


    def diagnose(self, answers: dict):
        if answers.get("Chief Complaint", "").lower() == "no":
            return []

        results = []

        for _, row in self.df.iterrows():
            match = True

            # Check endo history
            hist = answers.get("Endodontic Treatment History", "").lower()
            if hist == "no previous endodontics treatment":
                if "negative" not in str(row.get("Previously treated", "")).lower() or \
                "negative" not in str(row.get("Previously initiated", "")).lower():
                    continue
            elif hist == "previously treated":
                if "positive" not in str(row.get("Previously treated", "")).lower():
                    continue
            elif hist == "previously initiated":
                if "positive" not in str(row.get("Previously initiated", "")).lower():
                    continue

            # Check etiology
            etiologies = answers.get("Etiology Assessment", [])
            if etiologies and "not sure" not in [e.lower() for e in etiologies]:
                if not any(e.lower() in str(row.get("Etiology", "")).lower() for e in etiologies):
                    continue

            # All other fields
            field_map = {
                "Cold Test": "Cold Test",
                "Heat Test": "Heat Test*",
                "Electric Pulp Test (EPT)": "EPT*",
                "Palpation Test": "Palpation",
                "Percussion Test": "Percussion",
                "Bite Test": "Bite Test",
                "Swelling": "Fluctuant Swelling",
                "Sinus Tract": "Sinus Tract"
            }

            for qid, col in field_map.items():
                ans = answers.get(qid)
                if not ans:
                    continue  # Skip optional/missing fields

                answer = str(ans).strip().lower()
                cell = str(row.get(col, "")).lower()
                tokens = [t.split("-")[-1].strip().lower() for t in cell.split(",")]
                if answer not in tokens:
                    match = False
                    break

            if match:
                results.append({
                    "pulp_diagnosis": row.get("Pulp Dx", ""),
                    "periapical_disease": row.get("Periapical Dx", ""),
                    "etiology": row.get("Etiology", "")
                })

        return results


