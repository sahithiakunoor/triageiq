"""
SupportIQ — FastAPI Backend (Layer 3 entry point)
Deck Layer 1: PostgreSQL + ChromaDB + Docker
Deck Layer 2: BERT Classifier + XGBoost Priority + RAG Pipeline
Deck Layer 3: FastAPI + Streamlit pages + Human-in-the-Loop
"""

import time, threading, uuid
from datetime import datetime
from typing import Optional
import os, tempfile, shutil
from fastapi import UploadFile, File, Form

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import init_db, get_db, Ticket
from classifier import get_classifier
from priority_model import get_predictor
from data_pipeline import normalize_priority, urgency_score, PRIORITY_DISPLAY
from entities import extract_entities
from rag import seed_kb, retrieve_context
from llm import generate_assistance
from evaluator import evaluate_output

app = FastAPI(title="SupportIQ API", version="3.0.0", docs_url="/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    import threading
    from pathlib import Path

    init_db()
    await seed_kb()

    # Auto-convert DistilBERT to ONNX in background (non-blocking)
    distilbert_dir = Path(__file__).parent / "distilbert_classifier"
    onnx_path      = distilbert_dir / "model.onnx"

    if distilbert_dir.exists() and not onnx_path.exists():
        def _convert():
            print("[Startup] Converting DistilBERT → ONNX in background...")
            try:
                from optimum.onnxruntime import ORTModelForSequenceClassification
                from transformers import AutoTokenizer
                model     = ORTModelForSequenceClassification.from_pretrained(
                    str(distilbert_dir), export=True)
                tokenizer = AutoTokenizer.from_pretrained(str(distilbert_dir))
                model.save_pretrained(str(distilbert_dir))
                tokenizer.save_pretrained(str(distilbert_dir))
                print("[Startup] ONNX conversion complete ✓ — restart uvicorn to use ONNX")
            except Exception as e:
                print(f"[Startup] ONNX conversion failed: {e}")
        threading.Thread(target=_convert, daemon=True).start()

    # Force load models into memory
    clf = get_classifier()
    clf._load()
    get_predictor()


# ── Schemas ───────────────────────────────────────────────────────────────────

class TicketIn(BaseModel):
    title: str
    description: Optional[str] = ""
    evaluate: bool = False

class ReviewIn(BaseModel):
    ticket_id:   int
    action:      str                   # approve | edit | reject
    agent_reply: Optional[str] = None
    agent_notes: Optional[str] = None
    assigned_to: Optional[str] = None

class TrainIn(BaseModel):
    csv_path:  str
    sample_n:  int = 50000


# ── Health / info ─────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "SupportIQ", "version": "3.0.0", "status": "ok"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/model/info")
def model_info():
    clf  = get_classifier()
    clf._load()   # ensure model is loaded so train_report is populated
    pred = get_predictor()
    return {
        "classifier":  clf.train_report,
        "priority":    pred.train_report,
    }

def normalize_text_for_duplicate(s: str) -> str:
    return " ".join((s or "").lower().strip().split())

# ── Core analysis endpoint — all 5 AI layers ─────────────────────────────────

@app.post("/analyze")
async def analyze(req: TicketIn, db: Session = Depends(get_db)):
    if not req.title.strip():
        raise HTTPException(400, "Title is required")

    t0    = time.time()
    title = req.title.strip()
    desc  = (req.description or "").strip()
    text  = f"{title} {desc}".strip()

    # Prevent duplicate tickets before running the ML/LLM pipeline
    norm_title = normalize_text_for_duplicate(title)
    norm_desc  = normalize_text_for_duplicate(desc)

    existing = db.query(Ticket).all()

    for old in existing:
        old_title = normalize_text_for_duplicate(old.title)
        old_desc  = normalize_text_for_duplicate(old.description)

        if old_title == norm_title and old_desc == norm_desc:
            raise HTTPException(
                status_code=409,
                detail=f"Duplicate ticket detected. This issue already exists as Ticket #{old.id}."
            )
    # Layer 2a — BERT Issue Classifier (TF-IDF + LogisticRegression)
    clf_out = get_classifier().predict(text)
    if clf_out.get("category") == "Unknown" and "error" in clf_out:
        raise HTTPException(400, detail="Models not trained yet. Please upload the Jira CSV on the Train Models page first.")

    # Layer 2b — XGBoost Priority + SLA
    pri_out = get_predictor().predict(title, desc)
    if "error" in pri_out:
        raise HTTPException(400, detail="Models not trained yet. Please upload the Jira CSV on the Train Models page first.")

    # Layer 2c — spaCy Entity Extraction
    ents = extract_entities(text)

    # Layer 2d — ChromaDB RAG retrieval (Phase 2)
    kb_chunks = await retrieve_context(text, top_k=3)

    # Layer 2e — Groq/Llama GenAI RAG Pipeline
    llm_out   = await generate_assistance(
        ticket_text = text,
        issue_type  = clf_out["category"],
        priority    = pri_out["priority"],
        sla_risk    = pri_out.get("urgency_score", 40) / 100.0,
        entities    = ents,
        kb_results  = kb_chunks,
    )

    ms = int((time.time() - t0) * 1000)

    # Optional: LLM-as-judge evaluation
    eval_scores = None
    if req.evaluate:
        eval_scores = await evaluate_output(
            ticket_title = title,
            ticket_desc  = desc,
            kb_chunks    = kb_chunks,
            summary      = llm_out.get("summary", ""),
            questions    = llm_out.get("clarifying_questions", []),
            draft_reply  = llm_out.get("draft_reply", ""),
        )

    # Layer 1 — Persist to PostgreSQL
    ticket = Ticket(
        title           = title,
        description     = desc,
        category        = clf_out["category"],
        category_conf   = clf_out["confidence"],
        priority        = pri_out["priority"],
        priority_raw    = pri_out["priority_raw"],
        priority_conf   = pri_out["confidence"],
        sla_risk        = pri_out.get("priority_display", "Major"),
        sla_breach_pct  = pri_out.get("urgency_score", 40),
        entities        = ents,
        kb_sources      = [c["source"] for c in kb_chunks],
        summary         = llm_out.get("summary", ""),
        clarifying_qs   = llm_out.get("clarifying_questions", []),
        draft_reply     = llm_out.get("draft_reply", ""),
        status          = "pending",
        resolution_ms   = ms,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    return {
        "ticket_id":              ticket.id,
        # Classifier
        "category":               clf_out["category"],
        "category_confidence":    clf_out["confidence"],
        "category_all_scores":    clf_out["all_scores"],
        "category_source":        clf_out.get("model", "DistilBERT / TF-IDF + LR"),
        # Priority
        "priority":               pri_out["priority"],
        "priority_label":         pri_out["priority_label"],
        "priority_confidence":    pri_out["confidence"],
        "priority_all_proba":     pri_out["all_proba"],
        # SLA
        "sla_risk":               pri_out.get("priority_display", "Major"),
        "urgency_score":          pri_out.get("urgency_score", 40),
        # Entities
        "entities":               ents,
        # RAG
        "kb_chunks_used":         len(kb_chunks),
        "kb_sources":             [c["source"] for c in kb_chunks],
        "kb_similarities":        [c["similarity"] for c in kb_chunks],
        # LLM
        "summary":                llm_out.get("summary", ""),
        "clarifying_questions":   llm_out.get("clarifying_questions", []),
        "draft_reply":            llm_out.get("draft_reply", ""),
        "escalation_justification": llm_out.get("escalation_justification", ""),
        "processing_ms":          ms,
        "eval_scores":            eval_scores,
    }


# ── Human-in-the-Loop review ──────────────────────────────────────────────────

@app.post("/review")
def review(req: ReviewIn, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == req.ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    ticket.agent_notes = req.agent_notes

    if req.assigned_to:
        ticket.assigned_to = req.assigned_to

    if req.action == "edit":
        ticket.status = "edited"
        ticket.agent_reply = req.agent_reply
        ticket.resolved_at = None

    elif req.action == "approve":
        ticket.status = "approved"
        ticket.agent_reply = req.agent_reply or ticket.agent_reply or ticket.draft_reply
        ticket.resolved_at = datetime.utcnow()

    elif req.action == "reject":
        ticket.status = "rejected"
        ticket.resolved_at = datetime.utcnow()

    else:
        raise HTTPException(400, "Invalid review action")

    db.commit()
    return {"ticket_id": ticket.id, "status": ticket.status}


# ── Ticket list + detail ──────────────────────────────────────────────────────

@app.get("/tickets")
def list_tickets(
    status:   Optional[str] = None,
    priority: Optional[str] = None,
    skip: int = 0, limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(Ticket)
    if status:   q = q.filter(Ticket.status   == status)
    if priority: q = q.filter(Ticket.priority == priority)
    return [_to_dict(t) for t in q.order_by(Ticket.created_at.desc()).offset(skip).limit(limit)]


@app.get("/tickets/{tid}")
def get_ticket(tid: int, db: Session = Depends(get_db)):
    t = db.query(Ticket).filter(Ticket.id == tid).first()
    if not t:
        raise HTTPException(404, "Ticket not found")
    return _to_dict(t)


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.get("/analytics")
def analytics(db: Session = Depends(get_db)):
    tickets = db.query(Ticket).all()
    total   = len(tickets)
    if total == 0:
        return {"total": 0}

    by_cat = {}; by_pri = {}; by_status = {}
    avg_ms = 0

    for t in tickets:
        by_cat[t.category or "Unknown"]  = by_cat.get(t.category or "Unknown", 0) + 1
        by_pri[t.priority or "Unknown"]  = by_pri.get(t.priority or "Unknown", 0) + 1
        by_status[t.status or "pending"] = by_status.get(t.status or "pending", 0) + 1
        avg_ms += (t.resolution_ms or 0)

    resolved = sum(1 for t in tickets if t.status in ("approved", "edited"))
    p1p2     = sum(1 for t in tickets if t.priority in ("P1", "P2"))

    return {
        "total":             total,
        "resolved":          resolved,
        "resolution_rate":   round(resolved / total * 100, 1),
        "p1_p2_count":       p1p2,
        "avg_processing_ms": round(avg_ms / total),
        "by_category":       by_cat,
        "by_priority":       by_pri,
        "by_status":         by_status,
    }


# ── Train on uploaded CSV (multipart file upload) ───────────────────────────

@app.post("/train/upload")
async def train_upload(
    file: UploadFile = File(...),
    sample_n: str = Form("50000"),
):
    """Accept CSV upload from frontend, save to temp file, start training job."""
    import tempfile
    sample_n_int = int(sample_n)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        content_bytes = await file.read()
        tmp.write(content_bytes)
        tmp_path = tmp.name

    job_id = str(uuid.uuid4())[:8]
    _train_jobs[job_id] = {"status": "running", "result": None, "error": None}

    def _run():
        try:
            from data_pipeline import load_and_clean
            from classifier import IssueClassifier, get_classifier
            from priority_model import PriorityPredictor, get_predictor
            import os

            df = load_and_clean(tmp_path, sample_n=sample_n_int)

            # Classifier
            clf = get_classifier()
            clf._load()
            distilbert_ok = clf._trained and hasattr(clf._model, '_use_onnx')
            if distilbert_ok:
                clf_report = clf.train_report.copy()
                clf_report["source"] = "distilbert_finetuned"
            else:
                new_clf = IssueClassifier()
                clf_report = new_clf.train_on_dataframe(df)
                new_clf.save()

            # Priority
            pred = PriorityPredictor()
            pri_report = pred.train_on_dataframe(df)
            pred.save()

            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

            def _safe(r):
                if not r: return {}
                pc = r.get("per_class", {})
                return {
                    "accuracy":    round(float(r["accuracy"]), 4) if r.get("accuracy") else None,
                    "macro_f1":    round(float(r["macro_f1"]), 4) if r.get("macro_f1") else None,
                    "weighted_f1": round(float(r["weighted_f1"]), 4) if r.get("weighted_f1") else None,
                    "source":      r.get("source"),
                    "model":       r.get("model"),
                    "per_class":   {k: {"precision": float(v["precision"]),
                                        "recall":    float(v["recall"]),
                                        "f1":        float(v["f1"]),
                                        "support":   int(v["support"])}
                                    for k, v in pc.items()} if pc else {},
                }

            _train_jobs[job_id]["result"] = {
                "classifier": _safe(clf_report),
                "priority":   _safe(pri_report),
            }
            _train_jobs[job_id]["status"] = "done"

            # Reload singletons so next /analyze uses the newly trained models
            import priority_model as _pm
            import classifier as _clf_mod
            _pm._predictor   = _pm.PriorityPredictor.load()
            _clf_mod._clf    = None   # force reload on next predict

        except Exception as e:
            import traceback
            _train_jobs[job_id]["status"] = "error"
            _train_jobs[job_id]["error"]  = traceback.format_exc()

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id}


# ── Train on real Jira CSV (background job) ──────────────────────────────────

# In-memory job store — survives for the lifetime of the server process
_train_jobs: dict = {}   # job_id -> {status, result, error}

@app.post("/train")
def train_on_csv(req: TrainIn):
    """
    Kicks off training in a background thread immediately and returns a job_id.
    Poll GET /train/status/{job_id} to check progress.
    """
    import uuid
    job_id = str(uuid.uuid4())[:8]
    _train_jobs[job_id] = {"status": "running", "result": None, "error": None}

    def _run():
        try:
            from data_pipeline import load_and_clean
            from classifier import IssueClassifier
            from priority_model import PriorityPredictor

            df = load_and_clean(req.csv_path, sample_n=req.sample_n)

            clf = IssueClassifier()
            clf_report = clf.train_on_dataframe(df)
            clf.save()

            pred = PriorityPredictor()
            pri_report = pred.train_on_dataframe(df)
            pred.save()

            import classifier as clf_mod
            import priority_model as pri_mod
            clf_mod._clf       = clf
            pri_mod._predictor = pred

            # Strip non-serializable numpy types, keep all display fields
            def _safe(report):
                pc = report.get("per_class", {})
                safe_pc = {
                    k: {
                        "precision": float(v["precision"]),
                        "recall":    float(v["recall"]),
                        "f1":        float(v["f1"]),
                        "support":   int(v["support"]),
                    }
                    for k, v in pc.items()
                } if pc else {}
                return {
                    "accuracy":    round(float(report["accuracy"]), 4) if report.get("accuracy") else None,
                    "macro_f1":    round(float(report["macro_f1"]), 4) if report.get("macro_f1") else None,
                    "weighted_f1": round(float(report["weighted_f1"]), 4) if report.get("weighted_f1") else None,
                    "source":      report.get("source"),
                    "model":       report.get("model"),
                    "train_size":  int(report["train_size"]) if report.get("train_size") else None,
                    "test_size":   int(report["test_size"])  if report.get("test_size")  else None,
                    "per_class":   safe_pc,
                }

            _train_jobs[job_id]["result"] = {
                "rows_used":  int(len(df)),
                "classifier": _safe(clf_report),
                "priority":   _safe(pri_report),
            }
            _train_jobs[job_id]["status"] = "done"

            # Reload singletons so next /analyze uses newly trained models
            import priority_model as _pm
            import classifier as _clf_mod
            _pm._predictor = _pm.PriorityPredictor.load()
            _clf_mod._clf  = None
        except Exception as e:
            import traceback
            _train_jobs[job_id]["status"] = "error"
            _train_jobs[job_id]["error"]  = traceback.format_exc()

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id, "status": "running"}


@app.get("/train/status/{job_id}")
def train_status(job_id: str):
    job = _train_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job

@app.post("/train/upload")
async def train_uploaded_csv(
    file: UploadFile = File(...),
    sample_n: int = Form(50000),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files are supported")

    suffix = ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    import uuid
    job_id = str(uuid.uuid4())[:8]
    _train_jobs[job_id] = {"status": "running", "result": None, "error": None}

    def _run():
        try:
            from data_pipeline import load_and_clean
            from classifier import IssueClassifier
            from priority_model import PriorityPredictor

            df = load_and_clean(tmp_path, sample_n=sample_n)

            from pathlib import Path
            import classifier as clf_mod
            import priority_model as pri_mod

            distilbert_dir = Path(__file__).parent / "distilbert_classifier"
            has_distilbert = (distilbert_dir / "label_map.json").exists()

            if has_distilbert:
                # Keep fine-tuned DistilBERT as the issue classifier
                clf = IssueClassifier()
                clf._load()
                clf_report = clf.train_report
                clf_mod._clf = clf
            else:
                # Fallback only if DistilBERT is not present
                clf = IssueClassifier()
                clf_report = clf.train_on_dataframe(df)
                clf.save()
                clf_mod._clf = clf

            # Always train priority predictor
            pred = PriorityPredictor()
            pri_report = pred.train_on_dataframe(df)
            pred.save()
            pri_mod._predictor = pred


            
            def _safe(report):
                pc = report.get("per_class", {})
                safe_pc = {
                    k: {
                        "precision": float(v["precision"]),
                        "recall": float(v["recall"]),
                        "f1": float(v["f1"]),
                        "support": int(v["support"]),
                    }
                    for k, v in pc.items()
                } if pc else {}

                return {
                    "accuracy": round(float(report["accuracy"]), 4) if report.get("accuracy") else None,
                    "macro_f1": round(float(report["macro_f1"]), 4) if report.get("macro_f1") else None,
                    "weighted_f1": round(float(report["weighted_f1"]), 4) if report.get("weighted_f1") else None,
                    "source": report.get("source"),
                    "model": report.get("model"),
                    "train_size": int(report["train_size"]) if report.get("train_size") else None,
                    "test_size": int(report["test_size"]) if report.get("test_size") else None,
                    "per_class": safe_pc,
                }

            _train_jobs[job_id]["result"] = {
                "rows_used": int(len(df)),
                "classifier": _safe(clf_report),
                "priority": _safe(pri_report),
            }
            _train_jobs[job_id]["status"] = "done"

        except Exception:
            import traceback
            _train_jobs[job_id]["status"] = "error"
            _train_jobs[job_id]["error"] = traceback.format_exc()

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id, "status": "running"}


# ── KB seed endpoint ──────────────────────────────────────────────────────────

@app.post("/kb/seed")
async def kb_seed():
    return await seed_kb()


# ── Reset database ────────────────────────────────────────────────────────────

@app.post("/reset")
def reset_database(db: Session = Depends(get_db)):
    """Delete all tickets from the database — fresh start."""
    count = db.query(Ticket).count()
    db.query(Ticket).delete()
    db.commit()
    return {"deleted": count, "message": "Database cleared successfully"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_dict(t: Ticket) -> dict:
    return {
        "id":             t.id,
        "title":          t.title,
        "description":    t.description,
        "created_at":     t.created_at.isoformat() if t.created_at else None,
        "category":       t.category,
        "priority":       t.priority,
        "sla_risk":       t.sla_risk,
        "sla_breach_pct": t.sla_breach_pct,
        "entities":       t.entities,
        "kb_sources":     t.kb_sources,
        "status":         t.status,
        "summary":        t.summary,
        "clarifying_qs":  t.clarifying_qs,
        "draft_reply":    t.draft_reply,
        "agent_reply":    t.agent_reply,
        "agent_notes":    t.agent_notes,
        "assigned_to":    t.assigned_to,
        "resolved_at":    t.resolved_at.isoformat() if t.resolved_at else None,
        "resolution_ms":  t.resolution_ms,
    }