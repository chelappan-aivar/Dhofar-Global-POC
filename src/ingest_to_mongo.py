import argparse
import os
import shutil
from pathlib import Path
from typing import Dict

from mongo_connection import load_repo_root_env, make_mongo_client, require_mongo_auth
from processor import InvoicePOGRNClassifier, DocumentType

load_repo_root_env()


def iter_pdf_files(root: Path):
    for path in root.rglob("*.pdf"):
        if path.is_file():
            yield path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=
        "Parse PDFs from a simulated data lake via processor.py "
        "and ingest structured results into MongoDB.",
    )
    parser.add_argument(
        "assistant_id",
        nargs="?",
        default=None,
        help="Deprecated and ignored (kept for backward compatibility).",
    )
    parser.add_argument(
        "--data-lake-path",
        type=str,
        default="../data/simulated_data_lake",
        help="Path to the root of the simulated data lake containing PDFs.",
    )
    parser.add_argument(
        "--mongo-uri",
        type=str,
        default=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        help="MongoDB connection URI (default: mongodb://localhost:27017 or $MONGO_URI).",
    )
    parser.add_argument(
        "--db-name",
        type=str,
        default=os.getenv("MONGO_DB", "ema"),
        help="MongoDB database name (default: ema or $MONGO_DB).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on number of PDFs to process (for testing).",
    )

    args = parser.parse_args()

    data_lake_root = Path(args.data_lake_path).resolve()
    if not data_lake_root.exists():
        raise SystemExit(f"Data lake path does not exist: {data_lake_root}")

    client = make_mongo_client(args.mongo_uri)
    require_mongo_auth(client)
    db = client[args.db_name]

    # Ensure indexes for common query patterns (three-way reconciliation)
    invoices_coll = db["invoices"]
    po_coll = db["purchase_orders"]
    grn_coll = db["goods_receipts"]

    # Index for source_pdf_path to quickly check if file already processed
    invoices_coll.create_index("source_pdf_path", unique=True, sparse=True)
    po_coll.create_index("source_pdf_path", unique=True, sparse=True)
    grn_coll.create_index("source_pdf_path", unique=True, sparse=True)

    # invoice.reference_po ties invoice back to PO
    invoices_coll.create_index([
        ("document_type", 1),
        ("invoice.reference_po", 1),
    ])

    # purchase_order.po_number is the canonical PO identifier
    po_coll.create_index([
        ("document_type", 1),
        ("purchase_order.po_number", 1),
    ])

    # goods_receipt.reference_po ties GRN back to PO
    grn_coll.create_index([
        ("document_type", 1),
        ("goods_receipt.reference_po", 1),
    ])

    collection_map: Dict[DocumentType, str] = {
        DocumentType.INVOICE: "invoices",
        DocumentType.PURCHASE_ORDER: "purchase_orders",
        DocumentType.GOODS_RECEIPT: "goods_receipts",
    }
    
    folder_map: Dict[DocumentType, str] = {
        DocumentType.INVOICE: "invoices",
        DocumentType.PURCHASE_ORDER: "purchase_orders",
        DocumentType.GOODS_RECEIPT: "goods_receipts",
    }

    classifier = InvoicePOGRNClassifier()

    processed = 0
    skipped = 0
    moved = 0
    
    for pdf_path in iter_pdf_files(data_lake_root):
        if args.limit is not None and processed >= args.limit:
            break
            
        pdf_path_str = str(pdf_path)
        
        # Check if this PDF has already been processed in any collection
        already_exists = (
            invoices_coll.find_one({"source_pdf_path": pdf_path_str}) or
            po_coll.find_one({"source_pdf_path": pdf_path_str}) or
            grn_coll.find_one({"source_pdf_path": pdf_path_str})
        )
        
        if already_exists:
            print(f"Skipping {pdf_path} (already indexed)")
            skipped += 1
            continue
            
        print(f"Processing {pdf_path}...")
        try:
            extraction = classifier.classify_pdf(pdf_path_str)
        except Exception as e:  # noqa: BLE001
            print(f"  [ERROR] Failed to classify {pdf_path}: {e}")
            continue

        doc_type = extraction.document_type
        collection_name = collection_map.get(doc_type)
        if collection_name is None:
            print(f"  [WARN] Unknown document type for {pdf_path}: {doc_type}")
            continue

        # Determine destination folder
        dest_folder_name = folder_map.get(doc_type)
        if not dest_folder_name:
            print(f"  [WARN] No folder mapping for {doc_type}")
            continue
            
        # Calculate new path in the respective folder
        dest_folder = data_lake_root.parent / dest_folder_name
        dest_folder.mkdir(parents=True, exist_ok=True)
        dest_path = dest_folder / pdf_path.name
        dest_path_str = str(dest_path)

        payload = extraction.model_dump()
        payload["source_pdf_path"] = dest_path_str  # Store final path, not incoming path

        collection = db[collection_name]
        try:
            result = collection.insert_one(payload)
            print(f"  Inserted into {collection_name} with _id={result.inserted_id}")
            
            # Move file to respective folder after successful insertion
            shutil.move(str(pdf_path), str(dest_path))
            print(f"  Moved to {dest_path}")
            moved += 1
            processed += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [ERROR] Failed to insert/move {pdf_path}: {e}")
            continue

    print(f"Done. Total PDFs processed: {processed}, moved: {moved}, skipped: {skipped}")


if __name__ == "__main__":
    main()
