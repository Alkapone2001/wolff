# routes/summarize.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import MessageHistory
from utils.summarization import summarize_messages  # updated import
from datetime import datetime

router = APIRouter()

# Dependency to get a DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/summarize-context/{client_id}")
def summarize_context(client_id: str, db: Session = Depends(get_db)):
    # Fetch all user/assistant messages for this client, in chronological order
    messages = (
        db.query(MessageHistory)
        .filter(MessageHistory.client_id == client_id, MessageHistory.role.in_(["user", "assistant"]))
        .order_by(MessageHistory.timestamp.asc())
        .all()
    )

    if not messages:
        raise HTTPException(status_code=404, detail="No messages found for this client_id")

    # Convert ORM objects into simple dicts for summarization
    chat = [{"role": m.role, "content": m.content} for m in messages]

    # Call our new summarize_messages function
    try:
        summary = summarize_messages(chat)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization error: {e}")

    # Optionally, store the summary back into MessageHistory as a “summary” role
    from models import MessageHistory as MH  # avoid circular import
    summary_entry = MH(
        client_id=client_id,
        role="summary",
        content=summary,
        timestamp=datetime.utcnow()
    )
    db.add(summary_entry)
    db.commit()

    return {"summary": summary}
