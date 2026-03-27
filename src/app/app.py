from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from bson import ObjectId
from pydantic import BaseModel
import tempfile
import shutil

_SRC_ROOT = Path(__file__).resolve().parent.parent
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from mongo_connection import load_repo_root_env, make_mongo_client, require_mongo_auth

load_repo_root_env()

# Simple currency conversion rates (in production, use a real API)
CURRENCY_RATES = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 149.50,
    "INR": 83.12,
    "AUD": 1.52,
    "CAD": 1.36,
    "CHF": 0.88,
    "CNY": 7.24,
}

BASE_DIR = Path(__file__).resolve().parent

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "ema")

client = make_mongo_client(MONGO_URI)
require_mongo_auth(client)
db = client[MONGO_DB]


def _ensure_reconciliation_indexes() -> None:
    """Persist reconciliation data with one document per PO; decisions keyed by po_number."""
    db["reconciliation_results"].create_index("po_number", unique=True)
    db["reconciliation_decisions"].create_index("po_number", unique=True)


_ensure_reconciliation_indexes()

app = FastAPI(title="Procure Match")

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


@app.get("/api/invoices")
async def list_invoices() -> List[Dict[str, Any]]:
    coll = db["invoices"]
    docs = [
        _serialize_doc(doc)
        for doc in coll.find().sort("invoice.invoice_number")
    ]
    return docs


@app.get("/api/purchase_orders")
async def list_purchase_orders() -> List[Dict[str, Any]]:
    coll = db["purchase_orders"]
    docs = [
        _serialize_doc(doc)
        for doc in coll.find().sort("purchase_order.po_number")
    ]
    return docs


@app.get("/api/goods_receipts")
async def list_goods_receipts() -> List[Dict[str, Any]]:
    coll = db["goods_receipts"]
    docs = [
        _serialize_doc(doc)
        for doc in coll.find().sort("goods_receipt.grn_number")
    ]
    return docs


@app.get("/api/vendors")
async def list_vendors() -> List[Dict[str, Any]]:
    """Get all vendors with their associated invoices."""
    inv_coll = db["invoices"]
    
    # Aggregate vendors from invoices
    vendors_map: Dict[str, Dict[str, Any]] = {}
    
    for inv_doc in inv_coll.find():
        inv_s = _serialize_doc(inv_doc)
        inv_data = inv_s.get("invoice") or {}
        vendor_data = inv_data.get("vendor") or {}
        vendor_name = vendor_data.get("name")
        
        if not vendor_name:
            vendor_name = "Unknown Vendor"
        
        if vendor_name not in vendors_map:
            vendors_map[vendor_name] = {
                "name": vendor_name,
                "logo_url": vendor_data.get("logo_url"),
                "invoices": [],
                "total_amount": 0,
                "invoice_count": 0
            }
        
        vendors_map[vendor_name]["invoices"].append(inv_s)
        vendors_map[vendor_name]["invoice_count"] += 1
        
        # Add to total amount
        grand_total = inv_data.get("grand_total")
        if grand_total:
            vendors_map[vendor_name]["total_amount"] += grand_total
    
    # Convert to list and sort by name
    vendors_list = list(vendors_map.values())
    vendors_list.sort(key=lambda v: v["name"])
    
    return vendors_list


@app.get("/api/buyers")
async def list_buyers() -> List[Dict[str, Any]]:
    """Get all buyers with their associated purchase orders and goods receipts."""
    po_coll = db["purchase_orders"]
    grn_coll = db["goods_receipts"]
    
    # Aggregate buyers from purchase orders
    buyers_map: Dict[str, Dict[str, Any]] = {}
    
    for po_doc in po_coll.find():
        po_s = _serialize_doc(po_doc)
        po_data = po_s.get("purchase_order") or {}
        buyer_data = po_data.get("buyer") or {}
        buyer_name = buyer_data.get("name")
        
        if not buyer_name:
            buyer_name = "Unknown Buyer"
        
        if buyer_name not in buyers_map:
            buyers_map[buyer_name] = {
                "name": buyer_name,
                "address": buyer_data.get("address"),
                "country": buyer_data.get("country"),
                "purchase_orders": [],
                "goods_receipts": [],
                "total_amount": 0,
                "po_count": 0,
                "grn_count": 0
            }
        
        buyers_map[buyer_name]["purchase_orders"].append(po_s)
        buyers_map[buyer_name]["po_count"] += 1
        
        # Add to total amount
        grand_total = po_data.get("grand_total")
        if grand_total:
            buyers_map[buyer_name]["total_amount"] += grand_total
    
    # Add goods receipts to buyers
    for grn_doc in grn_coll.find():
        grn_s = _serialize_doc(grn_doc)
        grn_data = grn_s.get("goods_receipt") or {}
        buyer_data = grn_data.get("buyer") or {}
        buyer_name = buyer_data.get("name")
        
        if not buyer_name:
            buyer_name = "Unknown Buyer"
        
        if buyer_name not in buyers_map:
            buyers_map[buyer_name] = {
                "name": buyer_name,
                "address": buyer_data.get("address"),
                "country": buyer_data.get("country"),
                "purchase_orders": [],
                "goods_receipts": [],
                "total_amount": 0,
                "po_count": 0,
                "grn_count": 0
            }
        
        buyers_map[buyer_name]["goods_receipts"].append(grn_s)
        buyers_map[buyer_name]["grn_count"] += 1
    
    # Convert to list and sort by name
    buyers_list = list(buyers_map.values())
    buyers_list.sort(key=lambda b: b["name"])
    
    return buyers_list


