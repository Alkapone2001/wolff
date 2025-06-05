from sqlalchemy import Column, String, Integer, DateTime, JSON, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class ClientContext(Base):
    __tablename__ = 'client_contexts'

    client_id = Column(String, primary_key=True, index=True)
    conversation_id = Column(String, index=True)
    current_step = Column(String, default="awaiting_invoice")
    last_message = Column(String, nullable=True)
    additional_data = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    invoices = relationship("InvoiceContext", back_populates="client_context")
    messages = relationship("MessageHistory", back_populates="client_context", cascade="all, delete-orphan")  # ✅ new

class InvoiceContext(Base):
    __tablename__ = 'invoice_contexts'

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String, index=True)
    status = Column(String, default="received")
    date_uploaded = Column(DateTime, default=datetime.utcnow)
    client_id = Column(String, ForeignKey('client_contexts.client_id'))

    ocr_text = Column(Text, nullable=True)
    prompt_used = Column(Text, nullable=True)
    llm_response_raw = Column(Text, nullable=True)

    client_context = relationship("ClientContext", back_populates="invoices")

class MessageHistory(Base):
    __tablename__ = "message_history"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(String, ForeignKey('client_contexts.client_id'), index=True)
    role = Column(String)  # 'user' or 'assistant'
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

    client_context = relationship("ClientContext", back_populates="messages")
