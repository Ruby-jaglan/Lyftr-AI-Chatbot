import json
import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(128), nullable=False, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column("metadata", Text, nullable=True)
    created_at = Column(String, nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

class ChatSession(Base):
    __tablename__ = "sessions"
    session_id = Column(String(128), primary_key=True)
    system_prompt = Column(Text, nullable=True)

def create_tables():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def save_message(db, session_id, role, content, metadata=None):
    message = Message(session_id=session_id, role=role, content=content, metadata_json=json.dumps(metadata) if metadata else None)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message

def get_session_messages(db, session_id):
    return db.query(Message).filter(Message.session_id == session_id).order_by(Message.id.asc()).all()

def get_or_create_session(db, session_id, system_prompt=None):
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if session is None:
        session = ChatSession(session_id=session_id, system_prompt=system_prompt)
        db.add(session)
    elif system_prompt is not None:
        session.system_prompt = system_prompt
    db.commit()
    return session
