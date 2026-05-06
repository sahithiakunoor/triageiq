"""
Layer 2 — Priority Predictor (XGBoost)
Apache/Spring/JBoss priorities: Blocker, Critical, Major, Minor, Trivial → P1–P5
No seed data — requires real CSV training.
Class imbalance handled using balanced sample weights during XGBoost training.
A rule-based escalation layer is applied during prediction to prevent obvious P1/P2 cases from being under-prioritized.
"""

import os, pickle
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional

from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report
from xgboost import XGBClassifier

from data_pipeline import normalize_priority, urgency_score, PRIORITY_DISPLAY

# Resolve relative to this file (backend/) so models always save to backend/models/
# regardless of which directory training is triggered from
# Resolve at call time so env var changes take effect
def _get_model_dir() -> Path:
    # Use MODEL_DIR env var if set (Docker mounts volume there)
    # otherwise fall back to relative path from this file
    import os
    env_dir = os.getenv("MODEL_DIR")
    d = Path(env_dir) if env_dir else Path(__file__).parent / "models"
    d.mkdir(exist_ok=True)
    return d

def _model_path()   -> Path: return _get_model_dir() / "priority_model.pkl"
def _encoder_path() -> Path: return _get_model_dir() / "priority_label_encoder.pkl"

def rule_based_priority_override(text: str, model_priority: str) -> str:
    """
    Hybrid safety layer:
    Upgrade priority when the ticket contains strong operational-risk signals.
    This prevents obvious P1/P2 incidents from being under-prioritized as P3.
    """
    text_l = (text or "").lower()

    p1_keywords = [
        "production down",
        "prod down",
        "system down",
        "service down",
        "site down",
        "app down",
        "outage",
        "complete outage",
        "critical outage",
        "data loss",
        "lost data",
        "loses messages",
        "messages are dropped",
        "message loss",
        "payment failure",
        "payments failing",
        "security breach",
        "security vulnerability",
        "vulnerability",
        "rce",
        "remote code execution",
        "cannot login",
        "unable to login",
        "all users affected",
        "blocking production",
        "production issue",
        "crash in production",
        "database corruption",
        "customer impact",
        "major customer impact"
    ]

    p2_keywords = [
        "regression",
        "fails after upgrade",
        "build fails",
        "major failure",
        "intermittent failure",
        "broker failover",
        "memory leak",
        "high latency",
        "timeout",
        "deadlock",
        "incorrect result",
        "breaking change",
        "urgent",
        "critical",
        "blocker",
        "crash",
        "exception",
        "nullpointerexception",
        "npe"
    ]

    if any(k in text_l for k in p1_keywords):
        return "P1"

    if any(k in text_l for k in p2_keywords):
        if model_priority in ("P3", "P4", "P5"):
            return "P2"

    return model_priority


class PriorityPredictor:
    def __init__(self):
        self.label_enc    = LabelEncoder()
        self.tfidf        = None
        self.model        = None
        self._trained     = False
        self.classes_     = []
        self.train_report = {}

    def train_on_dataframe(self, df: pd.DataFrame, min_count: int = 50):
        counts = df["priority"].value_counts()
        valid  = counts[counts >= min_count].index
        pri_df = df[df["priority"].isin(valid)].copy()

        X_text = pri_df["text"]
        y      = self.label_enc.fit_transform(pri_df["priority"])
        self.classes_ = list(self.label_enc.classes_)

        X_tr_text, X_te_text, y_tr, y_te = train_test_split(
            X_text, y, test_size=0.2, random_state=42, stratify=y
        )

        # No CAP/MIN resampling — train on full dataset with balanced sample weights
        # This is better than resampling because:
        # - Model sees all 50K rows (more diverse patterns)
        # - P1/P2 minority classes are mathematically upweighted during training
        # - No synthetic or duplicated data needed
        from sklearn.utils.class_weight import compute_sample_weight

        # TF-IDF vectorize
        self.tfidf = TfidfVectorizer(
            max_features=80000,
            ngram_range=(1, 3),
            min_df=2,
            sublinear_tf=True,
            strip_accents="unicode",
        )
        X_tr = self.tfidf.fit_transform(X_tr_text)
        X_te = self.tfidf.transform(X_te_text)

        # XGBoost — with sample weights to further penalize P3 majority class
        self.model = XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=3,
            eval_metric="mlogloss",
            random_state=42,
            n_jobs=-1,
            tree_method="hist",
        )
        # Compute per-sample weights so P1/P2 minority classes get higher weight
        sample_weights = compute_sample_weight("balanced", y_tr)
        self.model.fit(X_tr, y_tr, sample_weight=sample_weights)
        preds = self.model.predict(X_te)
        self._trained = True

        report = classification_report(
            y_te, preds,
            target_names=self.classes_,
            output_dict=True,
            zero_division=0
        )
        self.train_report = {
            "accuracy":    round(float(accuracy_score(y_te, preds)), 4),
            "macro_f1":    round(float(f1_score(y_te, preds, average="macro",    zero_division=0)), 4),
            "weighted_f1": round(float(f1_score(y_te, preds, average="weighted", zero_division=0)), 4),
            "per_class":   {k: {"precision": round(v["precision"], 3),
                                "recall":    round(v["recall"], 3),
                                "f1":        round(v["f1-score"], 3),
                                "support":   int(v["support"])}
                            for k, v in report.items()
                            if k in self.classes_},
            "train_size":  int(X_tr.shape[0]),
            "test_size":   int(X_te.shape[0]),
            "source":      "real_dataset",
        }
        return self.train_report

    def predict(self, title: str, description: str) -> dict:
        if not self._trained:
            return {
                "priority":         "P3",
                "priority_raw":     "Major",
                "priority_label":   "P3 — Major",
                "priority_display": "Major",
                "confidence":       0.0,
                "urgency_score":    40,
                "all_proba":        {},
                "error":            "Model not trained. Upload CSV on Train Models page."
            }
        text  = f"{title} {description}"
        X     = self.tfidf.transform([text])
        proba = self.model.predict_proba(X)[0]
        idx   = int(proba.argmax())
        raw = self.classes_[idx]
        norm = normalize_priority(raw)

        # Hybrid override: upgrade obvious high-risk cases
        norm = rule_based_priority_override(text, norm)

        disp = PRIORITY_DISPLAY.get(norm, norm)
        return {
            "priority":         norm,
            "priority_raw":     raw,
            "priority_label":   f"{norm} — {disp}",
            "priority_display": disp,
            "confidence":       round(float(proba[idx]), 3),
            "urgency_score":    urgency_score(text, norm, ""),
            "all_proba":        {c: round(float(p), 3) for c, p in zip(self.classes_, proba)},
        }

    def save(self):
        with open(_model_path(),   "wb") as f: pickle.dump(self, f)
        with open(_encoder_path(), "wb") as f: pickle.dump(self.label_enc, f)

    @staticmethod
    def load() -> "PriorityPredictor":
        if _model_path().exists():
            with open(_model_path(), "rb") as f:
                return pickle.load(f)
        return PriorityPredictor()


_predictor: Optional[PriorityPredictor] = None

def get_predictor() -> PriorityPredictor:
    global _predictor
    if _predictor is None:
        _predictor = PriorityPredictor.load()
    return _predictor