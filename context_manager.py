# context_manager.py

from sqlalchemy.orm import Session
from models import ClientContext, InvoiceContext, MessageHistory
from schemas.mcp import ModelContext, Memory, MessageItem
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

def log_message(db: Session, client_id: str, role: str, content: str) -> MessageHistory:
    msg = MessageHistory(
        client_id=client_id,
        role=role,
        content=content,
        timestamp=datetime.utcnow()
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg

def build_model_context(db: Session, client_id: str, max_history: int = 20) -> ModelContext:
    """
    Assemble a ModelContext for MCP. This includes:
      - memory.last_summary  (latest “summary” message)
      - memory.additional_data  (e.g., current_step + last_message)
      - messages: up to max_history “user”/“assistant” messages
      - tool_inputs: None for now
    """
    # 1. Fetch ClientContext
    client_ctx = db.query(ClientContext).filter(ClientContext.client_id == client_id).first()
    if not client_ctx:
        raise ValueError(f"No ClientContext found for client_id={client_id!r}")

    # 2. Get latest “summary” entry, if any
    last_summary_entry = (
        db.query(MessageHistory)
        .filter(MessageHistory.client_id == client_id, MessageHistory.role == "summary")
        .order_by(MessageHistory.timestamp.desc())
        .first()
    )
    summary_text = last_summary_entry.content if last_summary_entry else None

    # 3. Build Memory object
    memory = Memory(
        last_summary=summary_text,
        additional_data={
            "current_step": client_ctx.current_step,
            "last_message": client_ctx.last_message
        }
    )

    # 4. Fetch recent “user”/“assistant” messages, excluding “summary”
    recent_msgs = (
        db.query(MessageHistory)
        .filter(
            MessageHistory.client_id == client_id,
            MessageHistory.role.in_(["user", "assistant"])
        )
        .order_by(MessageHistory.timestamp.desc())
        .limit(max_history)
        .all()
    )
    # Reverse so oldest is first
    recent_msgs = list(reversed(recent_msgs))

    # 5. Convert to MessageItem instances
    msgs = []
    for m in recent_msgs:
        msgs.append(
            MessageItem(
                role=m.role,
                content=m.content,
                timestamp=m.timestamp
            )
        )

    # 6. Construct and return ModelContext
    model_ctx = ModelContext(
        memory=memory,
        messages=msgs,
        tool_inputs=None
    )
    return model_ctx
