# context_manager.py

from sqlalchemy.orm import Session
from models import ClientContext, InvoiceContext, MessageHistory
from schemas.mcp import ModelContext, Memory, MessageItem
from datetime import datetime

# -------------------------------------------------------------------------------------------------
# 1) get_or_create_context
# -------------------------------------------------------------------------------------------------
def get_or_create_context(db: Session, client_id: str) -> ClientContext:
    context = db.query(ClientContext).filter(ClientContext.client_id == client_id).first()
    if not context:
        context = ClientContext(
            client_id=client_id,
            conversation_id=str(datetime.utcnow().timestamp()),
            current_step="awaiting_invoice",   # <--- use current_step
            last_message="",
            additional_data={}
        )
        db.add(context)
        db.commit()
        db.refresh(context)
    return context

# -------------------------------------------------------------------------------------------------
# 2) add_invoice
# -------------------------------------------------------------------------------------------------
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

# -------------------------------------------------------------------------------------------------
# 3) update_context_step (still uses current_step)
# -------------------------------------------------------------------------------------------------
def update_context_step(db: Session, client_id: str, step: str) -> ClientContext:
    context = get_or_create_context(db, client_id)
    context.current_step = step    # <--- use current_step
    db.commit()
    db.refresh(context)
    return context

# -------------------------------------------------------------------------------------------------
# 4) update_last_message
# -------------------------------------------------------------------------------------------------
def update_last_message(db: Session, client_id: str, message: str) -> ClientContext:
    context = get_or_create_context(db, client_id)
    context.last_message = message
    db.commit()
    db.refresh(context)
    return context

# -------------------------------------------------------------------------------------------------
# 5) get_context
# -------------------------------------------------------------------------------------------------
def get_context(db: Session, client_id: str) -> ClientContext:
    return db.query(ClientContext).filter(ClientContext.client_id == client_id).first()

# -------------------------------------------------------------------------------------------------
# 6) log_message
# -------------------------------------------------------------------------------------------------
def log_message(db: Session, client_id: str, role: str, content: str) -> MessageHistory:
    """
    Logs a new MessageHistory entry with the given role and content.
    """
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

# -------------------------------------------------------------------------------------------------
# 7) build_model_context
# -------------------------------------------------------------------------------------------------
def build_model_context(db: Session, client_id: str, max_history: int = 20) -> ModelContext:
    """
    Assemble a ModelContext for MCP.
    - memory.last_summary: latest summary message (if any)
    - memory.additional_data: { "current_step": ..., "last_message": ... }
    - messages: up to `max_history` user/assistant messages (oldest first)
    - tool_inputs: None (for now)
    - tools: will be injected by main.py before sending to GPT
    """
    # A) Fetch the ClientContext
    client_ctx = db.query(ClientContext).filter(ClientContext.client_id == client_id).first()
    if not client_ctx:
        raise ValueError(f"No ClientContext found for client_id={client_id!r}")

    # B) Get the latest “summary” row (if it exists)
    last_summary_entry = (
        db.query(MessageHistory)
        .filter(
            MessageHistory.client_id == client_id,
            MessageHistory.role == "summary"
        )
        .order_by(MessageHistory.timestamp.desc())
        .first()
    )
    summary_text = last_summary_entry.content if last_summary_entry else None

    # C) Build Memory object
    memory = Memory(
        last_summary=summary_text,
        additional_data={
            "current_step": client_ctx.current_step,  # <--- use current_step
            "last_message": client_ctx.last_message
        }
    )

    # D) Fetch recent user/assistant messages (excluding “summary”)
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
    recent_msgs = list(reversed(recent_msgs))  # oldest first

    # E) Convert each to a MessageItem instance
    msgs = []
    for m in recent_msgs:
        msgs.append(
            MessageItem(
                role=m.role,
                content=m.content,
                timestamp=m.timestamp
            )
        )

    # F) Construct ModelContext (tools will be injected later)
    model_ctx = ModelContext(
        memory=memory,
        messages=msgs,
        tool_inputs=None,
        tools=None   # main.py will populate this before sending to GPT
    )

    return model_ctx

# -------------------------------------------------------------------------------------------------
# 8) auto_summarize_if_needed
# -------------------------------------------------------------------------------------------------
def auto_summarize_if_needed(db: Session, client_id: str, threshold: int = 15):
    """
    If there are more than `threshold` user/assistant messages for this client,
    automatically call summarization and delete older chat rows.
    """
    # 8A) Count user/assistant messages (ignore role="summary")
    count = (
        db.query(MessageHistory)
        .filter(
            MessageHistory.client_id == client_id,
            MessageHistory.role.in_(["user", "assistant"])
        )
        .count()
    )
    if count <= threshold:
        return

    # 8B) Trigger summarization (reuse the existing summarize_context endpoint logic)
    from routes.summarize import summarize_context
    result = summarize_context(client_id, db)  # returns {"summary": ...}
    summary_text = result.get("summary", "")

    # 8C) Find IDs of the most recent `threshold` messages (desc), then prune others
    recent_ids = [
        m.id for m in (
            db.query(MessageHistory.id)
            .filter(
                MessageHistory.client_id == client_id,
                MessageHistory.role.in_(["user", "assistant"])
            )
            .order_by(MessageHistory.timestamp.desc())
            .limit(threshold)
            .all()
        )
    ]

    # Delete any user/assistant messages not in recent_ids
    db.query(MessageHistory).filter(
        MessageHistory.client_id == client_id,
        MessageHistory.role.in_(["user", "assistant"]),
        ~MessageHistory.id.in_(recent_ids)
    ).delete(synchronize_session=False)
    db.commit()

    # 8D) After summarization, the new MessageHistory row with role="summary"
    #       has already been inserted by summarize_context(), so no further action needed.
