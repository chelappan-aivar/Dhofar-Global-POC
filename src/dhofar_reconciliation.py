"""
dhofar_reconciliation.py

Full 5-pass reconciliation engine:
  Pass 1 – Direct invoice-number match (doc_no found in bank description)
  Pass 2 – Customer name + exact amount
  Pass 3 – Customer name + combination of invoices (2-3) summing to bank amount
  Pass 4 – Partial payment (bank < invoice, strong name match)
  Pass 5 – Processor / POS settlement accounts

Tables (MongoDB collections):
  bank_transactions      – one row per bank line, with match-tracking columns
  customer_open_items    – one row per open invoice/credit, with cleared columns
  recon_matched_pairs    – audit log of every allocation made
"""

from __future__ import annotations

import os, re, unicodedata
from datetime import datetime, date
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple
from bson import ObjectId
from mongo_connection import load_repo_root_env, make_mongo_client, require_mongo_auth

load_repo_root_env()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "ema")

AMOUNT_TOL   = 0.05   # AED tolerance for "exact" amount match
COMBO_MAX    = 3      # max invoices in a combination
NAME_THRESH  = 45.0   # minimum fuzzy name score to consider a customer match

# Processor remitters that are NOT end-customers
PROCESSOR_KEYWORDS = ["NETWORK INTERNATIONAL", "MASTERCARD", "VISA", "NEOPAY",
                       "MAGNATI", "CHECKOUT", "ADYEN", "STRIPE"]

# ─────────────────────────────────────────────────────────────────────────────
# TEXT / DATE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """Uppercase, strip accents, collapse spaces, drop punctuation."""
    t = unicodedata.normalize("NFKD", str(text))
    t = t.encode("ascii", "ignore").decode("ascii").upper()
    t = re.sub(r"[^A-Z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _token_set(a: str, b: str) -> float:
    sa, sb = set(_norm(a).split()), set(_norm(b).split())
    if not sa or not sb: return 0.0
    inter = sa & sb
    j = len(inter) / len(sa | sb)
    bonus = 0.15 if (sa <= sb or sb <= sa) else 0.0
    return min(100.0, (j + bonus) * 100)


def _lcs(a: str, b: str) -> float:
    a, b = _norm(a)[:120], _norm(b)[:120]
    if not a or not b: return 0.0
    m, n = len(a), len(b)
    dp = [[0]*(n+1) for _ in range(m+1)]
    for i in range(1, m+1):
        for j in range(1, n+1):
            dp[i][j] = dp[i-1][j-1]+1 if a[i-1]==b[j-1] else max(dp[i-1][j], dp[i][j-1])
    return dp[m][n] / max(m, n) * 100


def name_sim(a: str, b: str) -> float:
    return max(_token_set(a, b), _lcs(a, b))


def _parse_date(s: Any) -> Optional[date]:
    if not s: return None
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d-%m-%y",
                "%m/%d/%Y", "%d %b %Y"):
        try: return datetime.strptime(str(s).strip(), fmt).date()
        except ValueError: pass
    return None


def _amt(v: Any) -> float:
    if v is None: return 0.0
    try: return float(str(v).replace(",", "").strip())
    except: return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# PARSING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_DOC_PATTERN = re.compile(
    r"\b(DICSI\d{8,}|DGURFT\d{7,}|INV[-\s]?\d{4,}|SHJZARWT\d{10,})\b",
    re.IGNORECASE,
)

_REMITTER_PATTERNS = [
    r"Remitter\s+Info[:\s]+([A-Z][A-Z0-9 &\.\-\(\)\/]+?)(?:,|\s{2,}|Sender:|Value Date:)",
    r"By Order\s+([A-Z][A-Z0-9 &\.\-\(\)\/]+?)(?:\s{2,}|$)",
    r"AED[\s\d,\.]+\s{2,}([A-Z][A-Z0-9 &\.\-\(\)\/]+?)(?:\s{2,}|/REF/|INVOICE|\d{4,})",
    r"FROM\s+([A-Z][A-Z0-9 &\.\-\(\)\/]+?)(?:\s{2,}|/|$)",
    r"TRANSFER\s+.*?-\s+([A-Z][A-Z0-9 &\.\-\(\)\/]+?)\s+-",
]

