# AutoProcure System Architecture

## Overview

AutoProcure ingests procurement PDFs, stores structured documents in MongoDB, runs AI-assisted three-way reconciliation, and exposes results through a FastAPI application (**Procure Match**) with a static JavaScript UI.

### System Philosophy

- **Filesystem-first ingestion**: A CLI scans a folder of PDFs (default: `data/simulated_data_lake`) and upserts into MongoDB; the API also accepts uploads.
- **MongoDB as source of truth**: Purchase orders, invoices, goods receipts, reconciliation snapshots, and human decisions live in collections.
- **AI via AWS Bedrock**: `src/llm_client.py` (`LLMClient`) calls Bedrock with JSON-schema-guided prompts; Pydantic validates outputs.
- **Reconciliation as a job**: `src/reconciliation_agent.py` runs full or per-PO incremental passes; the API can spawn it via `subprocess` after uploads or on demand.
- **Type-safe I/O**: Pydantic models end to end.

An S3 → SQS → worker pipeline is **not** implemented in this repository; it is a plausible production extension in front of the same `processor` / MongoDB logic.

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  PDFs: API upload and/or folder (e.g. data/simulated_data_lake) │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  INGESTION — src/ingest_to_mongo.py                           │
│  • Walks --data-lake-path for *.pdf                           │
│  • processor.py: PDF → images → Bedrock → typed document      │
│  • Writes invoices | purchase_orders | goods_receipts         │
│  • Organizes copies under data/invoices, data/purchase_orders,│
│    data/goods_receipts                                        │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  MongoDB (localhost or Atlas)                                 │
│  • purchase_orders, invoices, goods_receipts                  │
│  • reconciliation_results, reconciliation_decisions           │
└────────────────────────┬─────────────────────────────────────┘
                         │
         ┌───────────────┴────────────────┐
         ▼                                ▼
