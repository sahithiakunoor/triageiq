"""
Data Pipeline — Jira Issue Reports v1 dataset
Projects: Apache Software Foundation, Spring Framework, JBoss, CodeHaus
Issue types: Bug, New Feature, Improvement, Task, Sub-task, Test, Wish
Priority labels: Blocker, Critical, Major, Minor, Trivial
"""

import re
import numpy as np
import pandas as pd


# ── Column auto-detection ─────────────────────────────────────────────────────

def _find_col(columns, candidates):
    lower_map = {str(c).lower().strip(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    for c in columns:
        if any(cand.lower() in str(c).lower() for cand in candidates):
            return c
    return None


def detect_columns(columns):
    return {
        "title":    _find_col(columns, ["title", "summary", "subject", "issue_title", "issue summary"]),
        "desc":     _find_col(columns, ["description", "body", "details", "text", "issue_description"]),
        "type":     _find_col(columns, ["issue_type", "issuetype", "type", "issue type"]),
        "priority": _find_col(columns, ["priority", "priority_name", "priority level"]),
        "status":   _find_col(columns, ["status", "state", "resolution"]),
        "created":  _find_col(columns, ["created", "created_at", "creation_date"]),
        "resolved": _find_col(columns, ["resolved", "resolved_at", "resolution_date", "closed_at"]),
    }


# ── Text cleaning ─────────────────────────────────────────────────────────────

def clean_text(x) -> str:
    if pd.isna(x):
        return ""
    x = str(x)
    x = re.sub(r"http\S+|www\.\S+", " URL ", x)
    x = re.sub(r"<.*?>", " ", x)
    x = re.sub(r"\{code[^}]*\}.*?\{code\}", " CODE_BLOCK ", x, flags=re.S)
    x = re.sub(r"\{noformat\}.*?\{noformat\}", " CODE_BLOCK ", x, flags=re.S)
    x = re.sub(r"[^\w\s\-\./:;#@!?()\[\]]", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x


# ── Priority normalisation — maps real Jira labels → P1–P5 ───────────────────
# Apache/Spring/JBoss use: Blocker, Critical, Major, Minor, Trivial

PRIORITY_DISPLAY = {
    "P1": "Blocker",
    "P2": "Critical",
    "P3": "Major",
    "P4": "Minor",
    "P5": "Trivial",
}

PRIORITY_COLORS = {
    "P1": "#f56565",
    "P2": "#ed8936",
    "P3": "#f6ad55",
    "P4": "#68d391",
    "P5": "#a0aec0",
}

def normalize_priority(priority: str) -> str:
    p = str(priority).lower().strip()
    if any(k in p for k in ["blocker", "p1", "critical_high", "show.stopper"]):
        return "P1"
    if any(k in p for k in ["critical", "p2", "major_high"]):
        return "P2"
    if any(k in p for k in ["major", "p3", "normal", "medium"]):
        return "P3"
    if any(k in p for k in ["minor", "p4", "low"]):
        return "P4"
    if any(k in p for k in ["trivial", "p5", "lowest", "wish"]):
        return "P5"
    return "P3"


# ── Urgency score (replaces SLA breach — not relevant for OSS projects) ───────
# Based on priority + keywords indicating user-blocking issues

_URGENT_KEYWORDS = [
    "blocker", "regression", "data loss", "crash", "infinite loop",
    "deadlock", "memory leak", "security", "cannot", "broken", "fails",
    "exception", "error", "npe", "nullpointer", "outofmemory",
    "production", "upgrade blocked", "prevents", "blocks release",
]

URGENCY_MAP = {"P1": 95, "P2": 72, "P3": 40, "P4": 15, "P5": 5}

def urgency_score(text: str, priority: str, issue_type: str) -> int:
    """Returns fix urgency 0-100. Replaces SLA breach % for OSS context."""
    norm  = normalize_priority(priority)
    base  = URGENCY_MAP.get(norm, 40)
    tl    = text.lower()
    if any(k in tl for k in _URGENT_KEYWORDS):
        base = min(base + 10, 98)
    if str(issue_type).lower() in ["bug", "regression"]:
        base = min(base + 5, 98)
    return int(base)


# ── Issue type inference fallback ─────────────────────────────────────────────

def infer_issue_type(text: str) -> str:
    tl = text.lower()
    if any(k in tl for k in ["exception", "error", "crash", "fail", "broken", "regression",
                               "npe", "nullpointer", "outofmemory", "stackover", "deadlock"]):
        return "Bug"
    if any(k in tl for k in ["add support", "new feature", "feature request", "would like",
                               "please add", "implement", "introduce"]):
        return "New Feature"
    if any(k in tl for k in ["improve", "enhancement", "performance", "optimize", "refactor",
                               "update", "upgrade", "better"]):
        return "Improvement"
    if any(k in tl for k in ["test", "unit test", "integration test", "coverage"]):
        return "Test"
    return "Task"


# ── Issue type consolidation ─────────────────────────────────────────────────
# Many rare types in the dataset map to core categories for better model learning

ISSUE_TYPE_MAP = {
    # Bug variants
    "bug":              "Bug",
    "defect":           "Bug",
    "error":            "Bug",
    "regression":       "Bug",
    "patch":            "Bug",
    # Feature variants
    "new feature":      "New Feature",
    "feature request":  "New Feature",
    "feature":          "New Feature",
    "wish":             "New Feature",
    # Improvement variants
    "improvement":      "Improvement",
    "enhancement":      "Improvement",
    "refactoring":      "Improvement",
    "optimisation":     "Improvement",
    "optimization":     "Improvement",
    # Task variants
    "task":             "Task",
    "sub-task":         "Task",
    "story":            "Task",
    "epic":             "Task",
    "documentation":    "Task",
    "component upgrade":"Task",
    "dependency upgrade":"Task",
    # Test
    "test":             "Test",
    "testing":          "Test",
}

def consolidate_issue_type(raw_type: str) -> str:
    return ISSUE_TYPE_MAP.get(str(raw_type).lower().strip(), None)


# ── Main loader ───────────────────────────────────────────────────────────────

def load_and_clean(csv_path: str, sample_n: int = 50000, random_state: int = 42) -> pd.DataFrame:
    try:
        df_raw = pd.read_csv(csv_path)
    except UnicodeDecodeError:
        df_raw = pd.read_csv(csv_path, encoding="latin1")

    if sample_n and len(df_raw) > sample_n:
        df_raw = df_raw.sample(sample_n, random_state=random_state)

    cols = detect_columns(df_raw.columns.tolist())

    for req in ["title", "desc", "priority"]:
        if cols[req] is None:
            raise ValueError(
                f"Could not detect '{req}' column. "
                f"Available: {df_raw.columns.tolist()}"
            )

    df = pd.DataFrame()
    df["title"]       = df_raw[cols["title"]].apply(clean_text)
    df["description"] = df_raw[cols["desc"]].apply(clean_text)
    df["text"]        = (df["title"] + " " + df["description"]).str.strip()
    df["priority_raw"] = df_raw[cols["priority"]].astype(str).str.strip()
    df["priority"]    = df["priority_raw"].apply(normalize_priority)

    if cols["type"]:
        raw_types = df_raw[cols["type"]].astype(str).str.strip()
        df["issue_type"] = raw_types.apply(
            lambda x: consolidate_issue_type(x) or infer_issue_type(df["text"].iloc[raw_types.tolist().index(x)] if x in raw_types.tolist() else "")
        )
        # Simpler: just map and fallback
        df["issue_type"] = raw_types.apply(
            lambda x: consolidate_issue_type(x) or "Task"
        )
    else:
        df["issue_type"] = df["text"].apply(infer_issue_type)

    df["status"]  = df_raw[cols["status"]].astype(str).str.strip() if cols["status"] else "Open"
    df["created"] = pd.to_datetime(df_raw[cols["created"]],  errors="coerce") if cols["created"]  else pd.NaT
    df["resolved"]= pd.to_datetime(df_raw[cols["resolved"]], errors="coerce") if cols["resolved"] else pd.NaT
    df["resolution_hours"] = (df["resolved"] - df["created"]).dt.total_seconds() / 3600

    df = df[df["text"].str.len() >= 20]
    df = df[df["priority"].notna()]
    df = df.drop_duplicates(subset=["text"]).reset_index(drop=True)

    return df