@app.get("/api/reconciliation")
async def reconciliation() -> List[Dict[str, Any]]:
    """
    Get reconciliation results from pre-computed data.
    Run the reconciliation agent (src/reconciliation_agent.py) to update results.
    """
    recon_coll = db["reconciliation_results"]
    decision_coll = db["reconciliation_decisions"]
    
    # Check if we have any results
    count = recon_coll.count_documents({})
    if count == 0:
        # No pre-computed results, return empty or trigger agent
        return []
    
    # Fetch all reconciliation results
    results = []
    for doc in recon_coll.find().sort("po_number", 1):
        result = _serialize_doc(doc)
        
        # Update decision info (in case it changed after reconciliation was run)
        po_number = result.get("po_number")
        if po_number:
            decision_doc = decision_coll.find_one({"po_number": po_number})
            if decision_doc:
                result["decision"] = {
                    "decision": decision_doc.get("decision"),
                    "comment": decision_doc.get("comment", ""),
                    "timestamp": decision_doc.get("timestamp"),
                    "user": decision_doc.get("user")
                }
            else:
                result["decision"] = None
        
        results.append(result)
    
    return results


@app.get("/api/reconciliation/decisions")
async def list_reconciliation_decisions() -> List[Dict[str, Any]]:
    """All stored approve / reject / dispute decisions (MongoDB collection ``reconciliation_decisions``)."""
    coll = db["reconciliation_decisions"]
    return [_serialize_doc(d) for d in coll.find().sort("po_number", 1)]