def _extract_remitter(desc: str) -> str:
    for pat in _REMITTER_PATTERNS:
        m = re.search(pat, desc, re.IGNORECASE)
        if m:
            c = m.group(1).strip()
            c = re.sub(r"\s+(OPC|LLC|LTD|INVOICE|NO|REF|AED|FT|IPP)\s*.*$",
                       "", c, flags=re.IGNORECASE).strip()
            if len(c) >= 4 and not c.replace(" ", "").isdigit():
                return c
    return desc


def _extract_doc_nos(desc: str) -> List[str]:
    return [m.upper().replace(" ", "") for m in _DOC_PATTERN.findall(desc)]


def _parse_bank_fields(desc: str) -> Dict[str, Any]:
    """Parse structured fields from a bank description string."""
    out: Dict[str, Any] = {}
    for key, pat in [
        ("value_date",   r"Value Date[:\s]+([0-9\-/]+)"),
        ("currency",     r"Trf Ccy[:\s]+([A-Z]{3})"),
        ("trf_amount",   r"Trf Amt[:\s]+([\d,\.]+)"),
        ("pay_details",  r"Pay Dtls[:\s]+([^,]+)"),
        ("purpose_code", r"POP[:\s]+([A-Z]+)"),
        ("ord_inst",     r"Ord Inst[:\s]+([^,\n]+)"),
        ("sender",       r"Sender[:\s]+([A-Z0-9]+)"),
        ("ipp_ref",      r"IPP Ref[:\s]+([A-Z0-9]+)"),
    ]:
        m = re.search(pat, desc, re.IGNORECASE)
        if m: out[key] = m.group(1).strip()
    return out


def _is_processor(remitter: str) -> bool:
    n = _norm(remitter)
    return any(_norm(kw) in n for kw in PROCESSOR_KEYWORDS)


# ─────────────────────────────────────────────────────────────────────────────
# TABLE BUILDERS  (MongoDB upsert-based)
# ─────────────────────────────────────────────────────────────────────────────

def build_bank_transactions(db: Any) -> None:
    """
    Read eft_payments → upsert into bank_transactions.
    Idempotent: existing rows are updated, new rows inserted.
    """
    coll = db["bank_transactions"]
    coll.create_index("source_id", unique=True, sparse=True)

    for eft_doc in db["eft_payments"].find():
        eft = eft_doc.get("eft_payment", {})
        eft_ref = eft.get("eft_reference", str(eft_doc["_id"]))

        for idx, item in enumerate(eft.get("items", [])):
            source_id = f"{eft_ref}::{idx}"
            desc = item.get("description", "") or ""
            parsed = _parse_bank_fields(desc)
            remitter = _extract_remitter(desc)
            candidate_docs = _extract_doc_nos(desc)
            amount = _amt(item.get("amount"))

            existing = coll.find_one({"source_id": source_id})
            if existing:
                # Never overwrite match-tracking fields on re-run
                coll.update_one({"source_id": source_id}, {"$set": {
                    "txn_date": item.get("transfer_date"),
                    "bank_name": item.get("bank_name"),
                    "raw_description": desc,
                    "remitter_name": remitter,
                    "sender_bank": parsed.get("sender"),
                    "value_date": parsed.get("value_date"),
                    "currency": parsed.get("currency", "AED"),
                    "amount": amount,
                    "pay_details": parsed.get("pay_details"),
                    "purpose_code": parsed.get("purpose_code"),
                    "ordering_institution": parsed.get("ord_inst"),
                    "candidate_doc_nos": candidate_docs,
                    "is_processor": _is_processor(remitter),
                    "eft_reference": eft_ref,
                }})
            else:
                coll.insert_one({
                    "source_id": source_id,
                    "txn_date": item.get("transfer_date"),
                    "bank_name": item.get("bank_name"),
                    "raw_description": desc,
                    "remitter_name": remitter,
                    "sender_bank": parsed.get("sender"),
                    "value_date": parsed.get("value_date"),
                    "currency": parsed.get("currency", "AED"),
                    "amount": amount,
                    "pay_details": parsed.get("pay_details"),
                    "purpose_code": parsed.get("purpose_code"),
                    "ordering_institution": parsed.get("ord_inst"),
                    "candidate_doc_nos": candidate_docs,
                    "is_processor": _is_processor(remitter),
                    "eft_reference": eft_ref,
                    # match-tracking
                    "matched_flag": False,
                    "matched_customer": None,
                    "matched_doc_nos": [],
                    "matched_amount": 0.0,
                    "unallocated_amount": amount,
                    "match_method": None,
                })

    print(f"  bank_transactions: {coll.count_documents({})} rows")


