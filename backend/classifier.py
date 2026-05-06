"""
Layer 2 — Issue Classifier
Primary:  Fine-tuned DistilBERT (from distilbert_classifier/ folder)
Fallback: TF-IDF + Logistic Regression (if DistilBERT not available)

To use DistilBERT:
1. Run SupportIQ_DistilBERT_Finetune.ipynb on Google Colab (T4 GPU, ~10 min)
2. Download distilbert_classifier.zip
3. Unzip and place distilbert_classifier/ folder inside backend/
4. Restart the backend — it auto-detects and loads DistilBERT
"""

import os, pickle, json
import pandas as pd
from pathlib import Path
from typing import Optional

def _get_model_dir() -> Path:
    # Use MODEL_DIR env var if set (Docker mounts volume there)
    import os
    env_dir = os.getenv("MODEL_DIR")
    d = Path(env_dir) if env_dir else Path(__file__).parent / "models"
    d.mkdir(exist_ok=True)
    return d

def _classifier_path() -> Path: return _get_model_dir() / "issue_classifier.pkl"

DISTILBERT_DIR = Path(__file__).parent / "distilbert_classifier"

CATEGORIES = ["Bug", "New Feature", "Improvement", "Task", "Test"]


# ── DistilBERT classifier (primary) ──────────────────────────────────────────

class DistilBertClassifier:
    """
    Loads fine-tuned DistilBERT from distilbert_classifier/ folder.
    Uses ONNX Runtime if model.onnx exists (3-5x faster on CPU).
    Falls back to PyTorch pipeline if ONNX not available.
    """

    def __init__(self, model_dir: str):
        import json
        label_map_path = Path(model_dir) / "label_map.json"
        with open(label_map_path) as f:
            self._label_map = json.load(f)

        onnx_path = Path(model_dir) / "model.onnx"

        if onnx_path.exists():
            # Fast path: ONNX Runtime (~3-5 sec on CPU)
            self._use_onnx = True
            from optimum.onnxruntime import ORTModelForSequenceClassification
            from transformers import AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(model_dir)
            self._model     = ORTModelForSequenceClassification.from_pretrained(model_dir)
            print("[Classifier] Loaded DistilBERT (ONNX Runtime) ✓")
        else:
            # Slow path: PyTorch (~60-90 sec on CPU)
            # Run: python convert_to_onnx.py  to enable ONNX
            self._use_onnx = False
            from transformers import pipeline as hf_pipeline
            import torch
            device = 0 if torch.cuda.is_available() else -1
            self._pipe = hf_pipeline(
                "text-classification",
                model=model_dir,
                tokenizer=model_dir,
                device=device,
                top_k=None,
                truncation=True,
                max_length=64,
            )
            print("[Classifier] Loaded DistilBERT (PyTorch — slow on CPU) ✓")
            print("[Classifier] Tip: run 'python convert_to_onnx.py' for 3-5x faster inference")

        self._trained = True

        self.train_report = {
            "source": "distilbert_finetuned",
            "model": "distilbert-base-uncased",
        }

        metrics_path = Path(model_dir) / "training_metrics.json"
        if metrics_path.exists():
            try:
                with open(metrics_path) as f:
                    metrics = json.load(f)
                self.train_report.update(metrics)
            except Exception:
                pass

    def predict(self, text: str) -> dict:
        if self._use_onnx:
            import torch
            inputs = self._tokenizer(
                text[:512], return_tensors="pt",
                truncation=True, max_length=64, padding=True
            )
            with torch.no_grad():
                logits = self._model(**inputs).logits
            import torch.nn.functional as F
            probs  = F.softmax(logits, dim=-1)[0]
            scores = {self._label_map.get(str(i), str(i)): round(float(p), 3)
                      for i, p in enumerate(probs)}
            best   = max(scores, key=scores.get)
            return {
                "category":   best,
                "confidence": scores[best],
                "all_scores": scores,
                "model":      "DistilBERT (ONNX)",
            }
        else:
            result = self._pipe(text[:512])[0]
            scores = {self._label_map.get(r["label"].replace("LABEL_", ""), r["label"]): round(r["score"], 3)
                      for r in result}
            best   = max(scores, key=scores.get)
            return {
                "category":   best,
                "confidence": scores[best],
                "all_scores": scores,
                "model":      "DistilBERT (PyTorch)",
            }


# ── TF-IDF + LR fallback ─────────────────────────────────────────────────────