@app.post("/api/reconciliation/run")
async def run_reconciliation() -> Dict[str, Any]:
    """
    Trigger full reconciliation agent to re-compute all results.
    This endpoint runs the reconciliation logic and stores results.
    """
    import subprocess
    import sys
    
    try:
        # Run the reconciliation agent (full mode)
        agent_path = Path(__file__).parent.parent / "reconciliation_agent.py"
        result = subprocess.run(
            [sys.executable, str(agent_path)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            return {
                "success": True,
                "message": "Full reconciliation completed successfully",
                "output": result.stdout
            }
        else:
            return {
                "success": False,
                "message": "Reconciliation failed",
                "error": result.stderr
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "Reconciliation timed out"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error running reconciliation: {str(e)}"
        }


@app.post("/api/reconciliation/trigger")
async def trigger_reconciliation(po_numbers: List[str]) -> Dict[str, Any]:
    """
    Trigger incremental reconciliation for specific PO numbers.
    This is a real-time trigger that only processes changed POs.
    
    Body:
        po_numbers: List of PO numbers to reconcile
    """
    import subprocess
    import sys
    
    if not po_numbers:
        raise HTTPException(status_code=400, detail="No PO numbers provided")
    
    try:
        # Run the reconciliation agent in incremental mode
        agent_path = Path(__file__).parent.parent / "reconciliation_agent.py"
        result = subprocess.run(
            [sys.executable, str(agent_path)] + po_numbers,
            capture_output=True,
            text=True,
            timeout=60  # 1 minute timeout for incremental
        )
        
        if result.returncode == 0:
            return {
                "success": True,
                "message": f"Incremental reconciliation completed for {len(po_numbers)} PO(s)",
                "po_numbers": po_numbers,
                "output": result.stdout
            }
        else:
            return {
                "success": False,
                "message": "Incremental reconciliation failed",
                "error": result.stderr
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "Incremental reconciliation timed out"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error running incremental reconciliation: {str(e)}"
        }


# Legacy endpoint - kept for backward compatibility but now just reads from stored data
@app.get("/api/reconciliation/legacy")
async def reconciliation_legacy() -> List[Dict[str, Any]]:
    """Legacy reconciliation endpoint that calculates on-the-fly (slow)."""
    po_coll = db["purchase_orders"]
    inv_coll = db["invoices"]
    grn_coll = db["goods_receipts"]
    decision_coll = db["reconciliation_decisions"]

    results: List[Dict[str, Any]] = []
    processed_po_numbers = set()

    # Process all POs and their linked documents
    for po in po_coll.find():
        po_s = _serialize_doc(po)
        po_data = po_s.get("purchase_order") or {}
        po_number = po_data.get("po_number")
        if not po_number:
            continue

        processed_po_numbers.add(po_number)

        invoices = [
            _serialize_doc(d)
            for d in inv_coll.find({"invoice.reference_po": po_number})
        ]
        grns = [
            _serialize_doc(d)
            for d in grn_coll.find({"goods_receipt.reference_po": po_number})
        ]

        status = "matched"
        issues: List[str] = []

        if not invoices:
            status = "missing_invoice"
            issues.append("No invoice found for this PO")
        if not grns:
            status = "missing_goods_receipt" if status == "matched" else status
            issues.append("No goods receipt found for this PO")

        # Perform detailed item-level reconciliation
        po_items = po_data.get("items") or []
        po_currency = po_data.get("currency", "USD")
        
        # Check invoice items against PO items
        for inv_doc in invoices:
            inv_data = inv_doc.get("invoice") or {}
            inv_items = inv_data.get("items") or []
            inv_number = inv_data.get("invoice_number", "Unknown")
            
            # Create item lookup by description for PO
            po_items_map = {item.get("description"): item for item in po_items}
            
            for inv_item in inv_items:
                inv_desc = inv_item.get("description")
                inv_qty = inv_item.get("quantity")
                inv_price = inv_item.get("unit_price")
                
                if inv_desc in po_items_map:
                    po_item = po_items_map[inv_desc]
                    po_qty = po_item.get("quantity")
                    po_price = po_item.get("unit_price")
                    
                    # Check quantity mismatch
                    if inv_qty != po_qty:
                        if status == "matched":
                            status = "amount_mismatch"
                        issues.append(
                            f"Quantity mismatch for '{inv_desc}': Invoice has {inv_qty} units vs PO has {po_qty} units (Δ {abs(inv_qty - po_qty)})"
                        )
                    
                    # Check unit price mismatch
                    if inv_price and po_price and abs(inv_price - po_price) > 0.01:
                        if status == "matched":
                            status = "amount_mismatch"
                        price_diff = inv_price - po_price
                        percentage = (price_diff / po_price) * 100 if po_price else 0
                        direction = "increased" if price_diff > 0 else "decreased"
                        issues.append(
                            f"Price {direction} for '{inv_desc}': {po_currency} {po_price:.2f} → {po_currency} {inv_price:.2f} ({percentage:+.1f}%)"
                        )
                else:
                    # Item in invoice but not in PO
                    if status == "matched":
                        status = "amount_mismatch"
                    issues.append(
                        f"Unexpected item in invoice {inv_number}: '{inv_desc}' (not in original PO)"
                    )
        
        # Check for missing items (in PO but not in any invoice)
        if invoices:
            all_inv_items = set()
            for inv_doc in invoices:
                inv_items = (inv_doc.get("invoice") or {}).get("items") or []
                all_inv_items.update(item.get("description") for item in inv_items)
            
            for po_item in po_items:
                po_desc = po_item.get("description")
                if po_desc not in all_inv_items:
                    if status == "matched":
                        status = "amount_mismatch"
                    issues.append(
                        f"Missing item from invoice: '{po_desc}' ({po_item.get('quantity')} units @ {po_currency} {po_item.get('unit_price', 0):.2f})"
                    )
        
        # Check GRN quantities against PO
        for grn_doc in grns:
            grn_data = grn_doc.get("goods_receipt") or {}
            grn_items = grn_data.get("items") or []
            grn_number = grn_data.get("grn_number", "Unknown")
            
            for grn_item in grn_items:
                grn_desc = grn_item.get("description")
                grn_qty = grn_item.get("quantity")
                
                if grn_desc in po_items_map:
                    po_item = po_items_map[grn_desc]
                    po_qty = po_item.get("quantity")
                    
                    # Check if received quantity differs from ordered
                    if grn_qty != po_qty:
                        if grn_qty < po_qty:
                            issues.append(
                                f"Partial delivery for '{grn_desc}': Received {grn_qty} of {po_qty} units (short by {po_qty - grn_qty})"
                            )
                        else:
                            issues.append(
                                f"Over-delivery for '{grn_desc}': Received {grn_qty} units vs ordered {po_qty} units (excess {grn_qty - po_qty})"
                            )
                else:
                    issues.append(
                        f"Unexpected item in GRN {grn_number}: '{grn_desc}' (not in original PO)"
                    )
        
        # Overall total check
        po_total = po_data.get("grand_total")
        if po_total is not None and invoices:
            for inv_doc in invoices:
                inv_data = inv_doc.get("invoice") or {}
                inv_total = inv_data.get("grand_total")
                inv_number = inv_data.get("invoice_number", "Unknown")
                
                if inv_total and abs(inv_total - po_total) > 0.01:
                    if status == "matched":
                        status = "amount_mismatch"
                    diff = inv_total - po_total
                    issues.append(
                        f"Total amount mismatch in {inv_number}: {po_currency} {po_total:.2f} (PO) vs {po_currency} {inv_total:.2f} (Invoice) - Difference: {po_currency} {diff:+.2f}"
                    )

        # Calculate recommended approval amount
        recommended_amount = 0.0
        deductions = []
        approval_calculation = {
            "po_amount": po_total or 0.0,
            "invoice_amount": 0.0,
            "recommended_amount": 0.0,
            "total_deductions": 0.0,
            "deduction_details": [],
            "calculation_notes": []
        }
        
        if invoices and po_total:
            # Start with PO amount as baseline
            recommended_amount = po_total
            
            # Calculate based on what was actually delivered (from GRN)
            if grns:
                delivered_value = 0.0
                for grn_doc in grns:
                    grn_data = grn_doc.get("goods_receipt") or {}
                    grn_items = grn_data.get("items") or []
                    
                    for grn_item in grn_items:
                        grn_desc = grn_item.get("description")
                        grn_qty = grn_item.get("quantity", 0)
                        
                        # Find matching PO item to get price
                        if grn_desc in po_items_map:
                            po_item = po_items_map[grn_desc]
                            po_qty = po_item.get("quantity", 0)
                            po_price = po_item.get("unit_price", 0)
                            
                            # Calculate value of delivered items
                            delivered_value += grn_qty * po_price
                            
                            # If partial delivery, calculate deduction
                            if grn_qty < po_qty:
                                shortage = po_qty - grn_qty
                                deduction_amount = shortage * po_price
                                deductions.append({
                                    "item": grn_desc,
                                    "reason": "Partial delivery",
                                    "ordered": po_qty,
                                    "received": grn_qty,
                                    "shortage": shortage,
                                    "unit_price": po_price,
                                    "amount": deduction_amount
                                })
                                approval_calculation["deduction_details"].append(
                                    f"Deduct {po_currency} {deduction_amount:.2f} for {shortage} units of '{grn_desc}' not delivered"
                                )
                
                # Check for items in PO but not in any GRN (not delivered at all)
                if grns:
                    all_grn_items = set()
                    for grn_doc in grns:
                        grn_items = (grn_doc.get("goods_receipt") or {}).get("items") or []
                        all_grn_items.update(item.get("description") for item in grn_items)
                    
                    for po_item in po_items:
                        po_desc = po_item.get("description")
                        if po_desc not in all_grn_items:
                            po_qty = po_item.get("quantity", 0)
                            po_price = po_item.get("unit_price", 0)
                            deduction_amount = po_qty * po_price
                            deductions.append({
                                "item": po_desc,
                                "reason": "Not delivered",
                                "ordered": po_qty,
                                "received": 0,
                                "shortage": po_qty,
                                "unit_price": po_price,
                                "amount": deduction_amount
                            })
                            approval_calculation["deduction_details"].append(
                                f"Deduct {po_currency} {deduction_amount:.2f} for '{po_desc}' (not delivered)"
                            )
            
            # Check for price increases in invoice
            for inv_doc in invoices:
                inv_data = inv_doc.get("invoice") or {}
                inv_items = inv_data.get("items") or []
                inv_total = inv_data.get("grand_total", 0)
                approval_calculation["invoice_amount"] = inv_total
                
                for inv_item in inv_items:
                    inv_desc = inv_item.get("description")
                    inv_price = inv_item.get("unit_price", 0)
                    inv_qty = inv_item.get("quantity", 0)
                    
                    if inv_desc in po_items_map:
                        po_item = po_items_map[inv_desc]
                        po_price = po_item.get("unit_price", 0)
                        
                        # If invoice price is higher than PO price, flag for deduction
                        if inv_price > po_price + 0.01:
                            price_diff = inv_price - po_price
                            deduction_amount = price_diff * inv_qty
                            deductions.append({
                                "item": inv_desc,
                                "reason": "Unauthorized price increase",
                                "po_price": po_price,
                                "invoice_price": inv_price,
                                "quantity": inv_qty,
                                "amount": deduction_amount
                            })
                            approval_calculation["deduction_details"].append(
                                f"Deduct {po_currency} {deduction_amount:.2f} for unauthorized price increase on '{inv_desc}'"
                            )
                    else:
                        # Item not in PO - should not be paid
                        item_total = inv_price * inv_qty
                        deductions.append({
                            "item": inv_desc,
                            "reason": "Not in original PO",
                            "quantity": inv_qty,
                            "unit_price": inv_price,
                            "amount": item_total
                        })
                        approval_calculation["deduction_details"].append(
                            f"Deduct {po_currency} {item_total:.2f} for '{inv_desc}' (not in original PO)"
                        )
            
            # Calculate final recommended amount with tax recalculation
            total_deductions = sum(d["amount"] for d in deductions)
            
            # Get tax information
            po_subtotal = po_data.get("subtotal", 0)
            po_tax = po_data.get("tax", 0)
            po_tax_rate = po_data.get("tax_rate", 0)
            
            # Calculate tax rate if not provided
            if not po_tax_rate and po_subtotal > 0 and po_tax > 0:
                po_tax_rate = po_tax / po_subtotal
            
            # Calculate adjusted amounts
            if invoices:
                inv_data = (invoices[0].get("invoice") or {})
                inv_subtotal = inv_data.get("subtotal", 0)
                inv_tax = inv_data.get("tax", 0)
                inv_total = inv_data.get("grand_total", 0)
                
                # Deductions reduce the subtotal
                adjusted_subtotal = inv_subtotal - total_deductions
                adjusted_subtotal = max(0, adjusted_subtotal)
                
                # Recalculate tax based on adjusted subtotal
                adjusted_tax = adjusted_subtotal * po_tax_rate if po_tax_rate else 0
                
                # Calculate new total
                recommended_amount = adjusted_subtotal + adjusted_tax
                
                # Store breakdown
                approval_calculation["original_subtotal"] = inv_subtotal
                approval_calculation["original_tax"] = inv_tax
                approval_calculation["adjusted_subtotal"] = adjusted_subtotal
                approval_calculation["adjusted_tax"] = adjusted_tax
                approval_calculation["tax_rate"] = po_tax_rate
                approval_calculation["tax_adjustment"] = inv_tax - adjusted_tax
            else:
                # No invoice, calculate from PO
                adjusted_subtotal = po_subtotal - total_deductions
                adjusted_subtotal = max(0, adjusted_subtotal)
                adjusted_tax = adjusted_subtotal * po_tax_rate if po_tax_rate else 0
                recommended_amount = adjusted_subtotal + adjusted_tax
                
                approval_calculation["original_subtotal"] = po_subtotal
                approval_calculation["original_tax"] = po_tax
                approval_calculation["adjusted_subtotal"] = adjusted_subtotal
                approval_calculation["adjusted_tax"] = adjusted_tax
                approval_calculation["tax_rate"] = po_tax_rate
                approval_calculation["tax_adjustment"] = po_tax - adjusted_tax
            
            # Ensure recommended amount is not negative
            recommended_amount = max(0, recommended_amount)
            
            approval_calculation["recommended_amount"] = recommended_amount
            approval_calculation["total_deductions"] = total_deductions
            
            # Add summary notes with tax information
            if total_deductions > 0:
                tax_note = f" (Tax adjusted from {po_currency} {approval_calculation['original_tax']:.2f} to {po_currency} {approval_calculation['adjusted_tax']:.2f})" if approval_calculation.get('tax_adjustment', 0) > 0.01 else ""
                approval_calculation["calculation_notes"].append(
                    f"Recommended to approve {po_currency} {recommended_amount:.2f} (Subtotal: {po_currency} {approval_calculation['adjusted_subtotal']:.2f} + Tax: {po_currency} {approval_calculation['adjusted_tax']:.2f}){tax_note}"
                )
                if approval_calculation.get('tax_adjustment', 0) > 0.01:
                    approval_calculation["deduction_details"].append(
                        f"Tax reduced by {po_currency} {approval_calculation['tax_adjustment']:.2f} due to subtotal deductions"
                    )
            else:
                approval_calculation["calculation_notes"].append(
                    f"No deductions required. Approve full amount: {po_currency} {recommended_amount:.2f}"
                )

        # Check for existing decision
        decision_doc = decision_coll.find_one({"po_number": po_number})
        decision_info = None
        if decision_doc:
            decision_info = {
                "decision": decision_doc.get("decision"),
                "comment": decision_doc.get("comment", ""),
                "timestamp": decision_doc.get("timestamp"),
                "user": decision_doc.get("user")
            }

        result = {
            "po": po_s,
            "invoices": invoices,
            "goods_receipts": grns,
            "status": status,
            "issues": issues,
            "decision": decision_info,
            "approval_calculation": approval_calculation,
        }
        results.append(result)

    # Find orphaned invoices (invoices without matching PO)
    for inv in inv_coll.find():
        inv_s = _serialize_doc(inv)
        inv_data = inv_s.get("invoice") or {}
        ref_po = inv_data.get("reference_po")
        
        # If invoice references a PO that doesn't exist or wasn't processed
        if ref_po and ref_po not in processed_po_numbers:
            # Check if this PO actually exists
            po_exists = po_coll.find_one({"purchase_order.po_number": ref_po})
            if not po_exists:
                # Ghost invoice - references non-existent PO
                grns = [
                    _serialize_doc(d)
                    for d in grn_coll.find({"goods_receipt.reference_po": ref_po})
                ]
                
                result = {
                    "po": {"purchase_order": {"po_number": ref_po, "vendor": {"name": "Unknown"}}},
                    "invoices": [inv_s],
                    "goods_receipts": grns,
                    "status": "ghost_po",
                    "issues": [f"Invoice references non-existent PO: {ref_po}"],
                    "decision": None,
                }
                results.append(result)
                processed_po_numbers.add(ref_po)
        elif not ref_po:
            # Invoice with no PO reference at all
            result = {
                "po": {"purchase_order": {"po_number": inv_data.get("invoice_number", "Unknown"), "vendor": {"name": inv_data.get("vendor", {}).get("name", "Unknown")}}},
                "invoices": [inv_s],
                "goods_receipts": [],
                "status": "orphaned_invoice",
                "issues": ["Invoice has no PO reference"],
                "decision": None,
            }
            results.append(result)

    # Find orphaned GRNs (GRNs without matching PO)
    for grn in grn_coll.find():
        grn_s = _serialize_doc(grn)
        grn_data = grn_s.get("goods_receipt") or {}
        ref_po = grn_data.get("reference_po")
        
        # If GRN references a PO that doesn't exist or wasn't processed
        if ref_po and ref_po not in processed_po_numbers:
            po_exists = po_coll.find_one({"purchase_order.po_number": ref_po})
            if not po_exists:
                # Ghost GRN - references non-existent PO
                result = {
                    "po": {"purchase_order": {"po_number": ref_po, "vendor": {"name": "Unknown"}}},
                    "invoices": [],
                    "goods_receipts": [grn_s],
                    "status": "ghost_po",
                    "issues": [f"GRN references non-existent PO: {ref_po}"],
                    "decision": None,
                }
                results.append(result)
                processed_po_numbers.add(ref_po)
        elif not ref_po:
            # GRN with no PO reference
            result = {
                "po": {"purchase_order": {"po_number": grn_data.get("grn_number", "Unknown"), "vendor": {"name": grn_data.get("vendor", {}).get("name", "Unknown")}}},
                "invoices": [],
                "goods_receipts": [grn_s],
                "status": "orphaned_grn",
                "issues": ["GRN has no PO reference"],
                "decision": None,
            }
            results.append(result)

    return results


@app.get("/api/pdf")
async def get_pdf(path: str):
    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="PDF not found")
    if pdf_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Not a PDF file")
    return FileResponse(pdf_path)


@app.get("/api/currencies")
async def get_currencies() -> Dict[str, Any]:
    """Get available currencies and their rates."""
    return {
        "currencies": list(CURRENCY_RATES.keys()),
        "rates": CURRENCY_RATES
    }


@app.get("/api/vendor_scores")
async def get_vendor_scores() -> List[Dict[str, Any]]:
    """Calculate vendor performance scores based on reconciliation data."""
    po_coll = db["purchase_orders"]
    inv_coll = db["invoices"]
    grn_coll = db["goods_receipts"]
    
    vendor_scores = {}
    
    # Process all POs and calculate vendor metrics
    for po_doc in po_coll.find():
        po_data = (po_doc.get("purchase_order") or {})
        vendor_data = po_data.get("vendor") or {}
        vendor_name = vendor_data.get("name")
        po_number = po_data.get("po_number")
        po_date = po_data.get("date")
        po_total = po_data.get("grand_total", 0)
        
        if not vendor_name:
            continue
            
        if vendor_name not in vendor_scores:
            vendor_scores[vendor_name] = {
                "vendor_name": vendor_name,
                "total_pos": 0,
                "total_value": 0,
                "on_time_deliveries": 0,
                "late_deliveries": 0,
                "price_matches": 0,
                "price_mismatches": 0,
                "quantity_matches": 0,
                "quantity_mismatches": 0,
                "clean_invoices": 0,
                "issues_found": 0,
                "avg_delivery_days": 0,
                "total_delivery_days": 0,
                "delivery_count": 0,
                "score": 0
            }
        
        vendor_scores[vendor_name]["total_pos"] += 1
        vendor_scores[vendor_name]["total_value"] += po_total
        
        # Check for matching invoice
        invoices = list(inv_coll.find({"invoice.reference_po": po_number}))
        grns = list(grn_coll.find({"goods_receipt.reference_po": po_number}))
        
        has_issues = False
        
        # Check delivery time
        if grns and po_date:
            for grn_doc in grns:
                grn_data = grn_doc.get("goods_receipt") or {}
                grn_date = grn_data.get("date")
                if grn_date and po_date:
                    try:
                        from datetime import datetime
                        po_dt = datetime.fromisoformat(po_date.replace('Z', '+00:00')) if isinstance(po_date, str) else po_date
                        grn_dt = datetime.fromisoformat(grn_date.replace('Z', '+00:00')) if isinstance(grn_date, str) else grn_date
                        delivery_days = (grn_dt - po_dt).days
                        vendor_scores[vendor_name]["total_delivery_days"] += delivery_days
                        vendor_scores[vendor_name]["delivery_count"] += 1
                        
                        # Assume 30 days is the standard delivery time
                        if delivery_days <= 30:
                            vendor_scores[vendor_name]["on_time_deliveries"] += 1
                        else:
                            vendor_scores[vendor_name]["late_deliveries"] += 1
                            has_issues = True
                    except:
                        pass
        
        # Check invoice accuracy
        if invoices:
            po_items_map = {item.get("description"): item for item in (po_data.get("items") or [])}
            
            for inv_doc in invoices:
                inv_data = inv_doc.get("invoice") or {}
                inv_items = inv_data.get("items") or []
                
                invoice_has_issues = False
                
                for inv_item in inv_items:
                    inv_desc = inv_item.get("description")
                    inv_qty = inv_item.get("quantity")
                    inv_price = inv_item.get("unit_price")
                    
                    if inv_desc in po_items_map:
                        po_item = po_items_map[inv_desc]
                        po_qty = po_item.get("quantity")
                        po_price = po_item.get("unit_price")
                        
                        # Check price match
                        if inv_price and po_price:
                            if abs(inv_price - po_price) <= 0.01:
                                vendor_scores[vendor_name]["price_matches"] += 1
                            else:
                                vendor_scores[vendor_name]["price_mismatches"] += 1
                                invoice_has_issues = True
                        
                        # Check quantity match
                        if inv_qty == po_qty:
                            vendor_scores[vendor_name]["quantity_matches"] += 1
                        else:
                            vendor_scores[vendor_name]["quantity_mismatches"] += 1
                            invoice_has_issues = True
                    else:
                        # Item not in PO
                        invoice_has_issues = True
                
                if invoice_has_issues:
                    vendor_scores[vendor_name]["issues_found"] += 1
                    has_issues = True
                else:
                    vendor_scores[vendor_name]["clean_invoices"] += 1
        
    # Calculate scores and averages
    for vendor_name, metrics in vendor_scores.items():
        total_pos = metrics["total_pos"]
        if total_pos == 0:
            continue
            
        # Calculate average delivery days
        if metrics["delivery_count"] > 0:
            metrics["avg_delivery_days"] = metrics["total_delivery_days"] / metrics["delivery_count"]
        
        # Calculate score (0-100)
        score = 100
        
        # Delivery performance (40 points)
        total_deliveries = metrics["on_time_deliveries"] + metrics["late_deliveries"]
        if total_deliveries > 0:
            on_time_rate = metrics["on_time_deliveries"] / total_deliveries
            score -= (1 - on_time_rate) * 40
        
        # Price accuracy (30 points)
        total_price_checks = metrics["price_matches"] + metrics["price_mismatches"]
        if total_price_checks > 0:
            price_accuracy = metrics["price_matches"] / total_price_checks
            score -= (1 - price_accuracy) * 30
        
        # Quantity accuracy (20 points)
        total_qty_checks = metrics["quantity_matches"] + metrics["quantity_mismatches"]
        if total_qty_checks > 0:
            qty_accuracy = metrics["quantity_matches"] / total_qty_checks
            score -= (1 - qty_accuracy) * 20
        
        # Invoice cleanliness (10 points)
        total_invoices = metrics["clean_invoices"] + metrics["issues_found"]
        if total_invoices > 0:
            clean_rate = metrics["clean_invoices"] / total_invoices
            score -= (1 - clean_rate) * 10
        
        metrics["score"] = max(0, round(score, 2))
        
        # Add rating
        if metrics["score"] >= 90:
            metrics["rating"] = "Excellent"
        elif metrics["score"] >= 75:
            metrics["rating"] = "Good"
        elif metrics["score"] >= 60:
            metrics["rating"] = "Fair"
        else:
            metrics["rating"] = "Poor"
    
    # Convert to list and sort by score
    scores_list = list(vendor_scores.values())
    scores_list.sort(key=lambda x: x["score"], reverse=True)
    
    return scores_list


@app.get("/api/outflow_analysis")
async def get_outflow_analysis() -> Dict[str, Any]:
    """Analyze cash outflow at buyer and overall levels."""
    po_coll = db["purchase_orders"]
    inv_coll = db["invoices"]
    
    buyer_outflows = {}
    overall_outflow = {
        "total_po_value": 0,
        "total_invoice_value": 0,
        "total_approved": 0,
        "total_pending": 0,
        "total_rejected": 0,
        "by_currency": {},
        "by_vendor": {},
        "monthly_trend": {}
    }
    
    decision_coll = db["reconciliation_decisions"]
    
    # Process purchase orders
    for po_doc in po_coll.find():
        po_data = po_doc.get("purchase_order") or {}
        buyer_data = po_data.get("buyer") or {}
        buyer_name = buyer_data.get("name", "Unknown")
        po_total = po_data.get("grand_total", 0)
        po_currency = po_data.get("currency", "USD")
        po_number = po_data.get("po_number")
        po_date = po_data.get("date", "")
        vendor_name = (po_data.get("vendor") or {}).get("name", "Unknown")
        
        # Initialize buyer if not exists
        if buyer_name not in buyer_outflows:
            buyer_outflows[buyer_name] = {
                "buyer_name": buyer_name,
                "total_po_value": 0,
                "total_invoice_value": 0,
                "total_approved": 0,
                "total_pending": 0,
                "total_rejected": 0,
                "po_count": 0,
                "by_currency": {},
                "by_vendor": {}
            }
        
        buyer_outflows[buyer_name]["total_po_value"] += po_total
        buyer_outflows[buyer_name]["po_count"] += 1
        overall_outflow["total_po_value"] += po_total
        
        # Track by currency
        if po_currency not in buyer_outflows[buyer_name]["by_currency"]:
            buyer_outflows[buyer_name]["by_currency"][po_currency] = 0
        buyer_outflows[buyer_name]["by_currency"][po_currency] += po_total
        
        if po_currency not in overall_outflow["by_currency"]:
            overall_outflow["by_currency"][po_currency] = 0
        overall_outflow["by_currency"][po_currency] += po_total
        
        # Track by vendor
        if vendor_name not in buyer_outflows[buyer_name]["by_vendor"]:
            buyer_outflows[buyer_name]["by_vendor"][vendor_name] = 0
        buyer_outflows[buyer_name]["by_vendor"][vendor_name] += po_total
        
        if vendor_name not in overall_outflow["by_vendor"]:
            overall_outflow["by_vendor"][vendor_name] = 0
        overall_outflow["by_vendor"][vendor_name] += po_total
        
        # Monthly trend
        if po_date:
            month_key = po_date[:7] if len(po_date) >= 7 else "Unknown"
            if month_key not in overall_outflow["monthly_trend"]:
                overall_outflow["monthly_trend"][month_key] = 0
            overall_outflow["monthly_trend"][month_key] += po_total
        
        # Check decision status
        decision = decision_coll.find_one({"po_number": po_number})
        if decision:
            if decision.get("decision") == "approved":
                buyer_outflows[buyer_name]["total_approved"] += po_total
                overall_outflow["total_approved"] += po_total
            elif decision.get("decision") == "rejected":
                buyer_outflows[buyer_name]["total_rejected"] += po_total
                overall_outflow["total_rejected"] += po_total
        else:
            buyer_outflows[buyer_name]["total_pending"] += po_total
            overall_outflow["total_pending"] += po_total
    
    # Process invoices
    for inv_doc in inv_coll.find():
        inv_data = inv_doc.get("invoice") or {}
        inv_total = inv_data.get("grand_total", 0)
        ref_po = inv_data.get("reference_po")
        
        overall_outflow["total_invoice_value"] += inv_total
        
        # Find corresponding PO to get buyer
        if ref_po:
            po_doc = po_coll.find_one({"purchase_order.po_number": ref_po})
            if po_doc:
                po_data = po_doc.get("purchase_order") or {}
                buyer_data = po_data.get("buyer") or {}
                buyer_name = buyer_data.get("name", "Unknown")
                
                if buyer_name in buyer_outflows:
                    buyer_outflows[buyer_name]["total_invoice_value"] += inv_total
    
    # Convert buyer outflows to list
    buyer_list = list(buyer_outflows.values())
    buyer_list.sort(key=lambda x: x["total_po_value"], reverse=True)
    
    return {
        "overall": overall_outflow,
        "by_buyer": buyer_list
    }


@app.get("/")
async def root():
    index_path = BASE_DIR / "static" / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=500, detail="UI not found")
    return FileResponse(index_path)