def build_customer_open_items(db: Any) -> None:
    """
    Read customer_cards statement_rows → upsert into customer_open_items.
    Only rows with remaining_amount != 0 are considered open.
    """
    coll = db["customer_open_items"]
    coll.create_index("source_id", unique=True, sparse=True)
    coll.create_index("doc_no")
    coll.create_index("customer_name_norm")

    for card_doc in db["customer_cards"].find():
        card = card_doc.get("customer_card", {})
        customer_name = card.get("customer_name", "Unknown")
        customer_code = card.get("customer_id")
        card_id = str(card_doc["_id"])

        for idx, row in enumerate(card.get("statement_rows", [])):
            rem = _amt(row.get("remaining_amount"))
            if rem == 0:
                continue  # already cleared

            source_id = f"{card_id}::{idx}"
            existing = coll.find_one({"source_id": source_id})

            base = {
                "customer_name": customer_name,
                "customer_name_norm": _norm(customer_name),
                "customer_code": customer_code,
                "card_id": card_id,
                "posting_date": row.get("posting_date"),
                "doc_no": (row.get("document_no") or "").upper().strip(),
                "lpo": row.get("lpo"),
                "sell_to_customer_name": row.get("sell_to_customer_name"),
                "original_amount": _amt(row.get("original_amount")),
                "currency": "AED",
            }

            if existing:
                # Only refresh static fields; never overwrite cleared_flag / remaining_amount
                coll.update_one({"source_id": source_id}, {"$set": base})
            else:
                coll.insert_one({
                    **base,
                    "source_id": source_id,
                    "remaining_amount": rem,
                    # match-tracking
                    "cleared_flag": False,
                    "cleared_by_bank_ids": [],
                })

    print(f"  customer_open_items: {coll.count_documents({})} rows "
          f"({coll.count_documents({'cleared_flag': False})} open)")


