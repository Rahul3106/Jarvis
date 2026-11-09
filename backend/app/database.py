import os
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, DateTime, ForeignKey, Text, Float, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jarvis.db")

# Ensure SQLite database directory exists before connection pool creation
if DATABASE_URL.startswith("sqlite"):
    db_file_path = DATABASE_URL.replace("sqlite:///", "")
    if db_file_path.startswith("./"):
        db_file_path = db_file_path[2:]
    db_dir = os.path.dirname(os.path.abspath(db_file_path))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

# Use SQLite compatible arguments if using SQLite
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Incident(Base):
    __tablename__ = "incidents"

    id = Column(String, primary_key=True, index=True) # e.g. INC-2026-102
    service = Column(String, index=True)
    alert_name = Column(String)
    status = Column(String, default="INVESTIGATING") # INVESTIGATING, EXECUTING_FIX, VERIFYING, RESOLVED, FAILED, PENDING_APPROVAL
    severity = Column(String)
    root_cause = Column(Text, nullable=True)
    confidence = Column(Integer, nullable=True)          # 0-100 confidence score from RCA
    risk_level = Column(String, nullable=True)            # LOW / MEDIUM / HIGH / CRITICAL
    evidence = Column(Text, nullable=True)                # JSON string: list of evidence items
    affected_services = Column(Text, nullable=True)       # JSON string: list of service names
    reasoning_summary = Column(Text, nullable=True)       # LLM reasoning narrative
    resolution_action = Column(Text, nullable=True)
    resolution_time_seconds = Column(Float, nullable=True)
    
    # Business & User Impact metrics
    failed_transactions = Column(Integer, default=0, nullable=True)
    failed_logins = Column(Integer, default=0, nullable=True)
    impact_summary = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    logs = relationship("IncidentLog", back_populates="incident", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="incident")

class IncidentLog(Base):
    __tablename__ = "incident_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    incident_id = Column(String, ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    level = Column(String, default="INFO") # INFO, WARNING, ERROR, AGENT_THOUGHT, AGENT_ACTION, AGENT_RESULT
    message = Column(Text)

    incident = relationship("Incident", back_populates="logs")

class Event(Base):
    """
    Unified Event Data Model for Multi-Source Ingestion:
    Collects events from APIs, uploaded log files (.log, .txt, JSON),
    AlertManager webhooks, and simulated live telemetry.
    """
    __tablename__ = "events"

    id = Column(String, primary_key=True, index=True) # e.g. EVT-20261109-1A2B3C4D
    incident_id = Column(String, ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True, index=True)
    source = Column(String, default="api", index=True) # api, file, alertmanager, simulator
    service = Column(String, index=True)
    event_type = Column(String, default="log", index=True) # alert, log, metric_anomaly, transaction_failure, login_failure
    severity = Column(String, default="info") # info, warning, error, critical
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    message = Column(Text)
    trace_id = Column(String, nullable=True, index=True)
    raw_payload = Column(Text, nullable=True) # JSON string representation
    metadata_json = Column(Text, nullable=True) # JSON string with extra attributes (e.g. error_code, latency_ms)

    incident = relationship("Incident", back_populates="events")

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "source": self.source,
            "service": self.service,
            "event_type": self.event_type,
            "severity": self.severity,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "message": self.message,
            "trace_id": self.trace_id,
            "raw_payload": self.raw_payload,
            "metadata_json": self.metadata_json,
        }

def init_db():
    Base.metadata.create_all(bind=engine)
    # Perform non-destructive column migrations for SQLite if columns were added
    if DATABASE_URL.startswith("sqlite"):
        try:
            with engine.connect() as conn:
                res = conn.execute(text("PRAGMA table_info(incidents);"))
                existing_cols = [row[1] for row in res.fetchall()]
                if existing_cols:
                    if "failed_transactions" not in existing_cols:
                        conn.execute(text("ALTER TABLE incidents ADD COLUMN failed_transactions INTEGER DEFAULT 0;"))
                    if "failed_logins" not in existing_cols:
                        conn.execute(text("ALTER TABLE incidents ADD COLUMN failed_logins INTEGER DEFAULT 0;"))
                    if "impact_summary" not in existing_cols:
                        conn.execute(text("ALTER TABLE incidents ADD COLUMN impact_summary TEXT;"))
                    conn.commit()
        except Exception:
            pass

# Auto-create tables before connection pools or sessions are accessed
try:
    init_db()
except Exception:
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