class ReconciliationDecision(BaseModel):
    po_number: str
    decision: str  # "approved", "rejected", or "dispute"
    comment: str = ""
    user: str = "JA"  # override when auth is wired


class ReconciliationResultPatch(BaseModel):
    """Partial update to a stored reconciliation snapshot (``reconciliation_results``)."""

    status: Optional[str] = None
    issues: Optional[List[str]] = None
    analyst_notes: Optional[str] = None


@app.post("/api/reconciliation/decision")
async def save_reconciliation_decision(decision: ReconciliationDecision) -> Dict[str, Any]:
    """Create or update a decision in ``reconciliation_decisions`` (upsert by ``po_number``)."""
    if decision.decision not in ["approved", "rejected", "dispute"]:
        raise HTTPException(status_code=400, detail="Decision must be 'approved', 'rejected', or 'dispute'")
    
    reconciliation_coll = db["reconciliation_decisions"]
    
    decision_record = {
        "po_number": decision.po_number,
        "decision": decision.decision,
        "comment": decision.comment,
        "timestamp": datetime.utcnow().isoformat(),
        "user": decision.user.strip() or "JA",
    }
    
    result = reconciliation_coll.update_one(
        {"po_number": decision.po_number},
        {"$set": decision_record},
        upsert=True
    )
    
    return {
        "success": True,
        "po_number": decision.po_number,
        "decision": decision.decision,
        "matched": result.matched_count,
        "modified": result.modified_count,
        "upserted_id": str(result.upserted_id) if result.upserted_id else None
    }