class TFIDFClassifier:
    """TF-IDF + Logistic Regression — used when DistilBERT model not available."""

    def __init__(self):
        from sklearn.pipeline import Pipeline
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression

        self.pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                max_features=80000, ngram_range=(1, 3),
                min_df=2, sublinear_tf=True, strip_accents="unicode",
            )),
            ("model", LogisticRegression(
                max_iter=3000, class_weight="balanced",
                C=5.0, solver="lbfgs", multi_class="multinomial", random_state=42,
            )),
        ])
        self._trained     = False
        self.train_report = {}

    def train_on_dataframe(self, df: pd.DataFrame, min_count: int = 50):
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, f1_score, classification_report

        counts = df["issue_type"].value_counts()
        valid  = counts[counts >= min_count].index
        clf_df = df[df["issue_type"].isin(valid)].copy()
        X, y   = clf_df["text"], clf_df["issue_type"]

        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        # Oversample minority classes
        import pandas as _pd
        tr_df = _pd.DataFrame({"text": X_tr, "label": y_tr})
        median_count = int(tr_df["label"].value_counts().median())
        target = min(median_count * 2, tr_df["label"].value_counts().max())
        oversampled = []
        for label, group in tr_df.groupby("label"):
            if len(group) < target:
                group = group.sample(target, replace=True, random_state=42)
            oversampled.append(group)
        tr_df  = _pd.concat(oversampled).sample(frac=1, random_state=42)
        X_tr, y_tr = tr_df["text"], tr_df["label"]

        self.pipeline.fit(X_tr, y_tr)
        preds      = self.pipeline.predict(X_te)
        self._trained = True

        report = classification_report(y_te, preds, output_dict=True, zero_division=0)
        self.train_report = {
            "accuracy":    round(float(accuracy_score(y_te, preds)), 4),
            "macro_f1":    round(float(f1_score(y_te, preds, average="macro",    zero_division=0)), 4),
            "weighted_f1": round(float(f1_score(y_te, preds, average="weighted", zero_division=0)), 4),
            "per_class":   {k: {"precision": round(v["precision"], 3),
                                "recall":    round(v["recall"], 3),
                                "f1":        round(v["f1-score"], 3),
                                "support":   int(v["support"])}
                            for k, v in report.items()
                            if k in list(self.pipeline.classes_)},
            "train_size":  len(X_tr),
            "test_size":   len(X_te),
            "source":      "tfidf_lr",
            "model":       "TF-IDF + Logistic Regression",
        }
        return self.train_report

    def predict(self, text: str) -> dict:
        if not self._trained:
            return {
                "category":   "Unknown",
                "confidence": 0.0,
                "all_scores": {},
                "error":      "Model not trained. Upload CSV on Train Models page.",
            }
        proba = self.pipeline.predict_proba([text])[0]
        idx   = int(proba.argmax())
        classes = list(self.pipeline.classes_)
        return {
            "category":   classes[idx],
            "confidence": round(float(proba[idx]), 3),
            "all_scores": {c: round(float(p), 3) for c, p in zip(classes, proba)},
            "model":      "TF-IDF + LR",
        }

    def save(self):
        with open(_classifier_path(), "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load() -> "TFIDFClassifier":
        if _classifier_path().exists():
            with open(_classifier_path(), "rb") as f:
                return pickle.load(f)
        return TFIDFClassifier()


# ── Public interface — auto-selects best available model ─────────────────────

class IssueClassifier:
    """
    Auto-selects DistilBERT if distilbert_classifier/ exists, else TF-IDF+LR.
    Exposes the same .predict() and .train_report interface either way.
    """

    def __init__(self):
        self._model       = None
        self._trained     = False
        self.train_report = {}
        self.classes_     = CATEGORIES

    def _load(self):
        if self._model is not None:
            return
        # Try DistilBERT first
        label_map = DISTILBERT_DIR / "label_map.json"
        if DISTILBERT_DIR.exists() and label_map.exists():
            try:
                self._model = DistilBertClassifier(str(DISTILBERT_DIR))
                self._trained     = True
                self.train_report = self._model.train_report
                print("[Classifier] Loaded fine-tuned DistilBERT ✓")
                return
            except Exception as e:
                print(f"[Classifier] DistilBERT load failed ({e}), falling back to TF-IDF+LR")
        # Fallback: TF-IDF+LR
        self._model = TFIDFClassifier.load()
        self._trained     = self._model._trained
        self.train_report = self._model.train_report

    def train_on_dataframe(self, df: pd.DataFrame, min_count: int = 50):
        """Only used for TF-IDF+LR training (DistilBERT is trained in Colab)."""
        tfidf = TFIDFClassifier()
        report = tfidf.train_on_dataframe(df, min_count)
        tfidf.save()
        self._model       = tfidf
        self._trained     = True
        self.train_report = report
        return report

    def save(self):
        """Delegate save to inner TF-IDF model if applicable."""
        if isinstance(self._model, TFIDFClassifier):
            self._model.save()

    def predict(self, text: str) -> dict:
        self._load()
        return self._model.predict(text)


# ── Singleton ─────────────────────────────────────────────────────────────────

_clf: Optional[IssueClassifier] = None

def get_classifier() -> IssueClassifier:
    global _clf
    if _clf is None:
        _clf = IssueClassifier()
    return _clf