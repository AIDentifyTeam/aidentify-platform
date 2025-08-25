import math


def clean_json(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return ""
    if isinstance(obj, dict):
        return {k: clean_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_json(x) for x in obj]
    return obj


# put this somewhere handy (e.g., endo/utils_debug_dx.py) and import it where needed
def explain_match(engine, answers):
    """
    Return a dict explaining row-match filtering for a given FE `answers` dict.
    Shows how many rows survive each constraint and where mismatches happen.
    """
    import pandas as pd

    report = {"total_rows": len(engine.df), "stages": []}
    df = engine.df.copy()

    def keep(mask, reason):
        nonlocal df
        before = len(df)
        df = df[mask]
        report["stages"].append(
            {"reason": reason, "kept": int(mask.sum()), "dropped": before - int(mask.sum())}
        )

    # PAGE1 constraints
    def _norm(x): return str(x or "").strip().lower()
    for qid, col in engine.PAGE1_COL_MAP.items():
        if qid not in answers:
            continue
        user_choice = _norm(answers[qid])
        # tokens for each row
        toks_series = df[col].astype(str).fillna("")
        def row_ok(cell):
            s = str(cell or "")
            if not s or s.lower() == "nan":
                return True  # wildcard
            parts = [p.strip() for p in s.split(",") if p.strip()]
            toks = []
            import re
            for p in parts:
                q = re.sub(r"^\s*\d+\s*-\s*", "", p)
                toks.append(str(q).strip().lower())
            return user_choice in set(toks)
        mask = toks_series.map(row_ok)
        keep(mask, f"P..X: {qid} == {answers[qid]} (column '{col}')")

    # History filter (same as engine)
    hist = _norm(answers.get("Endodontic Treatment History", ""))
    if hist:
        if hist == "no previous endodontics treatment":
            mask = df["Previously treated"].astype(str).str.lower().str.contains("negative") & \
                   df["Previously initiated"].astype(str).str.lower().str.contains("negative")
            keep(mask, "history: none")
        elif hist == "previously treated":
            mask = df["Previously treated"].astype(str).str.lower().str.contains("positive")
            keep(mask, "history: previously treated")
        elif hist == "previously initiated":
            mask = df["Previously initiated"].astype(str).str.lower().str.contains("positive")
            keep(mask, "history: previously initiated")

    # Clinical/radiographic
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
        if qid not in answers:
            continue
        ans = _norm(answers[qid])
        if col not in df.columns:
            report["stages"].append({"reason": f"clinical: {qid} (missing column {col})", "kept": len(df), "dropped": 0})
            continue
        def ok(cell):
            cell = str(cell or "").lower()
            toks = [t.split("-")[-1].strip().lower() for t in cell.split(",") if t.strip()]
            if not toks:
                return True  # wildcard column
            return ans in toks
        mask = df[col].map(ok)
        keep(mask, f"clinical: {qid} == {answers[qid]} (column '{col}')")

    # Etiology filter (Page-2)
    etios = [e.lower() for e in answers.get("Etiology Assessment", [])]
    if etios and "not sure" not in etios:
        mask = df["Etiology"].astype(str).str.lower().apply(lambda cell: any(e in cell for e in etios))
        keep(mask, f"etiology ∈ {answers.get('Etiology Assessment')}")

    report["matched_rows"] = len(df)
    report["matched_etiologies"] = sorted(set(
        e.strip() for val in df["Etiology"].astype(str) for e in val.split(",")
    ))
    report["wildcard_present"] = df["Etiology"].astype(str).str.strip().str.lower().isin({"none","any","all"}).any()
    return report
