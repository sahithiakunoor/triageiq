"""
Layer 1 — Infrastructure: PostgreSQL via SQLAlchemy
Falls back to SQLite for local dev / HuggingFace Spaces (no DATABASE_URL set).
"""

import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Text,
    DateTime, Float, JSON
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./supportiq.db")

# Render / some hosts give postgres:// — SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    poolclass=StaticPool if _is_sqlite else None,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Ticket(Base):
    __tablename__ = "tickets"

    id              = Column(Integer, primary_key=True, index=True)
    title           = Column(String(500), nullable=False)
    description     = Column(Text)
    created_at      = Column(DateTime, default=datetime.utcnow)

    # Layer 2 — ML outputs
    category        = Column(String(100))       # Bug / Feature / Incident / Task
    category_conf   = Column(Float)
    priority        = Column(String(20))        # P1–P5 (normalised)
    priority_raw    = Column(String(100))       # raw label from model
    priority_conf   = Column(Float)
    sla_risk        = Column(String(20))        # Critical / High / Medium / Low
    sla_breach_pct  = Column(Integer)

    # Layer 2 — NLP / entity extraction (spaCy)
    entities        = Column(JSON)              # {error_codes, versions, platform_os, ...}

    # Layer 2 — RAG + LLM outputs
    kb_sources      = Column(JSON)              # list of source filenames used
    summary         = Column(Text)
    clarifying_qs   = Column(JSON)
    draft_reply     = Column(Text)

    # Layer 3 — Human-in-the-Loop
    status          = Column(String(30), default="pending")   # pending|approved|edited|rejected
    agent_reply     = Column(Text)
    agent_notes     = Column(Text)
    assigned_to     = Column(String(100))
    resolved_at     = Column(DateTime)
    resolution_ms   = Column(Integer)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
