from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import ServerSelectionTimeoutError
from bson import ObjectId
import tempfile
import shutil

_SRC_ROOT = Path(__file__).resolve().parent.parent
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from mongo_connection import load_repo_root_env, make_mongo_client

load_repo_root_env()

BASE_DIR = Path(__file__).resolve().parent
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "ema")

# Connect lazily — don't crash at startup if Atlas is temporarily unreachable
client = make_mongo_client(MONGO_URI)
db = client[MONGO_DB]

app = FastAPI(title="DHOFAR")


def _mongo_unreachable_hints(exc: ServerSelectionTimeoutError) -> str:
    msg = str(exc).lower()
    base = (
        "Check Atlas Network Access (IP allowlist), VPN/firewall, and that "
        "`pip install -r requirements.txt` installed cryptography+pyopenssl. "
        "On macOS, try `MONGO_TLS_USE_SYSTEM_CA=1` in .env or remove it to use certifi."
    )
    if "ssl" in msg or "tls" in msg or "handshake" in msg:
        return base + " TLS handshake errors are often a blocked or inspected network path."
    return base


@app.exception_handler(ServerSelectionTimeoutError)
async def _mongo_server_selection_handler(
    _request: Request, exc: ServerSelectionTimeoutError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": str(exc),
            "hints": _mongo_unreachable_hints(exc),
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def _serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc = dict(doc)
    if "_id" in doc and isinstance(doc["_id"], ObjectId):
        doc["_id"] = str(doc["_id"])
    return doc


# ── Dhofar Reconciliation ──────────────────────────────────────────────────

@app.get("/api/dhofar/reconciliation")
async def get_dhofar_reconciliation() -> Dict[str, Any]:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from dhofar_reconciliation import get_matched_pairs, get_unmatched_bank, get_unmatched_invoices
    return {
        "matched": get_matched_pairs(db),
        "unmatched_bank": get_unmatched_bank(db),
        "unmatched_invoices": get_unmatched_invoices(db),
    }


@app.get("/api/dhofar/reconciliation/card/{card_id}")
async def get_dhofar_reconciliation_for_card(card_id: str) -> List[Dict[str, Any]]:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from dhofar_reconciliation import get_reconciliation_for_card
    return get_reconciliation_for_card(card_id, db)


@app.post("/api/dhofar/reconcile")
async def run_dhofar_reconciliation_api() -> Dict[str, Any]:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from dhofar_reconciliation import run_dhofar_reconciliation as _run
    try:
        summary = _run(db)
        return {"success": True, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Customer Cards ─────────────────────────────────────────────────────────

@app.get("/api/customer_cards")
async def list_customer_cards() -> List[Dict[str, Any]]:
    docs = [_serialize_doc(d) for d in db["customer_cards"].find().sort("customer_card.customer_name", 1)]
    return docs


@app.delete("/api/customer_cards/{doc_id}")
async def delete_customer_card(doc_id: str) -> Dict[str, Any]:
    result = db["customer_cards"].delete_one({"_id": ObjectId(doc_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Customer card not found")
    db["customer_open_items"].delete_many({"card_id": doc_id})
    return {"success": True, "deleted_id": doc_id}


# ── EFT Payments ───────────────────────────────────────────────────────────

@app.get("/api/eft_payments")
async def list_eft_payments() -> List[Dict[str, Any]]:
    docs = [_serialize_doc(d) for d in db["eft_payments"].find().sort("eft_payment.payment_date", -1)]
    return docs


@app.delete("/api/eft_payments/{doc_id}")
async def delete_eft_payment(doc_id: str) -> Dict[str, Any]:
    result = db["eft_payments"].delete_one({"_id": ObjectId(doc_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="EFT payment not found")
    return {"success": True, "deleted_id": doc_id}


# ── Recon Bank / Invoice delete ────────────────────────────────────────────

@app.delete("/api/recon/bank/{doc_id}")
async def delete_bank_transaction(doc_id: str) -> Dict[str, Any]:
    result = db["bank_transactions"].delete_one({"_id": ObjectId(doc_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bank transaction not found")
    db["recon_matched_pairs"].delete_many({"bank_id": doc_id})
    return {"success": True, "deleted_id": doc_id}


@app.delete("/api/recon/invoice/{doc_id}")
async def delete_open_invoice(doc_id: str) -> Dict[str, Any]:
    result = db["customer_open_items"].delete_one({"_id": ObjectId(doc_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    db["recon_matched_pairs"].delete_many({"invoice_ids": doc_id})
    return {"success": True, "deleted_id": doc_id}


# ── Upload ─────────────────────────────────────────────────────────────────

@app.post("/api/upload_dhofar")
async def upload_dhofar_document(file: UploadFile = File(...)) -> Dict[str, Any]:
    filename = file.filename or ""
    is_pdf   = filename.lower().endswith(".pdf")
    is_excel = filename.lower().endswith(".xlsx") or filename.lower().endswith(".xls")

    if not (is_pdf or is_excel):
        raise HTTPException(status_code=400, detail="Only PDF or Excel files are supported")

    suffix = ".pdf" if is_pdf else (".xlsx" if filename.lower().endswith(".xlsx") else ".xls")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        shutil.copyfileobj(file.file, tmp)

    try:
        if is_pdf:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).parent.parent))
            from dhofar_processor import CustomerCardClassifier

            classifier = CustomerCardClassifier()
            result = classifier.classify_pdf(tmp_path)

            dest_dir = Path(__file__).parent.parent.parent / "Dhofar" / "Invoices"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / filename
            counter = 1
            while dest_path.exists():
                stem, ext = filename.rsplit(".", 1)
                dest_path = dest_dir / f"{stem}_{counter}.{ext}"
                counter += 1
            shutil.move(tmp_path, str(dest_path))

            payload = result.model_dump()
            payload["source_file_path"] = str(dest_path)
            payload["uploaded_at"] = datetime.utcnow().isoformat()

            inserted = db["customer_cards"].insert_one(payload)
            card = result.customer_card
            return {
                "success": True,
                "document_type": "customer_card",
                "customer_name": card.customer_name if card else "Unknown",
                "customer_id": card.customer_id if card else None,
                "mongo_id": str(inserted.inserted_id),
                "file_path": str(dest_path),
            }

        else:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).parent.parent))
            from ingest_dhofar import process_eft_excel

            dest_dir = Path(__file__).parent.parent.parent / "Dhofar" / "PO"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / filename
            counter = 1
            while dest_path.exists():
                stem, ext = filename.rsplit(".", 1)
                dest_path = dest_dir / f"{stem}_{counter}.{ext}"
                counter += 1
            shutil.move(tmp_path, str(dest_path))

            payload = process_eft_excel(dest_path)
            eft = payload.get("eft_payment", {})

            if eft.get("notes") or not eft.get("items"):
                dest_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=422,
                    detail=eft.get("notes") or "Excel file could not be parsed — no payment rows found."
                )

            payload["source_file_path"] = str(dest_path)
            inserted = db["eft_payments"].insert_one(payload)
            return {
                "success": True,
                "document_type": "eft_payment",
                "eft_reference": eft.get("eft_reference"),
                "total_amount": eft.get("total_amount"),
                "mongo_id": str(inserted.inserted_id),
                "file_path": str(dest_path),
            }

    except HTTPException:
        raise
    except Exception as e:
        if Path(tmp_path).exists():
            Path(tmp_path).unlink()
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")
    finally:
        if Path(tmp_path).exists():
            try:
                Path(tmp_path).unlink()
            except Exception:
                pass


# ── Static / PDF ───────────────────────────────────────────────────────────

@app.get("/api/pdf")
async def get_pdf(path: str):
    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="PDF not found")
    if pdf_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Not a PDF file")
    return FileResponse(pdf_path)


@app.get("/")
async def root():
    index_path = BASE_DIR / "static" / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=500, detail="UI not found")
    return FileResponse(index_path)
