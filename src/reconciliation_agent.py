"""
Reconciliation Agent

This agent performs 3-way matching between Purchase Orders, Invoices, and Goods Receipts,
and stores the reconciliation results in MongoDB for fast retrieval.

Run this agent:
- Manually: python reconciliation_agent.py
- Scheduled: Set up a cron job or task scheduler
- On-demand: Call from the upload endpoint after new documents are added
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Set, Optional
from pathlib import Path

from bson import ObjectId
from pydantic import BaseModel, Field
from llm_client import LLMClient
from mongo_connection import load_repo_root_env, make_mongo_client, require_mongo_auth

load_repo_root_env()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "ema")
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "bedrock").strip().lower()

client = make_mongo_client(MONGO_URI)
require_mongo_auth(client)
db = client[MONGO_DB]

llm_client = LLMClient()


# Pydantic models for structured AI response
class ApprovalCalculation(BaseModel):
    """Approval calculation with deductions."""
    po_amount: float = Field(description="Purchase order grand total")
    invoice_amount: float = Field(description="Invoice grand total")
    recommended_amount: float = Field(description="Recommended amount to approve after deductions")
    total_deductions: float = Field(description="Sum of all deductions")
    deduction_details: List[str] = Field(default_factory=list, description="Itemized deductions with reasons")
    calculation_notes: List[str] = Field(default_factory=list, description="Explanation notes")


class AIAnalysis(BaseModel):
    """AI-powered analysis and recommendations."""
    risk_level: str = Field(description="Risk level: low, medium, or high")
    recommendation: str = Field(description="Recommendation: approve, reject, investigate, or dispute")
    reasoning: str = Field(description="Brief explanation of the recommendation")
    action_items: List[str] = Field(description="Specific actions to take")
    estimated_impact: str = Field(description="Financial impact description")


class ReconciliationResult(BaseModel):
    """Complete reconciliation result from AI."""
    status: str = Field(description="Reconciliation status: matched, amount_mismatch, missing_invoice, missing_goods_receipt, ghost_po, orphaned_invoice")
    issues: List[str] = Field(default_factory=list, description="List of specific issues found")
    approval_calculation: ApprovalCalculation = Field(description="Approval amount calculation")
    ai_analysis: Optional[AIAnalysis] = Field(default=None, description="AI analysis and recommendations")


def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert MongoDB document to JSON-serializable format."""
    doc = dict(doc)
    if "_id" in doc and isinstance(doc["_id"], ObjectId):
        doc["_id"] = str(doc["_id"])
    return doc


