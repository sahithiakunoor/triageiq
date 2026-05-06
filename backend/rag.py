"""
Layer 2 — RAG Pipeline: ChromaDB vector store
Deck: "Embed → Query ChromaDB → LLM prompt"
Notebook sections 10–11:
  - KB documents from .txt files
  - SentenceTransformer('all-MiniLM-L6-v2') local embeddings
  - Sliding-window chunking (120 words, 25 overlap)
  - ChromaDB PersistentClient with cosine similarity
  - Historical resolved tickets written into KB
  - Fallback: TF-IDF cosine similarity when sentence-transformers unavailable
"""

import os, hashlib, math
from pathlib import Path
from typing import Optional
import numpy as np

import chromadb
from chromadb.config import Settings

CHROMA_PATH = Path(os.getenv("CHROMA_PATH", "./chroma_db"))
KB_DIR      = Path(os.getenv("KB_DIR", "./data/kb"))
KB_DIR.mkdir(parents=True, exist_ok=True)

_client     = None
_collection = None
_embedder   = None          # SentenceTransformer instance
_tfidf_vecs = None          # fallback TF-IDF vectors
_tfidf_docs = None          # matching documents for fallback


# ── SentenceTransformer (local, matches notebook) ────────────────────────────

def _get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder
    try:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        _embedder = False   # fallback sentinel
    return _embedder


def _embed(text: str) -> list[float]:
    """Embed with SentenceTransformer or hash fallback."""
    emb = _get_embedder()
    if emb:
        vec = emb.encode([text[:512]])[0]
        return vec.tolist()
    return _hash_embed(text, 384)


def _hash_embed(text: str, dims: int = 384) -> list[float]:
    words = text.lower().split()
    vec = [0.0] * dims
    for i, word in enumerate(words):
        h   = int(hashlib.md5(word.encode()).hexdigest(), 16)
        idx = h % dims
        vec[idx] += 1.0 / (i + 1)
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


# ── Sliding-window chunking (notebook section 11) ────────────────────────────

def chunk_text(text: str, chunk_size: int = 120, overlap: int = 25) -> list[str]:
    words  = text.split()
    chunks = []
    start  = 0
    while start < len(words):
        chunks.append(" ".join(words[start: start + chunk_size]))
        start += chunk_size - overlap
    return [c for c in chunks if len(c.split()) > 5]


# ── ChromaDB client ───────────────────────────────────────────────────────────

def _get_collection():
    global _client, _collection
    if _collection is None:
        _client     = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _collection = _client.get_or_create_collection(
            "support_kb",
            metadata={"hnsw:space": "cosine"}
        )
    return _collection


# ── KB documents (notebook section 10 + extended) ────────────────────────────

KB_DOCS = {
    "login_runbook.txt": (
        "Login issue runbook: confirm username exists, try password reset, check browser cookies "
        "and cache, verify SSO provider status, check MFA device sync, review auth service logs "
        "for 401/403 patterns, check account lockout status. Common fix: clear cookies, restart "
        "auth-service pod, verify JWT secret rotation."
    ),
    "billing_runbook.txt": (
        "Billing issue runbook: ask for invoice ID, transaction date, payment method, account "
        "email, and screenshot. Check Stripe/payment gateway status page. Verify webhook "
        "endpoints responding. Review payment-service logs for timeout patterns. Notify finance "
        "team immediately for P1 payment incidents. Check for duplicate charges."
    ),
    "bug_runbook.txt": (
        "Bug triage runbook: collect steps to reproduce, expected behavior, actual behavior, "
        "full error logs, environment details, version number, screenshots, and any recent changes. "
        "Route reproducible bugs to engineering with complete reproduction case."
    ),
    "performance_runbook.txt": (
        "Performance issue runbook: ask for region, latency measurements, browser and device, "
        "timestamps, specific endpoint, network details, and frequency. Check DB query times in "
        "monitoring. Review CPU and memory metrics. Check CDN cache hit rates. Look for N+1 "
        "query patterns. Scale horizontally if CPU over 80 percent."
    ),
    "escalation_policy.txt": (
        "Escalation policy: P1 includes production outage, security incident, data loss, or "
        "total service unavailability. P2 includes major degraded functionality affecting many "
        "users. P1 requires immediate escalation to on-call engineer. SLA: P1 1hr response "
        "4hr resolution, P2 4hr response 8hr resolution, P3 8hr response 48hr resolution."
    ),
    "data_export_faq.txt": (
        "CSV and data export FAQ: exports available for all paid plans. Go to Settings > Data "
        "> Export. Exports generated asynchronously and emailed when ready. Under 10k rows "
        "typically 5 minutes. Over 100k rows may time out, use paginated API instead. "
        "Known issue: empty files caused by background job queue backlog."
    ),
    "password_reset_faq.txt": (
        "Password reset FAQ: click Forgot Password on login page. Reset link emailed within "
        "2 minutes. Link expires in 24 hours. If email not received check spam folder, verify "
        "email address is correct, check account exists. Contact support if still not received."
    ),
    "feature_request_process.txt": (
        "Feature request process: describe the use case not just the feature. Include affected "
        "user count and business impact. High-voted requests over 50 upvotes get expedited review. "
        "Timeline: typically 1 to 3 sprints for approved features. Submit via product portal."
    ),
}


async def seed_kb(resolved_tickets: list[dict] = None):
    """
    Phase 1 (deck): Ingest KB documents + optional resolved tickets into ChromaDB.
    Matches notebook sections 10–11.
    """
    collection = _get_collection()
    existing   = set(collection.get()["ids"])

    # Write KB .txt files to disk
    for fname, content in KB_DOCS.items():
        fpath = KB_DIR / fname
        if not fpath.exists():
            fpath.write_text(content, encoding="utf-8")

    # Add historical resolved tickets to KB (notebook section 10)
    if resolved_tickets:
        rt_path = KB_DIR / "historical_resolved_tickets.txt"
        with open(rt_path, "w", encoding="utf-8") as f:
            for row in resolved_tickets[:200]:
                f.write(
                    f"Issue Type: {row.get('issue_type', '')}\n"
                    f"Priority: {row.get('priority', '')}\n"
                    f"Text: {str(row.get('text', ''))[:1000]}\n---\n"
                )

    # Chunk + embed all .txt files
    all_chunks, ids, docs, metas = [], [], [], []
    for path in KB_DIR.glob("*.txt"):
        text   = path.read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            cid = f"{path.stem}_{i}"
            if cid not in existing:
                all_chunks.append({"id": cid, "source": path.name, "text": chunk})

    if not all_chunks:
        return {"seeded": 0, "total": collection.count()}

    embeddings = []
    for c in all_chunks:
        embeddings.append(_embed(c["text"]))
        ids.append(c["id"])
        docs.append(c["text"])
        metas.append({"source": c["source"]})

    collection.add(embeddings=embeddings, ids=ids, documents=docs, metadatas=metas)
    return {"seeded": len(all_chunks), "total": collection.count()}


async def retrieve_context(query: str, top_k: int = 3) -> list[dict]:
    """
    Phase 2 (deck): Embed ticket → query ChromaDB → return top-K chunks.
    Matches notebook section 11: retrieve_kb().
    """
    collection = _get_collection()
    if collection.count() == 0:
        await seed_kb()

    q_emb   = _embed(query)
    results = collection.query(
        query_embeddings=[q_emb],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "text":       doc,
            "source":     meta.get("source", "unknown"),
            "similarity": round(1 - dist, 3),
        })
    return chunks
