from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from database import SessionLocal
from models import MessageHistory
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

router = APIRouter(prefix="/message-history", tags=["Message History"])


# Pydantic response model
class MessageResponse(BaseModel):
    id: int
    client_id: str
    role: str
    content: str
    timestamp: datetime

    class Config:
        orm_mode = True


# Dependency to get DB session
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
    query = db.query(MessageHistory)
    if client_id:
        query = query.filter(MessageHistory.client_id == client_id)
    if role:
        query = query.filter(MessageHistory.role == role)
    query = query.order_by(MessageHistory.timestamp.desc()).limit(limit)
    return query.all()
