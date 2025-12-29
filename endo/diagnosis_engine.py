# endo/diagnosis_engine.py
import os
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
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
    "S": "Does biting/chewing trigger/aggravate the pain?",
    "T": "Are you able to function (bite or chew) on the painful side?",
    "U": "Do you experience spontaneous pain?",
    "V": "Does the pain wake you up at night or interfere with sleep?",
    "W": "Does the pain have any of the following qualities:",
    "X": "Do you also feel the pain in other areas like jawbone, ear, or\n"
        "temple, or eye, or cheek?",
}

PAIN_QUALITY_COLUMN = "Does the pain have any of the following qualities:"
PAIN_QUALITY_QIDS = {
    qid for qid, col in PAGE1_ID_TO_COL.items() if col == PAIN_QUALITY_COLUMN
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
    def _split_cell_values(cell: object) -> List[str]:
        """
        Split comma-delimited values while preserving commas that appear inside parentheses.
        Example: "1- A, 2- B (e.g., sample)" -> ["1- A", "2- B (e.g., sample)"].
        """
        s = str(cell or "")
        if not s or s.lower() == "nan":
            return []

        tokens: List[str] = []
        current: List[str] = []
        depth = 0

        for ch in s:
            if ch == "," and depth == 0:
                token = "".join(current).strip()
                if token:
                    tokens.append(token)
                current = []
                continue

            current.append(ch)
            if ch == "(":
                depth += 1
            elif ch == ")" and depth:
                depth -= 1

        tail = "".join(current).strip()
        if tail:
            tokens.append(tail)

        return tokens

    @staticmethod
    def _cell_tokens(cell: object) -> Set[str]:
        """
        "1- No,2- Yes" -> {"no", "yes"}
        BLANK/NaN -> empty set (treated as wildcard by matcher).
        """
        toks: List[str] = []
        for part in DiagnosisEngine._split_cell_values(cell):
            q = re.sub(r"^\s*\d+\s*-\s*", "", part)  # strip any "1- "
            cleaned = str(q).strip().lower()
            if cleaned:
                toks.append(cleaned)
        return set(toks)

    @staticmethod
    def _etiology_tokens(cell: object) -> Set[str]:
        """Split etiology cell like 'Caries, Trauma' -> {'caries','trauma'} (lower)."""
        return DiagnosisEngine._cell_tokens(cell)

    def _etiology_display_tokens(self, cell: object) -> List[str]:
        """Return cleaned etiology names with original casing preserved when known."""
        tokens: List[str] = []
        s = str(cell or "")
        if not s or s.lower() == "nan":
            return tokens

        for part in self._split_cell_values(s):
            cleaned = re.sub(r"^\s*\d+\s*-\s*", "", part).strip()
            if not cleaned:
                continue
            lower = cleaned.lower()
            tokens.append(self._etiology_name_by_lower.get(lower, cleaned))

        return tokens

    def _history_flags(self, answers: Dict[str, object]) -> Tuple[bool, bool]:
        """Infer history flags from either the history field or raw M/O answers."""
        if not isinstance(answers, dict):
            return False, False

        hist = self._norm(answers.get("Endodontic Treatment History",
                                       answers.get("endo_history", "")))
        prev_treated = hist == "previously treated"
        prev_initiated = hist in {"previously initiated", "previously initiated therapy"}

        prev_treated = prev_treated or (self._norm(answers.get(HIST_PREV_TREATED_ID)) in {"positive", "yes"})
        prev_initiated = prev_initiated or (self._norm(answers.get(HIST_PREV_INITIATED_ID)) in {"positive", "yes"})

        return prev_treated, prev_initiated

    def _apply_abscess_pulp_override(self, results: List[Dict[str, str]], answers: Dict[str, object]) -> None:
        """
        For Chronic/Acute apical abscess rows, set pulp diagnosis based on treatment history.
        Priority: previously treated > previously initiated > pulp necrosis.
        """
        if not results:
            return

        prev_treated, prev_initiated = self._history_flags(answers)
        if prev_treated:
            pulp_value = "Previously treated"
        elif prev_initiated:
            pulp_value = "Previously initiated therapy"
        else:
            pulp_value = "Pulp necrosis"

        for entry in results:
            peri = self._norm(entry.get("periapical_disease"))
            if peri in {"chronic apical abscess", "acute apical abscess"}:
                entry["pulp_diagnosis"] = pulp_value

    def _format_grouped_results(self, results: List[Dict[str, str]]) -> List[Dict[str, object]]:
        """Merge duplicate pulp/periapical rows and add a combined etiology sentence."""
        grouped: "OrderedDict[Tuple[str, str], Dict[str, Any]]" = OrderedDict()

        for entry in results:
            pulp = str(entry.get("pulp_diagnosis", "")).strip()
            periapical = str(entry.get("periapical_disease", "")).strip()
            key = (pulp, periapical)
            bucket = grouped.setdefault(
                key,
                {
                    "pulp_diagnosis": pulp,
                    "periapical_disease": periapical,
                    "etiologies": [],
                    "_seen": set(),
                },
            )

            tokens = self._etiology_display_tokens(entry.get("etiology", ""))
            if tokens:
                seen: Set[str] = bucket["_seen"]
                for token in tokens:
                    lower = token.lower()
                    if lower in seen:
                        continue
                    seen.add(lower)
                    bucket["etiologies"].append(token)

        formatted: List[Dict[str, object]] = []
        for bucket in grouped.values():
            etiologies: List[str] = bucket.get("etiologies", [])
            sentence = "Possible etiologies: "
            if etiologies:
                sentence += ", ".join(etiologies)
            else:
                sentence += "Not specified"

            etiology_list = list(etiologies)
            formatted.append(
                {
                    "section_label": "Pulp Diagnosis",
                    "pulp_diagnosis": bucket["pulp_diagnosis"],
                    "periapical_disease": bucket["periapical_disease"],
                    "etiology": sentence,
                    "etiology_list": etiology_list,
                }
            )

        return formatted

    def _rule_based_fallback(self, answers: Dict[str, object]) -> List[Dict[str, str]]:
        """Apply additional diagnostic rules when sheet lookup returns nothing."""
        pulp: Optional[str] = None
        peri: Optional[str] = None

        cold_test = self._norm(answers.get("E"))
        if cold_test == "lingering pain":
            pulp = "Symptomatic Irreversible Pulpitis"

        swelling = self._norm(answers.get("K"))
        sinus = self._norm(answers.get("L"))
        if sinus == "negative":
            if swelling == "positive":
                peri = "Acute Apical Abscess"
        elif sinus == "positive":
                peri = "Chronic Apical Abscess"

        if not pulp and not peri:
            return []

        return [
            {
                "pulp_diagnosis": pulp or "",
                "periapical_disease": peri or "",
                "etiology": "",
            }
        ]

    def _row_matches_page1(self, row: pd.Series, page1_answers: Dict[str, object]) -> bool:
        if not isinstance(page1_answers, dict):
            return True

        wildcard_tokens = {"", "not defined", "not sure", "unsure", "unknown", "n/a", "na"}
        pain_quality_optional = {"no", "none", "not defined", "not sure"}

        for qid, col in PAGE1_ID_TO_COL.items():
            if qid not in page1_answers:
                continue
            raw_value = page1_answers[qid]
            if isinstance(raw_value, (list, tuple, set)):
                user_tokens = {
                    self._norm(val)
                    for val in raw_value
                    if val is not None and str(val).strip()
                }
            else:
                user_choice = self._norm(raw_value)
                user_tokens = {user_choice} if raw_value is not None else set()

            is_pain_quality = (qid in PAIN_QUALITY_QIDS) or (col == PAIN_QUALITY_COLUMN)

            normalized_tokens = {tok for tok in user_tokens if tok}
            skip_tokens = wildcard_tokens | (pain_quality_optional if is_pain_quality else set())
            effective_tokens = normalized_tokens - skip_tokens
            if not normalized_tokens or not effective_tokens:
                continue

            tokens = self._cell_tokens(row.get(col, ""))
            if tokens and not (effective_tokens & tokens):
                return False
        return True

    # -------------------- Step-1 availability --------------------

    def etiology_choices_from_page1(self, page1_answers: Dict[str, object]) -> List[str]:
        # Filtering by page-1 answers is disabled by request; always return all known etiologies.
        return list(self._all_etiologies)


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
            row_pulp = self._norm(row.get("Pulp Dx", ""))

            if hist == "no previous endodontics treatment":
                if (
                    ("positive" in prev_tr)
                    or ("positive" in prev_in)
                    or row_pulp in {"previously treated", "previously initiated therapy"}
                ):
                    continue
            elif hist == "previously treated":
                if ("positive" not in prev_tr) and (row_pulp != "previously treated"):
                    continue
            elif hist == "previously initiated":
                if ("positive" not in prev_in) and (row_pulp != "previously initiated therapy"):
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
                    # allow soft/partial semantic matches (e.g., "normal" vs "normal periapex")
                    if not any(ans in t or t in ans for t in tokens):
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

    def run(self, answers: Dict[str, object]):
        """
        Unified entrypoint returning rule-engine matches and heuristic overrides.
        AI fallbacks are orchestrated by higher-level services.
        """
        answers = answers or {}
        results_raw = self.diagnose(answers)
        result_source = "rules_engine"

        if not results_raw:
            fallback_raw = self._rule_based_fallback(answers)
            if fallback_raw:
                results_raw = fallback_raw
                result_source = "rule_override"

        if results_raw:
            self._apply_abscess_pulp_override(results_raw, answers)

        formatted: List[Dict[str, object]] = []
        if results_raw:
            formatted = self._format_grouped_results(results_raw)

        payload: Dict[str, object] = {
            "source": "rules_engine" if formatted else "none",
            "engine_version": self.version,
            "results": formatted,
        }

        if formatted and result_source != "rules_engine":
            payload["result_source"] = result_source

        return payload
