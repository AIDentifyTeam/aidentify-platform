# endo/diagnosis_engine.py
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set
from endo.ai_fallback import gemini_fallback
import pandas as pd

pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_colwidth", None)
pd.set_option("display.expand_frame_repr", False)


# Page 1 (history) — IDs P..X
PAGE1_ID_TO_COL = {
    "P": "Do you have/experienced a toothache?",
    "Q": "Does cold temperature trigger/aggravate the pain?",
    "R": "Does cold temperature alleviate the pain?",
    "S": "Does biting/chewing trigger/aggravate the pain? Are you incapable of functioning (biting or chewing) on the painful side?",
    "T": "Do you experience spontaneous pain?",
    "U": "Does the pain wake you up at night or interfere with sleep?",
    "V": "Does the pain have any of the following qualities:",
    "W": "Do you also feel the pain in other areas like jawbone, ear, or\n"
        "temple, or eye, or cheek?",
}

# Clinical / Radiographic — IDs E..L
FIELD_ID_TO_COL = {
    "E": "Cold Test",
    "F": "Heat Test*",
    "G": "EPT*",
    "H": "Palpation",
    "I": "Percussion",
    "J": "Bite Test",
    "K": "Fluctuant Swelling",
    "L": "Sinus Tract",
    "N": "Periapical status"
}

# History columns used for “Endodontic Treatment History”
HIST_PREV_TREATED_ID = "M"       # Previously treated
HIST_PREV_INITIATED_ID = "O"     # Previously initiated

# Map those history IDs to the actual column names:
HISTORY_ID_TO_COL = {
    "M": "Previously treated",
    "O": "Previously initiated",
}


