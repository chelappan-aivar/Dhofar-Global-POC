"""
dhofar_reconciliation.py

Reconciles EFT payment rows against Customer Card statement rows.

Logic:
  For each EFT row, find the best-matching statement row across all cards using:
    - Name score  (50 pts): fuzzy match of EFT remitter vs card customer_name
    - Amount score (30 pts): EFT amount vs statement row original_amount
    - Date score  (20 pts): EFT transfer_date vs statement row posting_date

  A match is accepted at total_score >= 40.

  Results are stored per-card so the UI can show "accepted EFT rows" inside
  each customer card.

Run:
    cd src && python dhofar_reconciliation.py
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from bson import ObjectId
from mongo_connection import load_repo_root_env, make_mongo_client, require_mongo_auth

load_repo_root_env()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "ema")


# ---------------------------------------------------------------------------
# Text / date helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _token_set(a: str, b: str) -> float:
    sa = set(_normalize(a).split())
    sb = set(_normalize(b).split())
    if not sa or not sb:
        return 0.0
    inter = sa & sb
    union = sa | sb
    j = len(inter) / len(union)
    bonus = 0.15 if (sa <= sb or sb <= sa) else 0.0
    return min(100.0, (j + bonus) * 100)


def _lcs_ratio(a: str, b: str) -> float:
    a, b = _normalize(a)[:150], _normalize(b)[:150]
    if not a or not b:
        return 0.0
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            dp[i][j] = dp[i-1][j-1] + 1 if a[i-1] == b[j-1] else max(dp[i-1][j], dp[i][j-1])
    return dp[m][n] / max(m, n) * 100


def name_similarity(a: str, b: str) -> float:
    return max(_token_set(a, b), _lcs_ratio(a, b))


def _parse_date(s: Optional[str]) -> Optional[date]:
    """Parse DD/MM/YY, DD/MM/YYYY, YYYY-MM-DD."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def date_score(eft_date: Optional[str], stmt_date: Optional[str]) -> float:
    """
    Score date proximity (0-20):
      same day → 20, within 3 days → 15, within 7 → 10, within 30 → 5, else 0
    """
    d1 = _parse_date(eft_date)
    d2 = _parse_date(stmt_date)
    if d1 is None or d2 is None:
        return 10.0  # neutral when date missing
    diff = abs((d1 - d2).days)
    if diff == 0:
        return 20.0
    if diff <= 3:
        return 15.0
    if diff <= 7:
        return 10.0
    if diff <= 30:
        return 5.0
    return 0.0


def amount_score(eft_amt: Optional[float], stmt_amt: Optional[float]) -> float:
    """
    Score amount match (0-30):
      exact (±0.01) → 30, within 1% → 22, within 5% → 12, within 20% → 5, else 0
    """
    if eft_amt is None or stmt_amt is None or stmt_amt == 0:
        return 10.0  # neutral
    diff_pct = abs(eft_amt - stmt_amt) / abs(stmt_amt) * 100
    if diff_pct <= 0.01:
        return 30.0
    if diff_pct <= 1.0:
        return 22.0
    if diff_pct <= 5.0:
        return 12.0
    if diff_pct <= 20.0:
        return 5.0
    return 0.0


# ---------------------------------------------------------------------------
# Remitter extraction
# ---------------------------------------------------------------------------

_REMITTER_PATTERNS = [
    r"Remitter\s+Info[:\s]+([A-Z][A-Z0-9 &\.\-\(\)\/]+?)(?:,|\s{2,}|Sender:|Value Date:)",
    r"By Order\s+([A-Z][A-Z0-9 &\.\-\(\)\/]+?)(?:\s{2,}|$)",
    r"AED[\s\d,\.]+\s{2,}([A-Z][A-Z0-9 &\.\-\(\)\/]+?)(?:\s{2,}|/REF/|INVOICE|\d{4,})",
    r"FROM\s+([A-Z][A-Z0-9 &\.\-\(\)\/]+?)(?:\s{2,}|/|$)",
    r"TRANSFER\s+.*?-\s+([A-Z][A-Z0-9 &\.\-\(\)\/]+?)\s+-",
]

