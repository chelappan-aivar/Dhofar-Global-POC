"""
document_classifier.py

- Converts a PDF to high-res images (300 DPI).
- Encodes images to Base64.
- Sends payload to GPT-4o via Chat Completions API.
- Uses 'client.beta.chat.completions.parse' for direct Pydantic extraction.
"""

from __future__ import annotations

import base64
import re
from enum import Enum
from pathlib import Path
from typing import List, Optional, Union

from pdf2image import convert_from_path
from pydantic import BaseModel, Field, field_validator, ConfigDict

from llm_client import LLMClient

# ============================================================
# Pydantic Models (Strict Mode Compliant)
# ============================================================

class DocumentType(str, Enum):
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    GOODS_RECEIPT = "goods_receipt_note"

def _normalize_po_reference(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    match = re.search(r"(PO-\d+)", text)
    if match:
        return match.group(1)
    return text

class Party(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="Legal or trading name")
    country: Optional[str] = Field(..., description="Country. Null if not found.")
    address: Optional[str] = Field(..., description="Address. Null if not found.")

class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: Optional[str] = Field(..., description="SKU. Null if not found.")
    description: str = Field(..., description="Description. Include Japanese text if present.")
    quantity: Optional[float] = Field(..., description="Quantity.")
    unit_price: Optional[float] = Field(..., description="Unit price.")
    total: Optional[float] = Field(..., description="Line total.")
    currency: Optional[str] = Field(..., description="Currency code (USD, JPY).")
    status: Optional[str] = Field(..., description="GRN Status (e.g. 'Accepted'). Null otherwise.")

class PurchaseOrderModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    po_number: str = Field(..., description="PO Identifier (e.g. PO-12345)")
    date: Optional[str] = Field(..., description="Date (YYYY-MM-DD)")
    currency: Optional[str] = Field(..., description="Currency")
    vendor: Optional[Party] = Field(..., description="Vendor")
    buyer: Optional[Party] = Field(..., description="Buyer")
    items: List[LineItem] = Field(..., description="Line items")
    subtotal: Optional[float] = Field(..., description="Subtotal")
    tax: Optional[float] = Field(..., description="Tax")
    grand_total: Optional[float] = Field(..., description="Grand Total")

class InvoiceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_number: str = Field(..., description="Invoice ID (e.g. INV-123, 請求書番号)")
    date: Optional[str] = Field(..., description="Date (YYYY-MM-DD)")
    reference_po: Optional[str] = Field(..., description="Reference PO Number")
    currency: Optional[str] = Field(..., description="Currency")
    vendor: Optional[Party] = Field(..., description="Vendor")
    buyer: Optional[Party] = Field(..., description="Buyer")
    items: List[LineItem] = Field(..., description="Line items")
    subtotal: Optional[float] = Field(..., description="Subtotal")
    tax: Optional[float] = Field(..., description="Tax")
    tax_rate: Optional[float] = Field(..., description="Tax Rate (0.10)")
    grand_total: Optional[float] = Field(..., description="Grand Total")
    buyer_country: Optional[str] = Field(..., description="Buyer Country")
    buyer_currency: Optional[str] = Field(..., description="Buyer Currency")
    buyer_total: Optional[float] = Field(..., description="Buyer Total")
    note: Optional[str] = Field(..., description="Notes/Anomalies")

    @field_validator("reference_po", mode="before")
    @classmethod
    def _clean_reference_po(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_po_reference(v)

class GoodsReceiptModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grn_number: str = Field(..., description="GRN ID")
    date: Optional[str] = Field(..., description="Date")
    reference_po: Optional[str] = Field(..., description="Reference PO")
    vendor: Optional[Party] = Field(..., description="Vendor")
    buyer: Optional[Party] = Field(..., description="Buyer")
    items: List[LineItem] = Field(..., description="Items Received")

    @field_validator("reference_po", mode="before")
    @classmethod
    def _clean_reference_po(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_po_reference(v)

class DocumentExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: DocumentType
    invoice: Optional[InvoiceModel] = Field(..., description="Invoice data or null")
    purchase_order: Optional[PurchaseOrderModel] = Field(..., description="PO data or null")
    goods_receipt: Optional[GoodsReceiptModel] = Field(..., description="GRN data or null")

    def get_document(self) -> Union[InvoiceModel, PurchaseOrderModel, GoodsReceiptModel, None]:
        if self.document_type == DocumentType.INVOICE:
            return self.invoice
        if self.document_type == DocumentType.PURCHASE_ORDER:
            return self.purchase_order
        if self.document_type == DocumentType.GOODS_RECEIPT:
            return self.goods_receipt
        return None

# ============================================================
# Main Classifier Class (Chat Completion Version)
# ============================================================

class InvoicePOGRNClassifier:
    def __init__(
        self,
        poppler_path: Optional[str] = None,
        model_name: str = "gpt-4o",
    ) -> None:
        self.llm = LLMClient()
        self.poppler_path = poppler_path
        self.model_name = model_name

    def pdf_to_images(
        self,
        pdf_path: str | Path,
        output_dir: str | Path = "tmp_pdf_images",
        dpi: int = 300,
    ) -> List[Path]:
        """Converts PDF to PNG images at 300 DPI."""
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        pages = convert_from_path(
            pdf_path.as_posix(),
            dpi=dpi,
            poppler_path=self.poppler_path,
        )

        image_paths: List[Path] = []
        for i, page in enumerate(pages):
            image_path = output_dir / f"{pdf_path.stem}_page_{i+1}.png"
            page.save(image_path.as_posix(), "PNG")
            image_paths.append(image_path)
        return image_paths

    def _encode_image(self, image_path: Path) -> str:
        """Encodes a local image file to a Base64 string."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def classify_pdf(
        self,
        pdf_path: str | Path,
        use_first_page_only: bool = True,
    ) -> DocumentExtractionResult:
        """
        Extracts structured data using Chat Completions with Vision + Structured Outputs.
        """
        # 1. Convert PDF to Image(s)
        images = self.pdf_to_images(pdf_path, dpi=300)
        if not images:
            raise RuntimeError("No images generated.")

        # 2. Prepare Message Payload
        image_paths_to_use = [images[0]] if use_first_page_only else images
        
        user_content = []
        # Add text instruction
        user_content.append({
            "type": "text", 
            "text": "Analyze this document image. Extract all fields strictly according to the schema."
        })

        # Add base64 images
        for img_path in image_paths_to_use:
            base64_image = self._encode_image(img_path)
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64_image}"
                }
            })

        system_prompt = (
            "You are an expert procurement document parser (Invoice, PO, GRN).\n"
            "1. Identify document type ('請求書'=Invoice, '発注書'=PO, '受領書'=GRN).\n"
            "2. Extract Japanese text exactly.\n"
            "3. Handle currency: Use main table currency for line items. Note conversions in 'note'.\n"
            "4. Return null for missing fields."
            "5. get the buyer total for the buyer's currency. as defined in invoice. if invoice currency is not the buyer's currency"
        )

        # 3. Parse with configured provider (OpenAI or Bedrock)
        result = self.llm.parse_structured(
            model_name=self.model_name,
            system_prompt=system_prompt,
            user_content=user_content,
            response_model=DocumentExtractionResult,
            temperature=0.0,
            max_tokens=3000,
        )
        
        # Cleanup temp images (optional)
        # for img in images: img.unlink()

        return result

# ============================================================
# CLI Usage
# ============================================================
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python document_classifier.py <pdf_path>")
        sys.exit(1)

    pdf_path_arg = sys.argv[1]
    
    # No assistant_id needed anymore
    classifier = InvoicePOGRNClassifier()

    try:
        print(f"Processing {pdf_path_arg}...")
        extraction = classifier.classify_pdf(pdf_path_arg)
        
        print("\n--- Document Type ---")
        print(extraction.document_type.upper())
        
        print("\n--- Extracted Data (JSON) ---")
        print(extraction.model_dump_json(indent=2))

        # Save output
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        filename = Path(pdf_path_arg).stem + ".json"
        with open(output_dir / filename, "w", encoding="utf-8") as f:
            f.write(extraction.model_dump_json(indent=2))
            
    except Exception as e:
        print(f"\nError: {e}")