@app.delete("/api/reconciliation/decision/{po_number:path}")
async def delete_reconciliation_decision(po_number: str) -> Dict[str, Any]:
    """Remove a decision so the PO returns to pending (document deleted from ``reconciliation_decisions``)."""
    reconciliation_coll = db["reconciliation_decisions"]
    result = reconciliation_coll.delete_one({"po_number": po_number})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="No decision found for this PO")
    return {"success": True, "po_number": po_number, "deleted": True}


@app.patch("/api/reconciliation/result/{po_number:path}")
async def patch_reconciliation_result(
    po_number: str, patch: ReconciliationResultPatch
) -> Dict[str, Any]:
    """Merge editable fields into ``reconciliation_results`` for this PO."""
    updates = patch.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Provide at least one field to update")
    updates["result_last_modified_at"] = datetime.utcnow().isoformat()

    recon_coll = db["reconciliation_results"]
    result = recon_coll.update_one({"po_number": po_number}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="No reconciliation result for this PO")
    updated = recon_coll.find_one({"po_number": po_number})
    return {"success": True, "po_number": po_number, "record": _serialize_doc(updated) if updated else None}


@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Upload a PDF document, automatically extract data, classify it, and store in MongoDB.
    """
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    # Create a temporary file to store the upload
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
        tmp_path = tmp_file.name
        # Copy uploaded file to temp location
        shutil.copyfileobj(file.file, tmp_file)
    
    try:
        # Import processor here to avoid circular imports
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from processor import InvoicePOGRNClassifier, DocumentType
        
        # Initialize classifier and process the document
        classifier = InvoicePOGRNClassifier()
        extraction = classifier.classify_pdf(tmp_path)
        
        # Determine document type and collection
        doc_type = extraction.document_type
        collection_map = {
            DocumentType.INVOICE: "invoices",
            DocumentType.PURCHASE_ORDER: "purchase_orders",
            DocumentType.GOODS_RECEIPT: "goods_receipts",
        }
        
        folder_map = {
            DocumentType.INVOICE: "invoices",
            DocumentType.PURCHASE_ORDER: "purchase_orders",
            DocumentType.GOODS_RECEIPT: "goods_receipts",
        }
        
        collection_name = collection_map.get(doc_type)
        if not collection_name:
            raise HTTPException(status_code=500, detail=f"Unknown document type: {doc_type}")
        
        # Determine destination folder
        dest_folder_name = folder_map.get(doc_type)
        data_dir = Path(__file__).parent.parent.parent / "data" / dest_folder_name
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename if needed
        dest_filename = file.filename
        dest_path = data_dir / dest_filename
        counter = 1
        while dest_path.exists():
            name_parts = file.filename.rsplit('.', 1)
            dest_filename = f"{name_parts[0]}_{counter}.{name_parts[1]}"
            dest_path = data_dir / dest_filename
            counter += 1
        
        # Move file to permanent location
        shutil.move(tmp_path, str(dest_path))
        
        # Prepare document for MongoDB
        payload = extraction.model_dump()
        payload["source_pdf_path"] = str(dest_path)
        payload["uploaded_at"] = datetime.utcnow().isoformat()
        
        # Insert into MongoDB
        collection = db[collection_name]
        result = collection.insert_one(payload)
        
        # Get document identifier based on type
        doc_data = extraction.get_document()
        if doc_type == DocumentType.INVOICE:
            doc_id = doc_data.invoice_number if doc_data else "Unknown"
        elif doc_type == DocumentType.PURCHASE_ORDER:
            doc_id = doc_data.po_number if doc_data else "Unknown"
        else:
            doc_id = doc_data.grn_number if doc_data else "Unknown"
        
        # Trigger incremental reconciliation for affected PO(s)
        affected_po_numbers = []
        
        # Determine which PO(s) are affected by this upload
        if doc_type == DocumentType.PURCHASE_ORDER:
            # New PO uploaded - reconcile this PO
            affected_po_numbers.append(doc_id)
        elif doc_type == DocumentType.INVOICE:
            # New invoice - reconcile its reference PO
            doc_data = extraction.get_document()
            if hasattr(doc_data, 'reference_po') and doc_data.reference_po:
                affected_po_numbers.append(doc_data.reference_po)
        elif doc_type == DocumentType.GOODS_RECEIPT:
            # New GRN - reconcile its reference PO
            doc_data = extraction.get_document()
            if hasattr(doc_data, 'reference_po') and doc_data.reference_po:
                affected_po_numbers.append(doc_data.reference_po)
        
        # Trigger incremental reconciliation in background (non-blocking)
        if affected_po_numbers:
            try:
                import subprocess
                import sys as sys_module
                agent_path = Path(__file__).parent.parent / "reconciliation_agent.py"
                subprocess.Popen(
                    [sys_module.executable, str(agent_path)] + affected_po_numbers,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except:
                pass  # Don't fail upload if reconciliation trigger fails
        
        return {
            "success": True,
            "message": "Document uploaded and processed successfully",
            "document_type": doc_type.value,
            "document_id": doc_id,
            "collection": collection_name,
            "mongo_id": str(result.inserted_id),
            "file_path": str(dest_path),
            "reconciliation_triggered": True
        }
        
    except Exception as e:
        # Clean up temp file if it still exists
        if Path(tmp_path).exists():
            Path(tmp_path).unlink()
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")
    finally:
        # Ensure temp file is cleaned up
        if Path(tmp_path).exists():
            try:
                Path(tmp_path).unlink()
            except:
                pass
