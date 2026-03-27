"""
dhofar_processor.py

Processes Dhofar Customer Card PDFs:
  - Extracts customer/account header fields
  - Extracts ALL statement line rows (posting_date, document_no, lpo,
    sell_to_customer_name, original_amount, remaining_amount, running_total)
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any, Dict, List, Optional

from pdf2image import convert_from_path
from pydantic import BaseModel, Field, ConfigDict

from llm_client import LLMClient


# ============================================================
# Pydantic Models
# ============================================================

class CustomerAddress(BaseModel):
    model_config = ConfigDict(extra="allow")
    street: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    po_box: Optional[str] = None


class CustomerContactInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    phone: Optional[str] = None
    email: Optional[str] = None
    fax: Optional[str] = None
    website: Optional[str] = None


class StatementRow(BaseModel):
    """One line from the customer account statement table."""
    model_config = ConfigDict(extra="allow")
    posting_date: Optional[str] = Field(None, description="Posting date (DD/MM/YY or DD/MM/YYYY)")
    document_no: Optional[str] = Field(None, description="Document / invoice number e.g. DICSI26015130")
    lpo: Optional[str] = Field(None, description="LPO / order reference")
    sell_to_customer_name: Optional[str] = Field(None, description="Sell-to customer name on this line")
    original_amount: Optional[float] = Field(None, description="Original invoice amount (AED)")
    remaining_amount: Optional[float] = Field(None, description="Remaining / outstanding amount (AED)")
    running_total: Optional[float] = Field(None, description="Running balance after this row (AED)")


class CustomerCardModel(BaseModel):
    """Full customer card: header + all statement rows."""
    model_config = ConfigDict(extra="allow")

    # Header fields
    customer_id: Optional[str] = Field(None, description="Customer code e.g. CLAE05820")
    customer_name: str = Field(..., description="Full legal company name")
    trade_name: Optional[str] = Field(None, description="Trade / DBA name")
    account_type: Optional[str] = Field(None, description="GOLIVE / PROSPECT / ACTIVE etc.")
    status: Optional[str] = Field(None, description="Account status")
    currency: Optional[str] = Field(None, description="Currency code e.g. AED")
    credit_limit: Optional[float] = Field(None, description="Credit limit")
    payment_terms: Optional[str] = Field(None, description="Payment terms")
    industry: Optional[str] = Field(None, description="Industry / sector")
    registration_number: Optional[str] = Field(None, description="Trade licence / company reg number")
    tax_registration_number: Optional[str] = Field(None, description="TRN / VAT number")
    address: Optional[CustomerAddress] = Field(None, description="Primary address")
    contact: Optional[CustomerContactInfo] = Field(None, description="Contact info")
    account_manager: Optional[str] = Field(None, description="Account manager name")
    statement_date: Optional[str] = Field(None, description="Statement / document date")
    statement_number: Optional[str] = Field(None, description="Statement number")
    starting_date: Optional[str] = Field(None, description="Statement period start")
    ending_date: Optional[str] = Field(None, description="Statement period end")
    total_balance: Optional[float] = Field(None, description="Total outstanding balance (AED)")
    overdue_amount: Optional[float] = Field(None, description="Overdue amount (AED)")

    # Statement rows — the core data
    statement_rows: List[StatementRow] = Field(
        default_factory=list,
        description="All line items from the statement table"
    )

    # Catch-all for anything else
    raw_fields: Optional[Dict[str, Any]] = Field(None, description="Extra fields")


class DhofarDocumentResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    document_type: str = "customer_card"
    customer_card: Optional[CustomerCardModel] = None
    source_filename: Optional[str] = None


# ============================================================
# Classifier
# ============================================================

class CustomerCardClassifier:
    """Extracts header + all statement rows from a Customer Card PDF."""

    def __init__(self, poppler_path: Optional[str] = None) -> None:
        self.llm = LLMClient()
        self.poppler_path = poppler_path

    def _pdf_to_b64_images(self, pdf_path: Path, dpi: int = 250) -> List[str]:
        pages = convert_from_path(pdf_path.as_posix(), dpi=dpi, poppler_path=self.poppler_path)
        result = []
        for page in pages:
            buf = io.BytesIO()
            page.save(buf, "PNG")
            result.append(base64.b64encode(buf.getvalue()).decode())
        return result

    def classify_pdf(self, pdf_path: str | Path) -> DhofarDocumentResult:
        pdf_path = Path(pdf_path)
        images = self._pdf_to_b64_images(pdf_path)
        if not images:
            raise RuntimeError(f"No images from {pdf_path}")

        user_content: List[Dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "This is a Dhofar Global customer account statement PDF. "
                    "Extract:\n"
                    "1. All header fields: customer_id, customer_name, trade_name, "
                    "account_type, currency, credit_limit, payment_terms, address, contact, "
                    "account_manager, statement_date, statement_number, starting_date, "
                    "ending_date, total_balance, overdue_amount.\n"
                    "2. EVERY row from the statement table as statement_rows. "
                    "Each row has: posting_date, document_no, lpo, sell_to_customer_name, "
                    "original_amount, remaining_amount, running_total.\n"
                    "Extract ALL rows — do not skip any. "
                    "Negative amounts (payments/credits) should be negative numbers."
                ),
            }
        ]
        for b64 in images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })

        system_prompt = (
            "You are an expert at extracting structured data from financial account statements. "
            "Extract every single row from the statement table — including payment rows with negative amounts. "
            "Return null for missing fields. Do not invent data."
        )

        result = self.llm.parse_structured(
            model_name=None,
            system_prompt=system_prompt,
            user_content=user_content,
            response_model=CustomerCardModel,
            temperature=0.0,
            max_tokens=4000,
        )

        return DhofarDocumentResult(
            document_type="customer_card",
            customer_card=result,
            source_filename=pdf_path.name,
        )
