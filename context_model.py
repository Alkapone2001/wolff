from typing import List, Dict, Optional
from datetime import datetime

class InvoiceContext:
    def __init__(self,
                 invoice_number: str,
                 status: str = "received",
                 date_uploaded: Optional[datetime] = None):
        self.invoice_number = invoice_number
        self.status = status
        self.date_uploaded = date_uploaded or datetime.utcnow()

    def to_dict(self):
        return {
            "invoice_number": self.invoice_number,
            "status": self.status,
            "date_uploaded": self.date_uploaded.isoformat(),
        }

class ClientContext:
    def __init__(self,
                 client_id: str,
                 conversation_id: str,
                 uploaded_invoices: Optional[List[InvoiceContext]] = None,
                 current_step: str = "awaiting_invoice",
                 last_message: str = "",
                 additional_data: Optional[Dict] = None):
        self.client_id = client_id
        self.conversation_id = conversation_id
        self.uploaded_invoices = uploaded_invoices or []
        self.current_step = current_step
        self.last_message = last_message
        self.additional_data = additional_data or {}

    def to_dict(self):
        return {
            "client_id": self.client_id,
            "conversation_id": self.conversation_id,
            "uploaded_invoices": [inv.to_dict() for inv in self.uploaded_invoices],
            "current_step": self.current_step,
            "last_message": self.last_message,
            "additional_data": self.additional_data,
        }