def extract_remitter(description: str) -> str:
    for pat in _REMITTER_PATTERNS:
        m = re.search(pat, description, re.IGNORECASE)
        if m:
            c = m.group(1).strip()
            c = re.sub(r"\s+(OPC|LLC|LTD|INVOICE|NO|REF|AED|FT|IPP)\s*.*$", "", c, flags=re.IGNORECASE).strip()
            if len(c) >= 4 and not c.replace(" ", "").isdigit():
                return c
    return description


# ---------------------------------------------------------------------------
# Core: match one EFT row against all statement rows of all cards
# ---------------------------------------------------------------------------

def _score_eft_vs_stmt_row(
    remitter: str,
    description: str,
    eft_amount: Optional[float],
    eft_date: Optional[str],
    card_name: str,
    stmt_row: Dict[str, Any],
) -> float:
    """Return weighted total score (0-100) for one EFT ↔ statement-row pair."""
    # Name: compare remitter (and full description) against card name
    ns = max(
        name_similarity(remitter, card_name),
        name_similarity(description, card_name),
    )
    # Amount: EFT amount vs statement row original_amount
    as_ = amount_score(eft_amount, stmt_row.get("original_amount"))
    # Date: EFT transfer_date vs statement row posting_date
    ds = date_score(eft_date, stmt_row.get("posting_date"))

    return round(ns * 0.50 + as_ * 0.30 + ds * 0.20, 1)


def reconcile_eft_to_statement_rows(
    eft_items: List[Dict[str, Any]],
    customer_cards: List[Dict[str, Any]],
    min_score: float = 30.0,
) -> List[Dict[str, Any]]:
    """
    For every EFT item find the best-matching (card, statement_row) pair.

    Returns list of result dicts, one per EFT item:
      eft_item, remitter, transfer_date, amount,
      status (matched/partial/unmatched),
      matched_card_id, matched_card_name,
      matched_stmt_row,
      name_score, amount_score, date_score, total_score,
      all_candidates (top-3)
    """
    # Build flat list of (card_meta, stmt_row) pairs
    pairs: List[Dict[str, Any]] = []
    for card_doc in customer_cards:
        card = card_doc.get("customer_card") or {}
        card_meta = {
            "_id": str(card_doc.get("_id", "")),
            "customer_id": card.get("customer_id"),
            "customer_name": card.get("customer_name", ""),
            "source_file_path": card_doc.get("source_file_path"),
        }
        rows = card.get("statement_rows") or []
        if rows:
            for row in rows:
                pairs.append({"card": card_meta, "row": row})
        else:
            # Card has no statement rows — still allow name-only match
            pairs.append({"card": card_meta, "row": {}})

    results: List[Dict[str, Any]] = []

    for item in eft_items:
        description  = item.get("description", "") or ""
        eft_amount   = item.get("amount")
        transfer_date = item.get("transfer_date", "")
        remitter     = extract_remitter(description)

        candidates = []
        for pair in pairs:
            card_meta = pair["card"]
            stmt_row  = pair["row"]
            score = _score_eft_vs_stmt_row(
                remitter, description, eft_amount, transfer_date,
                card_meta["customer_name"], stmt_row,
            )
            candidates.append({
                "card": card_meta,
                "stmt_row": stmt_row,
                "name_score": round(max(
                    name_similarity(remitter, card_meta["customer_name"]),
                    name_similarity(description, card_meta["customer_name"]),
                ), 1),
                "amount_score": round(amount_score(eft_amount, stmt_row.get("original_amount")), 1),
                "date_score": round(date_score(transfer_date, stmt_row.get("posting_date")), 1),
                "total_score": score,
            })

        candidates.sort(key=lambda x: x["total_score"], reverse=True)
        top  = candidates[0] if candidates else None
        top3 = candidates[:3]

        # Both name AND amount must individually clear their thresholds
        name_ok   = top["name_score"]   > 40.0 if top else False
        amount_ok = top["amount_score"] > 20.0 if top else False

        if top and name_ok and amount_ok and top["total_score"] >= min_score:
            status = "matched"
        elif top and (name_ok or amount_ok) and top["total_score"] >= 25:
            status = "partial"
        else:
            status = "unmatched"

        results.append({
            "eft_item": item,
            "remitter": remitter,
            "transfer_date": transfer_date,
            "amount": eft_amount,
            "status": status,
            "matched_card_id": top["card"]["_id"] if top else None,
            "matched_card_name": top["card"]["customer_name"] if top else None,
            "matched_stmt_row": top["stmt_row"] if (top and status == "matched") else None,
            "name_score": top["name_score"] if top else 0,
            "amount_score": top["amount_score"] if top else 0,
            "date_score": top["date_score"] if top else 0,
            "total_score": top["total_score"] if top else 0,
            "all_candidates": [
                {
                    "customer_name": c["card"]["customer_name"],
                    "customer_id": c["card"]["customer_id"],
                    "stmt_row": c["stmt_row"],
                    "name_score": c["name_score"],
                    "amount_score": c["amount_score"],
                    "date_score": c["date_score"],
                    "total_score": c["total_score"],
                }
                for c in top3
            ],
        })

    return results