# ─────────────────────────────────────────────────────────────────────────────
# ALLOCATION HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _allocate(db: Any, bank_id: str, invoice_ids: List[str],
              amounts: List[float], method: str,
              customer_name: str, doc_nos: List[str]) -> None:
    """
    Apply one allocation: update bank_transactions + customer_open_items
    and write an audit record to recon_matched_pairs.
    """
    bt = db["bank_transactions"]
    oi = db["customer_open_items"]
    pairs = db["recon_matched_pairs"]

    total_alloc = sum(amounts)

    # Update bank row
    bt.update_one({"_id": ObjectId(bank_id)}, {"$inc": {
        "matched_amount": total_alloc,
        "unallocated_amount": -total_alloc,
    }, "$set": {
        "matched_customer": customer_name,
        "match_method": method,
    }, "$addToSet": {
        "matched_doc_nos": {"$each": doc_nos},
    }})
    # Set matched_flag if fully consumed
    row = bt.find_one({"_id": ObjectId(bank_id)})
    if row and row.get("unallocated_amount", 0) <= AMOUNT_TOL:
        bt.update_one({"_id": ObjectId(bank_id)}, {"$set": {"matched_flag": True}})

    # Update each invoice
    for inv_id, alloc_amt, doc_no in zip(invoice_ids, amounts, doc_nos):
        oi.update_one({"_id": ObjectId(inv_id)}, {
            "$inc": {"remaining_amount": -alloc_amt},
            "$addToSet": {"cleared_by_bank_ids": bank_id},
        })
        inv = oi.find_one({"_id": ObjectId(inv_id)})
        if inv and abs(inv.get("remaining_amount", 0)) <= AMOUNT_TOL:
            oi.update_one({"_id": ObjectId(inv_id)}, {"$set": {"cleared_flag": True}})

    # Audit record
    pairs.insert_one({
        "bank_id": bank_id,
        "invoice_ids": invoice_ids,
        "doc_nos": doc_nos,
        "customer_name": customer_name,
        "allocated_amounts": amounts,
        "total_allocated": total_alloc,
        "method": method,
        "reconciled_at": datetime.now().isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# PASS 1 – Direct invoice-number match
# ─────────────────────────────────────────────────────────────────────────────

def pass1_doc_no_match(db: Any) -> int:
    bt = db["bank_transactions"]
    oi = db["customer_open_items"]
    matched = 0

    for row in bt.find({"matched_flag": False, "unallocated_amount": {"$gt": AMOUNT_TOL},
                         "candidate_doc_nos": {"$ne": []}}):
        bank_id = str(row["_id"])
        unalloc = row["unallocated_amount"]

        for doc_no in row.get("candidate_doc_nos", []):
            inv = oi.find_one({"doc_no": doc_no.upper(), "cleared_flag": False,
                                "remaining_amount": {"$gt": AMOUNT_TOL}})
            if not inv:
                continue

            inv_rem = inv["remaining_amount"]
            alloc = min(unalloc, inv_rem)

            _allocate(db, bank_id, [str(inv["_id"])], [alloc],
                      "pass1_doc_no", inv["customer_name"], [doc_no])
            matched += 1

            # Refresh unallocated_amount for next candidate_doc_no
            row = bt.find_one({"_id": row["_id"]})
            unalloc = row.get("unallocated_amount", 0)
            if unalloc <= AMOUNT_TOL:
                break

    print(f"  Pass 1 (doc_no):  {matched} allocations")
    return matched


# ─────────────────────────────────────────────────────────────────────────────
# PASS 2 – Customer name + exact amount
# ─────────────────────────────────────────────────────────────────────────────

def pass2_name_exact_amount(db: Any) -> int:
    bt = db["bank_transactions"]
    oi = db["customer_open_items"]
    matched = 0

    for row in bt.find({"matched_flag": False, "unallocated_amount": {"$gt": AMOUNT_TOL}}):
        bank_id = str(row["_id"])
        unalloc = row["unallocated_amount"]
        remitter = row.get("remitter_name", "") or row.get("raw_description", "")

        # Find candidate customers by name similarity
        best_inv = None
        best_score = 0.0

        for inv in oi.find({"cleared_flag": False, "remaining_amount": {"$gt": AMOUNT_TOL}}):
            score = name_sim(remitter, inv["customer_name"])
            if score < NAME_THRESH:
                continue
            # Amount must match within tolerance
            if abs(inv["remaining_amount"] - unalloc) <= AMOUNT_TOL:
                if score > best_score:
                    best_score = score
                    best_inv = inv

        if best_inv:
            alloc = min(unalloc, best_inv["remaining_amount"])
            _allocate(db, bank_id, [str(best_inv["_id"])], [alloc],
                      "pass2_name_exact", best_inv["customer_name"],
                      [best_inv["doc_no"]])
            matched += 1

    print(f"  Pass 2 (name+exact): {matched} allocations")
    return matched


# ─────────────────────────────────────────────────────────────────────────────
# PASS 3 – Customer name + combination of invoices
# ─────────────────────────────────────────────────────────────────────────────

def pass3_name_combo(db: Any) -> int:
    bt = db["bank_transactions"]
    oi = db["customer_open_items"]
    matched = 0

    for row in bt.find({"matched_flag": False, "unallocated_amount": {"$gt": AMOUNT_TOL}}):
        bank_id = str(row["_id"])
        unalloc = row["unallocated_amount"]
        remitter = row.get("remitter_name", "") or row.get("raw_description", "")

        # Group open invoices by customer, keep only name-similar ones
        customer_invoices: Dict[str, List[Dict]] = {}
        for inv in oi.find({"cleared_flag": False, "remaining_amount": {"$gt": AMOUNT_TOL}}):
            score = name_sim(remitter, inv["customer_name"])
            if score < NAME_THRESH:
                continue
            cn = inv["customer_name"]
            customer_invoices.setdefault(cn, []).append(inv)

        found = False
        for cn, invs in customer_invoices.items():
            # Sort oldest first
            invs.sort(key=lambda x: _parse_date(x.get("posting_date")) or date.min)

            for size in range(2, min(COMBO_MAX + 1, len(invs) + 1)):
                for combo in combinations(invs, size):
                    total = sum(i["remaining_amount"] for i in combo)
                    if abs(total - unalloc) <= AMOUNT_TOL:
                        ids    = [str(i["_id"]) for i in combo]
                        amts   = [i["remaining_amount"] for i in combo]
                        dnos   = [i["doc_no"] for i in combo]
                        _allocate(db, bank_id, ids, amts, "pass3_combo", cn, dnos)
                        matched += 1
                        found = True
                        break
                if found:
                    break
            if found:
                break

    print(f"  Pass 3 (combo):   {matched} allocations")
    return matched


# ─────────────────────────────────────────────────────────────────────────────
# PASS 4 – Partial payment (bank < invoice, strong name match)
# ─────────────────────────────────────────────────────────────────────────────

def pass4_partial(db: Any) -> int:
    bt = db["bank_transactions"]
    oi = db["customer_open_items"]
    matched = 0

    for row in bt.find({"matched_flag": False, "unallocated_amount": {"$gt": AMOUNT_TOL}}):
        bank_id = str(row["_id"])
        unalloc = row["unallocated_amount"]
        remitter = row.get("remitter_name", "") or row.get("raw_description", "")

        best_inv = None
        best_score = 0.0

        for inv in oi.find({"cleared_flag": False, "remaining_amount": {"$gt": unalloc + AMOUNT_TOL}}):
            score = name_sim(remitter, inv["customer_name"])
            if score >= 70.0 and score > best_score:   # high confidence required
                best_score = score
                best_inv = inv

        if best_inv:
            _allocate(db, bank_id, [str(best_inv["_id"])], [unalloc],
                      "pass4_partial", best_inv["customer_name"],
                      [best_inv["doc_no"]])
            matched += 1

    print(f"  Pass 4 (partial): {matched} allocations")
    return matched


# ─────────────────────────────────────────────────────────────────────────────
# PASS 5 – Processor / POS settlement
# ─────────────────────────────────────────────────────────────────────────────

def pass5_processor(db: Any) -> int:
    bt = db["bank_transactions"]
    oi = db["customer_open_items"]
    matched = 0

    for row in bt.find({"matched_flag": False, "is_processor": True,
                         "unallocated_amount": {"$gt": AMOUNT_TOL}}):
        bank_id = str(row["_id"])
        unalloc = row["unallocated_amount"]
        remitter = row.get("remitter_name", "")

        # Find the processor's own open item (if any) by exact name
        inv = oi.find_one({
            "customer_name_norm": _norm(remitter),
            "cleared_flag": False,
            "remaining_amount": {"$gt": AMOUNT_TOL},
        })
        if inv:
            alloc = min(unalloc, inv["remaining_amount"])
            _allocate(db, bank_id, [str(inv["_id"])], [alloc],
                      "pass5_processor", inv["customer_name"], [inv["doc_no"]])
            matched += 1

    print(f"  Pass 5 (processor): {matched} allocations")
    return matched


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_dhofar_reconciliation(db: Any) -> Dict[str, Any]:
    """Build tables, run all passes, return summary."""
    print("Building BankTransactions …")
    build_bank_transactions(db)
    print("Building CustomerOpenItems …")
    build_customer_open_items(db)

    print("\nRunning matching passes …")
    p1 = pass1_doc_no_match(db)
    p2 = pass2_name_exact_amount(db)
    p3 = pass3_name_combo(db)
    p4 = pass4_partial(db)
    p5 = pass5_processor(db)

    bt = db["bank_transactions"]
    oi = db["customer_open_items"]

    total_bank   = bt.count_documents({})
    matched_bank = bt.count_documents({"matched_flag": True})
    total_inv    = oi.count_documents({})
    cleared_inv  = oi.count_documents({"cleared_flag": True})

    matched_amt  = sum(r.get("matched_amount", 0) for r in bt.find({"matched_flag": True}))
    unmatched_amt= sum(r.get("unallocated_amount", 0) for r in bt.find({"matched_flag": False}))

    summary = {
        "bank_rows_total": total_bank,
        "bank_rows_matched": matched_bank,
        "bank_rows_unmatched": total_bank - matched_bank,
        "invoices_total": total_inv,
        "invoices_cleared": cleared_inv,
        "invoices_open": total_inv - cleared_inv,
        "matched_amount": round(matched_amt, 2),
        "unmatched_amount": round(unmatched_amt, 2),
        "pass_counts": {"p1": p1, "p2": p2, "p3": p3, "p4": p4, "p5": p5},
    }
    print(f"\nSummary: {summary}")
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# VIEW HELPERS  (used by API)
# ─────────────────────────────────────────────────────────────────────────────

def _ser(doc: Dict) -> Dict:
    doc = dict(doc)
    if "_id" in doc and isinstance(doc["_id"], ObjectId):
        doc["_id"] = str(doc["_id"])
    return doc


def get_matched_pairs(db: Any) -> List[Dict]:
    """View (a): matched bank rows with their linked invoices."""
    bt = db["bank_transactions"]
    oi = db["customer_open_items"]
    pairs = db["recon_matched_pairs"]

    results = []
    for row in bt.find({"matched_flag": True}).sort("txn_date", 1):
        row = _ser(row)
        bank_id = row["_id"]
        linked = list(pairs.find({"bank_id": bank_id}))
        inv_ids = []
        for p in linked:
            inv_ids.extend(p.get("invoice_ids", []))
        invoices = [_ser(i) for i in oi.find({"_id": {"$in": [ObjectId(i) for i in inv_ids]}})]
        results.append({"bank_row": row, "invoices": invoices, "pairs": [_ser(p) for p in linked]})
    return results


def get_unmatched_bank(db: Any) -> List[Dict]:
    """View (b): bank rows still needing investigation."""
    return [_ser(r) for r in
            db["bank_transactions"].find({"matched_flag": False}).sort("txn_date", 1)]


def get_unmatched_invoices(db: Any) -> List[Dict]:
    """View (c): open invoices not yet reconciled."""
    return [_ser(r) for r in
            db["customer_open_items"].find({"cleared_flag": False}).sort("posting_date", 1)]


def get_reconciliation_for_card(card_id: str, db: Any) -> List[Dict]:
    """Return matched bank rows for a specific customer card (for UI tab)."""
    oi = db["customer_open_items"]
    bt = db["bank_transactions"]
    pairs = db["recon_matched_pairs"]

    inv_ids = [str(i["_id"]) for i in oi.find({"card_id": card_id})]
    if not inv_ids:
        return []

    bank_ids = set()
    for p in pairs.find({"invoice_ids": {"$in": inv_ids}}):
        bank_ids.add(p["bank_id"])

    results = []
    for bid in bank_ids:
        try:
            row = bt.find_one({"_id": ObjectId(bid)})
        except Exception:
            continue
        if not row:
            continue
        row = _ser(row)
        linked_pairs = [_ser(p) for p in pairs.find({"bank_id": bid, "invoice_ids": {"$in": inv_ids}})]
        results.append({
            "bank_row": row,
            "pairs": linked_pairs,
            "transfer_date": row.get("txn_date"),
            "remitter": row.get("remitter_name"),
            "amount": row.get("amount"),
            "matched_amount": row.get("matched_amount"),
            "matched_doc_nos": row.get("matched_doc_nos", []),
            "match_method": row.get("match_method"),
            "status": "matched" if row.get("matched_flag") else "partial",
            "total_score": 100 if row.get("matched_flag") else 60,
        })
    results.sort(key=lambda x: x.get("amount", 0), reverse=True)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    client = make_mongo_client(MONGO_URI)
    require_mongo_auth(client)
    db = client[MONGO_DB]
    summary = run_dhofar_reconciliation(db)

    print("\n=== RECONCILIATION COMPLETE ===")
    print(f"  Bank rows   : {summary['bank_rows_matched']}/{summary['bank_rows_total']} matched")
    print(f"  Invoices    : {summary['invoices_cleared']}/{summary['invoices_total']} cleared")
    print(f"  Matched AED : {summary['matched_amount']:,.2f}")
    print(f"  Unmatched   : {summary['unmatched_amount']:,.2f}")
    print(f"  Passes      : {summary['pass_counts']}")

    print("\n--- UNMATCHED BANK ROWS ---")
    for r in get_unmatched_bank(db):
        print(f"  {r['txn_date']} | AED {r['amount']:>10,.2f} | {r['remitter_name'][:50]}")

    print("\n--- UNMATCHED INVOICES ---")
    for r in get_unmatched_invoices(db):
        print(f"  {r['posting_date']} | {r['doc_no']:20} | AED {r['remaining_amount']:>10,.2f} | {r['customer_name'][:40]}")
