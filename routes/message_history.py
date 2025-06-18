# routes/message_history.py

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import MessageHistory
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

router = APIRouter(prefix="/message-history", tags=["Message History"])

class MessageResponse(BaseModel):
    id: int
    client_id: str
    role: str
    content: str
    timestamp: datetime

    class Config:
        from_attributes = True  # Pydantic v2 replacement for orm_mode

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=List[MessageResponse])
def get_message_history(
    client_id: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    GET /message-history/?client_id=foo&role=user
    Returns up to `limit` most recent messages (desc by timestamp).
    """
    query = db.query(MessageHistory)
    if client_id:
        query = query.filter(MessageHistory.client_id == client_id)
    if role:
        query = query.filter(MessageHistory.role == role)
    query = query.order_by(MessageHistory.timestamp.desc()).limit(limit)
    return query.all()

@router.get("/{client_id}", response_model=List[MessageResponse])
def get_message_history_by_id(client_id: str, db: Session = Depends(get_db)):
    """
    GET /message-history/{client_id}
    Returns all messages for that client_id, sorted ascending.
    """
    messages = (
        db.query(MessageHistory)
        .filter(MessageHistory.client_id == client_id)
        .order_by(MessageHistory.timestamp.asc())
        .all()
    )
    if not messages:
        raise HTTPException(status_code=404, detail="No messages found for this client_id")
    return messages
