from sqlalchemy.orm import Session
from models import ClientContext, InvoiceContext, MessageHistory
from datetime import datetime

def get_or_create_context(db: Session, client_id: str) -> ClientContext:
    context = db.query(ClientContext).filter(ClientContext.client_id == client_id).first()
    if not context:
        context = ClientContext(
            client_id=client_id,
            conversation_id=str(datetime.utcnow().timestamp()),
            current_step="awaiting_invoice"
        )
        db.add(context)
        db.commit()
        db.refresh(context)
    return context

def add_invoice(db: Session, client_id: str, invoice_number: str) -> InvoiceContext:
    context = get_or_create_context(db, client_id)
    invoice = InvoiceContext(
        invoice_number=invoice_number,
        status="received",
        date_uploaded=datetime.utcnow(),
        client_id=client_id
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice

def update_context_step(db: Session, client_id: str, step: str) -> ClientContext:
    context = get_or_create_context(db, client_id)
    context.current_step = step
    db.commit()
    db.refresh(context)
    return context

def update_last_message(db: Session, client_id: str, message: str) -> ClientContext:
    context = get_or_create_context(db, client_id)
    context.last_message = message
    db.commit()
    db.refresh(context)
    return context

def get_context(db: Session, client_id: str) -> ClientContext:
    return db.query(ClientContext).filter(ClientContext.client_id == client_id).first()

def log_message(db, client_id: str, role: str, content: str):
    message = MessageHistory(
        client_id=client_id,
        role=role,
        content=content,
        timestamp=datetime.utcnow()
    )
    db.add(message)
    db.commit()