class DiagnosisEngine:
    """
    Step-1: etiology_choices_from_page1(page1_answers)
      • For each answered P..X question:
          - If the sheet cell has tokens (e.g., "1- No,2- Yes"), the user's choice must be IN those tokens (OR).
          - If the cell is BLANK, treat as wildcard (match).
      • If a matched row's 'Etiology' is 'None'/'Any'/'All' → wildcard → contribute ALL known etiologies.
      • Return unique etiologies (sorted).

    Final diagnose(answers)
      • History must match (Previously treated / initiated / none).
      • Etiology filter:
          - If user selected specific etiologies (and not "Not sure"), only rows whose Etiology contains
            at least one of those tokens are allowed.
          - If user picked "Not sure" or provided nothing, do NOT filter by etiology.
      • Clinical/radiographic fields: if answered, choice must be present in row tokens; blank cells are wildcard.
    """
    def __init__(self, excel_path: str, sheet_name: str = "Main file"):
        if not os.path.exists(excel_path):
            raise FileNotFoundError(f"Excel file not found: {excel_path}")

        self.excel_path = excel_path
        self.version = datetime.fromtimestamp(Path(excel_path).stat().st_mtime).strftime(
            "%Y%m%d-%H%M%S"
        )

        # Load full sheet (we need all columns including P..X)
        self.df = pd.read_excel(excel_path, sheet_name=sheet_name)
        self.df.columns = [str(c).strip() for c in self.df.columns]
        self.df = self.df.dropna(axis=1, how="all")

        # Filter out impossible rows if column exists
        if "Possibility" in self.df.columns:
            poss = self.df["Possibility"].astype(str).str.strip().str.lower()
            self.df = self.df[poss != "no"]

        # Require key outputs
        self.df = self.df.dropna(subset=["Pulp Dx", "Periapical Dx", "Etiology"])

        # Cache all known etiologies (excluding wildcard keywords)
        all_etio_series = (
            self.df["Etiology"]
            .astype(str)
            .str.split(",")
            .explode()
            .map(lambda s: re.sub(r"^\s*\d+\s*-\s*", "", str(s or "")))  # strip "1- "
            .str.strip()
        )
        self._all_etiologies: List[str] = sorted(
            e for e in set(all_etio_series)
            if e and e.lower() not in {"none", "any", "all"}
        )
        self._etiology_name_by_lower: Dict[str, str] = {e.lower(): e for e in self._all_etiologies}

    # ---------------------------- helpers ----------------------------

    @staticmethod
    def _norm(x: object) -> str:
        return str(x or "").strip().lower()

    @staticmethod
    def _cell_tokens(cell: object) -> Set[str]:
        """
        "1- No,2- Yes" -> {"no", "yes"}
        BLANK/NaN -> empty set (treated as wildcard by matcher).
        """
        s = str(cell or "")
        if not s or s.lower() == "nan":
            return set()
        parts = [p.strip() for p in s.split(",") if p.strip()]
        toks: List[str] = []
        for p in parts:
            q = re.sub(r"^\s*\d+\s*-\s*", "", p)  # strip any "1- "
            toks.append(str(q).strip().lower())
        return set(toks)

    @staticmethod
    def _etiology_tokens(cell: object) -> Set[str]:
        """Split etiology cell like 'Caries, Trauma' -> {'caries','trauma'} (lower)."""
        return DiagnosisEngine._cell_tokens(cell)

    def _row_matches_page1(self, row: pd.Series, page1_answers: Dict[str, object]) -> bool:
        if not isinstance(page1_answers, dict):
            return True
        for qid, col in PAGE1_ID_TO_COL.items():
            if qid not in page1_answers:
                continue
            user_choice = self._norm(page1_answers[qid])
            tokens = self._cell_tokens(row.get(col, ""))
            if tokens and user_choice not in tokens:
                return False
        return True

    # -------------------- Step-1 availability --------------------

    def etiology_choices_from_page1(self, page1_answers: Dict[str, object]) -> List[str]:
        answers = page1_answers or {}
        mask = self.df.apply(lambda r: self._row_matches_page1(r, answers), axis=1)
        matched = self.df[mask]

        if matched.empty:
            return []

        etio_cells = matched["Etiology"].astype(str)
        has_wildcard = etio_cells.str.strip().str.lower().isin({"none", "any", "all"}).any()
        if has_wildcard:
            return list(self._all_etiologies)

        res_lower: Set[str] = set()
        for val in etio_cells:
            for t in self._etiology_tokens(val):
                if t and t not in {"none", "any", "all"}:
                    res_lower.add(t)

        return sorted(self._etiology_name_by_lower.get(t, t) for t in res_lower)


    def diagnose(self, answers: Dict[str, object]):
        results: List[Dict[str, str]] = []
        # --- Normalize selected etiologies (either key) ---
        selected_etios = answers.get("Etiology Assessment",
                            answers.get("etiology_assessment", []))
        if isinstance(selected_etios, str):
            selected_etios = [selected_etios]
        selected_etios_l = {self._norm(e) for e in (selected_etios or []) if str(e).strip()} # type: ignore

        for _, row in self.df.iterrows():
            # ---------- History (either key) ----------
            hist = self._norm(answers.get("Endodontic Treatment History",
                            answers.get("endo_history", "")))

            prev_tr = self._norm(row.get("Previously treated", ""))
            prev_in = self._norm(row.get("Previously initiated", ""))

            if hist == "no previous endodontics treatment":
                if ("positive" in prev_tr) or ("positive" in prev_in):
                    continue
            elif hist == "previously treated":
                if "positive" not in prev_tr:
                    continue
            elif hist == "previously initiated":
                if "positive" not in prev_in:
                    continue

            # ---------- Strict etiology filter ----------
            row_etios = self._etiology_tokens(row.get("Etiology", ""))
            if selected_etios_l and "not sure" not in selected_etios_l:
                if not (selected_etios_l & row_etios):
                    continue

            # ---------- Clinical/Radiographic (E..L) ----------
            ok = True
            for fid, col in FIELD_ID_TO_COL.items():
                if fid not in answers or not str(answers[fid]).strip():
                    continue
                ans = self._norm(answers[fid])
                tokens = self._cell_tokens(row.get(col, ""))
                if tokens and ans not in tokens:
                    ok = False
                    break
            if not ok:
                continue

            # ---------- Page‑1 P..X ----------
            if not self._row_matches_page1(row, answers):
                continue

            results.append({
                "pulp_diagnosis": str(row.get("Pulp Dx", "")).strip(),
                "periapical_disease": str(row.get("Periapical Dx", "")).strip(),
                "etiology": str(row.get("Etiology", "")).strip(),
            })

        return results

    def run(self, answers: Dict[str, object], use_ai_fallback: bool = True):
        """
        Unified entrypoint. Uses rules engine first; if empty and fallback is enabled,
        calls Gemini and returns a standard shape for the API/UI.
        """
        results = self.diagnose(answers)  # your existing method
        if results:
            return {"source": "rules_engine", "engine_version": self.version, "results": results}

        if not use_ai_fallback:
            return {"source": "rules_engine", "engine_version": self.version, "results": []}

        ai = gemini_fallback(answers, self.version) # type: ignore
        if ai:
            return {"source": "ai_fallback_gemini", "engine_version": self.version, "ai": ai}
        return {"source": "none", "engine_version": self.version, "results": []}