"""
ingest_dhofar.py

Ingests Dhofar-specific documents into MongoDB:
- Customer Card PDFs from Dhofar/Invoices/
- EFT Excel files from Dhofar/PO/

Usage:
    cd src
    python ingest_dhofar.py
    python ingest_dhofar.py --dhofar-path ../Dhofar
"""

from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from mongo_connection import load_repo_root_env, make_mongo_client, require_mongo_auth

load_repo_root_env()


def process_eft_excel(excel_path: Path) -> Dict[str, Any]:
    """Parse an EFT Excel file and return structured data."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(excel_path, data_only=True)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise ValueError("Empty Excel file")

        # Extract headers from first row
        headers = [str(c).strip() if c is not None else f"col_{i}" for i, c in enumerate(rows[0])]

        # Parse data rows
        items = []
        total_amount = 0.0
        payment_date = None

        for row in rows[1:]:
            if not any(cell is not None for cell in row):
                continue

            row_dict = {headers[j]: row[j] for j in range(min(len(headers), len(row)))}

            # Map known column names to standard fields
            item: Dict[str, Any] = {}

            for key, val in row_dict.items():
                if val is None:
                    continue
                key_lower = key.lower().strip()

                if "date" in key_lower or "transfer date" in key_lower:
                    item["transfer_date"] = str(val).strip()
                    if payment_date is None:
                        payment_date = str(val).strip()
                elif key_lower in ("bank", "bank name"):
                    item["bank_name"] = str(val).strip()
                elif key_lower in ("description", "narration", "remarks", "details"):
                    desc = str(val).strip()
                    item["description"] = desc
                    # Try to extract beneficiary name from description
                    # Common pattern: "AED <amount>  <BENEFICIARY NAME> ..."
                    import re as _re
                    match = _re.search(r'AED\s+[\d\s,\.]+\s{2,}([A-Z][A-Z\s&\.\-]+?)(?:\s{2,}|\d|/)', desc)
                    if match:
                        item["beneficiary_name"] = match.group(1).strip()
                    # Also try to extract reference numbers
                    ref_match = _re.search(r'(?:REF[:/]?\s*)([A-Z0-9]+)', desc)
                    if ref_match:
                        item["reference"] = ref_match.group(1)
                elif key_lower in ("amount", "credit", "debit"):
                    try:
                        item["amount"] = float(str(val).replace(",", ""))
                        total_amount += item["amount"]
                    except Exception:
                        item["amount_raw"] = str(val)
                else:
                    item[key] = val

            if item:
                items.append(item)

        # Use sheet name as EFT reference (e.g. "18-02-2026")
        eft_ref = ws.title or excel_path.stem

        return {
            "document_type": "eft_payment",
            "eft_payment": {
                "eft_reference": eft_ref,
                "payment_date": payment_date,
                "total_amount": round(total_amount, 2) if total_amount else None,
                "currency": "AED",
                "payer_name": None,
                "bank_name": items[0].get("bank_name") if items else None,
                "items": items,
            },
            "source_filename": excel_path.name,
            "source_file_path": str(excel_path),
            "uploaded_at": datetime.now().isoformat(),
        }

    except ImportError:
        print("  [WARN] openpyxl not installed. Install with: pip install openpyxl")
        return {
            "document_type": "eft_payment",
            "eft_payment": {
                "eft_reference": excel_path.stem,
                "payment_date": None,
                "total_amount": None,
                "currency": "AED",
                "items": [],
                "notes": "Could not parse: openpyxl not installed",
            },
            "source_filename": excel_path.name,
            "source_file_path": str(excel_path),
            "uploaded_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        print(f"  [ERROR] Failed to parse Excel {excel_path}: {e}")
        return {
            "document_type": "eft_payment",
            "eft_payment": {
                "eft_reference": excel_path.stem,
                "payment_date": None,
                "total_amount": None,
                "currency": "AED",
                "items": [],
                "notes": f"Parse error: {str(e)}",
            },
            "source_filename": excel_path.name,
            "source_file_path": str(excel_path),
            "uploaded_at": datetime.utcnow().isoformat(),
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Dhofar documents (Customer Cards + EFT files) into MongoDB."
    )
    parser.add_argument(
        "--dhofar-path",
        type=str,
        default="../Dhofar",
        help="Path to the Dhofar folder (default: ../Dhofar)",
    )
    parser.add_argument(
        "--mongo-uri",
        type=str,
        default=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
    )
    parser.add_argument(
        "--db-name",
        type=str,
        default=os.getenv("MONGO_DB", "ema"),
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=False,
        help="Skip files already in MongoDB. Default: re-process (upsert) all.",
    )

    args = parser.parse_args()

    dhofar_root = Path(args.dhofar_path).resolve()
    if not dhofar_root.exists():
        raise SystemExit(f"Dhofar path does not exist: {dhofar_root}")

    client = make_mongo_client(args.mongo_uri)
    require_mongo_auth(client)
    db = client[args.db_name]

    # Collections
    customer_cards_coll = db["customer_cards"]
    eft_payments_coll = db["eft_payments"]

    # Indexes
    customer_cards_coll.create_index("source_file_path", unique=True, sparse=True)
    customer_cards_coll.create_index("customer_card.customer_id", sparse=True)
    customer_cards_coll.create_index("customer_card.customer_name", sparse=True)
    eft_payments_coll.create_index("source_file_path", unique=True, sparse=True)

    print(f"Dhofar root: {dhofar_root}")
    print(f"MongoDB: {args.mongo_uri} / {args.db_name}")
    print()

    processed = 0
    skipped = 0
    errors = 0

    # --- Process Customer Card PDFs ---
    invoices_dir = dhofar_root / "Invoices"
    if invoices_dir.exists():
        pdf_files = list(invoices_dir.glob("*.pdf"))
        print(f"Found {len(pdf_files)} PDF(s) in {invoices_dir}")

        if pdf_files:
            from dhofar_processor import CustomerCardClassifier
            classifier = CustomerCardClassifier()

        for pdf_path in pdf_files:
            path_str = str(pdf_path)

            existing = customer_cards_coll.find_one({"source_file_path": path_str})
            if existing and args.skip_existing:
                print(f"  Skipping {pdf_path.name} (already indexed)")
                skipped += 1
                continue

            print(f"  Processing {pdf_path.name}...")
            try:
                result = classifier.classify_pdf(pdf_path)
                payload = result.model_dump()
                payload["source_file_path"] = path_str
                payload["uploaded_at"] = datetime.now().isoformat()

                if existing:
                    # Update in place — preserves _id, refreshes all fields
                    customer_cards_coll.replace_one({"_id": existing["_id"]}, payload)
                    print(f"    ↻ Updated: {result.customer_card.customer_name if result.customer_card else 'Unknown'} "
                          f"({len((result.customer_card.statement_rows if result.customer_card else []))} rows)")
                else:
                    customer_cards_coll.insert_one(payload)
                    print(f"    ✓ Inserted: {result.customer_card.customer_name if result.customer_card else 'Unknown'} "
                          f"({len((result.customer_card.statement_rows if result.customer_card else []))} rows)")
                processed += 1
            except Exception as e:
                print(f"    [ERROR] {e}")
                errors += 1
    else:
        print(f"No Invoices directory found at {invoices_dir}")

    # --- Process EFT Excel files ---
    po_dir = dhofar_root / "PO"
    if po_dir.exists():
        excel_files = list(po_dir.glob("*.xlsx")) + list(po_dir.glob("*.xls"))
        print(f"\nFound {len(excel_files)} Excel file(s) in {po_dir}")

        for excel_path in excel_files:
            path_str = str(excel_path)

            if args.skip_existing:
                existing = eft_payments_coll.find_one({"source_file_path": path_str})
                if existing:
                    print(f"  Skipping {excel_path.name} (already indexed)")
                    skipped += 1
                    continue

            print(f"  Processing {excel_path.name}...")
            try:
                payload = process_eft_excel(excel_path)
                payload["source_file_path"] = path_str
                eft_payments_coll.insert_one(payload)
                eft_data = payload.get("eft_payment", {})
                print(f"    ✓ Inserted EFT: {eft_data.get('eft_reference', 'Unknown')} | {len(eft_data.get('items', []))} items")
                processed += 1
            except Exception as e:
                print(f"    [ERROR] {e}")
                errors += 1
    else:
        print(f"No PO directory found at {po_dir}")

    print()
    print(f"Done. Processed: {processed}, Skipped: {skipped}, Errors: {errors}")


if __name__ == "__main__":
    main()