# ---------------------------------------------------------------------------
# Store & retrieve
# ---------------------------------------------------------------------------

def store_dhofar_reconciliation(
    results: List[Dict[str, Any]],
    eft_reference: str,
    db: Any,
) -> None:
    coll = db["dhofar_reconciliation_results"]
    coll.create_index("eft_reference")
    coll.create_index("status")
    coll.create_index("matched_card_id")

    coll.delete_many({"eft_reference": eft_reference})

    docs = []
    for r in results:
        docs.append({
            "eft_reference": eft_reference,
            "reconciled_at": datetime.now().isoformat(),
            **{k: v for k, v in r.items()},
        })
    if docs:
        coll.insert_many(docs)
    print(f"  Stored {len(docs)} reconciliation records for EFT {eft_reference}")


def get_reconciliation_results(db: Any) -> List[Dict[str, Any]]:
    coll = db["dhofar_reconciliation_results"]
    docs = list(coll.find().sort("total_score", -1))
    for doc in docs:
        if "_id" in doc and isinstance(doc["_id"], ObjectId):
            doc["_id"] = str(doc["_id"])
    return docs


def get_reconciliation_for_card(card_id: str, db: Any) -> List[Dict[str, Any]]:
    """Return all matched/partial EFT rows for a specific customer card."""
    coll = db["dhofar_reconciliation_results"]
    docs = list(
        coll.find(
            {"matched_card_id": card_id, "status": {"$in": ["matched", "partial"]}},
        ).sort("total_score", -1)
    )
    for doc in docs:
        if "_id" in doc and isinstance(doc["_id"], ObjectId):
            doc["_id"] = str(doc["_id"])
    return docs


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def build_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    matched   = [r for r in results if r["status"] == "matched"]
    partial   = [r for r in results if r["status"] == "partial"]
    unmatched = [r for r in results if r["status"] == "unmatched"]
    total_amt = sum(r["amount"] or 0 for r in results)
    return {
        "total_items": len(results),
        "matched": len(matched),
        "partial": len(partial),
        "unmatched": len(unmatched),
        "matched_amount": round(sum(r["amount"] or 0 for r in matched), 2),
        "partial_amount": round(sum(r["amount"] or 0 for r in partial), 2),
        "unmatched_amount": round(sum(r["amount"] or 0 for r in unmatched), 2),
        "total_amount": round(total_amt, 2),
        "match_rate_pct": round(len(matched) / len(results) * 100, 1) if results else 0,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_dhofar_reconciliation(db: Any) -> Dict[str, Any]:
    cards = list(db["customer_cards"].find())
    efts  = list(db["eft_payments"].find())

    if not cards:
        return {"error": "No customer cards found."}
    if not efts:
        return {"error": "No EFT payments found."}

    all_results: List[Dict[str, Any]] = []
    for eft_doc in efts:
        eft_data  = eft_doc.get("eft_payment", {})
        eft_ref   = eft_data.get("eft_reference", str(eft_doc.get("_id", "")))
        eft_items = eft_data.get("items", [])
        print(f"Reconciling EFT {eft_ref}: {len(eft_items)} items vs {len(cards)} cards...")
        results = reconcile_eft_to_statement_rows(eft_items, cards)
        store_dhofar_reconciliation(results, eft_ref, db)
        all_results.extend(results)

    summary = build_summary(all_results)
    print(f"Summary: {summary}")
    return summary


if __name__ == "__main__":
    client = make_mongo_client(MONGO_URI)
    require_mongo_auth(client)
    db = client[MONGO_DB]
    summary = run_dhofar_reconciliation(db)
    print("\n=== RECONCILIATION COMPLETE ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
