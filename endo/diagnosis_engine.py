import re
import pandas as pd
import os
from pathlib import Path
from datetime import datetime

pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_colwidth", None)
pd.set_option("display.expand_frame_repr", False)


class DiagnosisEngine:
    """
    Step-1: etiology_choices_from_page1(page1_answers)
      - For each answered P..X question:
          * If the sheet cell has tokens (e.g., "1- No,2- Yes"), user choice must be IN tokens (OR).
          * If the cell is BLANK, treat as wildcard (match).
      - If a matched row's 'Etiology' is 'None'/'Any'/'All' → wildcard → contribute ALL known etiologies.
      - Return unique etiologies (sorted).
    """

    PAGE1_COL_MAP = {
        "P": "Do you have/experienced a toothache?",
        "Q": "Does cold temperature trigger/aggravate the pain?",
        "R": "Does cold temperature alleviate the pain?",
        "S": "Does biting/chewing trigger/aggravate the pain?",
        "T": "Are you able to function (bite or chew) on the painful side?",
        "U": "Do you experience spontaneous pain?",
        "V": "Does the pain wake you up at night or interfere with sleep?",
        "W": "Does the pain have any of the following qualities:",
        "X": "Do you also feel the pain in other areas like jawbone, ear, or\ntemple, or eye, or cheek?",
    }

    def __init__(self, excel_path: str, sheet_name: str = "Main file"):
        if not os.path.exists(excel_path):
            raise FileNotFoundError(f"Excel file not found: {excel_path}")

        self.excel_path = excel_path
        self.version = datetime.fromtimestamp(Path(excel_path).stat().st_mtime).strftime(
            "%Y%m%d-%H%M%S"
        )

        # Load full sheet (do NOT slice columns; we need P..X)
        self.df = pd.read_excel(excel_path, sheet_name=sheet_name)

        # Normalize headers and drop all-empty columns
        self.df.columns = [str(c).strip() for c in self.df.columns]
        self.df = self.df.dropna(axis=1, how="all")

        # Keep only possible rows if column exists
        if "Possibility" in self.df.columns:
            self.df = self.df[
                self.df["Possibility"].astype(str).str.strip().str.lower() != "no"
            ]

        # Require Dx + Etiology present (Etiology may be 'None' meaning wildcard)
        self.df = self.df.dropna(subset=["Pulp Dx", "Periapical Dx", "Etiology"])

        # IMPORTANT CHANGE: do NOT drop rows where Etiology == 'none'
        # (We will treat 'none' as wildcard later.)

        # Cache ALL non-'none' etiologies (for wildcard expansion)
        all_etios_series = (
            self.df["Etiology"]
            .astype(str)
            .str.split(",")
            .explode()
            .map(lambda s: re.sub(r"^\s*\d+\s*-\s*", "", str(s or "")))  # strip "1- "
            .str.strip()
        )
        self._all_etiologies = sorted(
            e for e in set(all_etios_series) if e and e.lower() not in {"none", "any", "all"}
        )
        # map lowercase -> original for stable casing
        self._etiology_name_by_lower = {e.lower(): e for e in self._all_etiologies}

    # ---------------------------- Helpers ----------------------------

    @staticmethod
    def _norm(x: object) -> str:
        return str(x or "").strip().lower()

    @staticmethod
    def _cell_tokens(cell_value: object) -> set:
        """
        "1- No,2- Yes" -> {"no","yes"}
        BLANK/NaN -> empty set (treated as wildcard by matcher).
        """
        s = str(cell_value or "")
        if not s or s.lower() == "nan":
            return set()
        parts = [p.strip() for p in s.split(",") if p.strip()]
        toks = []
        for p in parts:
            q = re.sub(r"^\s*\d+\s*-\s*", "", p)  # strip "1- "
            toks.append(str(q).strip().lower())
        return set(toks)

    def _row_matches_page1(self, row: pd.Series, page1_answers: dict) -> bool:
        """
        For each answered question:
          - If sheet cell has tokens -> user's choice must be IN tokens (OR).
          - If sheet cell is BLANK -> wildcard (match).
        Unanswered qids are ignored.
        """
        if not isinstance(page1_answers, dict):
            return True
        for qid, col in self.PAGE1_COL_MAP.items():
            if qid not in page1_answers:
                continue
            user_choice = self._norm(page1_answers[qid])
            tokens = self._cell_tokens(row.get(col, ""))
            if not tokens:
                continue  # wildcard (no constraint)
            if user_choice not in tokens:
                return False
        return True

    @staticmethod
    def _etiology_tokens(cell_value: object) -> set:
        """
        Split etiology cell like "Caries, Trauma" -> {"caries","trauma"} (lowercased).
        Treat 'none'/'any'/'all' specially (handled by caller).
        """
        s = str(cell_value or "")
        if not s or s.lower() == "nan":
            return set()
        parts = [p.strip() for p in s.split(",") if p.strip()]
        toks = []
        for p in parts:
            q = re.sub(r"^\s*\d+\s*-\s*", "", p)  # strip "1- "
            toks.append(str(q).strip().lower())
        return set(toks)

    # -------------------- Step-1 availability -------------------

    def etiology_choices_from_page1(self, page1_answers: dict) -> list:
        """
        Return sorted unique etiologies from rows matching P..X answers.
        If any matched row has Etiology == 'none'/'any'/'all' -> return ALL known etiologies.
        """
        answers = page1_answers or {}
        mask = self.df.apply(lambda r: self._row_matches_page1(r, answers), axis=1)
        matched = self.df[mask]

        # If ANY matched row signals wildcard etiology, return all
        etio_cells = matched["Etiology"].astype(str)
        has_wildcard = etio_cells.str.strip().str.lower().isin({"none", "any", "all"}).any()
        if has_wildcard:
            return list(self._all_etiologies)  # already sorted

        # Else accumulate specific etiologies from matched rows
        res_lower = set()
        for val in etio_cells:
            for t in self._etiology_tokens(val):
                if t in {"none", "any", "all"} or not t:
                    continue
                res_lower.add(t)

        # Map back to original casing; sort
        out = sorted(self._etiology_name_by_lower.get(t, t) for t in res_lower) # type: ignore
        return out

    # -------------------- Existing final diagnosis -------------------

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

            # Check etiology (Page-2 selection)
            etiologies = answers.get("Etiology Assessment", [])
            if etiologies and "not sure" not in [e.lower() for e in etiologies]:
                if not any(e.lower() in str(row.get("Etiology", "")).lower() for e in etiologies):
                    continue

            # Clinical/Radiographic tests
            field_map = {
                "Cold Test": "Cold Test",
                "Heat Test": "Heat Test*",
                "Electric Pulp Test (EPT)": "EPT*",
                "Palpation Test": "Palpation",
                "Percussion Test": "Percussion",
                "Bite Test": "Bite Test",
                "Swelling": "Fluctuant Swelling",
                "Sinus Tract": "Sinus Tract",
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
                    "etiology": row.get("Etiology", ""),
                })

        return results