def reconcile_with_ai(
    po_data: Dict[str, Any],
    invoices: List[Dict[str, Any]],
    grns: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Use OpenAI to perform complete 3-way reconciliation analysis.
    
    Args:
        po_data: Purchase order data
        invoices: List of linked invoices
        grns: List of linked goods receipts
        
    Returns:
        Complete reconciliation result with status, issues, recommendations, and calculations
    """
    try:
        # Prepare comprehensive context for AI
        context = {
            "purchase_order": {
                "po_number": po_data.get("po_number"),
                "date": po_data.get("date"),
                "vendor": po_data.get("vendor"),
                "buyer": po_data.get("buyer"),
                "currency": po_data.get("currency", "USD"),
                "items": po_data.get("items", []),
                "subtotal": po_data.get("subtotal"),
                "tax": po_data.get("tax"),
                "tax_rate": po_data.get("tax_rate"),
                "grand_total": po_data.get("grand_total")
            },
            "invoices": [
                {
                    "invoice_number": inv.get("invoice", {}).get("invoice_number"),
                    "date": inv.get("invoice", {}).get("date"),
                    "reference_po": inv.get("invoice", {}).get("reference_po"),
                    "items": inv.get("invoice", {}).get("items", []),
                    "subtotal": inv.get("invoice", {}).get("subtotal"),
                    "tax": inv.get("invoice", {}).get("tax"),
                    "grand_total": inv.get("invoice", {}).get("grand_total")
                }
                for inv in invoices
            ],
            "goods_receipts": [
                {
                    "grn_number": grn.get("goods_receipt", {}).get("grn_number"),
                    "date": grn.get("goods_receipt", {}).get("date"),
                    "reference_po": grn.get("goods_receipt", {}).get("reference_po"),
                    "items": grn.get("goods_receipt", {}).get("items", [])
                }
                for grn in grns
            ]
        }
        
        prompt = f"""You are an expert procurement reconciliation system. Perform a complete 3-way matching analysis.

PURCHASE ORDER:
{json.dumps(context['purchase_order'], indent=2)}

INVOICES ({len(invoices)}):
{json.dumps(context['invoices'], indent=2)}

GOODS RECEIPTS ({len(grns)}):
{json.dumps(context['goods_receipts'], indent=2)}

Perform comprehensive reconciliation and return JSON with:

1. "status": One of: "matched", "amount_mismatch", "missing_invoice", "missing_goods_receipt", "ghost_po", "orphaned_invoice"

2. "issues": Array of specific issues found (e.g., quantity mismatches, price differences, missing items, delivery shortages)

3. "approval_calculation": {{
   "po_amount": PO grand total,
   "invoice_amount": Invoice grand total,
   "recommended_amount": Amount to approve after deductions,
   "total_deductions": Sum of all deductions,
   "deduction_details": Array of itemized deductions with reasons,
   "calculation_notes": Array of explanation notes
}}

4. "ai_analysis": {{
   "risk_level": "low" | "medium" | "high",
   "recommendation": "approve" | "reject" | "investigate" | "dispute",
   "reasoning": Brief explanation,
   "action_items": Array of 2-3 specific actions,
   "estimated_impact": Financial impact description
}}

RULES:
- Compare PO items vs Invoice items (quantities, prices, descriptions)
- Compare PO items vs GRN items (quantities received)
- Calculate deductions for: partial deliveries, price increases, missing items, unauthorized items
- Assess risk based on: amount of discrepancy, vendor history, issue severity
- Be precise with numbers and calculations
- Flag any suspicious patterns

Return ONLY valid JSON, no markdown or explanations."""

        result_obj = llm_client.parse_structured(
            model_name="gpt-4o-2024-08-06",
            system_prompt="You are a procurement reconciliation expert. Analyze documents and provide structured reconciliation results.",
            user_content=prompt,
            response_model=ReconciliationResult,
            temperature=0.2,
            max_tokens=2000,
        )
        
        # Convert Pydantic model to dict
        result = result_obj.model_dump()
        
        # Add metadata to AI analysis
        if result.get("ai_analysis"):
            result["ai_analysis"]["analyzed_at"] = datetime.utcnow().isoformat()
            result["ai_analysis"]["model"] = os.getenv(
                "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0"
            )
        
        return result
        
    except Exception as e:
        print(f"❌ AI reconciliation failed for {po_data.get('po_number')}: {e}")
        # Return basic fallback result
        return {
            "status": "error",
            "issues": [f"AI reconciliation error: {str(e)}"],
            "ai_analysis": None,
            "approval_calculation": {}
        }


def perform_reconciliation(po_numbers: List[str] = None) -> List[Dict[str, Any]]:
    """
    Perform 3-way reconciliation matching.
    
    Args:
        po_numbers: Optional list of specific PO numbers to reconcile.
                   If None, processes all POs (full reconciliation).
                   If provided, only processes specified POs (incremental).
    
    Returns:
        List of reconciliation results
    """
    po_coll = db["purchase_orders"]
    inv_coll = db["invoices"]
    grn_coll = db["goods_receipts"]
    decision_coll = db["reconciliation_decisions"]

    results: List[Dict[str, Any]] = []
    processed_po_numbers: Set[str] = set()

    if po_numbers:
        print(f"Starting incremental reconciliation for {len(po_numbers)} PO(s)...")
        query = {"purchase_order.po_number": {"$in": po_numbers}}
    else:
        print("Starting full reconciliation process...")
        query = {}
    
    # Process POs (all or specific ones)
    po_count = 0
    for po in po_coll.find(query):
        po_s = serialize_doc(po)
        po_data = po_s.get("purchase_order") or {}
        po_number = po_data.get("po_number")
        if not po_number:
            continue

        po_count += 1
        processed_po_numbers.add(po_number)

        # Find linked invoices and GRNs
        invoices = [
            serialize_doc(d)
            for d in inv_coll.find({"invoice.reference_po": po_number})
        ]
        grns = [
            serialize_doc(d)
            for d in grn_coll.find({"goods_receipt.reference_po": po_number})
        ]

        print(f"  Processing {po_number}: {len(invoices)} invoice(s), {len(grns)} GRN(s)")
        
        # Use AI to perform complete reconciliation
        ai_result = reconcile_with_ai(po_data, invoices, grns)
        
        status = ai_result.get("status", "error")
        issues = ai_result.get("issues", [])
        approval_calculation = ai_result.get("approval_calculation", {})
        ai_analysis = ai_result.get("ai_analysis")
        
        # Log AI analysis if available
        if ai_analysis:
            print(f"    ✓ AI: {ai_analysis.get('recommendation')} (risk: {ai_analysis.get('risk_level')})")
        if issues:
            print(f"    Issues: {len(issues)}")

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
            "po_number": po_number,
            "po": po_s,
            "invoices": invoices,
            "goods_receipts": grns,
            "status": status,
            "issues": issues,
            "decision": decision_info,
            "approval_calculation": approval_calculation,
            "ai_analysis": ai_analysis,  # Add AI insights
            "reconciled_at": datetime.utcnow().isoformat(),
        }
        results.append(result)

    # Handle orphaned invoices and GRNs (same as API)
    for inv in inv_coll.find():
        inv_s = serialize_doc(inv)
        inv_data = inv_s.get("invoice") or {}
        ref_po = inv_data.get("reference_po")
        
        if ref_po and ref_po not in processed_po_numbers:
            po_exists = po_coll.find_one({"purchase_order.po_number": ref_po})
            if not po_exists:
                grns = [
                    serialize_doc(d)
                    for d in grn_coll.find({"goods_receipt.reference_po": ref_po})
                ]
                
                result = {
                    "po_number": ref_po,
                    "po": {"purchase_order": {"po_number": ref_po, "vendor": {"name": "Unknown"}}},
                    "invoices": [inv_s],
                    "goods_receipts": grns,
                    "status": "ghost_po",
                    "issues": [f"Invoice references non-existent PO: {ref_po}"],
                    "decision": None,
                    "approval_calculation": {},
                    "reconciled_at": datetime.utcnow().isoformat(),
                }
                results.append(result)
                processed_po_numbers.add(ref_po)
        elif not ref_po:
            result = {
                "po_number": inv_data.get("invoice_number", "Unknown"),
                "po": {"purchase_order": {"po_number": inv_data.get("invoice_number", "Unknown"), "vendor": {"name": inv_data.get("vendor", {}).get("name", "Unknown")}}},
                "invoices": [inv_s],
                "goods_receipts": [],
                "status": "orphaned_invoice",
                "issues": ["Invoice has no PO reference"],
                "decision": None,
                "approval_calculation": {},
                "reconciled_at": datetime.utcnow().isoformat(),
            }
            results.append(result)

    print(f"Processed {po_count} purchase orders")
    print(f"Generated {len(results)} reconciliation records")
    
    return results


def calculate_approval_amount(po_data, invoices, grns, po_items):
    """Calculate recommended approval amount based on reconciliation."""
    po_currency = po_data.get("currency", "USD")
    po_total = po_data.get("grand_total", 0)
    po_subtotal = po_data.get("subtotal", 0)
    po_tax = po_data.get("tax", 0)
    po_tax_rate = po_data.get("tax_rate", 0)
    
    if not po_tax_rate and po_subtotal > 0 and po_tax > 0:
        po_tax_rate = po_tax / po_subtotal
    
    approval_calculation = {
        "po_amount": po_total,
        "invoice_amount": 0.0,
        "recommended_amount": 0.0,
        "total_deductions": 0.0,
        "deduction_details": [],
        "calculation_notes": []
    }
    
    if not invoices or not po_total:
        return approval_calculation
    
    deductions = []
    po_items_map = {item.get("description"): item for item in po_items}
    
    # Calculate based on what was actually delivered (from GRN)
    if grns:
        for grn_doc in grns:
            grn_data = grn_doc.get("goods_receipt") or {}
            grn_items = grn_data.get("items") or []
            
            for grn_item in grn_items:
                grn_desc = grn_item.get("description")
                grn_qty = grn_item.get("quantity", 0)
                
                if grn_desc in po_items_map:
                    po_item = po_items_map[grn_desc]
                    po_qty = po_item.get("quantity", 0)
                    po_price = po_item.get("unit_price", 0)
                    
                    if grn_qty < po_qty:
                        shortage = po_qty - grn_qty
                        deduction_amount = shortage * po_price
                        deductions.append({
                            "item": grn_desc,
                            "reason": "Partial delivery",
                            "amount": deduction_amount
                        })
                        approval_calculation["deduction_details"].append(
                            f"Deduct {po_currency} {deduction_amount:.2f} for {shortage} units of '{grn_desc}' not delivered"
                        )
        
        # Check for items in PO but not in any GRN
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
        inv_subtotal = inv_data.get("subtotal", 0)
        approval_calculation["invoice_amount"] = inv_total
        approval_calculation["original_subtotal"] = inv_subtotal
        approval_calculation["original_tax"] = inv_data.get("tax", 0)
        
        for inv_item in inv_items:
            inv_desc = inv_item.get("description")
            inv_price = inv_item.get("unit_price", 0)
            inv_qty = inv_item.get("quantity", 0)
            
            if inv_desc in po_items_map:
                po_item = po_items_map[inv_desc]
                po_price = po_item.get("unit_price", 0)
                
                if inv_price > po_price + 0.01:
                    price_diff = inv_price - po_price
                    deduction_amount = price_diff * inv_qty
                    deductions.append({
                        "item": inv_desc,
                        "reason": "Unauthorized price increase",
                        "amount": deduction_amount
                    })
                    approval_calculation["deduction_details"].append(
                        f"Deduct {po_currency} {deduction_amount:.2f} for unauthorized price increase on '{inv_desc}'"
                    )
            else:
                item_total = inv_price * inv_qty
                deductions.append({
                    "item": inv_desc,
                    "reason": "Not in original PO",
                    "amount": item_total
                })
                approval_calculation["deduction_details"].append(
                    f"Deduct {po_currency} {item_total:.2f} for '{inv_desc}' (not in original PO)"
                )
    
    # Calculate final recommended amount
    total_deductions = sum(d["amount"] for d in deductions)
    approval_calculation["total_deductions"] = total_deductions
    
    if invoices and approval_calculation.get("original_subtotal"):
        adjusted_subtotal = approval_calculation["original_subtotal"] - total_deductions
        adjusted_subtotal = max(0, adjusted_subtotal)
        adjusted_tax = adjusted_subtotal * po_tax_rate if po_tax_rate else 0
        recommended_amount = adjusted_subtotal + adjusted_tax
        
        approval_calculation["adjusted_subtotal"] = adjusted_subtotal
        approval_calculation["adjusted_tax"] = adjusted_tax
        approval_calculation["tax_rate"] = po_tax_rate
        approval_calculation["tax_adjustment"] = approval_calculation["original_tax"] - adjusted_tax
    else:
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
    
    approval_calculation["recommended_amount"] = max(0, recommended_amount)
    
    if total_deductions > 0:
        approval_calculation["calculation_notes"].append(
            f"Recommended to approve {po_currency} {approval_calculation['recommended_amount']:.2f}"
        )
    else:
        approval_calculation["calculation_notes"].append(
            f"No deductions required. Approve full amount: {po_currency} {approval_calculation['recommended_amount']:.2f}"
        )
    
    return approval_calculation


def store_reconciliation_results(results: List[Dict[str, Any]], incremental: bool = False):
    """
    Store reconciliation results in MongoDB.
    
    Args:
        results: List of reconciliation results to store
        incremental: If True, updates only specific POs. If False, clears all first.
    """
    recon_coll = db["reconciliation_results"]
    
    if not results:
        print("No results to store")
        return
    
    if incremental:
        # Incremental update: upsert specific POs
        print(f"Updating {len(results)} reconciliation result(s)...")
        for result in results:
            recon_coll.update_one(
                {"po_number": result["po_number"]},
                {"$set": result},
                upsert=True
            )
        print("✓ Reconciliation results updated successfully")
    else:
        # Full refresh: clear and insert all
        print("Clearing old reconciliation results...")
        recon_coll.delete_many({})
        
        print(f"Storing {len(results)} reconciliation results...")
        recon_coll.insert_many(results)
        print("✓ Reconciliation results stored successfully")
    
    # Ensure indexes exist (idempotent operation)
    recon_coll.create_index("po_number", unique=True)
    recon_coll.create_index("status")
    recon_coll.create_index("reconciled_at")


def reconcile_po_numbers(po_numbers: List[str]) -> int:
    """
    Perform incremental reconciliation for specific PO numbers.
    
    Args:
        po_numbers: List of PO numbers to reconcile
        
    Returns:
        Exit code (0 for success, 1 for error)
    """
    print("=" * 60)
    print("INCREMENTAL RECONCILIATION")
    print("=" * 60)
    print(f"MongoDB: {MONGO_URI}")
    print(f"Database: {MONGO_DB}")
    print(f"PO Numbers: {', '.join(po_numbers)}")
    print()
    
    try:
        # Perform reconciliation for specific POs
        results = perform_reconciliation(po_numbers=po_numbers)
        
        # Store results incrementally
        store_reconciliation_results(results, incremental=True)
        
        print()
        print("=" * 60)
        print("INCREMENTAL RECONCILIATION COMPLETE")
        print("=" * 60)
        print(f"Updated {len(results)} reconciliation record(s)")
        
        # Summary statistics
        status_counts = {}
        for r in results:
            status = r.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        if status_counts:
            print("\nStatus Summary:")
            for status, count in sorted(status_counts.items()):
                print(f"  {status}: {count}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


def main():
    """Main entry point for the reconciliation agent."""
    import sys
    
    # Check for command-line arguments for incremental reconciliation
    if len(sys.argv) > 1:
        # Incremental mode: reconcile specific PO numbers
        po_numbers = sys.argv[1:]
        return reconcile_po_numbers(po_numbers)
    
    # Full reconciliation mode
    print("=" * 60)
    print("FULL RECONCILIATION")
    print("=" * 60)
    print(f"MongoDB: {MONGO_URI}")
    print(f"Database: {MONGO_DB}")
    print()
    
    try:
        # Perform full reconciliation
        results = perform_reconciliation()
        
        # Store results (full refresh)
        store_reconciliation_results(results, incremental=False)
        
        print()
        print("=" * 60)
        print("RECONCILIATION COMPLETE")
        print("=" * 60)
        print(f"Total reconciliation records: {len(results)}")
        
        # Summary statistics
        status_counts = {}
        for r in results:
            status = r.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print("\nStatus Summary:")
        for status, count in sorted(status_counts.items()):
            print(f"  {status}: {count}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
