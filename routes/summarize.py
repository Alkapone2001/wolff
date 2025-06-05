# routes/summarize.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import MessageHistory
from summarization import summarize_messages   # root‐level import
from datetime import datetime
from typing import List

router = APIRouter(tags=["Summarization"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/summarize-context/{client_id}")
def summarize_context(client_id: str, db: Session = Depends(get_db)):
    """
    POST /summarize-context/{client_id}
    Summarize all user/assistant messages for the given client_id.
    Stores the summary back into MessageHistory (role="summary").
    """
    # 1. Fetch all user & assistant messages (chronological)
    messages = (
        db.query(MessageHistory)
        .filter(
            MessageHistory.client_id == client_id,
            MessageHistory.role.in_(["user", "assistant"])
        )
        .order_by(MessageHistory.timestamp.asc())
        .all()
    )

    if not messages:
        raise HTTPException(status_code=404, detail="No messages found for this client_id")

    # 2. Convert them to simple dicts
    chat = [{"role": m.role, "content": m.content} for m in messages]

    # 3. Call the summarizer
    try:
        summary = summarize_messages(chat)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization error: {e}")

    # 4. Store the summary as a new MessageHistory entry
    summary_entry = MessageHistory(
        client_id=client_id,
        role="summary",
        content=summary,
        timestamp=datetime.utcnow()
    )
    db.add(summary_entry)
    db.commit()

    return {"summary": summary}