┌─────────────────────────┐   ┌────────────────────────────────┐
│  RECONCILIATION         │   │  API — src/app/app.py (FastAPI)   │
│  src/reconciliation_    │   │  • Lists documents, reconciliation│
│  agent.py               │   │  • POST /api/reconciliation/run   │
│  • Full (no args)       │   │  • POST /api/reconciliation/      │
│  • Incremental (PO#…)  │   │    trigger                        │
│  • Bedrock + Pydantic   │   │  • Spawns agent subprocesses      │
└─────────────────────────┘   │  • Static UI: /static             │
                              └────────────────────────────────┘
```

---

## Document ingestion (classification & extraction)

### Purpose

Batch-ingest PDFs from a directory, classify each as PO / invoice / GRN, extract structured fields with Bedrock, and upsert into MongoDB. Copies of PDFs are placed under `data/purchase_orders`, `data/invoices`, and `data/goods_receipts` for the UI.

### Technology stack

- **Language**: Python 3.12+
- **AWS**: boto3 (Bedrock runtime only for LLM calls; standard AWS credential chain)
- **AI**: Anthropic on Bedrock via `LLMClient` (`MODEL_PROVIDER=bedrock`)
- **Validation**: Pydantic (`src/processor.py`)
- **Database**: PyMongo + shared TLS helpers (`src/mongo_connection.py`)

### Entry point

- **`src/ingest_to_mongo.py`** — CLI: `--data-lake-path`, `--mongo-uri`, `--db-name`, `--limit`
- **`src/processor.py`** — `InvoicePOGRNClassifier` / image pipeline → `LLMClient.parse_structured`

### Flow (conceptual)

```
PDF path → pdf2image → Bedrock (JSON matching Pydantic schema) → document_type
       → insert/upsert collection (invoices | purchase_orders | goods_receipts)
       → copy PDF to data/<type-folder>/
```

Indexes for reconciliation links are created in `ingest_to_mongo.py` (e.g. `invoice.reference_po`, `purchase_order.po_number`).

### Configuration

Set variables in the project root `.env` (loaded by `mongo_connection.load_repo_root_env()`). **Do not commit** real connection strings.

```bash
MODEL_PROVIDER=bedrock
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=...                    # or BEDROCK_INFERENCE_PROFILE_ARN
MONGO_URI=mongodb://localhost:27017    # or your Atlas URI from the Atlas UI only
MONGO_DB=ema                            # default in app and agents
# Optional: MONGO_USER / MONGO_PASSWORD override URI userinfo (see mongo_connection.py)
```

### Running

```bash
cd src
python ingest_to_mongo.py
# python ingest_to_mongo.py --data-lake-path ../data/simulated_data_lake --limit 5
```

---

## Reconciliation agent

### Purpose

Loads POs, invoices, and goods receipts from MongoDB, calls Bedrock (`LLMClient`) with a Pydantic `ReconciliationResult` schema, merges AI output with deterministic approval math where applicable, and upserts into `reconciliation_results`. The FastAPI app reads these documents and can spawn this script after uploads (`subprocess`) or via `POST /api/reconciliation/run` and `POST /api/reconciliation/trigger`.

### Technology stack

- **Language**: Python 3.12+
- **AI**: AWS Bedrock (same `LLMClient` as ingestion)
- **Validation**: Pydantic models in `reconciliation_agent.py`
- **Database**: PyMongo (no change streams in this codebase)

### Entry point

`src/reconciliation_agent.py`

### Flow (conceptual)

```
For each PO (or only requested PO numbers):
  load PO + linked invoices + GRNs from MongoDB
       → build JSON context
       → LLMClient.parse_structured(..., ReconciliationResult)
       → merge / enrich (e.g. deterministic approval_calculation paths)
       → store_reconciliation_results (full replace or incremental upsert)
```

### Pydantic models (in code)

See `ApprovalCalculation`, `AIAnalysis`, and `ReconciliationResult` in `src/reconciliation_agent.py` — these mirror the Bedrock JSON schema the model must return.

### Configuration

Same `.env` as ingestion: `MODEL_PROVIDER=bedrock`, AWS region and Bedrock model identifiers, and MongoDB settings. **Never commit** Atlas URIs or passwords.

```bash
MODEL_PROVIDER=bedrock
AWS_REGION=us-east-1
MONGO_URI=mongodb://localhost:27017
MONGO_DB=ema
```

### Running

```bash
cd src
python reconciliation_agent.py              # full recompute all POs
python reconciliation_agent.py PO-12345     # incremental for listed POs
```

There is **no** `--watch` or `--full` flag in the current script; scheduling or API-triggered runs cover production use. Indexes for transactional collections are created by `ingest_to_mongo.py`; `reconciliation_agent.py` / `app.py` ensure indexes on `reconciliation_results`.

### MongoDB notes

A replica set is **not** required for this codebase (no change streams). Use Atlas or a standalone `mongod` as you prefer.

---

## Data Flow

### End-to-end (as implemented)

```
1. PDFs land in data/simulated_data_lake (or another --data-lake-path), and/or user uploads via FastAPI.
2. ingest_to_mongo.py → processor.py + Bedrock → MongoDB collections + organized files under data/.
3. reconciliation_agent.py (CLI and/or API-spawned subprocess) → Bedrock → reconciliation_results.
4. uvicorn serves src/app/app.py → browser loads /static → GET /api/reconciliation and related endpoints.
5. User records decisions → POST /api/reconciliation/decision → reconciliation_decisions.
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **PDF storage (dev)** | Local `data/` tree | Simulated lake + organized copies for the UI |
| **Database** | MongoDB (local or Atlas) | Documents + reconciliation snapshots + decisions |
| **Backend** | FastAPI (`src/app/app.py`) | REST API, upload, reconciliation triggers |
| **Frontend** | Vanilla JS + Tailwind (`src/app/static`) | Dashboard, reconciliation, approvals |
| **AI (ingestion + recon)** | AWS Bedrock (Anthropic) via `LLMClient` | Structured JSON extraction and matching |
| **Validation** | Pydantic | Type-safe schemas |
| **Cloud SDK** | boto3 | Bedrock runtime + optional future S3 |
| **Language** | Python 3.12+ | Ingestion, agent, API |

---

## Deployment

### Local development (this repository)

Prerequisites: Python 3.12+, Poppler, MongoDB reachable from your machine, AWS credentials with Bedrock invoke access, `.env` at repo root (see `startup.md`).

```bash
cd src
python ingest_to_mongo.py
python reconciliation_agent.py
cd app
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

The API can also run full or incremental reconciliation via `POST /api/reconciliation/run` and `POST /api/reconciliation/trigger`, and may spawn `reconciliation_agent.py` in the background after PDF upload.

### Production-oriented notes

- Run **ingestion** on a schedule or when new files appear (today: directory scan; wiring S3 → Lambda/worker would be custom).
- Run **reconciliation** on a schedule or rely on API-triggered subprocesses; at scale prefer a job queue instead of `subprocess`.
- Inject `MONGO_URI` and AWS credentials via your platform’s secret store; never commit credentials to git.

### Illustrative container layout (not defined in-repo)

```yaml
# Example only — build your own image and CMD
services:
  api:
    image: your-registry/autoprocure-api
    ports: ["8080:8080"]
    environment:
      - MONGO_URI
      - MONGO_DB
      - MODEL_PROVIDER=bedrock
      - AWS_REGION
      - BEDROCK_MODEL_ID
```

---

## Monitoring & Observability

### Logging

```python
import logging
import structlog

# Structured logging
logger = structlog.get_logger()

# Ingestion logs (example fields)
logger.info("document_processed",
    path=str(pdf_path),
    doc_type=doc_type,
    processing_time=elapsed
)

# Reconciliation logs (example fields)
logger.info("reconciliation_completed",
    po_number=po_number,
    status=status,
    risk_level=risk_level,
    processing_time=elapsed
)
```

### Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# Ingestion metrics (examples)
documents_processed = Counter('documents_processed_total', 'Total documents processed', ['doc_type'])
processing_time = Histogram('document_processing_seconds', 'Document processing time')
extraction_errors = Counter('extraction_errors_total', 'Extraction errors')

# Reconciliation metrics (examples)
reconciliations_completed = Counter('reconciliations_completed_total', 'Total reconciliations', ['status'])
reconciliation_time = Histogram('reconciliation_seconds', 'Reconciliation time')
ai_api_calls = Counter('ai_api_calls_total', 'AI API calls', ['model'])
```

### Health Checks

```python
# Example: extend FastAPI with dependency checks as needed
@app.get("/health")
def health_check():
    return {"status": "healthy", "mongo": ping_mongodb()}
```

---

## Security

### AWS IAM (Bedrock)

Grant the runtime role or IAM user permission to invoke the configured foundation model (and inference profile ARN if used). Add S3 permissions only if you introduce object storage for PDFs.

### MongoDB security

- Use Atlas **Database Access** users with least privilege, or a self-hosted user scoped to the application database.
- Store `MONGO_URI` (or `MONGO_USER` / `MONGO_PASSWORD`) in environment variables or a secrets manager — never in the repository.

### Secrets management

```bash
# Example: store Mongo URI in AWS Secrets Manager (name is illustrative)
aws secretsmanager create-secret \
  --name autoprocure/mongo-uri \
  --secret-string "YOUR_MONGO_URI"

# Retrieve at runtime (application or task definition)
# Use the returned SecretString as MONGO_URI in the process environment.
```

---

## Cost Optimization

### S3 Lifecycle Policies

```json
{
  "Rules": [
    {
      "Id": "ArchiveRawFiles",
      "Status": "Enabled",
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "STANDARD_IA"
        },
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ]
    }
  ]
}
```

### Bedrock usage

- **Ingestion**: One model invocation per PDF (classification + extraction path in `processor.py`).
- **Reconciliation**: One invocation per PO reconciled (plus any API-triggered reruns).
- **Caching**: MongoDB stores extracted documents and `reconciliation_results` to avoid redundant work when data is unchanged.
- **Batching**: `ingest_to_mongo.py` processes files sequentially by default; parallel ingestion would be an application-level change.

### MongoDB Optimization

- **Indexes**: Ensure proper indexes on query fields
- **TTL**: Set TTL on old reconciliation results
- **Compression**: Enable compression for storage savings

---

## Troubleshooting

### Ingestion issues

**Problem**: PDFs not appearing in MongoDB

- Confirm `--data-lake-path` exists and contains `.pdf` files.
- Run `cd src && python ingest_to_mongo.py` and watch stderr for Bedrock or TLS errors.
- Verify `MODEL_PROVIDER=bedrock`, region, and model access in the AWS account.

**Problem**: Extraction errors

```bash
cd src
python -c "
from pathlib import Path
from processor import InvoicePOGRNClassifier
r = InvoicePOGRNClassifier().classify_pdf(Path('path/to/sample.pdf'))
print(r.model_dump_json(indent=2))
"
```

### Reconciliation issues

**Problem**: UI shows stale or empty reconciliation

- Run `cd src && python reconciliation_agent.py` for a full recompute, or call `POST /api/reconciliation/run` while the API is up.
- Confirm `reconciliation_results` has documents: `mongosh` / Compass on your `MONGO_DB`.
- If the API spawn fails, run the agent manually in another terminal (same `.env` as the API).

---

## Future Enhancements

### Short Term
- [ ] WebSocket for real-time UI updates
- [ ] Email notifications for reconciliation results
- [ ] Batch upload with progress tracking
- [ ] Export reports (PDF/Excel)

### Medium Term
- [ ] Multi-tenant support
- [ ] Role-based access control
- [ ] Audit trail and history
- [ ] Advanced analytics dashboard

### Long Term
- [ ] Machine learning for anomaly detection
- [ ] Predictive analytics for issues
- [ ] ERP system integration
- [ ] Mobile application

---

**Document Version**: 3.0  
**Last Updated**: March 27, 2025  
**Architecture**: Local/Atlas MongoDB + Bedrock LLM + FastAPI (batch ingestion and job-style reconciliation)
